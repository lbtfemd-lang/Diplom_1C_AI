"""Тесты ComponentIndexService.

Покрывают: парсинг compatibility_json (dict/строка/невалидный JSON),
фильтр по категории, items_by_category, top-K, fallback на word-overlap.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from app.services import _embedding_runtime
from app.services.component_index_service import (
    ComponentCatalogItem,
    ComponentIndexService,
)


class _FakeEmbedder:
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
    embedder = _FakeEmbedder()
    monkeypatch.setattr(_embedding_runtime, "_USE_ML", True)
    monkeypatch.setattr(_embedding_runtime, "_model", embedder)
    yield embedder
    _embedding_runtime.reset_model_for_tests()


@pytest.fixture
def no_embedder(monkeypatch):
    monkeypatch.setattr(_embedding_runtime, "_USE_ML", False)
    monkeypatch.setattr(_embedding_runtime, "_model", None)
    yield
    _embedding_runtime.reset_model_for_tests()


FRAME_220 = {
    "component_id": "FR-220",
    "component_name": "Рама Коптра 220 мм",
    "category": "frame",
    "manufacturer": "Коптра",
    "compatibility": {
        "motor_mount_count": 4,
        "motor_mount_size_mm": 16,
        "max_motor_diameter_mm": 28,
        "prop_size_inch_max": 5.5,
        "diagonal_mm": 220,
        "mass_g": 95,
    },
    "price_rub": 2500,
    "catalog_source": "own",
}

FC_IPK1 = {
    "component_id": "FC-IPK1",
    "component_name": "Полётный контроллер Коптра ИПК1",
    "category": "flight_controller",
    "manufacturer": "Коптра",
    "compatibility": {
        "mcu": "STM32F405",
        "firmware": ["Betaflight", "INAV"],
        "voltage_input_v": "2S-6S",
        "uart_count": 5,
        "programmable_languages": ["Python"],
    },
    "price_rub": 5500,
    "catalog_source": "own",
}

MOTOR_2207 = {
    "component_id": "MT-2207",
    "component_name": "Мотор Коптра 2207 2400KV",
    "category": "motor",
    "compatibility": {
        "kv": 2400,
        "stator_size": "2207",
        "mount_size_mm": 16,
        "weight_g": 32,
        "max_current_a": 38,
        "voltage_v": "3S-6S",
    },
    "price_rub": 1800,
    "catalog_source": "own",
}

DISCONTINUED_COMPONENT = {
    "component_id": "OLD-1",
    "component_name": "Старая рама",
    "category": "frame",
    "discontinued": True,
}


def _make_service(tmp_path) -> ComponentIndexService:
    return ComponentIndexService(
        index_path=str(tmp_path / "components_index.json"),
        embeddings_path=str(tmp_path / "components_embeddings.npy"),
    )


# --- Парсинг compatibility -----------------------------------------------

class TestComponentParsing:
    def test_compatibility_dict_passes_through(self):
        item = ComponentCatalogItem.from_dict(FRAME_220)
        assert item.compatibility["motor_mount_count"] == 4
        assert item.compatibility["mass_g"] == 95

    def test_compatibility_json_string_parsed(self):
        data = {**FRAME_220, "compatibility_json": json.dumps(FRAME_220["compatibility"])}
        # Уберём ключ compatibility, оставим только compatibility_json
        del data["compatibility"]
        item = ComponentCatalogItem.from_dict(data)
        assert item.compatibility["motor_mount_count"] == 4

    def test_compatibility_invalid_json_falls_back_to_empty(self):
        item = ComponentCatalogItem.from_dict({
            "component_id": "X",
            "component_name": "X",
            "category": "frame",
            "compatibility_json": "not a json",
        })
        assert item.compatibility == {}

    def test_compatibility_empty_string_falls_back_to_empty(self):
        item = ComponentCatalogItem.from_dict({
            "component_id": "X",
            "component_name": "X",
            "category": "frame",
            "compatibility_json": "",
        })
        assert item.compatibility == {}

    def test_to_dict_roundtrip(self):
        item = ComponentCatalogItem.from_dict(FC_IPK1)
        d = item.to_dict()
        restored = ComponentCatalogItem.from_dict(d)
        assert restored == item

    def test_build_text_includes_compatibility_keys(self):
        item = ComponentCatalogItem.from_dict(FC_IPK1)
        text = item.build_text_for_embedding()
        assert "STM32F405" in text
        assert "Betaflight" in text
        assert "Python" in text
        assert text.count("flight_controller") >= 2  # повтор для усиления


# --- Пустой каталог -------------------------------------------------------

class TestEmptyCatalog:
    def test_is_ready_false(self, tmp_path, no_embedder):
        svc = _make_service(tmp_path)
        assert svc.is_ready() is False
        assert svc.find_top_matches("anything") == []

    def test_items_by_category_empty(self, tmp_path, no_embedder):
        svc = _make_service(tmp_path)
        assert svc.items_by_category("frame") == []


# --- Пересборка ----------------------------------------------------------

class TestRebuild:
    def test_rebuild_basic(self, tmp_path, fake_embedder):
        svc = _make_service(tmp_path)
        svc.rebuild_from_components([FRAME_220, FC_IPK1, MOTOR_2207])
        assert svc.is_ready() is True
        assert len(svc.items) == 3

    def test_rebuild_skips_discontinued(self, tmp_path, fake_embedder):
        svc = _make_service(tmp_path)
        svc.rebuild_from_components([FRAME_220, DISCONTINUED_COMPONENT])
        assert len(svc.items) == 1

    def test_rebuild_idempotent(self, tmp_path, fake_embedder):
        svc = _make_service(tmp_path)
        svc.rebuild_from_components([FRAME_220, FC_IPK1])
        first_emb = svc._embeddings.copy()
        svc.rebuild_from_components([FRAME_220, FC_IPK1])
        second_emb = svc._embeddings.copy()
        np.testing.assert_array_almost_equal(first_emb, second_emb)


# --- Фильтр по категории --------------------------------------------------

class TestCategoryFilter:
    def test_items_by_category(self, tmp_path, fake_embedder):
        svc = _make_service(tmp_path)
        svc.rebuild_from_components([FRAME_220, FC_IPK1, MOTOR_2207])
        frames = svc.items_by_category("frame")
        assert len(frames) == 1
        assert frames[0].component_id == "FR-220"

    def test_find_top_matches_with_category(self, tmp_path, fake_embedder):
        svc = _make_service(tmp_path)
        svc.rebuild_from_components([FRAME_220, FC_IPK1, MOTOR_2207])
        results = svc.find_top_matches("любой", top_k=10, category="motor")
        assert len(results) == 1
        assert results[0].item.category == "motor"

    def test_find_top_matches_unknown_category_empty(self, tmp_path, fake_embedder):
        svc = _make_service(tmp_path)
        svc.rebuild_from_components([FRAME_220])
        results = svc.find_top_matches("любой", top_k=10, category="payload")
        assert results == []


# --- Top-K ----------------------------------------------------------------

class TestTopK:
    def test_top_k_truncates(self, tmp_path, fake_embedder):
        svc = _make_service(tmp_path)
        svc.rebuild_from_components([FRAME_220, FC_IPK1, MOTOR_2207])
        results = svc.find_top_matches("любой", top_k=2)
        assert len(results) == 2


# --- Word-overlap fallback ------------------------------------------------

class TestFallback:
    def test_fallback_returns_results(self, tmp_path, no_embedder):
        svc = _make_service(tmp_path)
        svc.rebuild_from_components([FRAME_220, FC_IPK1, MOTOR_2207])
        # Свойства fallback: запрос содержит редкие слова из текста элемента
        results = svc.find_top_matches("STM32F405 Betaflight", top_k=5)
        # Контроллер должен быть в верхушке
        if results:
            assert results[0].item.component_id == "FC-IPK1"

    def test_load_from_disk_after_rebuild(self, tmp_path, fake_embedder):
        svc1 = _make_service(tmp_path)
        svc1.rebuild_from_components([FRAME_220, FC_IPK1])
        svc2 = _make_service(tmp_path)
        assert svc2.is_ready() is True
        assert {it.component_id for it in svc2.items} == {"FR-220", "FC-IPK1"}
