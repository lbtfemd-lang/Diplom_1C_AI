"""Интеграционные тесты HTTP-эндпоинтов прикладного расширения.

Покрывают: успешные ответы /tender/parse и /tender/match, проверку ролей
(employee → 403, manager → 200, admin → 200), 404 при выключенной фиче,
503 при пустом каталоге БПЛА, 422 при ошибке парсинга, 401 без токена.
LLM-вызовы в TenderService мокаются на уровне `_call_llm_*`.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.core import reset_cache
from app.models.tender_models import TenderRequirements
from app.services import _embedding_runtime
from app.services.component_index_service import ComponentIndexService
from app.services.config_builder import ConfigBuilder
from app.services.drone_index_service import DroneIndexService
from app.services.tender_service import TenderService
from tests.conftest import make_user


# --- Фейковый эмбеддер ----------------------------------------------------

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


# --- Подмена singleton-сервисов TenderService на тестовые экземпляры ------

@pytest.fixture
def tender_setup(tmp_path, fake_embedder, monkeypatch):
    """Подменить singleton drone_index/components/tender на тестовые с tmp_path.

    Возвращает dict с ссылками на сервисы для дальнейшей подмены _call_llm_*.
    """
    import app.services.drone_index_service as dis_mod
    import app.services.component_index_service as cis_mod
    import app.services.tender_service as ts_mod
    import main

    # Создаём свежие инстансы с tmp_path
    drone_svc = DroneIndexService(
        index_path=str(tmp_path / "drones.json"),
        embeddings_path=str(tmp_path / "drones.npy"),
    )
    comp_svc = ComponentIndexService(
        index_path=str(tmp_path / "comp.json"),
        embeddings_path=str(tmp_path / "comp.npy"),
    )

    # Заполняем каталоги
    drone_svc.rebuild_from_drones([
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
            "price_rub": 85000, "catalog_source": "own",
        },
        {
            "model_id": "DRONE-100", "model_name": "Pioneer Mini",
            "drone_type": "quadcopter", "purpose": "educational",
            "motor_count": 4, "flight_time_minutes": 12,
            "price_rub": 48000, "catalog_source": "partner",
        },
    ])
    comp_svc.rebuild_from_components([
        {"component_id": "FR-300", "component_name": "Рама 300",
         "category": "frame", "catalog_source": "own", "price_rub": 3000,
         "compatibility": {"motor_mount_count": 4, "motor_mount_size_mm": 16,
                           "prop_size_inch_max": 7.5, "diagonal_mm": 300, "mass_g": 110}},
        {"component_id": "FC-IPK1", "component_name": "ИПК1",
         "category": "flight_controller", "catalog_source": "own", "price_rub": 5500,
         "compatibility": {"firmware": ["Betaflight"], "voltage_input_v": "2S-6S",
                           "uart_count": 5, "programmable_languages": ["Python"]}},
        {"component_id": "MT-2207", "component_name": "Мотор",
         "category": "motor", "catalog_source": "own", "price_rub": 1800,
         "compatibility": {"kv": 1700, "mount_size_mm": 16, "weight_g": 32,
                           "max_current_a": 38, "voltage_v": "3S-6S"}},
        {"component_id": "ESC-60", "component_name": "ESC",
         "category": "esc", "catalog_source": "own", "price_rub": 2200,
         "compatibility": {"current_continuous_a": 60, "voltage_v": "3S-6S"}},
        {"component_id": "BAT-4S", "component_name": "Батарея",
         "category": "battery", "catalog_source": "own", "price_rub": 3800,
         "compatibility": {"chemistry": "LiPo", "cells_s": 4,
                           "capacity_mah": 4000, "weight_g": 380}},
        {"component_id": "PRP-7", "component_name": "Пропеллер",
         "category": "propeller", "catalog_source": "own", "price_rub": 250,
         "compatibility": {"diameter_inch": 7.0}},
    ])

    builder = ConfigBuilder(comp_svc)

    # Подменяем singleton'ы внутри модулей сервисов и в main.py
    monkeypatch.setattr(dis_mod, "drone_index_service", drone_svc)
    monkeypatch.setattr(cis_mod, "component_index_service", comp_svc)
    monkeypatch.setattr(main, "drone_index_service", drone_svc)
    monkeypatch.setattr(main, "component_index_service", comp_svc)

    # Подменяем фабрику get_tender_service: всегда возвращает наш экземпляр
    from app.services.llm_service import llm_service as real_llm
    test_service = TenderService(real_llm, drone_svc, builder)
    monkeypatch.setattr(ts_mod, "_singleton", test_service)
    monkeypatch.setattr(ts_mod, "get_tender_service", lambda: test_service)
    # main.py уже импортировал get_tender_service по имени — подменим и там
    monkeypatch.setattr(main, "get_tender_service", lambda: test_service)

    yield {
        "drone_svc": drone_svc,
        "comp_svc": comp_svc,
        "tender_svc": test_service,
    }

    ts_mod.reset_tender_service_for_tests()


# --- Хелперы для подмены ответов LLM --------------------------------------

def stub_parse(tender_setup, payload: dict | str):
    """Вернёт async-функцию, имитирующую ответ LLM для парсинга."""
    body = payload if isinstance(payload, str) else json.dumps(payload)
    async def _stub(_text):
        return body
    return _stub


def stub_rerank(tender_setup, payload: dict | str):
    body = payload if isinstance(payload, str) else json.dumps(payload)
    async def _stub(_req, _cands):
        return body
    return _stub


# --- Хелпер: получить токен пользователя по логину/паролю -----------------

def login(client, username, password):
    resp = client.post("/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


# --- /tender/parse --------------------------------------------------------

class TestTenderParseEndpoint:
    def test_admin_can_parse(self, client, admin_headers, tender_setup, monkeypatch):
        canned = {
            "intent": "ready_model", "drone_type": "quadcopter",
            "motor_count_min": 4, "motor_count_max": 4,
        }
        monkeypatch.setattr(
            tender_setup["tender_svc"], "_call_llm_parse", stub_parse(tender_setup, canned)
        )
        resp = client.post(
            "/tender/parse",
            json={"tender_text": "Нужен квадрокоптер на 4 моторах"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["requirements"]["drone_type"] == "quadcopter"
        assert "Распознано" in body["summary"] or "распознавание" in body["summary"].lower()

    def test_manager_can_parse(self, client, admin_token, tender_setup, monkeypatch):
        # Создаём manager-пользователя
        make_user(client, admin_token, username="mgr", password="mgr123",
                  full_name="Менеджер", role="manager")
        token = login(client, "mgr", "mgr123")
        canned = {"intent": "auto"}
        monkeypatch.setattr(
            tender_setup["tender_svc"], "_call_llm_parse", stub_parse(tender_setup, canned)
        )
        resp = client.post(
            "/tender/parse",
            json={"tender_text": "Любой тендер"},
            headers={"X-Auth-Token": token},
        )
        assert resp.status_code == 200

    def test_employee_forbidden(self, client, admin_token, tender_setup):
        make_user(client, admin_token, username="emp", password="emp123",
                  full_name="Сотрудник", role="employee")
        token = login(client, "emp", "emp123")
        resp = client.post(
            "/tender/parse",
            json={"tender_text": "Тендер"},
            headers={"X-Auth-Token": token},
        )
        assert resp.status_code == 403

    def test_no_token_unauthorized(self, client, tender_setup):
        resp = client.post("/tender/parse", json={"tender_text": "Тендер"})
        assert resp.status_code == 401

    def test_invalid_llm_response_returns_422(self, client, admin_headers,
                                              tender_setup, monkeypatch):
        # LLM вернул не-JSON
        monkeypatch.setattr(
            tender_setup["tender_svc"], "_call_llm_parse",
            stub_parse(tender_setup, "не json"),
        )
        resp = client.post(
            "/tender/parse",
            json={"tender_text": "Тендер"},
            headers=admin_headers,
        )
        assert resp.status_code == 422
        assert "распознать" in resp.json()["detail"].lower()

    def test_empty_text_rejected_by_pydantic(self, client, admin_headers, tender_setup):
        resp = client.post(
            "/tender/parse",
            json={"tender_text": ""},
            headers=admin_headers,
        )
        # Pydantic-валидация: min_length=1 → 422
        assert resp.status_code == 422

    def test_summary_contains_key_fields(self, client, admin_headers,
                                        tender_setup, monkeypatch):
        canned = {
            "intent": "ready_model",
            "drone_type": "quadcopter",
            "motor_count_min": 4,
            "flight_time_min_minutes": 15,
            "quantity": 30,
            "budget_per_unit_rub": 60000,
        }
        monkeypatch.setattr(
            tender_setup["tender_svc"], "_call_llm_parse", stub_parse(tender_setup, canned)
        )
        resp = client.post(
            "/tender/parse",
            json={"tender_text": "..."},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        summary = resp.json()["summary"]
        assert "квадрокоптер" in summary
        assert "30" in summary
        assert "60000" in summary


# --- /tender/match --------------------------------------------------------

class TestTenderMatchEndpoint:
    def test_admin_match_ready_model(self, client, admin_headers, tender_setup, monkeypatch):
        canned = {
            "ranking": [
                {"model_id": "DRONE-001", "model_name": "Коптра Орлёнок",
                 "score": 90, "matches": [], "gaps": [], "explanation": "ok"},
            ],
            "summary": "Готово.",
        }
        monkeypatch.setattr(
            tender_setup["tender_svc"], "_call_llm_rerank",
            stub_rerank(tender_setup, canned),
        )
        body = {
            "requirements": {
                "intent": "ready_model",
                "drone_type": "quadcopter",
                "motor_count_min": 4, "motor_count_max": 4,
                "programmable_languages": ["Python"],
            }
        }
        resp = client.post("/tender/match", json=body, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent_used"] == "ready_model"
        assert len(data["results"]) >= 1
        assert data["results"][0]["model_id"] == "DRONE-001"
        assert data["bom"] is None

    def test_admin_match_build_config(self, client, admin_headers, tender_setup):
        body = {
            "requirements": {
                "intent": "build_config",
                "drone_type": "quadcopter",
                "motor_count_min": 4, "motor_count_max": 4,
                "frame_diagonal_mm": 300,
            }
        }
        resp = client.post("/tender/match", json=body, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent_used"] == "build_config"
        assert data["bom"] is not None
        assert data["bom"]["is_complete"] is True
        assert len(data["bom"]["items"]) >= 5

    def test_admin_match_auto(self, client, admin_headers, tender_setup, monkeypatch):
        canned = {
            "ranking": [
                {"model_id": "DRONE-001", "model_name": "Коптра Орлёнок",
                 "score": 80, "matches": [], "gaps": [], "explanation": ""},
            ],
            "summary": "",
        }
        monkeypatch.setattr(
            tender_setup["tender_svc"], "_call_llm_rerank",
            stub_rerank(tender_setup, canned),
        )
        body = {
            "requirements": {
                "intent": "auto",
                "drone_type": "quadcopter",
                "motor_count_min": 4, "motor_count_max": 4,
                "frame_diagonal_mm": 300,
            }
        }
        resp = client.post("/tender/match", json=body, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent_used"] == "auto"
        assert len(data["results"]) >= 1
        assert data["bom"] is not None

    def test_employee_forbidden(self, client, admin_token, tender_setup):
        make_user(client, admin_token, username="emp2", password="emp123",
                  full_name="Сотрудник", role="employee")
        token = login(client, "emp2", "emp123")
        body = {"requirements": {"intent": "auto"}}
        resp = client.post("/tender/match", json=body, headers={"X-Auth-Token": token})
        assert resp.status_code == 403

    def test_no_token_unauthorized(self, client, tender_setup):
        body = {"requirements": {"intent": "auto"}}
        resp = client.post("/tender/match", json=body)
        assert resp.status_code == 401

    def test_503_when_drone_catalog_empty(self, client, admin_headers,
                                          tmp_path, fake_embedder, monkeypatch):
        """503 при пустом каталоге БПЛА для intent ready_model/auto."""
        import app.services.drone_index_service as dis_mod
        import main

        empty_drones = DroneIndexService(
            index_path=str(tmp_path / "empty.json"),
            embeddings_path=str(tmp_path / "empty.npy"),
        )
        # Каталог пуст — is_ready() = False
        monkeypatch.setattr(dis_mod, "drone_index_service", empty_drones)
        monkeypatch.setattr(main, "drone_index_service", empty_drones)

        body = {"requirements": {"intent": "ready_model", "drone_type": "quadcopter"}}
        resp = client.post("/tender/match", json=body, headers=admin_headers)
        assert resp.status_code == 503
        assert "каталог" in resp.json()["detail"].lower()

    def test_build_config_does_not_check_drone_index(self, client, admin_headers,
                                                    tmp_path, fake_embedder, monkeypatch):
        """Для intent=build_config пустой каталог моделей не блокирует подбор."""
        import app.services.drone_index_service as dis_mod
        import app.services.component_index_service as cis_mod
        import app.services.tender_service as ts_mod
        from app.services.llm_service import llm_service as real_llm
        import main

        empty_drones = DroneIndexService(
            index_path=str(tmp_path / "ed.json"),
            embeddings_path=str(tmp_path / "ed.npy"),
        )
        comps = ComponentIndexService(
            index_path=str(tmp_path / "ec.json"),
            embeddings_path=str(tmp_path / "ec.npy"),
        )
        comps.rebuild_from_components([
            {"component_id": "FR-1", "component_name": "Рама",
             "category": "frame", "catalog_source": "own", "price_rub": 3000,
             "compatibility": {"motor_mount_count": 4, "motor_mount_size_mm": 16,
                               "prop_size_inch_max": 7.0, "diagonal_mm": 300,
                               "mass_g": 100}},
            {"component_id": "FC-1", "component_name": "FC",
             "category": "flight_controller", "catalog_source": "own", "price_rub": 5500,
             "compatibility": {"firmware": ["Betaflight"]}},
            {"component_id": "MT-1", "component_name": "Motor",
             "category": "motor", "catalog_source": "own", "price_rub": 1800,
             "compatibility": {"mount_size_mm": 16, "max_current_a": 30,
                               "voltage_v": "3S-6S"}},
            {"component_id": "ESC-1", "component_name": "ESC",
             "category": "esc", "catalog_source": "own", "price_rub": 2200,
             "compatibility": {"current_continuous_a": 50, "voltage_v": "3S-6S"}},
            {"component_id": "BAT-1", "component_name": "Battery",
             "category": "battery", "catalog_source": "own", "price_rub": 3800,
             "compatibility": {"cells_s": 4, "capacity_mah": 4000, "weight_g": 380}},
            {"component_id": "PRP-1", "component_name": "Prop",
             "category": "propeller", "catalog_source": "own", "price_rub": 250,
             "compatibility": {"diameter_inch": 7.0}},
        ])

        builder = ConfigBuilder(comps)
        test_service = TenderService(real_llm, empty_drones, builder)

        monkeypatch.setattr(dis_mod, "drone_index_service", empty_drones)
        monkeypatch.setattr(cis_mod, "component_index_service", comps)
        monkeypatch.setattr(main, "drone_index_service", empty_drones)
        monkeypatch.setattr(main, "component_index_service", comps)
        monkeypatch.setattr(ts_mod, "_singleton", test_service)
        monkeypatch.setattr(ts_mod, "get_tender_service", lambda: test_service)
        monkeypatch.setattr(main, "get_tender_service", lambda: test_service)

        body = {
            "requirements": {
                "intent": "build_config",
                "drone_type": "quadcopter",
                "motor_count_min": 4, "motor_count_max": 4,
                "frame_diagonal_mm": 300,
            }
        }
        resp = client.post("/tender/match", json=body, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["bom"] is not None
        ts_mod.reset_tender_service_for_tests()


# --- Фича-флаг ------------------------------------------------------------

class TestFeatureFlag:
    def test_404_when_feature_disabled_parse(self, client, admin_headers,
                                             tender_setup, monkeypatch):
        monkeypatch.setenv("DRONE_FEATURE_ENABLED", "false")
        reset_cache()
        try:
            resp = client.post(
                "/tender/parse",
                json={"tender_text": "Тендер"},
                headers=admin_headers,
            )
            assert resp.status_code == 404
        finally:
            monkeypatch.setenv("DRONE_FEATURE_ENABLED", "true")
            reset_cache()

    def test_404_when_feature_disabled_match(self, client, admin_headers,
                                             tender_setup, monkeypatch):
        monkeypatch.setenv("DRONE_FEATURE_ENABLED", "false")
        reset_cache()
        try:
            resp = client.post(
                "/tender/match",
                json={"requirements": {"intent": "auto"}},
                headers=admin_headers,
            )
            assert resp.status_code == 404
        finally:
            monkeypatch.setenv("DRONE_FEATURE_ENABLED", "true")
            reset_cache()


# --- /update_metadata с секциями drones/components ------------------------

class TestUpdateMetadataExtended:
    def test_drones_section_rebuilds_index(self, client, admin_headers,
                                           tender_setup, monkeypatch):
        body = {
            "items": [],
            "drones": [
                {"model_id": "NEW-001", "model_name": "Новая модель",
                 "drone_type": "quadcopter", "motor_count": 4,
                 "catalog_source": "own"},
            ],
            "components": [],
        }
        resp = client.post("/update_metadata", json=body, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data.get("drones_count") == 1
        assert data.get("components_count") == 0
        # Индекс перестроен
        assert tender_setup["drone_svc"].is_ready()
        assert any(it.model_id == "NEW-001" for it in tender_setup["drone_svc"].items)

    def test_no_drones_section_keeps_old_behaviour(self, client, admin_headers, tender_setup):
        """Без секций drones/components поведение совпадает со старым."""
        body = {"items": []}
        resp = client.post("/update_metadata", json=body, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "drones_count" not in data
        assert "components_count" not in data
