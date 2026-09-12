import pytest
from tests.conftest import make_user


class TestAuthLogin:
    def test_login_success(self, client):
        resp = client.post("/auth/login", json={"username": "admin", "password": "admin"})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["user"]["username"] == "admin"
        assert data["user"]["role"] == "admin"

    def test_login_wrong_password(self, client):
        resp = client.post("/auth/login", json={"username": "admin", "password": "wrong"})
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client):
        resp = client.post("/auth/login", json={"username": "nobody", "password": "x"})
        assert resp.status_code == 401


class TestAuthMe:
    def test_get_me(self, client, admin_headers):
        resp = client.get("/auth/me", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["username"] == "admin"

    def test_get_me_no_token(self, client):
        resp = client.get("/auth/me")
        assert resp.status_code == 401

    def test_get_me_invalid_token(self, client):
        resp = client.get("/auth/me", headers={"X-Auth-Token": "invalid"})
        assert resp.status_code == 401


class TestUserCRUD:
    def test_register_user(self, client, admin_token):
        resp = make_user(client, admin_token, username="newuser", role="employee")
        assert resp.status_code == 200
        assert resp.json()["username"] == "newuser"

    def test_register_duplicate_username(self, client, admin_token):
        make_user(client, admin_token, username="dup1")
        resp = make_user(client, admin_token, username="dup1")
        assert resp.status_code == 400

    def test_register_requires_admin(self, client, admin_token):
        make_user(client, admin_token, username="emp1", role="employee")
        emp_resp = client.post("/auth/login", json={"username": "emp1", "password": "test123"})
        emp_token = emp_resp.json()["access_token"]
        resp = make_user(client, emp_token, username="emp2")
        assert resp.status_code == 403

    def test_list_users_admin(self, client, admin_headers):
        resp = client.get("/auth/users", headers=admin_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert len(resp.json()) >= 1

    def test_delete_user(self, client, admin_token, admin_headers):
        reg = make_user(client, admin_token, username="todelete")
        uid = reg.json()["id"]
        resp = client.delete(f"/auth/users/{uid}", headers=admin_headers)
        assert resp.status_code == 200


class TestDepartments:
    def test_list_departments(self, client, admin_headers):
        resp = client.get("/departments", headers=admin_headers)
        assert resp.status_code == 200

    def test_create_department(self, client, admin_headers):
        resp = client.post("/departments", json={"name": "Тестовый отдел"}, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Тестовый отдел"

    def test_create_department_requires_admin(self, client, admin_token):
        make_user(client, admin_token, username="emp2", role="employee")
        emp_tok = client.post("/auth/login", json={"username": "emp2", "password": "test123"}).json()["access_token"]
        resp = client.post("/departments", json={"name": "Nope"}, headers={"X-Auth-Token": emp_tok})
        assert resp.status_code == 403


class TestPasswordSecurity:
    def test_no_hardcoded_admin_bypass(self, client):
        # Admin is seeded with hash of "admin" in conftest.
        # Previously, "admin123" was allowed as hardcoded bypass.
        # Now, only exact hash match must succeed.
        resp_bypass = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
        assert resp_bypass.status_code == 401

        resp_exact = client.post("/auth/login", json={"username": "admin", "password": "admin"})
        assert resp_exact.status_code == 200

    def test_change_password_flow(self, client, admin_headers):
        resp = client.post(
            "/auth/change-password",
            json={"old_password": "admin", "new_password": "NewAdminPass2026!"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        # Old password must now fail
        resp_old = client.post("/auth/login", json={"username": "admin", "password": "admin"})
        assert resp_old.status_code == 401

        # New password must succeed
        resp_new = client.post("/auth/login", json={"username": "admin", "password": "NewAdminPass2026!"})
        assert resp_new.status_code == 200
