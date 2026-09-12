import pytest
from tests.conftest import make_user


class TestRBACSecurityMatrix:
    """Проверка матричной модели разграничения прав доступа (RBAC) в 1С:УНФ"""

    def test_roles_seed_and_login(self, client):
        """Проверяем, что все ключевые роли могут успешно аутентифицироваться"""
        credentials = [
            ("director", "director123", "director"),
            ("cfo", "cfo123", "cfo"),
            ("manager", "manager123", "manager"),
            ("warehouse", "warehouse123", "warehouse"),
            ("employee", "employee123", "employee"),
            ("admin", "admin", "admin"),
        ]
        for username, password, expected_role in credentials:
            resp = client.post("/auth/login", json={"username": username, "password": password})
            assert resp.status_code == 200, f"Login failed for {username}"
            data = resp.json()
            assert data["user"]["role"] == expected_role
            assert "access_token" in data

    def test_financial_monitor_access_control(self, client):
        """
        Финансовый монитор (касса 69.8M, кассовые разрывы, кредиторы):
        - Анонимный доступ -> 401 Unauthorized
        - Сотрудник, Кладовщик, Менеджер -> 403 Forbidden
        - Директор, Финдиректор (CFO), Админ -> 200 OK
        """
        # 1. Анонимный
        anon_resp = client.get("/analytics/monitor")
        assert anon_resp.status_code == 401

        # 2. Менеджер (не имеет права на финансы)
        m_tok = client.post("/auth/login", json={"username": "manager", "password": "manager123"}).json()["access_token"]
        m_resp = client.get("/analytics/monitor", headers={"X-Auth-Token": m_tok})
        assert m_resp.status_code == 403

        # 3. Кладовщик
        w_tok = client.post("/auth/login", json={"username": "warehouse", "password": "warehouse123"}).json()["access_token"]
        w_resp = client.get("/analytics/monitor", headers={"X-Auth-Token": w_tok})
        assert w_resp.status_code == 403

        # 4. Рядовой сотрудник
        e_tok = client.post("/auth/login", json={"username": "employee", "password": "employee123"}).json()["access_token"]
        e_resp = client.get("/analytics/monitor", headers={"X-Auth-Token": e_tok})
        assert e_resp.status_code == 403

        # 5. Генеральный директор (полный доступ)
        d_tok = client.post("/auth/login", json={"username": "director", "password": "director123"}).json()["access_token"]
        d_resp = client.get("/analytics/monitor", headers={"X-Auth-Token": d_tok})
        assert d_resp.status_code == 200
        d_data = d_resp.json()
        assert d_data["kpi"]["cash_balance"] > 0
        assert "creditors" in d_data

        # 6. Финансовый директор (CFO) (полный доступ)
        cfo_tok = client.post("/auth/login", json={"username": "cfo", "password": "cfo123"}).json()["access_token"]
        cfo_resp = client.get("/analytics/monitor", headers={"Authorization": f"Bearer {cfo_tok}"})
        assert cfo_resp.status_code == 200
        assert cfo_resp.json()["kpi"]["cash_balance"] > 0

    def test_executive_email_endpoints_rbac(self, client):
        """Проверка защиты отправки дайджестов и претензий должникам"""
        e_tok = client.post("/auth/login", json={"username": "employee", "password": "employee123"}).json()["access_token"]
        d_tok = client.post("/auth/login", json={"username": "director", "password": "director123"}).json()["access_token"]

        # Сотрудник блокируется от генерации утреннего дайджеста
        resp_emp_digest = client.post("/integrations/email/digest", json={}, headers={"X-Auth-Token": e_tok})
        assert resp_emp_digest.status_code == 403

        # Директор формирует дайджест
        resp_dir_digest = client.post("/integrations/email/digest", json={}, headers={"X-Auth-Token": d_tok})
        assert resp_dir_digest.status_code == 200

        # Сотрудник блокируется от отправки претензий
        resp_emp_claim = client.post("/integrations/email/claim", json={"to": "test@test.ru"}, headers={"X-Auth-Token": e_tok})
        assert resp_emp_claim.status_code == 403

    def test_chat_financial_leak_prevention(self, client):
        """
        Проверка защиты от утечек коммерческой тайны через диалог с ИИ:
        Рядовой сотрудник при попытке запросить кассовый разрыв или остатки денег
        получает отказ со ссылкой на политику безопасности 1С:УНФ.
        """
        e_tok = client.post("/auth/login", json={"username": "employee", "password": "employee123"}).json()["access_token"]
        d_tok = client.post("/auth/login", json={"username": "director", "password": "director123"}).json()["access_token"]

        # Сотрудник спрашивает про кассовый разрыв
        emp_chat = client.post("/chat", json={"messages": [{"role": "user", "text": "какой у нас кассовый разрыв?"}]}, headers={"X-Auth-Token": e_tok})
        assert emp_chat.status_code == 200
        assert emp_chat.json()["action"] == "access_denied"
        assert "политикой безопасности" in emp_chat.json()["text"]

        # Директор спрашивает про кассовый разрыв
        dir_chat = client.post("/chat", json={"messages": [{"role": "user", "text": "какой у нас кассовый разрыв?"}]}, headers={"X-Auth-Token": d_tok})
        assert dir_chat.status_code == 200
        assert dir_chat.json()["action"] == "cash_gap_forecast"

    def test_costly_endpoints_require_authentication(self, client):
        """Эндпоинты, расходующие внешние квоты или пишущие в Канбан, закрыты от анонимов.

        Регрессия: /integrations/email/incoming, /voice/transcribe и /qr/generate
        были доступны без токена — любой запрос создавал задачу в Канбане
        и расходовал квоту LLM/распознавания.
        """
        # Email-to-Order: аноним не может создавать задачи в Канбане
        resp_email = client.post(
            "/integrations/email/incoming",
            json={"sender": "attacker@example.com", "subject": "spam", "body": "spam"},
        )
        assert resp_email.status_code in (401, 403)

        # Распознавание речи расходует квоту внешнего провайдера
        resp_voice = client.post("/voice/transcribe", json={"audio_base64": "", "format": "webm"})
        assert resp_voice.status_code == 401

        # Генерация QR
        resp_qr = client.get("/qr/generate?text=TEST")
        assert resp_qr.status_code == 401

    def test_email_ingestion_allows_authenticated_user(self, client, monkeypatch):
        """Закрытие эндпоинта не должно ломать штатный сценарий Email-to-Order."""

        async def stub_process(sender, subject, body, chat_handler):
            return {"status": "ok", "sender": sender}

        import app.services.email_service as email_mod
        monkeypatch.setattr(email_mod.email_service, "process_incoming_email", stub_process)

        d_tok = client.post(
            "/auth/login", json={"username": "director", "password": "director123"}
        ).json()["access_token"]
        resp = client.post(
            "/integrations/email/incoming",
            json={"sender": "client@alfatrade.ru", "subject": "Заказ", "body": "Кабель 50м"},
            headers={"X-Auth-Token": d_tok},
        )
        assert resp.status_code == 200


