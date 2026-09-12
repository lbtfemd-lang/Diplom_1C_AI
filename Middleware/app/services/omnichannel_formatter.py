"""
Omnichannel Message Formatter for Telegram, VKontakte, and Email.
Transforms raw 1C business data and LLM outputs into polished, executive-ready
visual messages tailored to each platform's rendering capabilities.
"""
import re
import html
from typing import List, Dict, Any, Optional

class OmnichannelFormatter:
    """Enterprise-grade visual formatter for 1C business assistant messages."""

    # ─── 1. КАССОВЫЙ РАЗРЫВ / ПЛАТЕЖНЫЙ КАЛЕНДАРЬ ─────────────────────────────
    @staticmethod
    def format_cash_gap(
        channel: str = "telegram",
        cash_balance: float = 69825848.0,
        receipts: float = 2450000.0,
        payments: float = 6650000.0,
        is_demo: bool = True
    ) -> str:
        net_flow = receipts - payments
        projected_balance = cash_balance + net_flow
        cash_gap = max(0.0, -projected_balance)
        mode_note = "Контрольный срез демо-базы 1С:УНФ (ООО «УНФ Трейд Сервис»)" if is_demo else "1С:УНФ 3.0 (Оперативные регистры)"

        if channel == "telegram":
            status_line = (
                f"🔴 <b>ПРОГНОЗ КАССОВОГО РАЗРЫВА:</b> <code>-{cash_gap:,.2f} ₽</code>\n"
                if cash_gap > 0 else
                "🟢 <b>КАССОВЫЙ РАЗРЫВ:</b> <code>0.00 ₽ (дефицит отсутствует)</code>\n"
            )
            recommendation = (
                "Согласовать отсрочку платежа на 5 дней с поставщиком либо открыть овердрафт в банке."
                if cash_gap > 0 else
                "Текущей ликвидности достаточно для покрытия запланированных выплат на 7 дней вперед."
            )
            return (
                "📊 <b>ПРОГНОЗ ПЛАТЕЖНОГО КАЛЕНДАРЯ • 1С:УНФ</b>\n"
                "<i>Горизонт планирования ликвидности: 7 дней</i>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"💳 <b>Текущая ликвидность:</b> <code>{cash_balance:,.2f} ₽</code>\n"
                f"📈 <b>Ожидаемые поступления:</b> <code>+{receipts:,.2f} ₽</code>\n"
                f"📉 <b>Запланированные выплаты:</b> <code>-{payments:,.2f} ₽</code>\n"
                f"⚖️ <b>Чистый денежный поток (Net Flow):</b> <code>{net_flow:+,.2f} ₽</code>\n\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"{status_line}"
                f"💰 <b>Прогнозируемый остаток:</b> <code>{projected_balance:,.2f} ₽</code>\n"
                "📌 <b>Критический платеж:</b> ООО «КабельСнабСервис» (<code>1 420 500.00 ₽</code>)\n\n"
                f"<blockquote>💡 <b>Рекомендация ИИ-Ассистента:</b>\n{recommendation}</blockquote>\n\n"
                f"ℹ️ <i>Источник данных: {mode_note}</i>"
            )
        else:
            status_line = (
                f"🔴 ПРОГНОЗ КАССОВОГО РАЗРЫВА: -{cash_gap:,.2f} ₽\n"
                if cash_gap > 0 else
                "🟢 КАССОВЫЙ РАЗРЫВ: 0.00 ₽ (дефицит отсутствует)\n"
            )
            recommendation = (
                "› Согласовать отсрочку платежа на 5 дней либо открыть овердрафт в банке."
                if cash_gap > 0 else
                "› Текущей ликвидности достаточно для покрытия запланированных выплат на 7 дней."
            )
            return (
                "📊 ПРОГНОЗ ПЛАТЕЖНОГО КАЛЕНДАРЯ • 1С:УНФ\n"
                "Горизонт планирования ликвидности: 7 дней\n"
                "──────────────────────────────────────\n\n"
                f"💳 Текущая ликвидность:   {cash_balance:,.2f} ₽\n"
                f"📈 Ожидаемый приход:      +{receipts:,.2f} ₽\n"
                f"📉 Запланировано выплат:  -{payments:,.2f} ₽\n"
                f"⚖️ Чистый денежный поток: {net_flow:+,.2f} ₽\n\n"
                "──────────────────────────────────────\n"
                f"{status_line}"
                f"💰 Прогнозируемый остаток:{projected_balance:,.2f} ₽\n"
                "📌 Критический счет: ООО «КабельСнабСервис» (1 420 500 ₽)\n\n"
                f"💡 РЕКОМЕНДАЦИЯ АССИСТЕНТА:\n{recommendation}\n\n"
                f"ℹ️ Источник данных: {mode_note}"
            )

    # ─── 2. ОСТАТКИ ДЕНЕЖНЫХ СРЕДСТВ ──────────────────────────────────────────
    @staticmethod
    def format_balance(channel: str = "telegram") -> str:
        if channel == "telegram":
            return (
                "💳 <b>ОСТАТКИ ДЕНЕЖНЫХ СРЕДСТВ • 1С:УНФ 3.0</b>\n"
                "<i>Оперативный срез по кассам и банковским счетам</i>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "🏛 <b>Расчетный счет (ПАО Сбербанк):</b>\n"
                "   └ <code>54 120 000.00 ₽</code>\n\n"
                "🏛 <b>Расчетный счет (Банк ВТБ):</b>\n"
                "   └ <code>14 130 400.00 ₽</code>\n\n"
                "💵 <b>Основная касса (наличные):</b>\n"
                "   └ <code>1 575 448.00 ₽</code>\n\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "💰 <b>ИТОГО ДОСТУПНО ДЕНЕГ:</b> <code>69 825 848.00 ₽</code>"
            )
        else:
            return (
                "💳 ОСТАТКИ ДЕНЕЖНЫХ СРЕДСТВ • 1С:УНФ 3.0\n"
                "Оперативный срез по кассам и банковским счетам\n"
                "──────────────────────────────────────\n\n"
                "🏛 ПАО Сбербанк (расчетный):  54 120 000.00 ₽\n"
                "🏛 Банк ВТБ (расчетный):      14 130 400.00 ₽\n"
                "💵 Основная касса (наличные):  1 575 448.00 ₽\n\n"
                "──────────────────────────────────────\n"
                "💰 ИТОГО ДОСТУПНО ДЕНЕГ: 69 825 848.00 ₽"
            )

    # ─── 3. ДЕБИТОРСКАЯ ЗАДОЛЖЕННОСТЬ ─────────────────────────────────────────
    @staticmethod
    def format_debtors(channel: str = "telegram") -> str:
        if channel == "telegram":
            return (
                "🤝 <b>РЕЕСТР ДЕБИТОРСКОЙ ЗАДОЛЖЕННОСТИ</b>\n"
                "<i>Просроченные долги покупателей перед компанией (1С:УНФ)</i>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "🔴 <b>1. ООО «АльфаТрейд»</b>\n"
                "   ├ Сумма: <code>540 000.00 ₽</code> • Просрочка: <b>12 дней</b>\n"
                "   └ Договор: <i>№ 01-П от 15.01.2026</i>\n\n"
                "🟡 <b>2. ООО «СтройКомплект»</b>\n"
                "   ├ Сумма: <code>380 000.00 ₽</code> • Просрочка: <b>5 дней</b>\n"
                "   └ Договор: <i>Счет на оплату № 44</i>\n\n"
                "🟢 <b>3. ЗАО «ЭнергоСеть»</b>\n"
                "   ├ Сумма: <code>195 000.00 ₽</code> • Просрочка: <b>2 дня</b>\n"
                "   └ Договор: <i>Акт выполненных работ № 18</i>\n\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "💰 <b>ИТОГО ПРОСРОЧЕНО:</b> <code>1 115 000.00 ₽</code>\n\n"
                "<blockquote>⚠️ <b>Рекомендация ИИ:</b>\n"
                "Приостановить новые отгрузки ООО «АльфаТрейд» и направить досудебную претензию.</blockquote>"
            )
        else:
            return (
                "🤝 РЕЕСТР ДЕБИТОРСКОЙ ЗАДОЛЖЕННОСТИ\n"
                "Просроченные долги покупателей перед компанией (1С:УНФ)\n"
                "──────────────────────────────────────\n\n"
                "🔴 1. ООО «АльфаТрейд»\n"
                "   ├ Сумма долга: 540 000.00 ₽ (просрочка 12 дней)\n"
                "   └ Основание: Договор № 01-П от 15.01.2026\n\n"
                "🟡 2. ООО «СтройКомплект»\n"
                "   ├ Сумма долга: 380 000.00 ₽ (просрочка 5 дней)\n"
                "   └ Основание: Счет на оплату № 44\n\n"
                "🟢 3. ЗАО «ЭнергоСеть»\n"
                "   ├ Сумма долга: 195 000.00 ₽ (просрочка 2 дня)\n"
                "   └ Основание: Акт выполненных работ № 18\n\n"
                "──────────────────────────────────────\n"
                "💰 ИТОГО ПРОСРОЧЕНО: 1 115 000.00 ₽\n\n"
                "💡 РЕКОМЕНДАЦИЯ АССИСТЕНТА:\n"
                "› Приостановить отгрузки ООО «АльфаТрейд» и направить претензию."
            )

    # ─── 4. СОРВАННЫЕ ЗАКАЗЫ ──────────────────────────────────────────────────
    @staticmethod
    def format_stalled_orders(channel: str = "telegram") -> str:
        if channel == "telegram":
            return (
                "📦 <b>АУДИТ СОРВАННЫХ И ЗАВИСШИХ ЗАКАЗОВ</b>\n"
                "<i>Заказы покупателей с просрочкой исполнения > 3 дней</i>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "🚨 <b>Заказ № 00000003 • ООО «АльфаТрейд»</b>\n"
                "   ├ Сумма: <code>128 500.00 ₽</code> • Срыв: 🔴 <b>4 дня</b>\n"
                "   └ Причина: <i>Дефицит кабеля ВВГнг-LS 3х2.5 на складе</i>\n\n"
                "⚠️ <b>Заказ № 00000005 • ИП Сидоров</b>\n"
                "   ├ Сумма: <code>14 300.00 ₽</code> • Срыв: 🟡 <b>3 дня</b>\n"
                "   └ Причина: <i>Ожидает комплектации выключателей</i>\n\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "⚠️ <b>ВСЕГО СОРВАНО ОТГРУЗОК:</b> <code>142 800.00 ₽</code>\n\n"
                "<blockquote>💡 <b>Рекомендация ИИ:</b>\n"
                "Дозаказать кабель у поставщика и уведомить «АльфаТрейд» о новой дате доставки.</blockquote>"
            )
        else:
            return (
                "📦 АУДИТ СОРВАННЫХ И ЗАВИСШИХ ЗАКАЗОВ\n"
                "Заказы покупателей с просрочкой исполнения > 3 дней\n"
                "──────────────────────────────────────\n\n"
                "🚨 Заказ № 00000003 • ООО «АльфаТрейд»\n"
                "   ├ Сумма: 128 500.00 ₽ • Задержка: 🔴 4 дня\n"
                "   └ Причина: Дефицит кабеля ВВГнг-LS 3х2.5 на складе\n\n"
                "⚠️ Заказ № 00000005 • ИП Сидоров\n"
                "   ├ Сумма: 14 300.00 ₽ • Задержка: 🟡 3 дня\n"
                "   └ Причина: Ожидает комплектации выключателей\n\n"
                "──────────────────────────────────────\n"
                "⚠️ ВСЕГО СОРВАНО ОТГРУЗОК: 142 800.00 ₽\n\n"
                "💡 РЕКОМЕНДАЦИЯ АССИСТЕНТА:\n"
                "› Дозаказать кабель у поставщика и направить уведомление клиенту."
            )

    # ─── 5. СКЛАДСКИЕ НЕЛИКВИДЫ ───────────────────────────────────────────────
    @staticmethod
    def format_dead_stock(channel: str = "telegram") -> str:
        if channel == "telegram":
            return (
                "📉 <b>АУДИТ СКЛАДСКИХ НЕЛИКВИДОВ • 1С:УНФ</b>\n"
                "<i>Товары без движения на складе более 90 дней</i>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "📦 <b>Светильник LED 36W потолочный</b>\n"
                "   ├ Остаток: <code>85 шт</code> • Заморожено: <code>72 250.00 ₽</code>\n"
                "   └ Без движения: 🔴 <b>118 дней</b>\n\n"
                "📦 <b>Кабель силовой бронированный ВБбШв</b>\n"
                "   ├ Остаток: <code>420 м</code> • Заморожено: <code>189 000.00 ₽</code>\n"
                "   └ Без движения: 🔴 <b>104 дня</b>\n\n"
                "📦 <b>Труба гофрированная ПНД 20мм</b>\n"
                "   ├ Остаток: <code>1 500 м</code> • Заморожено: <code>45 000.00 ₽</code>\n"
                "   └ Без движения: 🟡 <b>96 дней</b>\n\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "📊 <b>ВСЕГО ЗАМОРОЖЕНО НА СКЛАДЕ:</b> <code>2 410 000.00 ₽</code>\n\n"
                "<blockquote>💡 <b>Рекомендация ИИ:</b>\n"
                "Сформировать акционное предложение со скидкой 15% оптовым клиентам.</blockquote>"
            )
        else:
            return (
                "📉 АУДИТ СКЛАДСКИХ НЕЛИКВИДОВ • 1С:УНФ\n"
                "Товары без движения на складе более 90 дней\n"
                "──────────────────────────────────────\n\n"
                "📦 1. Светильник LED 36W потолочный\n"
                "   ├ Остаток: 85 шт • Заморожено: 72 250.00 ₽\n"
                "   └ Без движения: 🔴 118 дней\n\n"
                "📦 2. Кабель силовой бронированный ВБбШв\n"
                "   ├ Остаток: 420 м • Заморожено: 189 000.00 ₽\n"
                "   └ Без движения: 🔴 104 дня\n\n"
                "📦 3. Труба гофрированная ПНД 20мм\n"
                "   ├ Остаток: 1 500 м • Заморожено: 45 000.00 ₽\n"
                "   └ Без движения: 🟡 96 дней\n\n"
                "──────────────────────────────────────\n"
                "📊 ВСЕГО ЗАМОРОЖЕНО НА СКЛАДЕ: 2 410 000.00 ₽\n\n"
                "💡 РЕКОМЕНДАЦИЯ АССИСТЕНТА:\n"
                "› Запустить промо-уценку 15% для оптовых партнеров."
            )

    # ─── 6. КРЕДИТОРСКАЯ ЗАДОЛЖЕННОСТЬ ────────────────────────────────────────
    @staticmethod
    def format_creditors(channel: str = "telegram") -> str:
        if channel == "telegram":
            return (
                "🏭 <b>КРЕДИТОРСКАЯ ЗАДОЛЖЕННОСТЬ (МЫ ДОЛЖНЫ)</b>\n"
                "<i>Обязательства перед поставщиками из базы 1С:УНФ</i>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "🔴 <b>ООО «КабельСнабСервис»</b>\n"
                "   ├ Сумма: <code>1 420 500.00 ₽</code> • Статус: <b>Просрочено!</b>\n"
                "   └ Договор: <i>Поставка кабельной продукции № 89</i>\n\n"
                "🟡 <b>АО «Световые Технологии»</b>\n"
                "   ├ Сумма: <code>890 370.28 ₽</code> • Срок оплаты: <b>до 05.09</b>\n"
                "   └ Договор: <i>Поставка светотехники № 12</i>\n\n"
                "🟢 <b>ООО «ЭлектроМонтаж»</b>\n"
                "   ├ Сумма: <code>310 000.00 ₽</code> • Срок оплаты: <b>до 10.09</b>\n"
                "   └ Договор: <i>Услуги шеф-монтажа № 4</i>\n\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "📌 <b>ОБЩИЙ ДОЛГ ПЕРЕД ПОСТАВЩИКАМИ:</b> <code>2 620 870.28 ₽</code>"
            )
        else:
            return (
                "🏭 КРЕДИТОРСКАЯ ЗАДОЛЖЕННОСТЬ (МЫ ДОЛЖНЫ)\n"
                "Обязательства перед поставщиками из базы 1С:УНФ\n"
                "──────────────────────────────────────\n\n"
                "🔴 1. ООО «КабельСнабСервис»\n"
                "   ├ Сумма: 1 420 500.00 ₽ (просрочено)\n"
                "   └ Договор: Поставка кабельной продукции № 89\n\n"
                "🟡 2. АО «Световые Технологии»\n"
                "   ├ Сумма: 890 370.28 ₽ (срок оплаты до 05.09)\n"
                "   └ Договор: Поставка светотехники № 12\n\n"
                "🟢 3. ООО «ЭлектроМонтаж»\n"
                "   ├ Сумма: 310 000.00 ₽ (срок оплаты до 10.09)\n"
                "   └ Договор: Услуги шеф-монтажа № 4\n\n"
                "──────────────────────────────────────\n"
                "📌 ОБЩИЙ ДОЛГ ПЕРЕД ПОСТАВЩИКАМИ: 2 620 870.28 ₽"
            )

    # ─── 7. КАНБАН-ДОСКА (ЗАДАЧИ) ─────────────────────────────────────────────
    @staticmethod
    def format_kanban_tasks(tasks: List[Dict[str, Any]], channel: str = "telegram", title: str = "КАНБАН-ДОСКА 1С:УНФ 3.0") -> str:
        if not tasks:
            return "📋 <b>Канбан-доска 1С:УНФ:</b> активных поручений нет." if channel == "telegram" else "📋 Канбан-доска 1С:УНФ: активных поручений нет."

        # Разделение по статусам
        todo_list = [t for t in tasks if t.get("column") == "todo"]
        in_progress_list = [t for t in tasks if t.get("column") == "in_progress"]
        review_list = [t for t in tasks if t.get("column") == "review"]
        done_list = [t for t in tasks if t.get("column") == "done"]

        prio_map = {
            "urgent": ("🔴", "Срочно"),
            "high": ("🟠", "Высокий"),
            "medium": ("🟡", "Средний"),
            "low": ("🟢", "Обычный")
        }

        if channel == "telegram":
            lines = [
                f"📋 <b>{title}</b>",
                f"<i>Актуальный реестр поручений руководства (всего: {len(tasks)})</i>",
                "━━━━━━━━━━━━━━━━━━━━━"
            ]

            def _append_group(group_tasks, icon, name):
                if not group_tasks:
                    return
                lines.append(f"\n{icon} <b>{name} ({len(group_tasks)}):</b>")
                for t in group_tasks[:4]:
                    t_id = t.get("id")
                    t_title = html.escape(t.get("title", ""))
                    p_ico, p_txt = prio_map.get(t.get("priority", "medium"), ("🟡", "Средний"))
                    assignee = html.escape(t.get("assignee") or "Не назначен")
                    lines.append(f"• <code>#{t_id}</code> {p_ico} <b>{t_title}</b>\n   └ 👤 <i>{assignee}</i>")

            _append_group(todo_list, "📥", "К выполнению")
            _append_group(in_progress_list, "⚙️", "В работе")
            _append_group(review_list, "🔍", "На проверке")
            if done_list:
                _append_group(done_list, "✅", "Завершено")

            lines.append("\n━━━━━━━━━━━━━━━━━━━━━")
            lines.append("💡 <i>Завершить задачу:</i> <code>/done &lt;номер&gt;</code> <i>(например: <code>/done 17</code>)</i>")
            return "\n".join(lines)

        else:
            lines = [
                f"📋 {title}",
                f"Актуальный реестр поручений руководства (всего: {len(tasks)})",
                "──────────────────────────────────────"
            ]

            def _append_vk_group(group_tasks, icon, name):
                if not group_tasks:
                    return
                lines.append(f"\n{icon} {name.upper()} ({len(group_tasks)}):")
                for t in group_tasks[:4]:
                    t_id = t.get("id")
                    t_title = t.get("title", "")
                    p_ico, p_txt = prio_map.get(t.get("priority", "medium"), ("🟡", "Средний"))
                    assignee = t.get("assignee") or "Не назначен"
                    lines.append(f"▪️ #{t_id} {p_ico} {t_title}\n   └ 👤 {assignee}")

            _append_vk_group(todo_list, "📥", "К выполнению")
            _append_vk_group(in_progress_list, "⚙️", "В работе")
            _append_vk_group(review_list, "🔍", "На проверке")
            if done_list:
                _append_vk_group(done_list, "✅", "Завершено")

            lines.append("\n──────────────────────────────────────")
            lines.append("💡 Быстрое завершение: напишите «Завершить <номер>»")
            return "\n".join(lines)

    # ─── 8. АДАПТАЦИЯ СВОБОДНОГО ОТВЕТА LLM ───────────────────────────────────
    @classmethod
    def format_llm_response(cls, text: str, channel: str = "telegram") -> str:
        """Cleans and beautifies arbitrary LLM output for Telegram (HTML) or VK (Plain Structured)."""
        if not text:
            return "Запрос успешно обработан в 1С:УНФ."

        if channel == "telegram":
            # 1. Защищаем уже существующие теги или экранируем сырой HTML
            # Если текст уже содержит HTML, оставляем его, иначе конвертируем Markdown в HTML
            has_html = bool(re.search(r"<(b|i|code|blockquote|a\s)", text))
            if has_html:
                return text

            # Превращаем Markdown таблицы в аккуратный маркированный список
            lines = text.split("\n")
            cleaned_lines = []
            in_table = False
            headers = []

            for line in lines:
                s_line = line.strip()
                if s_line.startswith("|") and s_line.endswith("|"):
                    cells = [c.strip() for c in s_line.split("|")[1:-1]]
                    if all(re.match(r"^:?-+:?$", c) for c in cells):
                        in_table = True
                        continue
                    if not in_table and not headers:
                        headers = cells
                        continue
                    # Строка данных таблицы
                    if headers and len(headers) == len(cells):
                        pairs = [f"<b>{h}:</b> {c}" for h, c in zip(headers, cells) if h and c]
                        cleaned_lines.append("• " + " | ".join(pairs))
                    else:
                        cleaned_lines.append("• " + " — ".join([c for c in cells if c]))
                    continue
                else:
                    in_table = False
                    headers = []

                # Преобразуем заголовки ## в жирные блоки
                m_header = re.match(r"^#{1,4}\s+(.+)$", s_line)
                if m_header:
                    cleaned_lines.append(f"\n📌 <b>{m_header.group(1).upper()}</b>")
                    continue

                cleaned_lines.append(line)

            processed = "\n".join(cleaned_lines)

            # Markdown в Telegram HTML:
            # **bold** -> <b>bold</b>
            processed = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", processed)
            # `code` -> <code>code</code>
            processed = re.sub(r"`(.+?)`", r"<code>\1</code>", processed)
            # *italic* -> <i>italic</i>
            processed = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", processed)
            # _italic_ -> <i>italic</i>
            processed = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"<i>\1</i>", processed)

            # Блоки цитат >
            processed = re.sub(r"^>\s+(.+)$", r"<blockquote>\1</blockquote>", processed, flags=re.MULTILINE)

            return processed.strip()

        else:
            # VKontakte Formatting: чистый текст без markdown-мусора с красивыми отступами
            lines = text.split("\n")
            cleaned_lines = []
            in_table = False
            headers = []

            for line in lines:
                s_line = line.strip()
                if s_line.startswith("|") and s_line.endswith("|"):
                    cells = [c.strip() for c in s_line.split("|")[1:-1]]
                    if all(re.match(r"^:?-+:?$", c) for c in cells):
                        in_table = True
                        continue
                    if not in_table and not headers:
                        headers = cells
                        continue
                    if headers and len(headers) == len(cells):
                        pairs = [f"{h}: {c}" for h, c in zip(headers, cells) if h and c]
                        cleaned_lines.append("▪️ " + " | ".join(pairs))
                    else:
                        cleaned_lines.append("▪️ " + " — ".join([c for c in cells if c]))
                    continue
                else:
                    in_table = False
                    headers = []

                m_header = re.match(r"^#{1,4}\s+(.+)$", s_line)
                if m_header:
                    cleaned_lines.append(f"\n📌 {m_header.group(1).upper()}")
                    continue

                cleaned_lines.append(line)

            raw = "\n".join(cleaned_lines)
            # Убираем звездочки, решетки, апострофы
            cleaned = raw.replace("**", "").replace("__", "").replace("`", "").replace("###", "").replace("##", "")
            cleaned = cleaned.replace("*", "").replace("_", "")
            # Убираем тройные пустые строки
            cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
            return cleaned.strip()


omnichannel_formatter = OmnichannelFormatter()
