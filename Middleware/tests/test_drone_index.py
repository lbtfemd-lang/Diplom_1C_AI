"""Тесты DroneIndexService.

Покрывают: build_text_for_embedding, пересборку индекса с записью на диск,
жёсткий фильтр по типу с авто-снятием при < 3 кандидатов, мягкий бюджетный
фильтр, идемпотентность пересборки. Все тесты используют tmp_path для
изоляции от рабочих файлов middleware.
"""

from __future__ import annotations

import json
import os

import numpy as np
import pytest

from app.services import _embedding_runtime
from app.services.drone_index_service import (
    DroneCatalogItem,
    DroneIndexService,
)


# --- Стаб для encode_texts/encode_query без sentence-transformers ---------

class _FakeEmbedder:
    """Простой детерминированный эмбеддер на основе хеша слов.

    Каждое слово даёт фиксированный 8-мерный вектор. Такой эмбеддер
    в среднем повторяет word-overlap, но даёт нумерически стабильные
    эмбеддинги и даёт идентификаторам ML-ветки кода проигрываться.
    """

    DIM = 8

    def encode(self, texts, **kwargs):
        if isinstance(texts, str):
            texts = [texts]
        out = np.zeros((len(texts), self.DIM), dtype=np.float32)
        for i, text in enumerate(texts):
            words = (text or "").lower().split()
            for w in words:
                idx = abs(hash(w)) % self.DIM
                out[i, idx] += 1.0
            norm = np.linalg.norm(out[i])
            if norm > 0:
                out[i] /= norm
        return out


@pytest.fixture
def fake_embedder(monkeypatch):
    """Подменить sentence-transformers фейковым эмбеддером."""
    embedder = _FakeEmbedder()
    monkeypatch.setattr(_embedding_runtime, "_USE_ML", True)
    monkeypatch.setattr(_embedding_runtime, "_model", embedder)
    yield embedder
    _embedding_runtime.reset_model_for_tests()


@pytest.fixture
def no_embedder(monkeypatch):
    """Имитация окружения без sentence-transformers — fallback на word-overlap."""
    monkeypatch.setattr(_embedding_runtime, "_USE_ML", False)
    monkeypatch.setattr(_embedding_runtime, "_model", None)
    yield
    _embedding_runtime.reset_model_for_tests()


# --- Тестовые данные -------------------------------------------------------

KOPTRA_ORLENOK = {
    "model_id": "DRONE-001",
    "model_name": "Коптра Орлёнок",
    "drone_type": "quadcopter",
    "purpose": "educational",
    "motor_count": 4,
    "flight_time_minutes": 15,
    "max_speed_km_h": 75,
    "frame_diagonal_mm": 300,
    "programmable_languages": ["Python"],
    "price_rub": 55000,
    "manufacturer": "Коптра",
    "catalog_source": "own",
    "description": "Учебный программируемый квадрокоптер на Python.",
}

KOPTRA_FPV5 = {
    "model_id": "DRONE-002",
    "model_name": "Коптра FPV 5",
    "drone_type": "quadcopter",
    "purpose": "fpv_racing",
    "motor_count": 4,
    "flight_time_minutes": 25,
    "max_speed_km_h": 180,
    "frame_diagonal_mm": 220,
    "price_rub": 85000,
    "manufacturer": "Коптра",
    "catalog_source": "own",
}

KOPTRA_FPV10 = {
    "model_id": "DRONE-003",
    "model_name": "Коптра FPV 10",
    "drone_type": "quadcopter",
    "purpose": "logistics",
    "motor_count": 4,
    "payload_kg": 4.5,
    "flight_time_minutes": 30,
    "max_speed_km_h": 145,
    "price_rub": 220000,
    "manufacturer": "Коптра",
    "catalog_source": "own",
}

PARTNER_HEXA = {
    "model_id": "DRONE-100",
    "model_name": "Геоскан 401",
    "drone_type": "hexacopter",
    "purpose": "logistics",
    "motor_count": 6,
    "payload_kg": 8,
    "flight_time_minutes": 45,
    "price_rub": 350000,
    "catalog_source": "partner",
}

DISCONTINUED = {
    "model_id": "DRONE-EOL",
    "model_name": "Старая модель",
    "drone_type": "quadcopter",
    "discontinued": True,
}


def _make_service(tmp_path) -> DroneIndexService:
    return DroneIndexService(
        index_path=str(tmp_path / "drones_index.json"),
        embeddings_path=str(tmp_path / "drones_embeddings.npy"),
    )


# --- Базовые свойства DroneCatalogItem -----------------------------------

