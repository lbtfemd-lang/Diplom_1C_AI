"""
Изолированный векторный индекс по справочнику «Модели БПЛА».

Не использует MetadataService ядра ассистента: каталог продукции и метаданные
конфигурации обновляются независимо, разными API. Эмбеддинги хранятся в
`drones_embeddings.npy`, исходные данные — в `drones_index.json`.

Жёсткий фильтр по типу конструкции снимается автоматически, если после него
остаётся меньше трёх кандидатов (требование 3.5 спецификации). Мягкий фильтр
по бюджету не отсекает модели за пределами бюджета, а только повышает score
тех, что попадают в 1.2× бюджета (требование 3.6).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from ._embedding_runtime import (
    cosine_sim_matrix,
    encode_query,
    encode_texts,
    is_ml_available,
)

DRONES_INDEX_FILE = "drones_index.json"
DRONES_EMBEDDINGS_FILE = "drones_embeddings.npy"

# Жёсткий фильтр по типу конструкции снимается, если после него
# остаётся меньше этого числа кандидатов.
_HARD_FILTER_MIN_KEEP = 3

# Мягкий фильтр по бюджету: модели с ценой ≤ 1.2× бюджета получают надбавку.
_BUDGET_TOLERANCE = 1.2
_BUDGET_BONUS = 0.05


@dataclass
class DroneCatalogItem:
    """Элемент каталога моделей БПЛА в виде, удобном для индексации."""

    model_id: str                    # GUID или артикул из 1С
    model_name: str
    drone_type: Optional[str] = None  # quadcopter / hexacopter / ...
    purpose: Optional[str] = None     # educational / fpv_racing / ...
    motor_count: Optional[int] = None
    payload_kg: Optional[float] = None
    flight_time_minutes: Optional[int] = None
    range_km: Optional[float] = None
    max_speed_km_h: Optional[float] = None
    frame_diagonal_mm: Optional[int] = None
    supported_payloads: List[str] = field(default_factory=list)
    compatible_software: List[str] = field(default_factory=list)
    programmable_languages: List[str] = field(default_factory=list)
    price_rub: Optional[float] = None
    manufacturer: Optional[str] = None
    catalog_source: str = "own"       # own / partner
    description: Optional[str] = None
    discontinued: bool = False        # флаг НеИспользуется

    @classmethod
    def from_dict(cls, data: dict) -> "DroneCatalogItem":
        """Создать из словаря, выгруженного из 1С (`/update_metadata` payload)."""
        return cls(
            model_id=str(data.get("model_id") or data.get("id") or data.get("guid") or ""),
            model_name=str(data.get("model_name") or data.get("name") or ""),
            drone_type=data.get("drone_type"),
            purpose=data.get("purpose"),
            motor_count=data.get("motor_count"),
            payload_kg=data.get("payload_kg"),
            flight_time_minutes=data.get("flight_time_minutes"),
            range_km=data.get("range_km"),
            max_speed_km_h=data.get("max_speed_km_h"),
            frame_diagonal_mm=data.get("frame_diagonal_mm"),
            supported_payloads=list(data.get("supported_payloads", []) or []),
            compatible_software=list(data.get("compatible_software", []) or []),
            programmable_languages=list(data.get("programmable_languages", []) or []),
            price_rub=data.get("price_rub"),
            manufacturer=data.get("manufacturer"),
            catalog_source=data.get("catalog_source", "own"),
            description=data.get("description"),
            discontinued=bool(data.get("discontinued", False)),
        )

    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "model_name": self.model_name,
            "drone_type": self.drone_type,
            "purpose": self.purpose,
            "motor_count": self.motor_count,
            "payload_kg": self.payload_kg,
            "flight_time_minutes": self.flight_time_minutes,
            "range_km": self.range_km,
            "max_speed_km_h": self.max_speed_km_h,
            "frame_diagonal_mm": self.frame_diagonal_mm,
            "supported_payloads": list(self.supported_payloads),
            "compatible_software": list(self.compatible_software),
            "programmable_languages": list(self.programmable_languages),
            "price_rub": self.price_rub,
            "manufacturer": self.manufacturer,
            "catalog_source": self.catalog_source,
            "description": self.description,
            "discontinued": self.discontinued,
        }

    def build_text_for_embedding(self) -> str:
        """Текст для векторизации модели.

        Конкатенирует ключевые поля с повторами для усиления вклада типа и
        нагрузок в семантический поиск.
        """
        parts: List[str] = [self.model_name]
        if self.manufacturer:
            parts.append(self.manufacturer)
        # Повторяем тип конструкции и назначение для усиления вклада
        if self.drone_type:
            parts.extend([self.drone_type, self.drone_type])
        if self.purpose:
            parts.extend([self.purpose, self.purpose])
        if self.motor_count:
            parts.append(f"{self.motor_count} мотор")
        if self.payload_kg:
            parts.append(f"грузоподъёмность {self.payload_kg} кг")
        if self.flight_time_minutes:
            parts.append(f"время полёта {self.flight_time_minutes} минут")
        if self.range_km:
            parts.append(f"дальность {self.range_km} км")
        if self.max_speed_km_h:
            parts.append(f"скорость {self.max_speed_km_h} км/ч")
        if self.frame_diagonal_mm:
            parts.append(f"диагональ {self.frame_diagonal_mm} мм")
        if self.supported_payloads:
            parts.append("Нагрузки: " + ", ".join(self.supported_payloads))
        if self.compatible_software:
            parts.append("ПО: " + ", ".join(self.compatible_software))
        if self.programmable_languages:
            parts.append("Языки: " + ", ".join(self.programmable_languages))
        if self.description:
            parts.append(self.description[:300])
        return " ".join(parts)


@dataclass
class DroneCandidate:
    """Кандидат, возвращаемый методом find_top_matches."""

    item: DroneCatalogItem
    cosine_score: float
    out_of_budget: bool = False


class DroneIndexService:
    """Векторный индекс по каталогу моделей БПЛА.

    Параметры:
        index_path:       путь к JSON-файлу с сериализованным каталогом моделей.
        embeddings_path:  путь к .npy-файлу с предвычисленными эмбеддингами.

    При создании сервис пытается загрузить ранее сохранённые данные. Метод
    `is_ready()` сообщает, готов ли сервис к поиску. Метод `rebuild_from_drones`
    пересобирает индекс из новых данных и сохраняет на диск.
    """

    def __init__(
        self,
        index_path: str = DRONES_INDEX_FILE,
        embeddings_path: str = DRONES_EMBEDDINGS_FILE,
    ):
        self._index_path = index_path
        self._embeddings_path = embeddings_path
        self._items: List[DroneCatalogItem] = []
        self._embeddings: Optional[np.ndarray] = None
        self._load_from_disk()

    # --- Управление индексом -----------------------------------------------

    def _load_from_disk(self) -> None:
        if not os.path.exists(self._index_path):
            return
        try:
            with open(self._index_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            self._items = [DroneCatalogItem.from_dict(d) for d in raw]
        except Exception as exc:  # pragma: no cover
            print(f"DroneIndexService: failed to load index: {exc}")
            self._items = []
            return

        if os.path.exists(self._embeddings_path):
            try:
                self._embeddings = np.load(self._embeddings_path)
                if self._embeddings.shape[0] != len(self._items):
                    # Несинхронизированные файлы — отбрасываем эмбеддинги
                    print("DroneIndexService: embeddings size mismatch, dropping.")
                    self._embeddings = None
            except Exception as exc:  # pragma: no cover
                print(f"DroneIndexService: failed to load embeddings: {exc}")
                self._embeddings = None

    def rebuild_from_drones(self, drones: List[dict]) -> None:
        """Принять список словарей из 1С и пересобрать индекс.

        Записывает JSON и .npy на диск. Элементы с discontinued=True
        пропускаются — они не должны участвовать в подборе.
        """
        items = [
            DroneCatalogItem.from_dict(d) for d in drones
            if not bool(d.get("discontinued", False))
        ]
        self._items = items

        try:
            with open(self._index_path, "w", encoding="utf-8") as f:
                json.dump([it.to_dict() for it in items], f, ensure_ascii=False, indent=2)
        except Exception as exc:  # pragma: no cover
            print(f"DroneIndexService: failed to save index: {exc}")

        if not items:
            self._embeddings = None
            self._delete_embeddings_file()
            return

        texts = [it.build_text_for_embedding() for it in items]
        emb = encode_texts(texts)
        if emb is None:
            # Fallback: ML недоступен. Сохраняем индекс, но не эмбеддинги.
            self._embeddings = None
            self._delete_embeddings_file()
            return
        self._embeddings = emb
        try:
            np.save(self._embeddings_path, emb)
        except Exception as exc:  # pragma: no cover
            print(f"DroneIndexService: failed to save embeddings: {exc}")

    def _delete_embeddings_file(self) -> None:
        if os.path.exists(self._embeddings_path):
            try:
                os.remove(self._embeddings_path)
            except OSError:  # pragma: no cover
                pass

    def is_ready(self) -> bool:
        """True, если каталог загружен и непуст."""
        return bool(self._items)

    @property
    def items(self) -> List[DroneCatalogItem]:
        return list(self._items)

    @property
    def has_embeddings(self) -> bool:
        return self._embeddings is not None

    # --- Поиск -------------------------------------------------------------

    def find_top_matches(
        self,
        query_text: str,
        top_k: int = 10,
        type_filter: Optional[str] = None,
        budget_per_unit_rub: Optional[float] = None,
    ) -> List[DroneCandidate]:
        """Top-K моделей по семантическому сходству.

        type_filter: жёсткий фильтр по drone_type. Если после фильтра
        остаётся меньше трёх кандидатов, фильтр снимается и поиск
        выполняется по всему каталогу (требование 3.5).

        budget_per_unit_rub: мягкий фильтр. Модели с price_rub ≤ 1.2× бюджета
        получают надбавку +0.05 к косинусному score. Остальные не отсекаются,
        но помечаются out_of_budget=True (требование 3.6).
        """
        if not self._items or top_k < 1:
            return []

        # Шаг 1: список индексов для рассмотрения с учётом жёсткого фильтра
        candidate_idx = self._apply_type_filter(type_filter)

        # Шаг 2: косинусные оценки или word-overlap fallback
        if self._embeddings is not None and is_ml_available():
            scored = self._score_with_embeddings(query_text, candidate_idx)
        else:
            scored = self._score_with_word_overlap(query_text, candidate_idx)

        # Шаг 3: бюджетный мягкий фильтр
        if budget_per_unit_rub is not None and budget_per_unit_rub > 0:
            scored = [
                self._apply_budget(idx, score, budget_per_unit_rub)
                for idx, score in scored
            ]
        else:
            scored = [(idx, score, False) for idx, score in scored]

        # Шаг 4: сортировка по убыванию итогового score, обрезка до top_k
        scored.sort(key=lambda t: t[1], reverse=True)
        scored = scored[:top_k]

        return [
            DroneCandidate(
                item=self._items[idx],
                cosine_score=float(score),
                out_of_budget=oob,
            )
            for idx, score, oob in scored
        ]

    # --- Внутренняя кухня --------------------------------------------------

    def _apply_type_filter(self, type_filter: Optional[str]) -> List[int]:
        """Список индексов товаров после жёсткого фильтра по типу.

        При нехватке кандидатов фильтр снимается.
        """
        all_idx = list(range(len(self._items)))
        if not type_filter:
            return all_idx
        filtered = [i for i in all_idx if self._items[i].drone_type == type_filter]
        if len(filtered) < _HARD_FILTER_MIN_KEEP:
            return all_idx
        return filtered

    def _score_with_embeddings(
        self, query_text: str, candidate_idx: List[int]
    ) -> List[Tuple[int, float]]:
        if not candidate_idx:
            return []
        query_emb = encode_query(query_text)
        if query_emb is None or self._embeddings is None:
            return self._score_with_word_overlap(query_text, candidate_idx)
        sub = self._embeddings[candidate_idx]
        scores = cosine_sim_matrix(query_emb, sub)
        # Косинус ∈ [-1, 1], нормализуем к [0, 1]
        normalized = (scores + 1.0) / 2.0
        return [(candidate_idx[i], float(normalized[i])) for i in range(len(candidate_idx))]

    def _score_with_word_overlap(
        self, query_text: str, candidate_idx: List[int]
    ) -> List[Tuple[int, float]]:
        """Простой fallback на пересечении слов запроса и текста модели."""
        words = {w for w in query_text.lower().split() if len(w) >= 3}
        if not words:
            return [(idx, 0.0) for idx in candidate_idx]
        result: List[Tuple[int, float]] = []
        for idx in candidate_idx:
            text = self._items[idx].build_text_for_embedding().lower()
            item_words = set(text.split())
            overlap = len(words & item_words)
            score = overlap / len(words)
            result.append((idx, float(score)))
        return result

    def _apply_budget(
        self, idx: int, score: float, budget: float
    ) -> Tuple[int, float, bool]:
        item = self._items[idx]
        if item.price_rub is None:
            return idx, score, False
        if item.price_rub <= budget * _BUDGET_TOLERANCE:
            return idx, min(score + _BUDGET_BONUS, 1.0), False
        return idx, score, True


# Singleton-инстанс с дефолтными путями.
drone_index_service = DroneIndexService()
