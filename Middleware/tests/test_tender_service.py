"""Тесты TenderService.

Покрывают: успешный парсинг, провал парсинга, успешный матчинг ready_model,
успешную сборку build_config, режим auto (оба результата), fallback при сбое
LLM, отсев фантомных model_id, детерминированность при фиксированных
ответах LLM.
"""

from __future__ import annotations

import json

import pytest

from app.models.tender_models import TenderRequirements
from app.services import _embedding_runtime
from app.services.component_index_service import ComponentIndexService
from app.services.config_builder import ConfigBuilder
from app.services.drone_index_service import DroneIndexService
from app.services.tender_service import TenderParseError, TenderService


# --- Фикстуры -------------------------------------------------------------

class _FakeEmbedder:
    DIM = 8

    def encode(self, texts, **kwargs):
        import numpy as np
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


class _StubLLM:
    """Минимальный заглушечный LLMService с методом _extract_json."""

    def __init__(self):
        self.client = None
        self.model = "stub"

    @staticmethod
    def _extract_json(text):
        if not text:
            return None
        try:
            return json.loads(text)
        except (TypeError, ValueError):
            return None


@pytest.fixture
def services(tmp_path, fake_embedder):
    """Полный стек: drone_index + components + builder + service."""
    drones = DroneIndexService(
        index_path=str(tmp_path / "di.json"),
        embeddings_path=str(tmp_path / "de.npy"),
    )
    drones.rebuild_from_drones([
        {
            "model_id": "DRONE-001", "model_name": "Коптра Орлёнок",
            "drone_type": "quadcopter", "purpose": "educational",
            "motor_count": 4, "flight_time_minutes": 15,
            "frame_diagonal_mm": 300, "programmable_languages": ["Python"],
            "price_rub": 55000, "catalog_source": "own",
        },
        {
            "model_id": "DRONE-002", "model_name": "Коптра FPV 5",
            "drone_type": "quadcopter", "purpose": "fpv_racing",
            "motor_count": 4, "max_speed_km_h": 180,
            "frame_diagonal_mm": 220, "price_rub": 85000,
            "catalog_source": "own",
        },
        {
            "model_id": "DRONE-100", "model_name": "Pioneer Mini",
            "drone_type": "quadcopter", "purpose": "educational",
            "motor_count": 4, "flight_time_minutes": 12,
            "price_rub": 48000, "catalog_source": "partner",
        },
    ])

    components = ComponentIndexService(
        index_path=str(tmp_path / "ci.json"),
        embeddings_path=str(tmp_path / "ce.npy"),
    )
    components.rebuild_from_components([
        {
            "component_id": "FR-300", "component_name": "Рама Коптра 300",
            "category": "frame", "catalog_source": "own", "price_rub": 3000,
            "compatibility": {"motor_mount_count": 4, "motor_mount_size_mm": 16,
                              "prop_size_inch_max": 7.5, "diagonal_mm": 300, "mass_g": 110},
        },
        {
            "component_id": "FC-IPK1", "component_name": "ИПК1",
            "category": "flight_controller", "catalog_source": "own", "price_rub": 5500,
            "compatibility": {"mcu": "STM32F405", "firmware": ["Betaflight"],
                              "voltage_input_v": "2S-6S", "uart_count": 5,
                              "programmable_languages": ["Python"]},
        },
        {
            "component_id": "MT-2207", "component_name": "Мотор 2207",
            "category": "motor", "catalog_source": "own", "price_rub": 1800,
            "compatibility": {"kv": 1700, "mount_size_mm": 16,
                              "weight_g": 32, "max_current_a": 38,
                              "voltage_v": "3S-6S"},
        },
        {
            "component_id": "ESC-60", "component_name": "ESC 60",
            "category": "esc", "catalog_source": "own", "price_rub": 2200,
            "compatibility": {"current_continuous_a": 60, "voltage_v": "3S-6S"},
        },
        {
            "component_id": "BAT-4S", "component_name": "Батарея 4S",
            "category": "battery", "catalog_source": "own", "price_rub": 3800,
            "compatibility": {"chemistry": "LiPo", "cells_s": 4,
                              "capacity_mah": 4000, "weight_g": 380},
        },
        {
            "component_id": "PRP-7", "component_name": "Пропеллер 7",
            "category": "propeller", "catalog_source": "own", "price_rub": 250,
            "compatibility": {"diameter_inch": 7.0},
        },
    ])

    builder = ConfigBuilder(components)
    llm = _StubLLM()
    return {
        "llm": llm,
        "drones": drones,
        "components": components,
        "builder": builder,
        "service": TenderService(llm, drones, builder),
    }