class TestDroneCatalogItem:
    def test_from_dict_minimal(self):
        item = DroneCatalogItem.from_dict({"model_id": "X", "model_name": "Y"})
        assert item.model_id == "X"
        assert item.model_name == "Y"
        assert item.programmable_languages == []
        assert item.catalog_source == "own"

    def test_build_text_includes_repeated_type(self):
        item = DroneCatalogItem.from_dict(KOPTRA_ORLENOK)
        text = item.build_text_for_embedding()
        assert text.count("quadcopter") >= 2  # повтор для усиления вклада
        assert text.count("educational") >= 2
        assert "Коптра Орлёнок" in text
        assert "300" in text
        assert "Python" in text

    def test_to_dict_roundtrip(self):
        item = DroneCatalogItem.from_dict(KOPTRA_ORLENOK)
        d = item.to_dict()
        restored = DroneCatalogItem.from_dict(d)
        assert restored == item


# --- Пустой каталог --------------------------------------------------------

class TestEmptyCatalog:
    def test_is_ready_false_without_data(self, tmp_path, no_embedder):
        svc = _make_service(tmp_path)
        assert svc.is_ready() is False
        assert svc.find_top_matches("anything") == []

    def test_rebuild_with_empty_list(self, tmp_path, no_embedder):
        svc = _make_service(tmp_path)
        svc.rebuild_from_drones([])
        assert svc.is_ready() is False
        assert svc.find_top_matches("anything") == []


# --- Пересборка и сохранение на диск --------------------------------------

