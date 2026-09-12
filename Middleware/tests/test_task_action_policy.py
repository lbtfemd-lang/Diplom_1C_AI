"""Cross-route visibility and untrusted model output regression tests."""
import pytest
from app.services.kanban_service import kanban_service
from app.services.llm_service import llm_service


@pytest.mark.parametrize("role", ["employee", "manager", "warehouse"])
def test_foreign_task_hidden_on_all_routes(client, role):
    token = client.post("/auth/login", json={"username": role, "password": role + "123"}).json()["access_token"]
    headers = {"X-Auth-Token": token}
    task = kanban_service.create_task(title="restricted marker", department_id=6,
                                      assignee="cfo", created_by="cfo")
    task_id = task["id"]
    assert client.get("/kanban/tasks", headers=headers).json() == []
    assert client.get("/kanban/board", headers=headers).json()["tasks"] == []
    assert client.get("/kanban/stats", headers=headers).json()["total"] == 0
    assert client.get("/kanban/notifications", headers=headers).json() == []
    assert "restricted marker" not in client.get("/kanban/tasks/export", headers=headers).text
    assert client.get(f"/kanban/tasks/{task_id}", headers=headers).status_code == 403
    assert client.put(f"/kanban/tasks/{task_id}", headers=headers, json={"title": "changed"}).status_code == 403
    assert client.post("/kanban/tasks/move", headers=headers, json={"task_id": task_id, "column": "done"}).status_code == 403
    assert client.delete(f"/kanban/tasks/{task_id}", headers=headers).status_code == 403
    assert kanban_service.get_task(task_id)["title"] == "restricted marker"


@pytest.mark.parametrize("role", ["manager", "warehouse", "service_bridge", "unknown"])
def test_no_department_is_not_global_access(client, role):
    kanban_service.create_task(title="foreign", created_by="cfo")
    assert kanban_service.get_tasks_for_user(999, role, username="unassigned") == []
    assert kanban_service.get_stats(999, role, username="unassigned")["total"] == 0


def test_employee_cannot_transfer_own_task(client):
    token = client.post("/auth/login", json={"username": "employee", "password": "employee123"}).json()["access_token"]
    headers = {"X-Auth-Token": token}
    task = client.post("/kanban/tasks", headers=headers, json={"title": "own"}).json()
    assert client.get(f"/kanban/tasks/{task['id']}", headers=headers).status_code == 200
    assert client.put(f"/kanban/tasks/{task['id']}", headers=headers, json={"assignee": "director"}).status_code == 403
    assert client.post("/kanban/tasks", headers=headers, json={"title": "foreign dept", "department_id": 6}).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role,action", [
    ("employee", "get_cash_balance"), ("manager", "get_creditors"),
    ("warehouse", "cash_gap_forecast"), ("service_bridge", "get_debtors"),
    ("employee", "create_procurement_order"), ("admin", "delete_database"),
])
async def test_model_cannot_grant_itself_permission(monkeypatch, role, action):
    async def malicious(*args, **kwargs):
        return {"text": "sensitive marker", "action": action, "data": {"secret": "marker"}}
    monkeypatch.setattr(llm_service, "_generate_message", malicious)
    result = await llm_service.generate_response([], user_role=role)
    assert result["action"] == "access_denied"
    assert result["data"] is None
    assert "marker" not in str(result)


@pytest.mark.parametrize("role,action", [("cfo", "get_cash_balance"), ("manager", "parse_order_text"), ("warehouse", "get_stock")])
def test_allowed_actions_preserved(role, action):
    response = {"text": "ok", "action": action, "data": {}}
    assert llm_service.authorize_response(response, role) == response


@pytest.mark.parametrize("response", [[], {"text": "x", "action": []}, {"text": "x", "action": "get_stock", "data": []}])
def test_malformed_output_fails_closed(response):
    assert llm_service.authorize_response(response, "admin")["action"] == "access_denied"


def test_seed_preserves_revoked_role(client, admin_headers):
    from app.services.auth_service import auth_service
    director = auth_service.get_user_by_username("director")
    response = client.put(f"/auth/users/{director['id']}", headers=admin_headers,
                          json={"role": "employee", "is_active": False})
    assert response.status_code == 200
    auth_service._seed_default_users()
    updated = auth_service.get_user_by_username("director")
    assert updated["role"] == "employee"
    assert updated["is_active"] is False