# --- Парсинг --------------------------------------------------------------

class TestParse:
    @pytest.mark.asyncio
    async def test_successful_parse(self, services, monkeypatch):
        canned = json.dumps({
            "intent": "ready_model",
            "purpose": "educational",
            "drone_type": "quadcopter",
            "motor_count_min": 4, "motor_count_max": 4,
            "flight_time_min_minutes": 15,
            "frame_diagonal_mm": 300,
            "programmable_languages": ["Python"],
            "quantity": 30, "budget_per_unit_rub": 60000,
            "confidence": 0.9,
        })
        async def stub(_text):
            return canned
        monkeypatch.setattr(services["service"], "_call_llm_parse", stub)

        req = await services["service"].parse("Любой текст тендера")
        assert req.intent == "ready_model"
        assert req.purpose == "educational"
        assert req.drone_type == "quadcopter"
        assert req.motor_count_min == 4
        assert req.programmable_languages == ["Python"]

    @pytest.mark.asyncio
    async def test_empty_text_raises(self, services):
        with pytest.raises(TenderParseError):
            await services["service"].parse("")

    @pytest.mark.asyncio
    async def test_invalid_json_raises(self, services, monkeypatch):
        async def stub(_text):
            return "это не json"
        monkeypatch.setattr(services["service"], "_call_llm_parse", stub)
        with pytest.raises(TenderParseError):
            await services["service"].parse("Тендер на квадрокоптер")

    @pytest.mark.asyncio
    async def test_invalid_schema_raises(self, services, monkeypatch):
        # Валидный JSON, но motor_count_min=20 (вне диапазона)
        canned = json.dumps({"motor_count_min": 20})
        async def stub(_text):
            return canned
        monkeypatch.setattr(services["service"], "_call_llm_parse", stub)
        with pytest.raises(TenderParseError):
            await services["service"].parse("Тендер")

    @pytest.mark.asyncio
    async def test_extra_fields_ignored(self, services, monkeypatch):
        canned = json.dumps({"intent": "auto", "unknown": "ignored"})
        async def stub(_text):
            return canned
        monkeypatch.setattr(services["service"], "_call_llm_parse", stub)
        req = await services["service"].parse("Тендер")
        assert req.intent == "auto"


# --- Match ready_model ----------------------------------------------------

