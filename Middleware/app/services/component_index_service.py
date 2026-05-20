"""
Изолированный векторный индекс по справочнику «Комплектующие».

Используется сборщиком конфигурации (`config_builder`) для семантического
отбора кандидатов внутри каждой категории и для подсказок в форме «Подбор
по тендеру». Индекс хранится в `components_index.json` и
`components_embeddings.npy`. Параметры физической совместимости
(`compatibility_json`) хранятся как dict и не участвуют в эмбеддинге —
они проверяются детерминированно в `config_builder`.
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

COMPONENTS_INDEX_FILE = "components_index.json"
COMPONENTS_EMBEDDINGS_FILE = "components_embeddings.npy"


@dataclass
class ComponentCatalogItem:
    component_id: str
    component_name: str
    category: str  # frame / flight_controller / esc / motor / battery / propeller / ...
    manufacturer: Optional[str] = None
    description: Optional[str] = None
    compatibility: dict = field(default_factory=dict)
    price_rub: Optional[float] = None
    stock: Optional[int] = None
    catalog_source: str = "own"  # own / partner
    discontinued: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "ComponentCatalogItem":
        compat_raw = data.get("compatibility") or data.get("compatibility_json") or {}
        if isinstance(compat_raw, str):
            try:
                compat_raw = json.loads(compat_raw) if compat_raw.strip() else {}
            except json.JSONDecodeError:
                compat_raw = {}
        if not isinstance(compat_raw, dict):
            compat_raw = {}

        return cls(
            component_id=str(data.get("component_id") or data.get("id") or data.get("guid") or ""),
            component_name=str(data.get("component_name") or data.get("name") or ""),
            category=str(data.get("category") or ""),
            manufacturer=data.get("manufacturer"),
            description=data.get("description"),
            compatibility=compat_raw,
            price_rub=data.get("price_rub"),
            stock=data.get("stock"),
            catalog_source=data.get("catalog_source", "own"),
            discontinued=bool(data.get("discontinued", False)),
        )

    def to_dict(self) -> dict:
        return {
            "component_id": self.component_id,
            "component_name": self.component_name,
            "category": self.category,
            "manufacturer": self.manufacturer,
            "description": self.description,
            "compatibility": dict(self.compatibility),
            "price_rub": self.price_rub,
            "stock": self.stock,
            "catalog_source": self.catalog_source,
            "discontinued": self.discontinued,
        }

    def build_text_for_embedding(self) -> str:
        parts: List[str] = [self.component_name]
        if self.category:
            parts.extend([self.category, self.category])  # повторяем для усиления
        if self.manufacturer:
            parts.append(self.manufacturer)
        if self.description:
            parts.append(self.description[:200])
        # Существенные поля совместимости встраиваем как текст
        for key, value in self.compatibility.items():
            if value is None:
                continue
            if isinstance(value, list):
                parts.append(f"{key}: {', '.join(str(v) for v in value)}")
            else:
                parts.append(f"{key}: {value}")
        return " ".join(parts)


@dataclass
class ComponentCandidate:
    item: ComponentCatalogItem
    cosine_score: float


class ComponentIndexService:
    def __init__(
        self,
        index_path: str = COMPONENTS_INDEX_FILE,
        embeddings_path: str = COMPONENTS_EMBEDDINGS_FILE,
    ):
        self._index_path = index_path
        self._embeddings_path = embeddings_path
        self._items: List[ComponentCatalogItem] = []
        self._embeddings: Optional[np.ndarray] = None
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        if not os.path.exists(self._index_path):
            return
        try:
            with open(self._index_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            self._items = [ComponentCatalogItem.from_dict(d) for d in raw]
        except Exception as exc:  # pragma: no cover
            print(f"ComponentIndexService: failed to load index: {exc}")
            self._items = []
            return

        if os.path.exists(self._embeddings_path):
            try:
                self._embeddings = np.load(self._embeddings_path)
                if self._embeddings.shape[0] != len(self._items):
                    print("ComponentIndexService: embeddings size mismatch, dropping.")
                    self._embeddings = None
            except Exception as exc:  # pragma: no cover
                print(f"ComponentIndexService: failed to load embeddings: {exc}")
                self._embeddings = None

    def rebuild_from_components(self, components: List[dict]) -> None:
        items = [
            ComponentCatalogItem.from_dict(d) for d in components
            if not bool(d.get("discontinued", False))
        ]
        self._items = items

        try:
            with open(self._index_path, "w", encoding="utf-8") as f:
                json.dump([it.to_dict() for it in items], f, ensure_ascii=False, indent=2)
        except Exception as exc:  # pragma: no cover
            print(f"ComponentIndexService: failed to save index: {exc}")

        if not items:
            self._embeddings = None
            self._delete_embeddings_file()
            return

        texts = [it.build_text_for_embedding() for it in items]
        emb = encode_texts(texts)
        if emb is None:
            self._embeddings = None
            self._delete_embeddings_file()
            return
        self._embeddings = emb
        try:
            np.save(self._embeddings_path, emb)
        except Exception as exc:  # pragma: no cover
            print(f"ComponentIndexService: failed to save embeddings: {exc}")

    def _delete_embeddings_file(self) -> None:
        if os.path.exists(self._embeddings_path):
            try:
                os.remove(self._embeddings_path)
            except OSError:  # pragma: no cover
                pass

    def is_ready(self) -> bool:
        return bool(self._items)

    @property
    def items(self) -> List[ComponentCatalogItem]:
        return list(self._items)

    @property
    def has_embeddings(self) -> bool:
        return self._embeddings is not None

    def items_by_category(self, category: str) -> List[ComponentCatalogItem]:
        return [it for it in self._items if it.category == category]

    def find_top_matches(
        self,
        query_text: str,
        top_k: int = 10,
        category: Optional[str] = None,
    ) -> List[ComponentCandidate]:
        """Top-K комплектующих, опционально с жёстким фильтром по категории."""
        if not self._items or top_k < 1:
            return []
        all_idx = list(range(len(self._items)))
        if category:
            candidate_idx = [i for i in all_idx if self._items[i].category == category]
            if not candidate_idx:
                return []
        else:
            candidate_idx = all_idx

        if self._embeddings is not None and is_ml_available():
            scored = self._score_with_embeddings(query_text, candidate_idx)
        else:
            scored = self._score_with_word_overlap(query_text, candidate_idx)

        scored.sort(key=lambda t: t[1], reverse=True)
        scored = scored[:top_k]
        return [
            ComponentCandidate(
                item=self._items[idx],
                cosine_score=float(score),
            )
            for idx, score in scored
        ]

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
        normalized = (scores + 1.0) / 2.0
        return [(candidate_idx[i], float(normalized[i])) for i in range(len(candidate_idx))]

    def _score_with_word_overlap(
        self, query_text: str, candidate_idx: List[int]
    ) -> List[Tuple[int, float]]:
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


# Singleton с дефолтными путями.
component_index_service = ComponentIndexService()
