"""Тесты post-processing действий в LLMService.

Покрывают: пост-обработку канбан-маркеров, не-срабатывание на посторонних запросах.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm_service import LLMService


def _make_mock_llm_response(action: str, text: str = "Ответ", data: dict | None = None):
    """Создать mock-объект, имитирующий ответ OpenAI API с заданным JSON."""
    payload = json.dumps({"text": text, "action": action, "data": data}, ensure_ascii=False)
    mock_choice = MagicMock()
    mock_choice.message.content = payload
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    return mock_completion


def _make_messages(text: str) -> list:
    """Создать список сообщений с одним пользовательским."""
    msg = MagicMock()
    msg.role = "user"
    msg.text = text
    return [msg]


@pytest.fixture
def llm(monkeypatch):
    """LLMService с мокнутым API-клиентом и RAG."""
    svc = LLMService()
    monkeypatch.setattr(svc, "client", MagicMock())
    monkeypatch.setattr(
        "app.services.llm_service.metadata_service.find_top_matches",
        lambda *a, **kw: [],
    )
    return svc


class TestKanbanPostProcessing:
    @pytest.mark.asyncio
    async def test_kanban_show_post_processing(self, llm):
        llm.client.chat.completions.create.return_value = _make_mock_llm_response(
            "expert_answer", "Канбан", None,
        )
        result = await llm.generate_response(
            _make_messages("Покажи доску канбан"),
        )
        assert result["action"] == "show_kanban"

    @pytest.mark.asyncio
    async def test_kanban_create_post_processing(self, llm):
        llm.client.chat.completions.create.return_value = _make_mock_llm_response(
            "expert_answer", "Задача", None,
        )
        result = await llm.generate_response(
            _make_messages("Создай задачу по подготовке отчёта"),
        )
        assert result["action"] == "create_kanban_task"

    @pytest.mark.asyncio
    async def test_non_expert_answer_not_rewritten(self, llm):
        llm.client.chat.completions.create.return_value = _make_mock_llm_response(
            "create_kanban_task", "Задача", {"title": "test"},
        )
        result = await llm.generate_response(
            _make_messages("Добавь задачу срочно"),
        )
        assert result["action"] == "create_kanban_task"

    @pytest.mark.asyncio
    async def test_expert_answer_stays(self, llm):
        llm.client.chat.completions.create.return_value = _make_mock_llm_response(
            "expert_answer", "Консультация", None,
        )
        result = await llm.generate_response(
            _make_messages("Как оформить возврат?"),
        )
        assert result["action"] == "expert_answer"
