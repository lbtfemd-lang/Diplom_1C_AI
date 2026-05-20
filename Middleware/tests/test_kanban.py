import pytest
from tests.conftest import make_user


class TestKanbanBoard:
    def test_get_board(self, client, admin_headers):
        resp = client.get("/kanban/board", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "tasks" in data
        assert "columns" in data

    def test_create_task(self, client, admin_headers):
        resp = client.post("/kanban/tasks", json={
            "title": "Тестовая задача",
            "column": "todo",
            "priority": "medium",
        }, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["title"] == "Тестовая задача"

    def test_get_task(self, client, admin_headers):
        create = client.post("/kanban/tasks", json={
            "title": "Найти задачу",
            "column": "todo",
            "priority": "high",
        }, headers=admin_headers)
        tid = create.json()["id"]
        resp = client.get(f"/kanban/tasks/{tid}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["title"] == "Найти задачу"

    def test_update_task(self, client, admin_headers):
        create = client.post("/kanban/tasks", json={
            "title": "Обновить меня",
            "column": "todo",
            "priority": "low",
        }, headers=admin_headers)
        tid = create.json()["id"]
        resp = client.put(f"/kanban/tasks/{tid}", json={
            "title": "Обновлено",
            "priority": "high",
        }, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["title"] == "Обновлено"
        assert resp.json()["priority"] == "high"

    def test_move_task(self, client, admin_headers):
        create = client.post("/kanban/tasks", json={
            "title": "Переместить",
            "column": "todo",
            "priority": "medium",
        }, headers=admin_headers)
        tid = create.json()["id"]
        resp = client.post("/kanban/tasks/move", json={
            "task_id": tid,
            "column": "in_progress",
        }, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["column"] == "in_progress"

    def test_delete_task(self, client, admin_headers):
        create = client.post("/kanban/tasks", json={
            "title": "Удалить",
            "column": "todo",
            "priority": "medium",
        }, headers=admin_headers)
        tid = create.json()["id"]
        resp = client.delete(f"/kanban/tasks/{tid}", headers=admin_headers)
        assert resp.status_code == 200

    def test_employee_can_only_see_own_tasks(self, client, admin_token, admin_headers):
        make_user(client, admin_token, username="emp3", role="employee")
        emp_tok = client.post("/auth/login", json={"username": "emp3", "password": "test123"}).json()["access_token"]
        emp_h = {"X-Auth-Token": emp_tok}

        client.post("/kanban/tasks", json={"title": "Чужая", "column": "todo", "priority": "medium", "assignee": "admin"}, headers=admin_headers)
        client.post("/kanban/tasks", json={"title": "Моя", "column": "todo", "priority": "medium", "assignee": "emp3"}, headers=admin_headers)

        board = client.get("/kanban/board", headers=emp_h).json()
        titles = [t["title"] for t in board["tasks"]]
        assert "Моя" in titles
        assert "Чужая" not in titles


class TestKanbanStats:
    def test_stats(self, client, admin_headers):
        client.post("/kanban/tasks", json={"title": "S1", "column": "todo", "priority": "medium"}, headers=admin_headers)
        resp = client.get("/kanban/stats", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert data["total"] >= 1


class TestKanbanNotifications:
    def test_notifications(self, client, admin_headers):
        resp = client.get("/kanban/notifications", headers=admin_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestKanbanExport:
    def test_csv_export(self, client, admin_headers):
        client.post("/kanban/tasks", json={"title": "CSV Export", "column": "todo", "priority": "medium"}, headers=admin_headers)
        resp = client.get("/kanban/tasks/export", headers=admin_headers)
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
