import pytest
from unittest.mock import patch, AsyncMock


class TestChatEndpoint:
    @pytest.mark.asyncio
    async def test_chat_requires_auth(self, client):
        resp = client.post("/chat", json={"messages": [{"role": "user", "text": "Привет"}]})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_chat_with_auth(self, client, admin_headers):
        mock_response = {"text": "Привет! Чем могу помочь?", "action": None, "data": None}
        with patch("app.services.llm_service.llm_service.generate_response", new_callable=AsyncMock, return_value=mock_response):
            resp = client.post("/chat", json={"messages": [{"role": "user", "text": "Привет"}]}, headers=admin_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["text"] == "Привет! Чем могу помочь?"
            assert data["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_chat_creates_kanban_task(self, client, admin_headers):
        mock_response = {
            "text": "Создаю задачу",
            "action": "create_kanban_task",
            "data": {"title": "Подготовить отчёт", "column": "todo", "priority": "high"},
        }
        with patch("app.services.llm_service.llm_service.generate_response", new_callable=AsyncMock, return_value=mock_response):
            resp = client.post("/chat", json={"messages": [{"role": "user", "text": "Создай задачу"}]}, headers=admin_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert "task_id" in data.get("data", {})


class TestUpdateMetadata:
    def test_update_metadata_requires_admin(self, client, admin_headers):
        resp = client.post("/update_metadata", json={"items": []}, headers=admin_headers)
        assert resp.status_code == 200

    def test_update_metadata_no_auth(self, client):
        resp = client.post("/update_metadata", json={"items": []})
        assert resp.status_code == 401
