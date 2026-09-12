"""Unverified senders and webhook configuration must fail closed."""

from unittest.mock import AsyncMock

import pytest


def test_internal_exception_detail_is_not_exposed(client, admin_headers, monkeypatch, caplog):
    import main

    monkeypatch.setattr(main.llm_service, "generate_response", AsyncMock(side_effect=RuntimeError("private-diagnostic-marker")))
    response = client.post("/chat", headers=admin_headers,
        json={"messages": [{"role": "user", "text": "test"}]})
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "private-diagnostic-marker" not in caplog.text


@pytest.mark.parametrize("name", ["admin", "director", "Директор", "Email_director@example.test"])
@pytest.mark.asyncio
async def test_sender_name_does_not_grant_financial_access(client, monkeypatch, name):
    from main import _internal_bot_chat_handler
    from app.services.omnichannel_formatter import omnichannel_formatter

    def unexpected_access(*args, **kwargs):
        pytest.fail("Unverified sender reached financial formatter")

    monkeypatch.setattr(omnichannel_formatter, "format_balance", unexpected_access)
    answer = await _internal_bot_chat_handler("/balance", name)
    assert "Доступ ограничен" in answer


@pytest.mark.parametrize("channel", ["telegram", "vk"])
@pytest.mark.parametrize("secret_state", ["missing", "wrong", "valid"])
def test_webhooks_validate_configuration_before_dispatch(client, monkeypatch, channel, secret_state):
    import main

    if channel == "telegram":
        endpoint = "/integrations/telegram/webhook"
        setting = "TELEGRAM_WEBHOOK_SECRET"
        service, method = main.telegram_bot_service, "process_webhook_update"
        payload = {"update_id": 1}
        headers = {"X-Telegram-Bot-Api-Secret-Token": "test-webhook-secret"}
    else:
        endpoint = "/integrations/vk/callback"
        setting = "VK_SECRET_KEY"
        service, method = main.vk_bot_service, "process_callback_update"
        payload = {"type": "message_new", "secret": "test-webhook-secret"}
        headers = {}
    dispatch = AsyncMock(return_value={"status": "ok"})
    monkeypatch.setattr(service, method, dispatch)
    monkeypatch.setenv(setting, {"missing": "", "wrong": "different-secret", "valid": "test-webhook-secret"}[secret_state])
    response = client.post(endpoint, json=payload, headers=headers)
    assert response.status_code == {"missing": 503, "wrong": 403, "valid": 200}[secret_state]
    if secret_state == "valid":
        dispatch.assert_awaited_once()
    else:
        dispatch.assert_not_awaited()
