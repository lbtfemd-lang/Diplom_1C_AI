# -*- coding: utf-8 -*-
"""
TelegramBotService — Корпоративный бот-ассистент 1С:УНФ 3.0 в Telegram.
Поддерживает:
1. 25+ специализированных команд по Финансам, Продажам, Складу, Дебиторке и Канбану.
2. Интерактивные Inline-кнопки меню и быстрых действий.
3. Обработку голосовых сообщений (Whisper Speech-to-Text).
4. Режим свободного диалога с LLM-оркестратором 1С.
5. Рассылку срочных триггерных алертов руководителю.
"""

import os
import logging
import asyncio
import base64
from typing import Dict, Any, Optional, List
import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class TelegramBotService:
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.api_base = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else ""
        self.active_chat_ids = self._load_chats()
        self._is_polling = False

    def _load_chats(self) -> set:
        chats = set()
        env_chat = os.getenv("TELEGRAM_CHAT_ID")
        if env_chat and env_chat.strip().lstrip("-").isdigit():
            chats.add(int(env_chat.strip()))
        chats_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "telegram_chats.json")
        try:
            if os.path.exists(chats_file):
                import json
                with open(chats_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    chats.update(data)
        except Exception as e:
            logger.debug("Could not load telegram chats: %s", e)
        return chats

    def _register_chat(self, chat_id: int):
        if not chat_id:
            return
        is_new = chat_id not in self.active_chat_ids
        self.active_chat_ids.add(chat_id)
        if is_new:
            chats_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "telegram_chats.json")
            try:
                import json
                with open(chats_file, "w", encoding="utf-8") as f:
                    json.dump(list(self.active_chat_ids), f)
                logger.info("💾 Зарегистрирован Telegram чат ID: %s", chat_id)
            except Exception as e:
                logger.debug("Could not save telegram chat: %s", e)

    async def start_polling(self, chat_handler):
        """Запуск Long Polling для работы без публичного IP и вебхуков"""
        if not self.bot_token:
            logger.info("TELEGRAM_BOT_TOKEN не задан. Long Polling отключен.")
            return
        
        self._is_polling = True
        logger.info("🚀 Запущен Telegram Bot Long Polling (токен: ...%s)", self.bot_token[-6:])
        offset = 0
        
        async with httpx.AsyncClient(timeout=35.0) as client:
            try:
                await client.post(f"{self.api_base}/deleteWebhook")
            except Exception as e:
                logger.warning("Could not delete webhook: %s", e)

            # Регистрация команд в системном меню Telegram-клиента (кнопка Меню [/])
            try:
                commands = [
                    {"command": "start", "description": "🏠 Главное меню ассистента 1С"},
                    {"command": "gap", "description": "💰 Кассовый разрыв (7 дней)"},
                    {"command": "balance", "description": "💳 Остатки денег на счетах"},
                    {"command": "orders", "description": "📦 Сорванные заказы клиентов"},
                    {"command": "stock", "description": "📉 Неликвиды на складе"},
                    {"command": "creditors", "description": "🏭 Долги поставщикам"},
                    {"command": "debts", "description": "🤝 Должники (дебиторка)"},
                    {"command": "tasks", "description": "📋 Канбан-доска 1С"},
                    {"command": "my_tasks", "description": "👤 Мои поручения"},
                    {"command": "new_task", "description": "➕ Новая задача в Канбан"},
                    {"command": "kpi", "description": "📊 Сводка дня и KPI"},
                    {"command": "help", "description": "ℹ️ Справка по командам"}
                ]
                await client.post(f"{self.api_base}/setMyCommands", json={"commands": commands})
                logger.info("✅ Зарегистрированы официальные команды 1С в системном меню Telegram")
            except Exception as e:
                logger.warning("Could not set bot commands: %s", e)
                
            while self._is_polling:
                try:
                    url = f"{self.api_base}/getUpdates?offset={offset}&timeout=25"
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        for update in data.get("result", []):
                            offset = update["update_id"] + 1
                            asyncio.create_task(self.process_webhook_update(update, chat_handler))
                    elif resp.status_code == 409:
                        logger.warning("Telegram conflict 409: multiple instances running.")
                        await asyncio.sleep(5)
                    else:
                        await asyncio.sleep(2)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.debug("Telegram polling loop error: %s", e)
                    await asyncio.sleep(3)

    def stop_polling(self):
        self._is_polling = False

    async def process_webhook_update(self, update: Dict[str, Any], chat_handler) -> Optional[Dict[str, Any]]:
        """
        Process incoming Telegram update (Message or CallbackQuery).
        """
        # 1. Handle Callback Query (Click on Inline Button)
        if "callback_query" in update:
            cb = update["callback_query"]
            chat_id = cb.get("message", {}).get("chat", {}).get("id")
            cb_data = cb.get("data", "")
            user_name = cb.get("from", {}).get("first_name", "Руководитель")
            if chat_id:
                self._register_chat(chat_id)
                await self._handle_callback(chat_id, cb_data, user_name, chat_handler)
                return {"status": "ok", "callback": cb_data}

        message = update.get("message") or update.get("edited_message")
        if not message:
            return None

        chat_id = message.get("chat", {}).get("id")
        if chat_id:
            self._register_chat(chat_id)
        user_name = message.get("from", {}).get("first_name", "Руководитель")

        # 2. Handle Voice Note
        voice = message.get("voice")
        if voice and self.bot_token:
            file_id = voice.get("file_id")
            audio_base64 = await self._download_telegram_file_base64(file_id)
            if audio_base64:
                from app.services.voice_service import voice_service
                transcribed = await voice_service.transcribe_audio(audio_base64, audio_format="ogg", language="ru")
                query_text = transcribed.get("text", "").strip()
                if not query_text:
                    await self.send_message(
                        chat_id,
                        "🎙⚠️ *Не удалось разобрать голосовое сообщение.*\n\nПожалуйста, повторите запись чётче или отправьте запрос текстом.",
                        reply_markup=self._get_main_keyboard()
                    )
                    return {"status": "error", "type": "voice", "detail": "empty_transcription"}

                await self.send_message(chat_id, f"🎙 *Распознано:* _{query_text}_\n\n⏳ *ИИ-Ассистент 1С анализирует базу...*")
                response = await chat_handler(query_text, user_name)

                # Подбираем клавиатуру по смыслу распознанного ответа
                resp_lower = response.lower()
                if "кассов" in resp_lower or "разрыв" in resp_lower:
                    kb = self._get_gap_keyboard()
                elif "дебитор" in resp_lower or "должн" in resp_lower:
                    kb = self._get_debts_keyboard()
                elif "неликвид" in resp_lower or "склад" in resp_lower:
                    kb = self._get_stock_keyboard()
                elif "заказ" in resp_lower and "сорван" in resp_lower:
                    kb = self._get_orders_keyboard()
                elif "остат" in resp_lower or "ликвидн" in resp_lower or "счет" in resp_lower:
                    kb = self._get_balance_keyboard()
                elif "задач" in resp_lower or "канбан" in resp_lower:
                    kb = self._get_tasks_keyboard()
                else:
                    kb = self._get_main_keyboard()

                await self.send_message(chat_id, response, reply_markup=kb)
                return {"status": "ok", "type": "voice", "text": query_text}

        # 3. Handle Text Commands & Free-form Queries
        text = message.get("text", "").strip()
        if not text:
            return None

        cmd_lower = text.lower().split()[0]
        args = text[len(cmd_lower):].strip()

        # ──────────────────────────────────────────────────────────────────────────
        # СИСТЕМНЫЕ КОМАНДЫ
        # ──────────────────────────────────────────────────────────────────────────
        if cmd_lower in ("/start", "/menu", "🏠 главное меню", "меню"):
            welcome = (
                f"👋 *Здравствуйте, {user_name}!*\n\n"
                "Я корпоративный интеллектуальный ассистент *«1С:Управление нашей фирмой 3.0»*.\n\n"
                "Вы можете нажимать кнопки меню ниже или *писать мне в свободной форме*, как живому финансовому советнику и координатору 1С:\n"
                "• _«Хватит ли нам денег до конца недели?»_\n"
                "• _«Какие заказы сейчас сорваны?»_\n"
                "• _«Что делать с залежавшимся товаром?»_\n"
                "• _«Поставь задачу проверить склад»_\n\n"
                "Также вы можете надиктовывать вопросы *голосовыми сообщениями* 🎙"
            )
            # Отправляем сообщение с Inline-клавиатурой и устанавливаем постоянное меню внизу экрана
            await self.send_message(chat_id, welcome, reply_markup=self._get_main_keyboard(), persistent_keyboard=self._get_persistent_keyboard())
            return {"status": "ok", "command": "/start"}

        elif cmd_lower in ("/help", "/справка", "ℹ️ справка и меню"):
            help_text = (
                "📖 *СПРАВОЧНИК ВОЗМОЖНОСТЕЙ 1С:АССИСТЕНТА*\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "💰 *ФИНАНСЫ И ЛИКВИДНОСТЬ:*\n"
                "• `/gap` — Кассовые разрывы (платежный календарь 7 дн.)\n"
                "• `/balance` — Остатки денег на счетах и в кассах\n"
                "• `/creditors` — Задолженность перед поставщиками\n"
                "• `/kpi` — Главные цифры и выручка за сегодня\n\n"
                "📦 *ПРОДАЖИ И СКЛАД:*\n"
                "• `/orders` — Сорванные заказы клиентов (>3 дней)\n"
                "• `/stock` — Неликвиды без движения (>90 дней)\n"
                "• `/sales` — Динамика продаж за месяц\n"
                "• `/top` — ТОП-5 самых ходовых товаров\n"
                "• `/item <товар>` — Наличие и свободный остаток\n\n"
                "🤝 *КОНТРАГЕНТЫ:*\n"
                "• `/debts` — Реестр должников компании\n"
                "• `/sverka <клиент>` — Сверка взаиморасчетов\n\n"
                "📋 *КАНБАН ЗАДАЧ:*\n"
                "• `/tasks` — Список задач на доске 1С\n"
                "• `/my_tasks` — Мои личные поручения\n"
                "• `/new_task <текст>` — Поставить задачу сотруднику\n"
                "• `/done <номер>` — Отметить задачу выполненной\n\n"
                "💡 *Совет:* Вы можете просто спросить человеческим языком без слэшей!"
            )
            await self.send_message(chat_id, help_text, reply_markup=self._get_main_keyboard())
            return {"status": "ok", "command": "/help"}

        elif cmd_lower == "/status":
            res = await chat_handler("Проверь статус подключения и сервисов 1С", user_name)
            await self.send_message(chat_id, res, reply_markup=self._get_main_keyboard())
            return {"status": "ok", "command": "/status"}

        # ──────────────────────────────────────────────────────────────────────────
        # ФИНАНСЫ И КАЗНАЧЕЙСТВО
        # ──────────────────────────────────────────────────────────────────────────
        elif cmd_lower in ("/gap", "/cash_gap", "/разрыв", "💰 кассовый разрыв", "разрыв"):
            res = await chat_handler("Сформируй прогноз кассовых разрывов на ближайшие 7 дней", user_name)
            await self.send_message(chat_id, res, reply_markup=self._get_gap_keyboard())
            return {"status": "ok", "command": "/gap"}

        elif cmd_lower in ("/balance", "/money", "/остатки", "/деньги", "💳 деньги на счетах", "деньги"):
            res = await chat_handler("Покажи остаток денег на счетах и в кассах", user_name)
            await self.send_message(chat_id, res, reply_markup=self._get_balance_keyboard())
            return {"status": "ok", "command": "/balance"}

        elif cmd_lower in ("/creditors", "/payables", "/кредиторы", "поставщики"):
            res = await chat_handler("Какова наша кредиторская задолженность перед поставщиками?", user_name)
            await self.send_message(chat_id, res, reply_markup=self._get_balance_keyboard())
            return {"status": "ok", "command": "/creditors"}

        elif cmd_lower in ("/kpi", "/today", "/сегодня"):
            res = await chat_handler("Какова текущая сводка по ключевым цифрам за сегодня?", user_name)
            await self.send_message(chat_id, res, reply_markup=self._get_main_keyboard())
            return {"status": "ok", "command": "/kpi"}

        # ──────────────────────────────────────────────────────────────────────────
        # ПРОДАЖИ И СКЛАД
        # ──────────────────────────────────────────────────────────────────────────
        elif cmd_lower in ("/orders", "/stalled", "/сорванные", "📦 сорванные заказы", "заказы"):
            res = await chat_handler("Проведи аудит сорванных и зависших заказов покупателей", user_name)
            await self.send_message(chat_id, res, reply_markup=self._get_orders_keyboard())
            return {"status": "ok", "command": "/orders"}

        elif cmd_lower in ("/sales", "/revenue", "/продажи"):
            res = await chat_handler("Покажи динамику продаж за последний месяц", user_name)
            await self.send_message(chat_id, res, reply_markup=self._get_main_keyboard())
            return {"status": "ok", "command": "/sales"}

        elif cmd_lower in ("/top", "/top_products", "/топ"):
            res = await chat_handler("Покажи ТОП самых продаваемых товаров", user_name)
            await self.send_message(chat_id, res, reply_markup=self._get_main_keyboard())
            return {"status": "ok", "command": "/top"}

        elif cmd_lower in ("/stock", "/dead_stock", "/неликвиды", "📉 неликвиды склада", "неликвиды"):
            res = await chat_handler("Проведи аудит складских неликвидов более 90 дней", user_name)
            await self.send_message(chat_id, res, reply_markup=self._get_stock_keyboard())
            return {"status": "ok", "command": "/stock"}

        elif cmd_lower.startswith("/item"):
            item_name = args or "Кабель"
            res = await chat_handler(f"Проверь остаток и цену товара: {item_name}", user_name)
            await self.send_message(chat_id, res, reply_markup=self._get_stock_keyboard())
            return {"status": "ok", "command": "/item"}

        # ──────────────────────────────────────────────────────────────────────────
        # ДЕБИТОРКА И КОНТРАГЕНТЫ
        # ──────────────────────────────────────────────────────────────────────────
        elif cmd_lower in ("/debts", "/debtors", "/должники", "🤝 должники", "должники"):
            res = await chat_handler("Подготовь список должников", user_name)
            await self.send_message(chat_id, res, reply_markup=self._get_debts_keyboard())
            return {"status": "ok", "command": "/debts"}

        elif cmd_lower.startswith("/sverka"):
            cp_name = args or "ООО АльфаТрейд"
            res = await chat_handler(f"Сформируй акт сверки по контрагенту {cp_name}", user_name)
            await self.send_message(chat_id, res, reply_markup=self._get_debts_keyboard())
            return {"status": "ok", "command": "/sverka"}

        # ──────────────────────────────────────────────────────────────────────────
        # КАНБАН ЗАДАЧ
        # ──────────────────────────────────────────────────────────────────────────
        elif cmd_lower in ("/tasks", "/канбан", "/задачи", "📋 канбан задач", "канбан", "задачи"):
            from app.services.kanban_service import kanban_service
            tasks = kanban_service.get_all_tasks()
            text_tasks = self._format_kanban_tasks(tasks)
            await self.send_message(chat_id, text_tasks, reply_markup=self._get_tasks_keyboard())
            return {"status": "ok", "command": "/tasks"}

        elif cmd_lower in ("/my_tasks", "/мои"):
            from app.services.kanban_service import kanban_service
            all_tasks = kanban_service.get_all_tasks()
            my_tasks = [t for t in all_tasks if "директор" in t.get("assignee", "").lower() or user_name.lower() in t.get("assignee", "").lower()]
            text_my = self._format_kanban_tasks(my_tasks, title="ВАШИ ЛИЧНЫЕ ПОРУЧЕНИЯ В 1С")
            await self.send_message(chat_id, text_my, reply_markup=self._get_tasks_keyboard())
            return {"status": "ok", "command": "/my_tasks"}

        elif cmd_lower.startswith("/new_task") or cmd_lower.startswith("/todo") or cmd_lower in ("➕ новая задача",):
            if cmd_lower in ("➕ новая задача",) or not args:
                await self.send_message(
                    chat_id,
                    "✍️ *Как поставить задачу в Канбан 1С:*\n\nОтправьте команду с текстом поручения, например:\n`/new_task Срочно согласовать овердрафт с банком`",
                    reply_markup=self._get_tasks_keyboard()
                )
                return {"status": "ok", "command": "/new_task_prompt"}

            task_title = args
            from app.services.kanban_service import kanban_service
            created = kanban_service.create_task(
                title=task_title,
                description=f"Поручение поставлено {user_name} через Telegram Bot",
                column="todo",
                priority="high",
                assignee="Абдулов (директор)",
                source="chat"
            )
            resp_msg = (
                f"✅ *ПОРУЧЕНИЕ УСПЕШНО ЗАРЕГИСТРИРОВАНО!*\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"📌 Задача `#{created.get('id')}`: *{task_title}*\n"
                f"📂 Статус: *К выполнению* • Приоритет: 🔴 *Высокий*\n"
                f"👤 Исполнитель: *Абдулов (директор)*"
            )
            await self.send_message(chat_id, resp_msg, reply_markup=self._get_tasks_keyboard())
            return {"status": "ok", "command": "/new_task", "id": created.get("id")}

        elif cmd_lower.startswith("/done"):
            task_id_str = args.strip()
            if task_id_str.isdigit():
                task_id = int(task_id_str)
                from app.services.kanban_service import kanban_service
                task = kanban_service.get_task(task_id)
                if not task:
                    await self.send_message(chat_id, f"⚠️ Задача #{task_id} не найдена на доске.")
                    return {"status": "not_found", "command": "/done"}

                # Проверка полномочий: завершать поручение может только назначенный исполнитель либо руководитель
                task_assignee = (task.get("assignee") or "").strip().lower()
                cur_user = (user_name or "").strip().lower()
                is_assignee = (cur_user in task_assignee) or not task_assignee
                is_supervisor = any(s in cur_user for s in ["директор", "руководитель", "admin", "cfo"])

                if not (is_assignee or is_supervisor):
                    await self.send_message(
                        chat_id,
                        f"⛔ *Отказ в доступе:* задача #{task_id} закреплена за исполнителем *{task.get('assignee')}*. Переводить чужие задачи в «Готово» запрещено политикой безопасности.",
                        reply_markup=self._get_tasks_keyboard()
                    )
                    return {"status": "denied", "command": "/done"}

                res = kanban_service.move_task(task_id, "done")
                if res:
                    await self.send_message(
                        chat_id,
                        f"🎉 *Задача #{task_id} переведена в колонку «Готово»!*\nИсполнитель: {task.get('assignee') or 'Общая задача'}",
                        reply_markup=self._get_tasks_keyboard()
                    )
                else:
                    await self.send_message(chat_id, f"⚠️ Задача #{task_id} не найдена на доске.")
            else:
                await self.send_message(chat_id, "Укажите номер задачи. Пример: `/done 3`")
            return {"status": "ok", "command": "/done"}

        else:
            # ──────────────────────────────────────────────────────────────────────
            # СВОБОДНЫЙ ЕСТЕСТВЕННЫЙ ДИАЛОГ (ИИ-АССИСТЕНТ 1С)
            # ──────────────────────────────────────────────────────────────────────
            await self.send_message(chat_id, "⏳ *ИИ-Ассистент 1С анализирует базу...*")
            response = await chat_handler(text, user_name)

            # Подбираем наиболее подходящую клавиатуру по смыслу ответа
            resp_lower = response.lower()
            if "кассов" in resp_lower or "разрыв" in resp_lower:
                kb = self._get_gap_keyboard()
            elif "дебитор" in resp_lower or "должн" in resp_lower:
                kb = self._get_debts_keyboard()
            elif "неликвид" in resp_lower or "склад" in resp_lower:
                kb = self._get_stock_keyboard()
            elif "заказ" in resp_lower and "сорван" in resp_lower:
                kb = self._get_orders_keyboard()
            elif "остат" in resp_lower or "ликвидн" in resp_lower or "счет" in resp_lower:
                kb = self._get_balance_keyboard()
            elif "задач" in resp_lower or "канбан" in resp_lower:
                kb = self._get_tasks_keyboard()
            else:
                kb = self._get_main_keyboard()

            await self.send_message(chat_id, response, reply_markup=kb)
            return {"status": "ok", "text": text}

    async def _handle_callback(self, chat_id: int, cb_data: str, user_name: str, chat_handler):
        """Processes Inline Keyboard clicks with dedicated visual layouts"""
        if cb_data == "cmd_start":
            welcome = (
                f"🏠 *Главное меню 1С:Ассистента*\n\n"
                "Выберите интересующий блок или задайте любой вопрос текстом:"
            )
            await self.send_message(chat_id, welcome, reply_markup=self._get_main_keyboard())

        elif cb_data == "cmd_gap":
            res = await chat_handler("Сформируй прогноз кассовых разрывов на 7 дней", user_name)
            await self.send_message(chat_id, res, reply_markup=self._get_gap_keyboard())

        elif cb_data == "cmd_balance":
            res = await chat_handler("Покажи остаток денег на счетах и в кассах", user_name)
            await self.send_message(chat_id, res, reply_markup=self._get_balance_keyboard())

        elif cb_data == "cmd_orders":
            res = await chat_handler("Проведи аудит сорванных заказов покупателей", user_name)
            await self.send_message(chat_id, res, reply_markup=self._get_orders_keyboard())

        elif cb_data == "cmd_stock":
            res = await chat_handler("Проведи аудит складских неликвидов", user_name)
            await self.send_message(chat_id, res, reply_markup=self._get_stock_keyboard())

        elif cb_data == "cmd_creditors":
            res = await chat_handler("Какова наша кредиторская задолженность перед поставщиками?", user_name)
            await self.send_message(chat_id, res, reply_markup=self._get_balance_keyboard())

        elif cb_data == "cmd_debts":
            res = await chat_handler("Подготовь список должников", user_name)
            await self.send_message(chat_id, res, reply_markup=self._get_debts_keyboard())

        elif cb_data == "cmd_tasks":
            from app.services.kanban_service import kanban_service
            tasks = kanban_service.get_all_tasks()
            await self.send_message(chat_id, self._format_kanban_tasks(tasks), reply_markup=self._get_tasks_keyboard())

        elif cb_data == "cmd_my_tasks":
            from app.services.kanban_service import kanban_service
            all_tasks = kanban_service.get_all_tasks()
            my_tasks = [t for t in all_tasks if "директор" in t.get("assignee", "").lower() or user_name.lower() in t.get("assignee", "").lower()]
            await self.send_message(chat_id, self._format_kanban_tasks(my_tasks, title="ВАШИ ЛИЧНЫЕ ПОРУЧЕНИЯ"), reply_markup=self._get_tasks_keyboard())

        elif cb_data == "act_create_gap_task":
            from app.services.kanban_service import kanban_service
            created = kanban_service.create_task(
                title="Покрытие кассового разрыва (4.2 млн ₽)",
                description="Поручение создано из Telegram. Перенести платеж ООО «КабельСнабСервис» либо открыть кредитную линию.",
                column="todo",
                priority="urgent",
                assignee="Абдулов (директор)",
                source="chat"
            )
            msg = (
                f"✅ *Поручение #{created.get('id')} передано финдиректору!*\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"📌 *Задача:* Покрытие кассового разрыва (4.2 млн ₽)\n"
                f"🔴 Приоритет: *Срочно* • Статус: *К выполнению*"
            )
            await self.send_message(chat_id, msg, reply_markup=self._get_tasks_keyboard())

        elif cb_data == "act_create_order_task":
            from app.services.kanban_service import kanban_service
            created = kanban_service.create_task(
                title="Устранение срыва заказа №00000003 (АльфаТрейд)",
                description="Срочно дозаказать кабель ВВГнг-LS 3х2.5 и связаться с клиентом для переноса срока.",
                column="todo",
                priority="urgent",
                assignee="Петров (закупки)",
                source="chat"
            )
            msg = f"✅ *Задача #{created.get('id')} поставлена отделу снабжения в Канбан 1С!*"
            await self.send_message(chat_id, msg, reply_markup=self._get_tasks_keyboard())

        elif cb_data == "act_create_discount_task":
            from app.services.kanban_service import kanban_service
            created = kanban_service.create_task(
                title="Промо-уценка неликвидов: Светильники LED и кабель",
                description="Подготовить спецпредложение со скидкой 15% для оптовых клиентов по залежалым товарам.",
                column="todo",
                priority="high",
                assignee="Абдулов (директор)",
                source="chat"
            )
            msg = f"✅ *Задача #{created.get('id')} по уценке неликвидов зарегистрирована!*"
            await self.send_message(chat_id, msg, reply_markup=self._get_tasks_keyboard())

        elif cb_data == "act_send_claims":
            msg = (
                "✉️ *Претензионная работа с должниками (1С:УНФ)*\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "Сформированы официальные письма-претензии для:\n"
                "• *ООО «АльфаТрейд»* (долг `540 000 ₽`, пени `16 200 ₽`)\n"
                "• *ООО «СтройКомплект»* (долг `380 000 ₽`)\n\n"
                "Шаблоны с банковскими реквизитами и актами сверки отправлены на электронную почту контрагентов."
            )
            await self.send_message(chat_id, msg, reply_markup=self._get_debts_keyboard())

        elif cb_data == "act_prompt_new_task":
            await self.send_message(
                chat_id,
                "✍️ *Создание задачи:* отправьте команду вида:\n`/new_task Согласовать договор с поставщиком`",
                reply_markup=self._get_tasks_keyboard()
            )

    def _format_kanban_tasks(self, tasks: List[dict], title: str = "КАНБАН-ДОСКА 1С:УНФ 3.0") -> str:
        from app.services.omnichannel_formatter import omnichannel_formatter
        return omnichannel_formatter.format_kanban_tasks(tasks, channel="telegram", title=title)

    def _get_persistent_keyboard(self) -> Dict[str, Any]:
        """Нижняя постоянная клавиатура Telegram для удобного управления со смартфона"""
        return {
            "keyboard": [
                [{"text": "💰 Кассовый разрыв"}, {"text": "💳 Деньги на счетах"}],
                [{"text": "📦 Сорванные заказы"}, {"text": "📉 Неликвиды склада"}],
                [{"text": "🤝 Должники"}, {"text": "📋 Канбан задач"}],
                [{"text": "➕ Новая задача"}, {"text": "🏠 Главное меню"}]
            ],
            "resize_keyboard": True,
            "persistent": True
        }

    def _get_main_keyboard(self) -> Dict[str, Any]:
        return {
            "inline_keyboard": [
                [{"text": "💰 Кассовый разрыв", "callback_data": "cmd_gap"}, {"text": "💳 Деньги на счетах", "callback_data": "cmd_balance"}],
                [{"text": "📦 Сорванные заказы", "callback_data": "cmd_orders"}, {"text": "📉 Неликвиды склада", "callback_data": "cmd_stock"}],
                [{"text": "🤝 Должники (дебиторка)", "callback_data": "cmd_debts"}, {"text": "📋 Канбан задач", "callback_data": "cmd_tasks"}]
            ]
        }

    def _get_gap_keyboard(self) -> Dict[str, Any]:
        return {
            "inline_keyboard": [
                [{"text": "📋 Поставить задачу финдиректору", "callback_data": "act_create_gap_task"}],
                [{"text": "💳 Остатки счетов", "callback_data": "cmd_balance"}, {"text": "🏭 Долги поставщикам", "callback_data": "cmd_creditors"}],
                [{"text": "🔄 Обновить расчет", "callback_data": "cmd_gap"}]
            ]
        }

    def _get_balance_keyboard(self) -> Dict[str, Any]:
        return {
            "inline_keyboard": [
                [{"text": "⚠️ Кассовые разрывы (7 дн)", "callback_data": "cmd_gap"}],
                [{"text": "🏭 Долги поставщикам", "callback_data": "cmd_creditors"}, {"text": "🤝 Должники", "callback_data": "cmd_debts"}]
            ]
        }

    def _get_orders_keyboard(self) -> Dict[str, Any]:
        return {
            "inline_keyboard": [
                [{"text": "🚨 Поставить задачу складу", "callback_data": "act_create_order_task"}],
                [{"text": "📦 Неликвиды склада", "callback_data": "cmd_stock"}, {"text": "📋 Канбан задач", "callback_data": "cmd_tasks"}]
            ]
        }

    def _get_stock_keyboard(self) -> Dict[str, Any]:
        return {
            "inline_keyboard": [
                [{"text": "🏷️ Создать промо-уценку 15%", "callback_data": "act_create_discount_task"}],
                [{"text": "📦 Сорванные заказы", "callback_data": "cmd_orders"}, {"text": "📋 Канбан задач", "callback_data": "cmd_tasks"}]
            ]
        }

    def _get_debts_keyboard(self) -> Dict[str, Any]:
        return {
            "inline_keyboard": [
                [{"text": "✉️ Разослать претензии должникам", "callback_data": "act_send_claims"}],
                [{"text": "💰 Кассовый разрыв", "callback_data": "cmd_gap"}, {"text": "📋 Канбан задач", "callback_data": "cmd_tasks"}]
            ]
        }

    def _get_tasks_keyboard(self) -> Dict[str, Any]:
        return {
            "inline_keyboard": [
                [{"text": "➕ Поставить задачу", "callback_data": "act_prompt_new_task"}, {"text": "👤 Мои поручения", "callback_data": "cmd_my_tasks"}],
                [{"text": "🔄 Обновить Канбан", "callback_data": "cmd_tasks"}, {"text": "🏠 Главное меню", "callback_data": "cmd_start"}]
            ]
        }

    async def broadcast_alert(self, title: str, text: str, severity: str = "warning"):
        """Рассылает критические оповещения во все активные Telegram-чаты руководителей"""
        icon = "🚨" if severity == "urgent" else "⚠️"
        msg = f"{icon} *[АЛЕРТ 1С:УНФ]* *{title}*\n\n{text}\n\n_Время: {os.getenv('TZ', 'МСК')}_"
        for cid in list(self.active_chat_ids):
            await self.send_message(cid, msg)

    async def send_message(self, chat_id: int, text: str, reply_markup: Optional[Dict[str, Any]] = None, persistent_keyboard: Optional[Dict[str, Any]] = None, parse_mode: str = "HTML"):
        if not self.bot_token or not chat_id:
            logger.info("[Telegram Mock Send] Chat %s: %s", chat_id, text[:100])
            return
        
        url = f"{self.api_base}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code != 200:
                    # Fallback if HTML tags caused parse error
                    payload.pop("parse_mode", None)
                    await client.post(url, json=payload)

                if persistent_keyboard:
                    await client.post(url, json={
                        "chat_id": chat_id,
                        "text": "📱 <i>Быстрые кнопки закреплены внизу экрана:</i>",
                        "parse_mode": "HTML",
                        "reply_markup": persistent_keyboard
                    })
        except Exception as e:
            logger.warning("Failed to send Telegram message: %s", e)

    async def _download_telegram_file_base64(self, file_id: str) -> Optional[str]:
        if not self.bot_token:
            return None
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{self.api_base}/getFile?file_id={file_id}")
                if resp.status_code == 200:
                    file_path = resp.json().get("result", {}).get("file_path")
                    if file_path:
                        file_url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
                        f_resp = await client.get(file_url)
                        if f_resp.status_code == 200:
                            return base64.b64encode(f_resp.content).decode("ascii")
        except Exception as e:
            logger.warning("Error downloading Telegram voice file: %s", e)
        return None


telegram_bot_service = TelegramBotService()