class TestRebuild:
    def test_rebuild_creates_index_file(self, tmp_path, fake_embedder):
        svc = _make_service(tmp_path)
        svc.rebuild_from_drones([KOPTRA_ORLENOK, KOPTRA_FPV5])
        assert svc.is_ready() is True
        index_path = tmp_path / "drones_index.json"
        emb_path = tmp_path / "drones_embeddings.npy"
        assert index_path.exists()
        assert emb_path.exists()
        with open(index_path, encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 2

    def test_rebuild_skips_discontinued(self, tmp_path, fake_embedder):
        svc = _make_service(tmp_path)
        svc.rebuild_from_drones([KOPTRA_ORLENOK, DISCONTINUED])
        assert len(svc.items) == 1
        assert svc.items[0].model_id == "DRONE-001"

    def test_rebuild_idempotent(self, tmp_path, fake_embedder):
        svc = _make_service(tmp_path)
        svc.rebuild_from_drones([KOPTRA_ORLENOK, KOPTRA_FPV5])
        first_emb = svc._embeddings.copy()
        svc.rebuild_from_drones([KOPTRA_ORLENOK, KOPTRA_FPV5])
        second_emb = svc._embeddings.copy()
        np.testing.assert_array_almost_equal(first_emb, second_emb)
        assert len(svc.items) == 2

    def test_load_from_disk_after_rebuild(self, tmp_path, fake_embedder):
        svc1 = _make_service(tmp_path)
        svc1.rebuild_from_drones([KOPTRA_ORLENOK, KOPTRA_FPV5])
        # Создаём новый сервис с теми же путями — должен подтянуть данные
        svc2 = _make_service(tmp_path)
        assert svc2.is_ready() is True
        assert {it.model_id for it in svc2.items} == {"DRONE-001", "DRONE-002"}

    def test_rebuild_without_ml_skips_embeddings(self, tmp_path, no_embedder):
        svc = _make_service(tmp_path)
        svc.rebuild_from_drones([KOPTRA_ORLENOK, KOPTRA_FPV5])
        assert svc.is_ready() is True
        assert svc.has_embeddings is False
        # Файл эмбеддингов не должен быть создан
        emb_path = tmp_path / "drones_embeddings.npy"
        assert not emb_path.exists()


# --- Жёсткий фильтр по типу с авто-снятием --------------------------------

class TestTypeFilter:
    def test_type_filter_keeps_matching_models(self, tmp_path, fake_embedder):
        svc = _make_service(tmp_path)
        svc.rebuild_from_drones([
            KOPTRA_ORLENOK, KOPTRA_FPV5, KOPTRA_FPV10, PARTNER_HEXA,
        ])
        results = svc.find_top_matches(
            "учебный квадрокоптер", top_k=10, type_filter="quadcopter"
        )
        # Все три квадрокоптера должны попасть
        ids = {c.item.model_id for c in results}
        assert "DRONE-100" not in ids  # гексакоптер должен быть отфильтрован
        assert ids == {"DRONE-001", "DRONE-002", "DRONE-003"}

    def test_type_filter_auto_drops_when_too_few(self, tmp_path, fake_embedder):
        svc = _make_service(tmp_path)
        # Только один гексакоптер — фильтр должен сняться, чтобы вернуть >= 3
        svc.rebuild_from_drones([
            KOPTRA_ORLENOK, KOPTRA_FPV5, KOPTRA_FPV10, PARTNER_HEXA,
        ])
        results = svc.find_top_matches(
            "что-нибудь", top_k=10, type_filter="hexacopter"
        )
        # Должны вернуться все 4 модели, не только гексакоптер
        assert len(results) == 4

    def test_type_filter_no_match_returns_all(self, tmp_path, fake_embedder):
        svc = _make_service(tmp_path)
        svc.rebuild_from_drones([KOPTRA_ORLENOK, KOPTRA_FPV5, KOPTRA_FPV10])
        results = svc.find_top_matches(
            "что-нибудь", top_k=10, type_filter="fixed_wing"
        )
        # Нет fixed_wing — фильтр снят, возвращаются все три квадрокоптера
        assert len(results) == 3


# --- Мягкий бюджетный фильтр ----------------------------------------------

class TestBudgetFilter:
    def test_within_budget_not_marked(self, tmp_path, fake_embedder):
        svc = _make_service(tmp_path)
        svc.rebuild_from_drones([KOPTRA_ORLENOK, KOPTRA_FPV5, KOPTRA_FPV10])
        results = svc.find_top_matches(
            "учебный", top_k=10, budget_per_unit_rub=60_000
        )
        orlenok = next(c for c in results if c.item.model_id == "DRONE-001")
        assert orlenok.out_of_budget is False

    def test_above_budget_marked(self, tmp_path, fake_embedder):
        svc = _make_service(tmp_path)
        svc.rebuild_from_drones([KOPTRA_ORLENOK, KOPTRA_FPV5, KOPTRA_FPV10])
        results = svc.find_top_matches(
            "что-нибудь", top_k=10, budget_per_unit_rub=60_000
        )
        # FPV 10 за 220k — точно выше 1.2*60k=72k
        fpv10 = next(c for c in results if c.item.model_id == "DRONE-003")
        assert fpv10.out_of_budget is True

    def test_within_tolerance_zone_not_marked(self, tmp_path, fake_embedder):
        # Цена 65k, бюджет 60k, толерантность 1.2 → допуск до 72k
        svc = _make_service(tmp_path)
        svc.rebuild_from_drones([
            {**KOPTRA_ORLENOK, "price_rub": 65_000},
        ])
        results = svc.find_top_matches(
            "учебный", top_k=10, budget_per_unit_rub=60_000
        )
        assert results[0].out_of_budget is False

    def test_no_budget_no_marking(self, tmp_path, fake_embedder):
        svc = _make_service(tmp_path)
        svc.rebuild_from_drones([KOPTRA_ORLENOK, KOPTRA_FPV10])
        results = svc.find_top_matches("что-нибудь", top_k=10)
        assert all(c.out_of_budget is False for c in results)


# --- Top-K и сортировка ---------------------------------------------------

class TestTopK:
    def test_top_k_truncates(self, tmp_path, fake_embedder):
        svc = _make_service(tmp_path)
        svc.rebuild_from_drones([
            KOPTRA_ORLENOK, KOPTRA_FPV5, KOPTRA_FPV10, PARTNER_HEXA,
        ])
        results = svc.find_top_matches("дрон", top_k=2)
        assert len(results) == 2

    def test_results_sorted_descending(self, tmp_path, fake_embedder):
        svc = _make_service(tmp_path)
        svc.rebuild_from_drones([KOPTRA_ORLENOK, KOPTRA_FPV5, KOPTRA_FPV10])
        results = svc.find_top_matches("учебный", top_k=10)
        scores = [c.cosine_score for c in results]
        assert scores == sorted(scores, reverse=True)


# --- Word-overlap fallback ------------------------------------------------

class TestFallback:
    def test_fallback_returns_results(self, tmp_path, no_embedder):
        svc = _make_service(tmp_path)
        svc.rebuild_from_drones([
            KOPTRA_ORLENOK, KOPTRA_FPV5, KOPTRA_FPV10,
        ])
        results = svc.find_top_matches("учебный квадрокоптер для уроков", top_k=10)
        assert len(results) > 0
        # Орлёнок должен быть в верхушке
        top_ids = [c.item.model_id for c in results[:2]]
        assert "DRONE-001" in top_ids

    def test_fallback_handles_empty_query(self, tmp_path, no_embedder):
        svc = _make_service(tmp_path)
        svc.rebuild_from_drones([KOPTRA_ORLENOK])
        results = svc.find_top_matches("", top_k=5)
        # Не падает, возвращает что-то осмысленное
        assert isinstance(results, list)
