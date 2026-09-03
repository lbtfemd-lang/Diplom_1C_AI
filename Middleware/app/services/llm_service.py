import os
import json
import re
import asyncio
import logging
from typing import Dict, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv
import json_repair
from .metadata_service import metadata_service

logger = logging.getLogger(__name__)

# Загружаем переменные окружения
load_dotenv()

class LLMService:
    VALID_ACTIONS = {
        "expert_answer", "create_object", "open_list", "open_form",
        "find_object", "prepare_payment", "accrual_writeoff",
        "warehouse_move", "employee_info", "get_dossier",
        "get_status", "get_orders", "get_stock", "get_debtors", "run_analytics",
        "create_kanban_task", "show_kanban", "update_metadata",
        "parse_order_text", "generate_debt_letters", "create_procurement_order",
        "generate_commercial_proposal", "audit_stalled_orders",
    }

    def __init__(self):
        self._init_client()

    def _init_client(self):
        load_dotenv(override=True)
        
        self.api_key = (
            os.getenv("GEMINI_API_KEY")
            or os.getenv("OPENROUTER_API_KEY")
            or os.getenv("GROQ_API_KEY")
            or os.getenv("DEEPSEEK_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("FIREWORKS_API_KEY")
            or "dummy_key"
        )
        
        custom_base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL")
        custom_model = os.getenv("OPENAI_MODEL") or os.getenv("LLM_MODEL")
        
        if custom_base_url:
            self.base_url = custom_base_url
            self.model = custom_model or "gpt-4o-mini"
            logger.info("Using Custom OpenAI-compatible URL (%s), Model: %s", self.base_url, self.model)
        elif os.getenv("GEMINI_API_KEY") and not os.getenv("GEMINI_API_KEY").startswith("your_"):
            self.base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
            self.api_key = os.getenv("GEMINI_API_KEY")
            self.model = custom_model or "gemini-flash-latest"
            logger.info("Using Google Gemini API (%s)", self.model)
        elif os.getenv("GROQ_API_KEY") and not os.getenv("GROQ_API_KEY").startswith("your_"):
            self.base_url = "https://api.groq.com/openai/v1"
            self.api_key = os.getenv("GROQ_API_KEY")
            self.model = custom_model or "llama-3.3-70b-versatile"
            logger.info("Using Groq API (%s)", self.model)
        elif os.getenv("DEEPSEEK_API_KEY") and not os.getenv("DEEPSEEK_API_KEY").startswith("your_"):
            self.base_url = "https://api.deepseek.com"
            self.model = custom_model or "deepseek-chat"
            logger.info("Using DeepSeek API (deepseek-chat)")
        elif os.getenv("OPENROUTER_API_KEY") and not os.getenv("OPENROUTER_API_KEY").startswith("your_"):
            self.base_url = "https://openrouter.ai/api/v1"
            self.model = custom_model or "qwen/qwen-2.5-72b-instruct"
            logger.info("Using OpenRouter (%s)", self.model)
        elif os.getenv("FIREWORKS_API_KEY") and not os.getenv("FIREWORKS_API_KEY").startswith("your_"):
            self.base_url = "https://api.fireworks.ai/inference/v1"
            self.model = custom_model or "accounts/fireworks/models/llama-v3p3-70b-instruct"
            logger.info("Using Fireworks AI (%s)", self.model)
        elif os.getenv("OPENAI_API_KEY") and not os.getenv("OPENAI_API_KEY").startswith("your_"):
            self.base_url = "https://api.openai.com/v1"
            self.model = custom_model or "gpt-4o-mini"
            logger.info("Using OpenAI (%s)", self.model)
        else:
            self.base_url = "https://openrouter.ai/api/v1"
            self.model = custom_model or "qwen/qwen-2.5-72b-instruct"
            logger.warning("No active API key found in .env. Please configure API key in Middleware/.env")

        try:
            # Fix httpx bug on Windows with IPv6 in NO_PROXY (e.g. ::1)
            if "NO_PROXY" in os.environ and "::" in os.environ["NO_PROXY"]:
                clean_no_proxy = ",".join([p for p in os.environ["NO_PROXY"].split(",") if "::" not in p])
                os.environ["NO_PROXY"] = clean_no_proxy or "127.0.0.1,localhost"

            self.client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=15.0,
            )
            logger.info("LLM client initialized. Model: %s, Base URL: %s", self.model, self.base_url)
        except Exception as e:
            logger.error("Error initializing LLM client: %s", e)
            self.client = None

    @staticmethod
    def strip_emojis(text: str) -> str:
        if not text:
            return ""
        emoji_pattern = re.compile(
            "["
            "\U00010000-\U0010FFFF"
            "\u2600-\u27BF"
            "\u2300-\u23FF"
            "\u2B50\u2705\u274C\u2728\u2702-\u27B0"
            "]+",
            flags=re.UNICODE
        )
        return emoji_pattern.sub("", str(text)).strip()

    def _extract_json(self, text: str) -> dict | None:
        if not text:
            return None
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
        candidate = match.group(1).strip() if match else text.strip()

        try:
            parsed = json_repair.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        try:
            parsed = json_repair.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception as e:
            logger.warning("Failed to extract JSON with json_repair: %s", e)

        return None

    async def generate_response(self, messages: list, context: str = "Клиент 1С:УНФ 3.0") -> dict:
        return await self.process_message(messages, context_str=context)

    def _fast_classify_intent(self, user_text: str) -> dict:
        user_lower = user_text.lower().strip()
        
        # 1. Stalled Orders Audit
        if any(k in user_lower for k in ["зависшие заказы", "узкие места", "проблемные заказы", "аудит заказов", "заказы без движения", "контроль заказов"]):
            return {
                "role": "assistant",
                "text": "Выполняю предиктивный аудит открытых заказов на предмет зависания и узких мест в цепочке исполнения.",
                "action": "audit_stalled_orders",
                "data": {"days_threshold": 3}
            }

        # 2. Procurement Order from Shortage
        elif any(k in user_lower for k in ["заказ поставщику", "закупить дефицит", "пополни склад", "заказ на дефицит", "дефициту на складе", "по дефициту"]):
            return {
                "role": "assistant",
                "text": "Рассчитываю реальную потребность по дефициту товаров и формирую документ «Заказ поставщику».",
                "action": "create_procurement_order",
                "data": {"fields": {"supplier": ""}}
            }

        # 3. Commercial Proposal (КП)
        elif any(k in user_lower for k in ["коммерческое предложение", "составь кп", "сделай кп", "предложение для", "кп для"]):
            client_guess = ""
            match_for = re.search(r'(?:для|клиент|покупател[ья])\s+([a-zA-Zа-яА-Я0-9_\-\s«»"]+?)(?:\s+по|\s+на|$)', user_text, re.IGNORECASE)
            if match_for:
                client_guess = match_for.group(1).replace("«", "").replace("»", "").replace('"', '').strip()
            client_final = client_guess or "ООО АльфаМарт"
            return {
                "role": "assistant",
                "text": f"Формирую персонализированное коммерческое предложение для контрагента «{client_final}».",
                "action": "generate_commercial_proposal",
                "data": {"client_name": client_final, "topic": "комплексная поставка"}
            }

        # 4. Debt Letters Generator
        elif any(k in user_lower for k in ["письма должникам", "напомнить должникам", "претензии", "письмо должнику", "составь письмо должнику", "напоминания об оплате"]):
            return {
                "role": "assistant",
                "text": "Формирую персонализированные тексты писем-напоминаний для контрагентов с дебиторской задолженностью.",
                "action": "generate_debt_letters",
                "data": {}
            }

        # 5. Orders Listing
        elif any(k in user_lower for k in ["список заказов", "заказы покупателей", "открытые заказы", "заказы в работе", "какие заказы", "покажи заказы"]):
            return {
                "role": "assistant",
                "text": "Формирую оперативный список заказов покупателей из базы данных 1С.",
                "action": "get_orders",
                "data": {"fields": {"status": "all"}}
            }

        # 6. Parsing Order from Unstructured Multi-Item Text
        elif any(k in user_lower for k in ["выстави счет", "счет для", "заявка на", "заявка от", "нужно отгрузить", "сформируй счет", "создай заказ", "оформи заказ"]) or (("шт" in user_lower or "кг" in user_lower or "руб" in user_lower or "м" in user_lower) and any(k in user_lower for k in ["заказ", "счет", "купить"])):
            client_guess = ""
            match_for = re.search(r'(?:для|клиент|покупател[ья]|счет\s+на)\s+([a-zA-Zа-яА-Я0-9_\-\s«»"]+?)(?:\s*:|\s+на|\s+клей|\s+кабель|\s+товар|\s+позици|$)', user_text, re.IGNORECASE)
            if match_for:
                client_guess = match_for.group(1).replace("«", "").replace("»", "").replace('"', '').strip()
            
            items_list = []
            lines = user_text.replace(",", "\n").replace(";", "\n").split("\n")
            for line in lines:
                line_clean = line.strip()
                m_item = re.search(r'([a-zA-Zа-яА-Я0-9_\-\s]+?)\s+(\d+)\s*(шт|кг|м|упак|компл)?(?:\s*по\s*(\d+))?', line_clean, re.IGNORECASE)
                if m_item:
                    name_raw = m_item.group(1).replace("для", "").replace("счет", "").replace("заказ", "").replace("Выстави", "").replace("выстави", "").strip()
                    qty = int(m_item.group(2))
                    unit = m_item.group(3) or "шт"
                    price = float(m_item.group(4)) if m_item.group(4) else 0.0
                    if len(name_raw) > 1 and not name_raw.isdigit():
                        items_list.append({"name": name_raw, "quantity": qty, "price": price, "unit": unit})
            
            if not items_list:
                items_list = [{"name": "Товар", "quantity": 1, "price": 0, "unit": "шт"}]
            
            client_final = client_guess or "ООО АльфаМарт"
            return {
                "role": "assistant",
                "text": f"Заявка успешно распознана: контрагент «{client_final}», позиций: {len(items_list)} шт. Формирую черновик документа «Заказ покупателя».",
                "action": "parse_order_text",
                "data": {
                    "client_name": client_final,
                    "warehouse_name": "Основной склад",
                    "items": items_list,
                    "comment": "Заказ распознан ИИ-ассистентом из текста заявки"
                }
            }

        # 7. Debtors Listing
        elif any(k in user_lower for k in ["должник", "дебитор", "кто нам должен", "кто должен", "взаиморасчет", "задолженност"]):
            return {
                "role": "assistant",
                "text": "Формирую отчет по дебиторской задолженности контрагентов.",
                "action": "get_debtors",
                "data": {}
            }

        # 8. Stock and Shortage
        elif any(k in user_lower for k in ["остатки на складе", "остатки", "дефицит", "сколько на складе", "наличие товара", "осталось"]):
            return {
                "role": "assistant",
                "text": "Формирую отчет по складским остаткам и дефициту.",
                "action": "get_stock",
                "data": {"fields": {"Item": ""}}
            }

        # 9. Clients / Dossier
        elif any(k in user_lower for k in ["список клиентов", "клиентская база", "контрагенты", "покупатели", "досье"]):
            client_name = ""
            for prefix in ["досье клиента", "досье контрагента", "досье"]:
                if prefix in user_lower:
                    client_name = user_text[user_lower.find(prefix) + len(prefix):].replace("«", "").replace("»", "").strip()
            return {
                "role": "assistant",
                "text": f"Формирую {'досье по контрагенту «' + client_name + '»' if client_name else 'список контрагентов и клиентской базы'}.",
                "action": "get_dossier",
                "data": {"type": "Справочник.Контрагенты", "fields": {"Client": client_name}}
            }

        # 10. Kanban Task Creation
        elif any(k in user_lower for k in ["создай задачу на канбан", "создать задачу на канбан", "поставь задачу", "задача на канбан"]):
            title = user_text.replace("Создай задачу на канбан:", "").replace("создай задачу на канбан:", "").strip()
            return {
                "role": "assistant",
                "text": f"Создаю новую задачу на Канбан-доске: «{title or 'Новая задача'}».",
                "action": "create_kanban_task",
                "data": {"title": title or "Новая задача", "description": user_text, "priority": "high" if "высок" in user_lower else "medium", "due_date": ""}
            }

        return None

    async def process_message(self, messages: list, context_str: str = "Клиент 1С:УНФ 3.0") -> dict:
        self._init_client()
        
        user_message_text = messages[-1].text if messages else ""
        
        fast_result = self._fast_classify_intent(user_message_text)
        if fast_result:
            return fast_result
        top_matches = metadata_service.find_top_matches(user_message_text, top_k=5)

        candidates_str = ""
        if top_matches:
            candidates_str = "НАИБОЛЕЕ ПОДХОДЯЩИЕ ОБЪЕКТЫ 1С (НАЙДЕНО RAG-ПОИСКОМ):\n"
            for match in top_matches:
                obj_name = match.get("name", "Unknown")
                obj_synonym = match.get("synonym", "")
                obj_comment = match.get("comment", "")
                obj_type = match.get("type", "Unknown")
                candidates_str += f"- [{obj_type}] {obj_name} ({obj_synonym}): {obj_comment}\n"
        else:
            candidates_str = "Подходящие объекты метаданных не найдены (будет использован общий контекст)."

        current_context_str = f"ТЕКУЩИЙ КОНТЕКСТ РАБОТЫ: {context_str}"

        system_prompt = f"""Ты — интеллектуальный бизнес-ассистент в среде «1С:Управление нашей фирмой 3.0» (1С:УНФ).
Твоя ключевая задача — понимать запросы пользователя на естественном языке, автоматизировать бизнес-процессы и возвращать строго типизированный JSON-ответ с соответствующим действием (action) и структурированными данными (data) для исполнения в 1С.

ПРАВИЛА ОФОРМЛЕНИЯ ТЕКСТА:
- Категорически запрещено использовать любые эмодзи и пиктограммы.
- Используй академический деловой стиль и русские кавычки-елочки (« »).

ТАБЛИЦА МАРШРУТИЗАЦИИ И СЦЕНАРИЕВ АВТОМАТИЗАЦИИ:
1. ПАРСИНГ ЗАЯВКИ ИЗ ТЕКСТА / МЕССЕНДЖЕРА (содержит список товаров, цены, количества, заявку на заказ):
   - action="parse_order_text", data={{"client_name": "...", "warehouse_name": "Основной склад", "items": [{{"name": "...", "quantity": 1, "price": 0, "unit": "шт"}}]}}

2. АВТОГЕНЕРАЦИЯ ПИСЕМ ДОЛЖНИКАМ / ПРЕТЕНЗИИ ПО ДЕБИТОРКЕ:
   - action="generate_debt_letters", data={{}}

3. ЗАКАЗ ПОСТАВЩИКУ ПО ДЕФИЦИТУ / АВТОЗАКУПКА:
   - action="create_procurement_order", data={{"fields": {{"supplier": ""}}}}

4. ГЕНЕРАЦИЯ КОММЕРЧЕСКОГО ПРЕДЛОЖЕНИЯ (КП):
   - action="generate_commercial_proposal", data={{"client_name": "...", "topic": "..."}}

5. АУДИТ ЗАВИСШИХ ЗАКАЗОВ / УЗКИХ МЕСТ:
   - action="audit_stalled_orders", data={{"days_threshold": 3}}

6. СПИСОК ЗАКАЗОВ / ОТКРЫТЫЕ ЗАКАЗЫ:
   - action="get_orders", data={{"fields": {{"status": "all"}}}}

7. СКЛАДСКИЕ ОСТАТКИ / НАЛИЧИЕ ТОВАРА:
   - action="get_stock", data={{"fields": {{"Item": "..."}}}}

8. ДОСЬЕ / КАРТОЧКА КЛИЕНТА:
   - action="get_dossier", data={{"type": "Справочник.Контрагенты", "fields": {{"Client": "..."}}}}

9. ПОСТАНОВКА ЗАДАЧИ В КАНБАН:
   - action="create_kanban_task", data={{"title": "...", "description": "...", "priority": "high|medium|low", "due_date": "YYYY-MM-DD"}}

10. ОБЩИЕ ВОПРОСЫ / КОНСУЛЬТАЦИИ:
   - action="expert_answer", data=null

{current_context_str}
{candidates_str}

ФОРМАТ ВЫВОДА (ТОЛЬКО JSON, БЕЗ ЛИШНЕГО ТЕКСТА):
{{
  "text": "Пояснение для пользователя на русском языке.",
  "action": "одно из действий выше",
  "data": {{ ... }}
}}
"""

        messages_payload = [{"role": "system", "content": system_prompt}]
        recent_messages = messages[-10:] if len(messages) > 10 else messages
        for msg in recent_messages:
            role = "user" if msg.role == "user" else "assistant"
            messages_payload.append({"role": role, "content": msg.text})

        # Формируем список моделей для отказоустойчивости при пиковых нагрузках (503/429)
        candidate_models = [self.model]
        if "generativelanguage" in self.base_url:
            for fallback in ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-2.0-flash"]:
                if fallback not in candidate_models:
                    candidate_models.append(fallback)

        last_error = None
        for current_model in candidate_models:
            try:
                completion = await asyncio.to_thread(
                    self.client.chat.completions.create,
                    extra_headers={
                        "HTTP-Referer": "http://localhost:8000",
                        "X-Title": "1C-AI-Assistant",
                    } if "openrouter" in self.base_url else {},
                    model=current_model,
                    messages=messages_payload,
                    temperature=0.3,
                    max_tokens=1500
                )

                generated_text = completion.choices[0].message.content
                logger.info("LLM Output successfully received using model: %s", current_model)

                parsed = self._extract_json(generated_text)
                if parsed:
                    action = parsed.get("action", "")
                    if action and action not in self.VALID_ACTIONS:
                        parsed["action"] = "expert_answer"
                    if "text" in parsed:
                        parsed["text"] = self.strip_emojis(parsed["text"])
                    return parsed
                else:
                    return {
                        "text": self.strip_emojis(generated_text),
                        "action": "expert_answer",
                        "data": None
                    }
            except Exception as e:
                logger.warning("Model %s failed (%s). Attempting fallback to next model...", current_model, e)
                last_error = e
                await asyncio.sleep(0.5)

        logger.error("All candidate LLM models failed. Last error: %s", last_error)
        return {
            "text": f"Сервис генерации временно перегружен ({last_error}). Пожалуйста, повторите запрос через несколько секунд.",
            "action": "expert_answer",
            "data": None
        }

llm_service = LLMService()
