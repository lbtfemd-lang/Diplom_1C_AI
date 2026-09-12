import os
import json
import logging
import random
import asyncio
from typing import Dict, Any, Optional
import httpx
from dotenv import load_dotenv

load_dotenv()

# Fix Windows httpx NO_PROXY issue with IPv6
if "NO_PROXY" in os.environ and "::" in os.environ["NO_PROXY"]:
    os.environ["NO_PROXY"] = ",".join([p for p in os.environ["NO_PROXY"].split(",") if "::" not in p])

logger = logging.getLogger(__name__)


class VkBotService:
    def __init__(self):
        self.confirmation_code = os.getenv("VK_CONFIRMATION_CODE", "1c_ai_assistant_vk")
        self.api_version = "5.131"
        self.api_base = "https://api.vk.com/method"
        self._is_polling = False

    @property
    def access_token(self) -> str:
        return os.getenv("VK_GROUP_TOKEN", "")

    @property
    def group_id(self) -> str:
        return os.getenv("VK_GROUP_ID", "")

    def _get_bind_ip(self) -> Optional[str]:
        ip = os.getenv("VK_BIND_IP", "").strip()
        if ip:
            return ip
        try:
            import subprocess
            cmd = ["powershell", "-NoProfile", "-Command", "Get-NetIPAddress -InterfaceAlias 'Ethernet*' -AddressFamily IPv4 | Select-Object -ExpandProperty IPAddress"]
            out = subprocess.check_output(cmd, text=True, timeout=3).strip()
            if out and "." in out:
                return out.split()[0]
        except Exception as exc:
            logger.debug("VK local address detection failed (%s)", type(exc).__name__)
        return None

    def _create_client(self, timeout: float = 35.0) -> httpx.AsyncClient:
        bind_ip = self._get_bind_ip()
        transport = httpx.AsyncHTTPTransport(local_address=bind_ip) if bind_ip else None
        return httpx.AsyncClient(transport=transport, timeout=timeout)

    async def start_polling(self, chat_handler):
        """Запуск VK Bots Long Poll для работы без вебхуков с экспоненциальным backoff"""
        if not self.access_token or not self.group_id:
            logger.info("VK_GROUP_TOKEN или VK_GROUP_ID не заданы. VK Long Poll отключен.")
            return

        self._is_polling = True
        logger.info("🚀 Запущен VK Bot Long Poll (Group ID: %s, Bind IP: %s)", self.group_id, self._get_bind_ip())

        backoff = 5
        async with self._create_client(timeout=35.0) as client:
            while self._is_polling:
                try:
                    # Получение сервера Long Poll
                    lp_params = {
                        "group_id": self.group_id,
                        "access_token": self.access_token,
                        "v": self.api_version
                    }
                    lp_resp = await client.get(f"{self.api_base}/groups.getLongPollServer", params=lp_params)
                    lp_data = lp_resp.json().get("response", {})
                    server = lp_data.get("server")
                    key = lp_data.get("key")
                    ts = lp_data.get("ts")

                    if not server or not key or not ts:
                        logger.warning("Не удалось получить VK Long Poll Server (ответ: %s). Пауза %d сек...", lp_resp.json(), backoff)
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 2, 60)
                        continue

                    backoff = 10
                    logger.info("✅ VK Bot Long Poll подключен к серверу сообщений VK")

                    while self._is_polling:
                        poll_url = f"{server}?act=a_check&key={key}&ts={ts}&wait=25"
                        poll_resp = await client.get(poll_url)
                        res = poll_resp.json()
                        if "failed" in res:
                            break  # Need to re-fetch key/ts
                        ts = res.get("ts", ts)
                        for update in res.get("updates", []):
                            asyncio.create_task(self.process_callback_update(update, chat_handler))
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.warning("VK polling pause due to network/rate-limit (%s). Повтор через %d сек...", e, backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60)

    def stop_polling(self):
        self._is_polling = False

    async def process_callback_update(self, data: Dict[str, Any], chat_handler) -> Dict[str, Any]:
        """
        Process VK Callback API update.
        """
        req_type = data.get("type")
        if req_type == "confirmation":
            return {"response": self.confirmation_code}

        if req_type == "message_new":
            obj = data.get("object", {}).get("message", {})
            user_id = obj.get("from_id")
            text = obj.get("text", "").strip()

            # 1. Распознавание голосовых сообщений VK
            if not text and obj.get("attachments"):
                for att in obj["attachments"]:
                    att_type = att.get("type")
                    if att_type in ("audio_message", "audiomsg"):
                        audio_info = att.get(att_type, {})
                        # Проверка встроенного распознавания VK
                        transcript = audio_info.get("transcript")
                        if transcript:
                            text = transcript
                            logger.info("VK Voice transcription from VK API: %s", text)
                            await self.send_message(user_id, f"🎙 Распознано: «{text}»", with_keyboard=False)
                            break

                        # Скачивание аудиофайла и распознавание через voice_service
                        ogg_url = audio_info.get("link_ogg") or audio_info.get("link_mp3")
                        if ogg_url:
                            try:
                                await self.send_message(user_id, "🎙 Распознаю голосовое сообщение...", with_keyboard=False)
                                async with self._create_client(timeout=15.0) as dl_client:
                                    audio_resp = await dl_client.get(ogg_url)
                                if audio_resp.status_code == 200:
                                    import base64
                                    from app.services.voice_service import voice_service
                                    audio_b64 = base64.b64encode(audio_resp.content).decode("ascii")
                                    v_res = await voice_service.transcribe_audio(audio_b64, audio_format="ogg")
                                    text = v_res.get("text", "").strip()
                                    if text:
                                        logger.info("VK Voice transcribed via voice_service: %s", text)
                                        await self.send_message(user_id, f"🎙 Распознано: «{text}»", with_keyboard=False)
                                        break
                            except Exception as e:
                                logger.warning("Failed to transcribe VK voice message: %s", e)

            # 2. Обработка payload интерактивных кнопок VK
            payload = obj.get("payload")
            if payload:
                try:
                    p_data = json.loads(payload) if isinstance(payload, str) else payload
                    cmd = p_data.get("cmd")
                    if cmd:
                        cmd_map = {
                            "gap": "разрыв",
                            "money": "деньги",
                            "orders": "заказы",
                            "stock": "неликвиды",
                            "debts": "должники",
                            "tasks": "канбан",
                            "new_task": "новая задача",
                            "help": "справка"
                        }
                        text = cmd_map.get(cmd, text)
                except Exception as exc:
                    logger.warning("VK command payload ignored (%s)", type(exc).__name__)

            if text and user_id:
                t_lower = text.lower()

                # Меню и Справка
                if any(w in t_lower for w in ("начать", "start", "/start", "меню", "/menu", "кнопки")):
                    welcome = (
                        "👋 Здравствуйте!\n\n"
                        "Я интеллектуальный ИИ-ассистент системы «1С:Управление нашей фирмой 3.0».\n\n"
                        "📌 Выберите раздел на клавиатуре или напишите вопрос в свободной форме (например: «Выстави счет АльфаМарт на 50м кабеля»)."
                    )
                    await self.send_message(user_id, welcome)

                elif any(w in t_lower for w in ("справка", "/help", "помощь")):
                    help_msg = (
                        "📖 СПРАВОЧНИК КОМАНД И ВОЗМОЖНОСТЕЙ • 1С:УНФ\n"
                        "──────────────────────────────────────\n\n"
                        "💰 ФИНАНСЫ И ЛИКВИДНОСТЬ:\n"
                        "▪️ «Разрыв» — прогноз кассового разрыва на 7 дней\n"
                        "▪️ «Деньги» — остатки на счетах (Сбер, ВТБ) и в кассе\n"
                        "▪️ «Кредиторы» — задолженность перед поставщиками\n\n"
                        "📦 СКЛАД И ЗАКАЗЫ:\n"
                        "▪️ «Заказы» — сорванные и зависшие отгрузки покупателей\n"
                        "▪️ «Неликвиды» — товары без движения более 90 дней\n"
                        "▪️ «Продажи» — помесячная динамика выручки компании\n\n"
                        "👥 ЗАДАЧИ И ДЕБИТОРКА:\n"
                        "▪️ «Должники» — просроченная задолженность клиентов\n"
                        "▪️ «Канбан» — поручения руководства по колонкам\n"
                        "▪️ «Новая задача <текст>» — создание поручения в 1С\n\n"
                        "──────────────────────────────────────\n"
                        "💡 Подсказка: Вы можете нажимать кнопки клавиатуры или отправлять голосовые сообщения."
                    )
                    await self.send_message(user_id, help_msg)

                # Финансы
                elif any(w in t_lower for w in ("разрыв", "кассовый разрыв", "/gap")):
                    await self.send_message(user_id, "⏳ Формирую расчет кассовых разрывов по регистрам 1С...", with_keyboard=False)
                    res = await chat_handler("Сформируй прогноз кассовых разрывов на ближайшие 7 дней", f"VK_{user_id}", channel="vk")
                    await self.send_message(user_id, self._clean_text_for_vk(res))

                elif any(w in t_lower for w in ("деньги", "баланс", "остатки", "/balance")):
                    res = await chat_handler("Покажи остаток денег на счетах и в кассах", f"VK_{user_id}", channel="vk")
                    await self.send_message(user_id, self._clean_text_for_vk(res))

                elif any(w in t_lower for w in ("кредиторы", "долги наши", "/creditors")):
                    res = await chat_handler("Какова наша кредиторская задолженность перед поставщиками?", f"VK_{user_id}", channel="vk")
                    await self.send_message(user_id, self._clean_text_for_vk(res))

                # Заказы и Склад
                elif any(w in t_lower for w in ("заказы", "сорванные заказы", "/orders")):
                    res = await chat_handler("Проведи аудит сорванных и зависших заказов покупателей", f"VK_{user_id}", channel="vk")
                    await self.send_message(user_id, self._clean_text_for_vk(res))

                elif any(w in t_lower for w in ("продажи", "динамика продаж", "/sales")):
                    res = await chat_handler("Покажи динамику продаж за последний месяц", f"VK_{user_id}", channel="vk")
                    await self.send_message(user_id, self._clean_text_for_vk(res))

                elif any(w in t_lower for w in ("неликвиды", "склад", "/stock")):
                    res = await chat_handler("Проведи аудит складских неликвидов более 90 дней", f"VK_{user_id}", channel="vk")
                    await self.send_message(user_id, self._clean_text_for_vk(res))

                elif any(w in t_lower for w in ("поставщики", "цены", "/suppliers")):
                    res = await chat_handler("Сравни закупочные цены поставщиков по номенклатуре", f"VK_{user_id}", channel="vk")
                    await self.send_message(user_id, self._clean_text_for_vk(res))

                # Дебиторка
                elif any(w in t_lower for w in ("должники", "дебиторы", "/debts", "дебиторка")):
                    res = await chat_handler("Подготовь список должников и письма", f"VK_{user_id}", channel="vk")
                    await self.send_message(user_id, self._clean_text_for_vk(res))

                # Канбан
                elif any(w in t_lower for w in ("канбан", "задачи", "/tasks")):
                    from app.services.kanban_service import kanban_service
                    from app.services.omnichannel_formatter import omnichannel_formatter
                    tasks = kanban_service.get_all_tasks()
                    msg = omnichannel_formatter.format_kanban_tasks(tasks, channel="vk")
                    await self.send_message(user_id, msg)

                elif t_lower.startswith("новая задача") or t_lower.startswith("/new_task"):
                    task_text = text[12:].lstrip(",: -").strip() or "Поручение из VK"
                    from app.services.kanban_service import kanban_service
                    created = kanban_service.create_task(
                        title=task_text,
                        description=f"Создано через ВКонтакте (ID пользователя: {user_id})",
                        column="todo",
                        priority="high",
                        assignee="Абдулов (директор)",
                        source="chat"
                    )
                    confirm_msg = (
                        f"✅ Задача #{created.get('id')} успешно создана на Канбан-доске 1С:УНФ!\n"
                        f"──────────────────────────────────────\n"
                        f"📌 Наименование: {created.get('title')}\n"
                        f"📋 Стадия: К выполнению\n"
                        f"🔴 Приоритет: Высокий\n"
                        f"👤 Исполнитель: Абдулов (директор)\n"
                        f"──────────────────────────────────────"
                    )
                    await self.send_message(user_id, confirm_msg)

                else:
                    # Произвольный диалог с LLM
                    await self.send_message(user_id, "⏳ Запрос передан в 1С:УНФ...", with_keyboard=False)
                    resp = await chat_handler(text, f"VK_User_{user_id}", channel="vk")
                    await self.send_message(user_id, self._clean_text_for_vk(resp))
                    await self.send_message(user_id, self._clean_text_for_vk(resp))

            return {"response": "ok"}

        return {"response": "ok"}

    def _clean_text_for_vk(self, text: str) -> str:
        """Removes Markdown formatting tags and applies VK executive styling"""
        if not text:
            return ""
        from app.services.omnichannel_formatter import omnichannel_formatter
        return omnichannel_formatter.format_llm_response(text, channel="vk")

    def _get_vk_keyboard(self) -> Dict[str, Any]:
        """Builds interactive 4-row VK Button Keyboard with native color schemes"""
        return {
            "one_time": False,
            "buttons": [
                [
                    {"action": {"type": "text", "label": "💰 Разрыв", "payload": "{\"cmd\": \"gap\"}"}, "color": "negative"},
                    {"action": {"type": "text", "label": "💳 Деньги", "payload": "{\"cmd\": \"money\"}"}, "color": "positive"}
                ],
                [
                    {"action": {"type": "text", "label": "📦 Заказы", "payload": "{\"cmd\": \"orders\"}"}, "color": "primary"},
                    {"action": {"type": "text", "label": "🏷 Неликвиды", "payload": "{\"cmd\": \"stock\"}"}, "color": "secondary"}
                ],
                [
                    {"action": {"type": "text", "label": "👥 Должники", "payload": "{\"cmd\": \"debts\"}"}, "color": "secondary"},
                    {"action": {"type": "text", "label": "📋 Канбан", "payload": "{\"cmd\": \"tasks\"}"}, "color": "primary"}
                ],
                [
                    {"action": {"type": "text", "label": "➕ Новая задача", "payload": "{\"cmd\": \"new_task\"}"}, "color": "positive"},
                    {"action": {"type": "text", "label": "ℹ️ Справка", "payload": "{\"cmd\": \"help\"}"}, "color": "secondary"}
                ]
            ]
        }

    async def send_message(self, user_id: int, message: str, keyboard: Optional[Dict[str, Any]] = None, with_keyboard: bool = True):
        if not self.access_token or not user_id:
            logger.info("[VK Mock Send] User %s: %s", user_id, message[:100])
            return

        params = {
            "user_id": user_id,
            "random_id": random.randint(1, 2147483647),
            "message": message,
            "access_token": self.access_token,
            "v": self.api_version
        }
        if keyboard:
            params["keyboard"] = json.dumps(keyboard, ensure_ascii=False)
        elif with_keyboard:
            params["keyboard"] = json.dumps(self._get_vk_keyboard(), ensure_ascii=False)

        try:
            async with self._create_client(timeout=10.0) as client:
                resp = await client.post(f"{self.api_base}/messages.send", data=params)
                if resp.status_code == 200:
                    r_json = resp.json()
                    if "error" in r_json:
                        logger.warning("VK API messages.send error: %s", r_json.get("error"))
                    else:
                        logger.info("VK message sent successfully to %s: msg_id=%s", user_id, r_json.get("response"))
        except Exception as e:
            logger.warning("Failed to send VK message: %s", e)


vk_bot_service = VkBotService()
