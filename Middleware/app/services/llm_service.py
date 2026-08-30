import os
import json
import re
import asyncio
import logging
from openai import OpenAI
from dotenv import load_dotenv
from .metadata_service import metadata_service

logger = logging.getLogger(__name__)

# Загружаем переменные окружения
load_dotenv()

class LLMService:
    def __init__(self):
        self.api_key = os.getenv("FIREWORKS_API_KEY") or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
             logger.warning("No API key found. Set FIREWORKS_API_KEY or OPENROUTER_API_KEY in .env")

        if os.getenv("FIREWORKS_API_KEY"):
            self.base_url = "https://api.fireworks.ai/inference/v1"
            self.model = "accounts/fireworks/models/glm-5p1"
            logger.info("Using Fireworks AI (GLM 5.1)")
        else:
            self.base_url = "https://openrouter.ai/api/v1"
            self.model = "qwen/qwen-2.5-72b-instruct"
            logger.info("Using OpenRouter (Qwen 2.5 72B)")

        try:
            self.client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
            )
            logger.info("LLM client initialized. Model: %s", self.model)
        except Exception as e:
            logger.error("Error initializing LLM client: %s", e)
            self.client = None

    VALID_ACTIONS = {
        "expert_answer", "create_object", "open_list", "open_form",
        "find_object", "prepare_payment", "accrual_writeoff",
        "warehouse_move", "employee_info", "get_dossier",
        "get_status", "get_stock", "get_debtors", "run_analytics",
        "create_kanban_task", "show_kanban", "update_metadata",
    }

    def _sanitize_json(self, text: str) -> str:
        text = re.sub(r'//.*?$', '', text, flags=re.MULTILINE)
        text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
        text = re.sub(r",\s*([}\]])", r"\1", text)
        text = re.sub(r"'", '"', text)
        text = re.sub(r'(\w+)\s*:', r'"\1":', text, count=0)
        return text

    def _extract_json(self, text: str) -> dict | None:
        match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            candidate = match.group(1)
            for attempt in (candidate, self._sanitize_json(candidate)):
                try:
                    return json.loads(attempt)
                except json.JSONDecodeError:
                    continue

        start = text.find('{')
        if start == -1:
            return None
        depth = 0
        candidates = []
        for i, ch in enumerate(text[start:], start):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
            if depth == 0:
                candidates.append(text[start:i+1])
                start = text.find('{', i + 1)
                if start == -1:
                    break
                depth = 0

        for candidate in candidates:
            for attempt in (candidate, self._sanitize_json(candidate)):
                try:
                    return json.loads(attempt)
                except json.JSONDecodeError:
                    try:
                        return json.loads(attempt.replace('{{', '{').replace('}}', '}'))
                    except json.JSONDecodeError:
                        continue
        return None

    async def generate_response(self, messages: list, context: str = None) -> dict:
        """
        Генерация ответа через OpenRouter API.
        messages — полная история диалога (список объектов с .role и .text).
        """
        if not self.client:
            return {
                "text": "Ошибка: API клиент не инициализирован. Проверьте ключ API.",
                "action": None,
                "data": None
            }

        # Последнее сообщение пользователя для RAG
        user_message_text = messages[-1].text
        
        # 1. Поиск кандидатов (RAG) — по последнему сообщению
        candidates = metadata_service.find_top_matches(user_message_text, top_k=7)
        
        candidates_str = ""
        if candidates:
            candidates_str = "ДОСТУПНЫЕ ОБЪЕКТЫ 1С:\n"
            for c in candidates:
                fields_str = ""
                if "fields" in c and c["fields"]:
                    field_parts = []
                    for f in c["fields"][:8]:
                        part = f["name"]
                        if f.get("type"):
                            part += "[" + f["type"] + "]"
                        field_parts.append(part)
                    fields_str = " (Поля: " + ", ".join(field_parts) + ")"
                candidates_str += f"- {c['name']} (Синоним: {c['synonym']}){fields_str}\n"
        else:
            candidates_str = "Список объектов пуст."

        current_context_str = f"ТЕКУЩИЙ КОНТЕКСТ 1С: {context}\n" if context else ""

        system_prompt = f"""Ты - Продвинутый ИИ-Ассистент и Бизнес-Консультант для конфигурации 1С:УНФ.
Твоя задача - четко разделять вопросы о **МЕТОДОЛОГИИ** и команды на **ИСПОЛНЕНИЕ**.

ПРАВИЛА ОПРЕДЕЛЕНИЯ НАМЕРЕНИЙ (INTENT):
1. **КОНСУЛЬТАЦИЯ (expert_answer)**:
   - Если пользователь спрашивает "Как...", "Зачем...", "Каков порядок...", "Расскажи про правила...".
   - ТВОЕ ДЕЙСТВИЕ: Дай подробный совет. В конце ответа ОБЯЗАТЕЛЬНО спроси, нужно ли подготовить документ для этого.
   - Поля 'fields' для создания: 'Client' (Контрагент), 'Item' (Номенклатура), 'Quantity' (Количество), 'Amount' (Сумма), 'BankAccount' (Банковский счет), 'Warehouse' (Склад), 'Number' (Номер документа).
   - Если пользователь просит создать "Клиента", "Поставщика" или "Контрагента" - используй `Справочник.Контрагенты`.
   - Всегда проверяй список доступных типов (CANDIDATES).
   - ПРИМЕР: "Для оформления возврата нужно... Желаете, чтобы я подготовил черновик документа 'Расходная накладная' с видом операции 'Возврат'?"
   - В JSON: action="expert_answer".

2. **ИСПОЛНЕНИЕ (create_object / find_object / etc.)**:
   - Если пользователь говорит "Создай", "Продай", "Оформи", "Сделай", или явно подтверждает твое предложение ("Да, делай").
   - ТВОЕ ДЕЙСТВИЕ: Переходи к выполнению команды.
   - В JSON: action="create_object" (или другой подходящий).

3. **ЗАДАЧА В КАНБАН (create_kanban_task)**:
   - Если пользователь просит добавить задачу, поставить задачу сотруднику, запланировать работу.
   - Ключевые фразы: "Добавь задачу", "Поставь задачу", "Запланируй", "Создай задачу", "Добавь в канбан", "Нужно сделать".
   - ТВОЕ ДЕЙСТВИЕ: Сформируй данные задачи для канбан-доски.
   - В JSON: action="create_kanban_task", data содержит поля задачи.
   - Колонки: "todo" (К выполнению), "in_progress" (В работе), "review" (На проверке), "done" (Готово).
   - Приоритеты: "low", "medium", "high", "urgent".
   - Если не указана колонка — ставь "todo". Если не указан приоритет — "medium".

{current_context_str}
{candidates_str}

ТВОИ ВОЗМОЖНОСТИ (ACTION):
- "create_object": Создать новую карточку (Справочник) или новый Документ.
- "open_list": Открыть список документов или справочников.
- "open_form": Открыть конкретную форму отчета, обработки или настройки.
- "find_object": Найти существующий объект по номеру/коду. data: {{"type": "...", "number": "..."}}
- "prepare_payment": (ДЕНЬГИ) Подготовить платежное поручение или расход из кассы.
- "accrual_writeoff": (ДЕНЬГИ) Оформить начисление или списание (налоги, бонусы, расходы).
- "warehouse_move": (СКЛАД) Подготовить перемещение запасов между складами.
- "employee_info": (ПЕРСОНАЛ) Показать данные сотрудника.
- "get_dossier": (ДОСЬЕ) Собрать полное досье по контрагенту или номенклатуре. data: {{"type": "Справочник.Контрагенты", "fields": {{"Client": "ИмяКлиента"}}}}
- "get_status": (СТАТУС) Узнать статус документа (проведён/не проведён). data: {{"type": "Документ.ЗаказПокупателя", "number": "32"}}
- "get_stock": (СКЛАД) Узнать остаток товара на складе. data: {{"fields": {{"Item": "НазваниеТовара"}}}}
- "get_debtors": (ФИНАНСЫ) Показать список должников / дебиторскую задолженность. data: {{}}
- "run_analytics": (АНАЛИТИКА) Выполнить расчет. data: {{"query": "описание запроса", "period": "today|week|month|year", "filter": "Контрагент или Товар"}}
- "create_kanban_task": (КАНБАН) Создать задачу на канбан-доске. data: {{"title": "Название задачи", "description": "Описание", "column": "todo|in_progress|review|done", "priority": "low|medium|high|urgent", "assignee": "Имя сотрудника", "due_date": "YYYY-MM-DD", "tags": ["тег1", "тег2"]}}
- "show_kanban": (КАНБАН) Показать канбан-доску со всеми задачами. data: {{}}

ФОРМАТ ОТВЕТА (строго JSON, без markdown-блоков вокруг):
{{
  "text": "Текст ответа (консультация или подтверждение действия).",
  "action": "...",
  "data": {{ ... }}
}}

FEW-SHOT ПРИМЕРЫ:
- "Проведён ли заказ 32?" → {{"text": "Проверяю статус заказа №32...", "action": "get_status", "data": {{"type": "Документ.ЗаказПокупателя", "number": "32"}}}}
- "Сколько ноутбуков на складе?" → {{"text": "Запрашиваю остатки...", "action": "get_stock", "data": {{"fields": {{"Item": "Ноутбук"}}}}}}
- "Покажи должников" → {{"text": "Формирую список дебиторов...", "action": "get_debtors", "data": {{}}}}
- "Продажи за месяц" → {{"text": "Считаю продажи за месяц...", "action": "run_analytics", "data": {{"query": "продажи", "period": "month"}}}}
- "Продажи по клиенту Ромашка" → {{"text": "Считаю продажи...", "action": "run_analytics", "data": {{"query": "продажи", "filter": "Ромашка"}}}}
- "Добавь задачу: подготовить отчёт по продажам для Иванова до пятницы" → {{"text": "Создаю задачу на канбан-доске...", "action": "create_kanban_task", "data": {{"title": "Подготовить отчёт по продажам", "description": "Подготовить отчёт по продажам для Иванова", "column": "todo", "priority": "medium", "assignee": "Иванов", "due_date": "2026-04-24", "tags": ["отчёт", "продажи"]}}}}
- "Поставь задачу срочно — проверить остатки на складе" → {{"text": "Создаю срочную задачу...", "action": "create_kanban_task", "data": {{"title": "Проверить остатки на складе", "description": "Срочная проверка складских остатков", "column": "todo", "priority": "urgent", "tags": ["склад", "срочно"]}}}}
- "Покажи канбан доску" → {{"text": "Загружаю канбан-доску...", "action": "show_kanban", "data": {{}}}}
- "Какие задачи в работе?" → {{"text": "Показываю канбан-доску...", "action": "show_kanban", "data": {{}}}}

ВАЖНО: Ответ ВСЕГДА только JSON объект. Если дал совет (expert_answer), всегда предлагай СЛЕДУЮЩИЙ ШАГ.
"""

        # Формируем историю диалога для API (до 10 последних сообщений)
        messages_payload = [{"role": "system", "content": system_prompt}]
        
        # Берём последние 10 сообщений для контекста истории
        recent_messages = messages[-10:] if len(messages) > 10 else messages
        for msg in recent_messages:
            role = "user" if msg.role == "user" else "assistant"
            messages_payload.append({"role": role, "content": msg.text})
        
        try:
            completion = await asyncio.to_thread(
                self.client.chat.completions.create,
                extra_headers={
                    "HTTP-Referer": "http://localhost:8000",
                    "X-Title": "1C-AI-Assistant-Expert",
                } if "openrouter" in self.base_url else {},
                model=self.model,
                messages=messages_payload,
                temperature=0.3,
                max_tokens=1500
            )
            
            generated_text = completion.choices[0].message.content
            logger.debug("LLM Output: %s", generated_text)
            
            parsed = self._extract_json(generated_text)
            if parsed:
                action = parsed.get("action", "")
                if action and action not in self.VALID_ACTIONS:
                    logger.warning("Unknown action '%s', falling back to expert_answer", action)
                    parsed["text"] = parsed.get("text", "") + f"\n(Неизвестное действие: {action})"
                    parsed["action"] = "expert_answer"
                    parsed["data"] = None

                user_lower = user_message_text.lower()

                if parsed.get("action") == "expert_answer":
                    is_show = any(kw in user_lower for kw in ["канбан", "доск", "задач"]) and any(kw in user_lower for kw in ["покажи", "показ", "отобраз", "список", "какие", "открыть", "посмотри"])
                    is_create = any(kw in user_lower for kw in ["создай задач", "добавь задач", "поставь задач", "запланируй задач"])

                    if is_show:
                        parsed["action"] = "show_kanban"
                        parsed["data"] = {}
                        logger.debug("Post-processed: expert_answer -> show_kanban")
                    elif is_create:
                        parsed["action"] = "create_kanban_task"
                        if not parsed.get("data"):
                            parsed["data"] = {"title": user_message_text[:100]}
                        logger.debug("Post-processed: expert_answer -> create_kanban_task")

                return parsed
            else:
                clean_text = re.sub(r'[{}\[\]"]', '', generated_text)
                clean_text = re.sub(r'\b(text|action|data)\s*:', '', clean_text)
                clean_text = clean_text.strip()
                return {
                    "text": clean_text or generated_text[:500],
                    "action": "expert_answer",
                    "data": None
                }
                
        except Exception as e:
            logger.error("LLM API Error: %s", e)
            return {
                "text": f"Ошибка нейросети: {e}",
                "action": None,
                "data": None
            }

llm_service = LLMService()