class TestOmnichannelSimulation:
    """Регрессия на отладочные маршруты /simulate.

    Обе симуляции подменяли `send_message` заглушкой с сигнатурой, не совпадающей
    с боевой: VK-путь падал с TypeError на `with_keyboard=False`, а обработчик
    объявлял `ch=`, тогда как сервис вызывает его с `channel=`. В нагрузочном
    прогоне это давало нулевую успешность канала VK.
    """

    def _manager_headers(self, client):
        tok = client.post(
            "/auth/login", json={"username": "manager", "password": "manager123"}
        ).json()["access_token"]
        return {"X-Auth-Token": tok}

    def test_vk_simulate_returns_messages(self, client):
        resp = client.post(
            "/integrations/vk/simulate",
            json={"text": "Покажи канбан", "user_id": 20001},
            headers=self._manager_headers(client),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["channel"] == "vk"
        assert len(data["messages"]) >= 1

    def test_telegram_simulate_returns_messages(self, client):
        resp = client.post(
            "/integrations/telegram/simulate",
            json={"text": "/start", "user_name": "Client_1"},
            headers=self._manager_headers(client),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["channel"] == "telegram"
        assert len(data["messages"]) >= 1

    def test_vk_simulate_requires_authorized_role(self, client):
        e_tok = client.post(
            "/auth/login", json={"username": "employee", "password": "employee123"}
        ).json()["access_token"]
        resp = client.post(
            "/integrations/vk/simulate",
            json={"text": "Покажи канбан", "user_id": 20001},
            headers={"X-Auth-Token": e_tok},
        )
        assert resp.status_code == 403
