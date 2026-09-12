import os
import sys
import tempfile
from unittest.mock import patch

# Isolate configuration before importing module-level service singletons.
import dotenv

_test_storage = tempfile.TemporaryDirectory(prefix="diplom-pytest-")
_test_environment = {
    "SQLITE_DB_PATH": os.path.join(_test_storage.name, "bootstrap.db"),
    "METADATA_DATA_DIR": _test_storage.name,
    "METADATA_ML_ENABLED": "false",
    "RATE_LIMIT_ENABLED": "false",
    "JWT_SECRET": "isolated-pytest-secret-not-for-deployment",
}
for _key in (
    "GEMINI_API_KEY", "OPENROUTER_API_KEY", "GROQ_API_KEY", "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY", "FIREWORKS_API_KEY", "GIGACHAT_CREDENTIALS", "GIGACHAT_API_KEY",
    "YANDEX_API_KEY", "YANDEX_SPEECHKIT_API_KEY", "OLLAMA_HOST", "LOCAL_RUSSIAN_LLM",
    "OPENAI_BASE_URL", "LLM_BASE_URL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
    "VK_GROUP_TOKEN", "VK_GROUP_ID", "SMTP_USER", "SMTP_PASSWORD", "IMAP_USER",
    "IMAP_PASSWORD", "VK_BIND_IP", "SMTP_BIND_IP", "EMAIL_HOOK_SECRET",
    "TELEGRAM_WEBHOOK_SECRET", "VK_SECRET_KEY",
):
    _test_environment[_key] = ""
_environment_patch = patch.dict(os.environ, _test_environment)
_dotenv_patch = patch.object(dotenv, "load_dotenv", return_value=False)
_environment_patch.start()
_dotenv_patch.start()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.services.auth_service as auth_mod
import app.services.kanban_service as kanban_mod
from app.services.auth_service import UserDB, DepartmentDB

TEST_JWT_SECRET = "test-secret-key-for-pytest"

os.environ["RATE_LIMIT_ENABLED"] = "false"


@pytest.fixture(autouse=True)
def isolate_external_integrations(monkeypatch, tmp_path):
    import httpx
    import smtplib
    import imaplib
    import app.services.metadata_service as metadata_mod
    from app.services.telegram_bot import telegram_bot_service

    def deny_network(*args, **kwargs):
        raise AssertionError("External network access is forbidden in unit tests")

    async def deny_async_network(*args, **kwargs):
        deny_network()

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", deny_network)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", deny_async_network)
    monkeypatch.setattr(smtplib, "SMTP", deny_network)
    monkeypatch.setattr(smtplib, "SMTP_SSL", deny_network)
    monkeypatch.setattr(imaplib, "IMAP4_SSL", deny_network)
    monkeypatch.setattr(telegram_bot_service, "active_chat_ids", set())
    monkeypatch.setattr(telegram_bot_service, "_register_chat", lambda chat_id: None)
    for name in ("METADATA_FILE", "EMBEDDINGS_FILE", "INDEX_LITE_FILE"):
        monkeypatch.setattr(metadata_mod, name, str(tmp_path / os.path.basename(getattr(metadata_mod, name))))
    monkeypatch.setattr(metadata_mod.metadata_service, "metadata_index", [])
    monkeypatch.setattr(metadata_mod.metadata_service, "model", None)


def pytest_unconfigure(config):
    auth_mod.engine.dispose()
    kanban_mod.engine.dispose()
    _dotenv_patch.stop()
    _environment_patch.stop()
    _test_storage.cleanup()


def _make_test_engine():
    eng = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    @event.listens_for(eng, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    return eng


def _seed_test_data(session):
    depts = [
        DepartmentDB(name="IT"),
        DepartmentDB(name="Продажи"),
        DepartmentDB(name="Закупки"),
        DepartmentDB(name="Склад"),
        DepartmentDB(name="Дирекция"),
        DepartmentDB(name="Финансовый отдел"),
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
            username="director",
            password_hash=auth_mod.pwd_context.hash("director123"),
            full_name="Абдулов Ринат Фаридович",
            role="director",
            department_id=depts[4].id,
            avatar_color="#ef4444",
            is_active=True,
        ),
        UserDB(
            username="cfo",
            password_hash=auth_mod.pwd_context.hash("cfo123"),
            full_name="Филиппова Елена Анатольевна",
            role="cfo",
            department_id=depts[5].id,
            avatar_color="#f59e0b",
            is_active=True,
        ),
        UserDB(
            username="accountant",
            password_hash=auth_mod.pwd_context.hash("buh123"),
            full_name="Смирнова Ольга Викторовна (Главбух)",
            role="cfo",
            department_id=depts[5].id,
            avatar_color="#06b6d4",
            is_active=True,
        ),
        UserDB(
            username="manager",
            password_hash=auth_mod.pwd_context.hash("manager123"),
            full_name="Иванов Алексей Сергеевич",
            role="manager",
            department_id=depts[1].id,
            avatar_color="#10b981",
            is_active=True,
        ),
        UserDB(
            username="warehouse",
            password_hash=auth_mod.pwd_context.hash("warehouse123"),
            full_name="Сидорова Мария Петровна",
            role="warehouse",
            department_id=depts[3].id,
            avatar_color="#8b5cf6",
            is_active=True,
        ),
        UserDB(
            username="employee",
            password_hash=auth_mod.pwd_context.hash("employee123"),
            full_name="Тестов Тимур Павлович",
            role="employee",
            department_id=depts[1].id,
            avatar_color="#6b7280",
            is_active=True,
        ),
    ]
    session.add_all(users)
    session.commit()


@pytest.fixture(scope="function")
def db_engine():
    eng = _make_test_engine()
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

    _seed_test_data(test_sl())

    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin_token(client):
    resp = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def admin_headers(admin_token):
    return {"X-Auth-Token": admin_token}


def make_user(client, token, username="testuser", password="test123", full_name="Test User", role="employee", department_id=None):
    headers = {"X-Auth-Token": token, "Content-Type": "application/json"}
    data = {"username": username, "password": password, "full_name": full_name, "role": role}
    if department_id:
        data["department_id"] = department_id
    return client.post("/auth/register", json=data, headers=headers)


class FakeEmbedder:
    def __init__(self, dim=8):
        self.dim = dim

    def encode(self, texts, **kwargs):
        if isinstance(texts, str):
            return self._hash_vec(texts)
        return [self._hash_vec(t) for t in texts]

    def _hash_vec(self, text):
        import numpy as np
        vec = np.zeros(self.dim)
        for i, ch in enumerate(text):
            vec[i % self.dim] += ord(ch)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec


@pytest.fixture
def fake_embedder():
    return FakeEmbedder()