class TestMatchReadyModel:
    @pytest.mark.asyncio
    async def test_basic_ranking_with_llm(self, services, monkeypatch):
        # Готовый ответ LLM-rerank
        canned = json.dumps({
            "ranking": [
                {"model_id": "DRONE-001", "model_name": "Коптра Орлёнок",
                 "score": 92, "matches": ["время полёта 15"], "gaps": [],
                 "explanation": "Полностью соответствует."},
                {"model_id": "DRONE-100", "model_name": "Pioneer Mini",
                 "score": 64, "matches": [], "gaps": ["время полёта мало"],
                 "explanation": "Не дотягивает по времени полёта."},
            ],
            "summary": "Лучший — Коптра Орлёнок.",
        })
        async def stub(_req, _cands):
            return canned
        monkeypatch.setattr(services["service"], "_call_llm_rerank", stub)

        req = TenderRequirements(
            intent="ready_model",
            purpose="educational",
            drone_type="quadcopter",
            motor_count_min=4, motor_count_max=4,
            flight_time_min_minutes=15,
            programmable_languages=["Python"],
            budget_per_unit_rub=60000,
        )
        resp = await services["service"].match(req)

        assert resp.intent_used == "ready_model"
        assert resp.bom is None
        assert len(resp.results) >= 1
        assert resp.fallback_used is False
        assert resp.candidates_total >= 2
        # Орлёнок должен быть первым по итоговому score
        assert resp.results[0].model_id == "DRONE-001"
        assert resp.results[0].score >= 50
        assert "Коптра Орлёнок" in resp.summary

    @pytest.mark.asyncio
    async def test_phantom_id_filtered(self, services, monkeypatch):
        canned = json.dumps({
            "ranking": [
                {"model_id": "PHANTOM-999", "model_name": "Несуществующая модель",
                 "score": 100, "matches": [], "gaps": [], "explanation": "выдумка"},
                {"model_id": "DRONE-001", "model_name": "Коптра Орлёнок",
                 "score": 80, "matches": [], "gaps": [], "explanation": ""},
            ],
            "summary": "",
        })
        async def stub(_req, _cands):
            return canned
        monkeypatch.setattr(services["service"], "_call_llm_rerank", stub)

        req = TenderRequirements(intent="ready_model", drone_type="quadcopter")
        resp = await services["service"].match(req)
        ids = {r.model_id for r in resp.results}
        assert "PHANTOM-999" not in ids
        assert "DRONE-001" in ids

    @pytest.mark.asyncio
    async def test_fallback_on_invalid_llm(self, services, monkeypatch):
        async def stub(_req, _cands):
            return "не-JSON"
        monkeypatch.setattr(services["service"], "_call_llm_rerank", stub)

        req = TenderRequirements(intent="ready_model", drone_type="quadcopter")
        resp = await services["service"].match(req)
        assert resp.fallback_used is True
        assert len(resp.results) >= 1
        assert all(r.llm_score >= 0 for r in resp.results)

    @pytest.mark.asyncio
    async def test_fallback_on_empty_ranking(self, services, monkeypatch):
        canned = json.dumps({"ranking": [], "summary": "ничего не найдено"})
        async def stub(_req, _cands):
            return canned
        monkeypatch.setattr(services["service"], "_call_llm_rerank", stub)

        req = TenderRequirements(intent="ready_model", drone_type="quadcopter")
        resp = await services["service"].match(req)
        assert resp.fallback_used is True

    @pytest.mark.asyncio
    async def test_top_n_truncation(self, services, monkeypatch):
        # LLM возвращает 3 модели, проверяем сортировку по score
        canned = json.dumps({
            "ranking": [
                {"model_id": "DRONE-100", "model_name": "Pioneer Mini",
                 "score": 50, "matches": [], "gaps": [], "explanation": ""},
                {"model_id": "DRONE-002", "model_name": "FPV 5",
                 "score": 30, "matches": [], "gaps": [], "explanation": ""},
                {"model_id": "DRONE-001", "model_name": "Орлёнок",
                 "score": 90, "matches": [], "gaps": [], "explanation": ""},
            ],
            "summary": "",
        })
        async def stub(_req, _cands):
            return canned
        monkeypatch.setattr(services["service"], "_call_llm_rerank", stub)

        req = TenderRequirements(intent="ready_model")
        resp = await services["service"].match(req)
        # Сортировка по убыванию score
        scores = [r.score for r in resp.results]
        assert scores == sorted(scores, reverse=True)
        # Орлёнок должен быть на первом месте (LLM дал 90)
        assert resp.results[0].model_id == "DRONE-001"


# --- Match build_config ---------------------------------------------------

class TestMatchBuildConfig:
    @pytest.mark.asyncio
    async def test_build_config_returns_bom(self, services):
        req = TenderRequirements(
            intent="build_config",
            drone_type="quadcopter",
            motor_count_min=4, motor_count_max=4,
            frame_diagonal_mm=300,
        )
        resp = await services["service"].match(req)
        assert resp.intent_used == "build_config"
        assert resp.bom is not None
        assert resp.bom.is_complete is True
        assert len(resp.bom.items) >= 5
        # Готовых моделей в этом режиме нет
        assert resp.results == []


