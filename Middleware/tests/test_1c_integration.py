"""
Интеграционные тесты, моделирующие запросы от 1С-расширений к Middleware.

Проверяет контракт между 1С-кодом (.bsl) и серверным API: форматы запросов,
учётные данные сервисного аккаунта, значения полей source, ответы на
failure-сценарии.
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.services.auth_service as auth_mod
import app.services.kanban_service as kanban_mod
from app.services.auth_service import UserDB, DepartmentDB

TEST_JWT_SECRET = "test-secret-key-for-pytest-1c-integration"


def _make_engine():
    eng = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(eng, "connect")
    def _pragma(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return eng


def _seed(session):
    depts = [
        DepartmentDB(name="IT"),
        DepartmentDB(name="Продажи"),
        DepartmentDB(name="Закупки"),
        DepartmentDB(name="Склад"),
    ]
    session.add_all(depts)
    session.flush()

    users = [
        UserDB(
            username="admin",
            password_hash=auth_mod.pwd_context.hash("admin"),
            full_name="Администратор",
            role="admin",
            department_id=depts[0].id,
            avatar_color="#3b82f6",
            is_active=True,
        ),
        UserDB(
            username="1c_service",
            password_hash=auth_mod.pwd_context.hash("1c_service_2024"),
            full_name="1С:Предприятие (сервисный аккаунт)",
            role="service_bridge",
            department_id=depts[0].id,
            avatar_color="#6366f1",
            is_active=True,
        ),
        UserDB(
            username="ivanov",
            password_hash=auth_mod.pwd_context.hash("123456"),
            full_name="Иванов А.С.",
            role="manager",
            department_id=depts[1].id,
            avatar_color="#ef4444",
            is_active=True,
        ),
        UserDB(
            username="sidorova",
            password_hash=auth_mod.pwd_context.hash("123456"),
            full_name="Сидорова М.П.",
            role="employee",
            department_id=depts[2].id,
            avatar_color="#22c55e",
            is_active=True,
        ),
    ]
    session.add_all(users)
    session.commit()


@pytest.fixture(scope="function")
def db_engine():
    eng = _make_engine()
    auth_mod.Base.metadata.create_all(eng)
    kanban_mod.Base.metadata.create_all(eng)
    return eng


@pytest.fixture(scope="function")
def client(db_engine, monkeypatch):
    from fastapi.testclient import TestClient
    from main import app

    test_sl = sessionmaker(bind=db_engine)

    monkeypatch.setattr(auth_mod, "SessionLocal", test_sl)
    monkeypatch.setattr(auth_mod, "engine", db_engine)
    monkeypatch.setattr(auth_mod, "JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setattr(auth_mod.auth_service, "_get_session", test_sl)

    monkeypatch.setattr(kanban_mod, "SessionLocal", test_sl)
    monkeypatch.setattr(kanban_mod, "engine", db_engine)
    monkeypatch.setattr(kanban_mod.kanban_service, "_get_session", test_sl)

    _seed(test_sl())

    with TestClient(app) as c:
        yield c


@pytest.fixture
def service_token(client):
    resp = client.post(
        "/auth/login",
        json={"username": "1c_service", "password": "1c_service_2024"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def service_headers(service_token):
    return {"X-Auth-Token": service_token}


@pytest.fixture
def admin_token(client):
    resp = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def admin_headers(admin_token):
    return {"X-Auth-Token": admin_token}


# =============================================================================
# 1С-сервисный аккаунт
# =============================================================================


class Test1CServiceAccount:
    def test_login_with_1c_service_credentials(self, client):
        resp = client.post(
            "/auth/login",
            json={"username": "1c_service", "password": "1c_service_2024"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body

    def test_1c_service_has_service_bridge_role(self, client, service_headers):
        resp = client.get("/auth/me", headers=service_headers)
        assert resp.status_code == 200
        assert resp.json()["role"] == "service_bridge"

    def test_wrong_1c_service_password_fails(self, client):
        resp = client.post(
            "/auth/login",
            json={"username": "1c_service", "password": "wrong_password"},
        )
        assert resp.status_code == 401


# =============================================================================
# Канбан — source от разных расширений 1С
# =============================================================================


class Test1CKanbanSources:
    def test_create_task_source_1c(self, client, service_headers):
        resp = client.post(
            "/kanban/tasks",
            json={"title": "Задача из чата", "column": "todo", "priority": "medium", "source": "1c"},
            headers=service_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "1c"

    def test_create_task_source_1c_kanban(self, client, service_headers):
        resp = client.post(
            "/kanban/tasks",
            json={"title": "Задача из канбана", "column": "todo", "priority": "medium", "source": "1c_kanban"},
            headers=service_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "1c_kanban"

    def test_create_task_source_1c_mobile(self, client, service_headers):
        resp = client.post(
            "/kanban/tasks",
            json={"title": "Задача из мобильного", "column": "todo", "priority": "medium", "source": "1c_mobile"},
            headers=service_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "1c_mobile"


# =============================================================================
# Чат — context-параметр от 1С
# =============================================================================


class Test1CChatContext:
    def test_chat_with_1c_form_context(self, client, service_headers, monkeypatch):
        async def stub_generate(messages, context="", actions=None, user_role="admin"):
            return {"text": "Тестовый ответ", "action": None, "data": None}

        import app.services.llm_service as llm_mod

        monkeypatch.setattr(llm_mod.llm_service, "generate_response", stub_generate)

        resp = client.post(
            "/chat",
            json={
                "messages": [{"role": "user", "text": "Привет"}],
                "context": "Форма: Обработка.ИнтеллектуальныйАссистент.Форма",
            },
            headers=service_headers,
        )
        assert resp.status_code == 200

    def test_chat_acting_user_least_privilege_and_provider_metadata(self, client, service_headers, monkeypatch):
        captured_role = []

        async def stub_generate(messages, context="", actions=None, user_role="employee"):
            captured_role.append(user_role)
            return {
                "text": "Ответ для менеджера",
                "action": None,
                "data": None,
                "provider_used": "gigachat",
                "is_fallback": False,
                "model_name": "GigaChat-Pro",
            }

        import app.services.llm_service as llm_mod
        monkeypatch.setattr(llm_mod.llm_service, "generate_response", stub_generate)

        # Сервисный JWT не удостоверяет личность указанного в заголовке менеджера.
        headers = {
            **service_headers,
            "X-1C-User-Name": "ivanov",
        }
        resp = client.post(
            "/chat",
            json={"messages": [{"role": "user", "text": "План продаж"}], "user_identity": "ivanov"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider_used"] == "gigachat"
        assert data["is_fallback"] is False
        assert data["model_name"] == "GigaChat-Pro"
        assert captured_role == ["employee"]

    @pytest.mark.parametrize("claimed_name", ["admin", "ivanov"])
    def test_bridge_cannot_impersonate_existing_account(self, client, service_headers, monkeypatch, claimed_name):
        from main import llm_service
        roles = []

        async def capture(messages, context="", user_role="employee"):
            roles.append(user_role)
            return {"text": "ok", "action": None, "data": None}

        monkeypatch.setattr(llm_service, "generate_response", capture)
        response = client.post("/chat", headers={**service_headers, "X-1C-User-Name": claimed_name},
            json={"messages": [{"role": "user", "text": "test"}], "user_identity": claimed_name, "user_role": "admin"})
        assert response.status_code == 200
        assert roles == ["employee"]

    def test_personal_jwt_preserves_manager_role(self, client, monkeypatch):
        from main import llm_service
        roles = []

        async def capture(messages, context="", user_role="employee"):
            roles.append(user_role)
            return {"text": "ok", "action": None, "data": None}

        monkeypatch.setattr(llm_service, "generate_response", capture)
        login = client.post("/auth/login", json={"username": "ivanov", "password": "123456"})
        response = client.post("/chat", headers={"X-Auth-Token": login.json()["access_token"], "X-1C-User-Name": "admin"},
            json={"messages": [{"role": "user", "text": "test"}], "user_role": "admin"})
        assert response.status_code == 200
        assert roles == ["manager"]

    def test_chat_role_header_cannot_escalate_privileges(self, client, service_headers, monkeypatch):
        """Заголовок X-1C-User-Role не должен повышать привилегии.

        Регрессия на уязвимость обхода RBAC: раньше роль принималась из заголовка
        как есть, и держатель токена service_bridge мог объявить себя director,
        получив доступ к финансовым регистрам.
        """
        captured_role = []

        async def stub_generate(messages, context="", actions=None, user_role="employee"):
            captured_role.append(user_role)
            return {"text": "ok", "action": None, "data": None}

        import app.services.llm_service as llm_mod
        monkeypatch.setattr(llm_mod.llm_service, "generate_response", stub_generate)

        # `sidorova` (employee) заявляет себя директором через заголовок и тело запроса
        resp = client.post(
            "/chat",
            json={
                "messages": [{"role": "user", "text": "Остатки денег"}],
                "user_identity": "sidorova",
                "user_role": "director",
            },
            headers={**service_headers, "X-1C-User-Name": "sidorova", "X-1C-User-Role": "director"},
        )
        assert resp.status_code == 200
        assert captured_role == ["employee"], "Роль из заголовка не должна повышать привилегии"

    def test_chat_unknown_bridge_user_downgraded_to_employee(self, client, service_headers, monkeypatch):
        """Неизвестный пользователь из 1С получает минимальные права, а не заявленные."""
        captured_role = []

        async def stub_generate(messages, context="", actions=None, user_role="employee"):
            captured_role.append(user_role)
            return {"text": "ok", "action": None, "data": None}

        import app.services.llm_service as llm_mod
        monkeypatch.setattr(llm_mod.llm_service, "generate_response", stub_generate)

        resp = client.post(
            "/chat",
            json={"messages": [{"role": "user", "text": "Кассовый разрыв"}]},
            headers={**service_headers, "X-1C-User-Name": "nonexistent_user", "X-1C-User-Role": "cfo"},
        )
        assert resp.status_code == 200
        assert captured_role == ["employee"]


# =============================================================================
# Синхронизация финансовых срезов из 1С
# =============================================================================


class Test1CFinancialSnapshotSync:
    def test_sync_financial_snapshot_and_live_monitor(self, client, service_headers, admin_headers):
        # 1. Verify monitor can accept live 1C registers
        live_payload = {
            "source": "1С:УНФ 3.0 (Рабочая ИБ)",
            "kpi": {
                "cash_balance": 15000000.0,
                "cash_gap": 0.0,
                "liquidity_reserve": 14000000.0,
            },
            "creditors": [],
            "dead_stock": [],
        }
        sync_resp = client.post(
            "/analytics/1c/sync-financial-snapshot",
            json=live_payload,
            headers=service_headers,
        )
        assert sync_resp.status_code == 200
        assert sync_resp.json()["status"] == "ok"

        # 2. Monitor now serves live_1c_sync
        m2 = client.get("/analytics/monitor", headers=admin_headers)
        assert m2.status_code == 200
        assert m2.json()["mode"] == "live_1c_sync"
        assert m2.json()["is_mock_data"] is False
        assert m2.json()["kpi"]["cash_balance"] == 15000000.0


# =============================================================================
# Failure-сценарии
# =============================================================================


class TestExpiredJWT:
    def test_expired_token_returns_401(self, client, monkeypatch):
        import jose.jwt as jwt_mod

        expired_payload = {
            "sub": "1c_service",
            "role": "admin",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        expired_token = jwt_mod.encode(expired_payload, TEST_JWT_SECRET, algorithm="HS256")

        resp = client.get("/kanban/tasks", headers={"X-Auth-Token": expired_token})
        assert resp.status_code == 401


class TestKanbanNotFound:
    def test_delete_nonexistent_task_404(self, client, service_headers):
        resp = client.delete("/kanban/tasks/99999", headers=service_headers)
        assert resp.status_code == 404

    def test_move_nonexistent_task(self, client, service_headers):
        resp = client.post(
            "/kanban/tasks/move",
            json={"task_id": 99999, "column": "done"},
            headers=service_headers,
        )
        assert resp.status_code == 404


class TestEmptyChat:
    def test_chat_with_empty_messages(self, client, service_headers, monkeypatch):
        async def stub_generate(messages, context="", actions=None, user_role="admin"):
            return {"text": "Пустой запрос", "action": None, "data": None}

        import app.services.llm_service as llm_mod

        monkeypatch.setattr(llm_mod.llm_service, "generate_response", stub_generate)

        resp = client.post(
            "/chat",
            json={"messages": [], "context": ""},
            headers=service_headers,
        )
        assert resp.status_code == 200


class TestInactiveUserLogin:
    def test_inactive_user_cannot_login(self, client, db_engine):
        test_sl = sessionmaker(bind=db_engine)
        session = test_sl()
        user = UserDB(
            username="inactive_user",
            password_hash=auth_mod.pwd_context.hash("pass123"),
            full_name="Неактивный",
            role="employee",
            is_active=False,
        )
        session.add(user)
        session.commit()

        resp = client.post(
            "/auth/login",
            json={"username": "inactive_user", "password": "pass123"},
        )
        assert resp.status_code == 401


class TestMetadataUpdateByNonAdmin:
    def test_employee_cannot_update_metadata(self, client, admin_headers, monkeypatch):
        emp_resp = client.post(
            "/auth/register",
            json={"username": "emp1", "password": "emp1", "full_name": "Employee", "role": "employee"},
            headers=admin_headers,
        )
        if emp_resp.status_code == 200:
            emp_token = emp_resp.json().get("access_token")
            if not emp_token:
                login_resp = client.post(
                    "/auth/login",
                    json={"username": "emp1", "password": "emp1"},
                )
                emp_token = login_resp.json()["access_token"]

            resp = client.post(
                "/update_metadata",
                json={"items": []},
                headers={"X-Auth-Token": emp_token},
            )
            assert resp.status_code == 403
