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
            role="admin",
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

    def test_1c_service_has_admin_role(self, client, service_headers):
        resp = client.get("/auth/me", headers=service_headers)
        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"

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