# --- Match auto -----------------------------------------------------------

class TestMatchAuto:
    @pytest.mark.asyncio
    async def test_auto_returns_both(self, services, monkeypatch):
        canned = json.dumps({
            "ranking": [
                {"model_id": "DRONE-001", "model_name": "Орлёнок",
                 "score": 80, "matches": [], "gaps": [], "explanation": ""},
            ],
            "summary": "",
        })
        async def stub(_req, _cands):
            return canned
        monkeypatch.setattr(services["service"], "_call_llm_rerank", stub)

        req = TenderRequirements(
            intent="auto",
            drone_type="quadcopter",
            motor_count_min=4, motor_count_max=4,
            frame_diagonal_mm=300,
        )
        resp = await services["service"].match(req)
        assert resp.intent_used == "auto"
        assert len(resp.results) >= 1
        assert resp.bom is not None
        assert resp.bom.is_complete is True


# --- parse_and_match (для тестов golden-set) ------------------------------

class TestParseAndMatch:
    @pytest.mark.asyncio
    async def test_full_pipeline(self, services, monkeypatch):
        parse_payload = json.dumps({
            "intent": "ready_model",
            "drone_type": "quadcopter",
            "motor_count_min": 4, "motor_count_max": 4,
        })
        rerank_payload = json.dumps({
            "ranking": [
                {"model_id": "DRONE-001", "model_name": "Орлёнок",
                 "score": 85, "matches": [], "gaps": [], "explanation": ""},
            ],
            "summary": "Готово",
        })
        async def stub_parse(_text):
            return parse_payload
        async def stub_rerank(_req, _cands):
            return rerank_payload
        monkeypatch.setattr(services["service"], "_call_llm_parse", stub_parse)
        monkeypatch.setattr(services["service"], "_call_llm_rerank", stub_rerank)

        resp = await services["service"].parse_and_match("Любой тендер")
        assert resp.intent_used == "ready_model"
        assert resp.results[0].model_id == "DRONE-001"


# --- Детерминированность --------------------------------------------------

class TestDeterminism:
    @pytest.mark.asyncio
    async def test_same_input_same_output(self, services, monkeypatch):
        canned = json.dumps({
            "ranking": [
                {"model_id": "DRONE-001", "model_name": "Орлёнок",
                 "score": 80, "matches": ["a"], "gaps": ["b"], "explanation": "test"},
            ],
            "summary": "Готово",
        })
        async def stub(_req, _cands):
            return canned
        monkeypatch.setattr(services["service"], "_call_llm_rerank", stub)

        req = TenderRequirements(intent="ready_model", drone_type="quadcopter")
        r1 = await services["service"].match(req)
        r2 = await services["service"].match(req)
        # Структуры результатов и финальный скоринг идентичны
        assert r1.results[0].model_id == r2.results[0].model_id
        assert r1.results[0].score == r2.results[0].score
        assert r1.results[0].cosine_score == r2.results[0].cosine_score


# --- Empty drone catalog --------------------------------------------------

class TestEmptyCatalog:
    @pytest.mark.asyncio
    async def test_empty_drone_catalog_returns_empty_results(self, tmp_path, fake_embedder):
        drones = DroneIndexService(
            index_path=str(tmp_path / "di.json"),
            embeddings_path=str(tmp_path / "de.npy"),
        )
        # Каталог пуст
        components = ComponentIndexService(
            index_path=str(tmp_path / "ci.json"),
            embeddings_path=str(tmp_path / "ce.npy"),
        )
        components.rebuild_from_components([])
        builder = ConfigBuilder(components)
        llm = _StubLLM()
        svc = TenderService(llm, drones, builder)

        req = TenderRequirements(intent="ready_model")
        resp = await svc.match(req)
        assert resp.results == []
        assert resp.bom is None
