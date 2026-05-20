import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.services.auth_service as auth_mod
import app.services.kanban_service as kanban_mod
from app.services.auth_service import UserDB, DepartmentDB

TEST_JWT_SECRET = "test-secret-key-for-pytest"


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
