# -*- coding: utf-8 -*-
"""
MarginService — Сервис защиты маржинальности и расчета юнит-экономики сделок 1С:УНФ 3.0.
Включает расчет НДС 20%, налога на прибыль, УСН, учет логистики, комиссии менеджера 
и альтернативной стоимости денег при отсрочке платежа (по ключевой ставке ЦБ РФ 21%).
При падении рентабельности ниже установленного порога сделка блокируется с созданием 
задачи на согласование в Канбан-доске 1С.
"""

import logging
from typing import Optional
from app.models.margin_models import (
    DealCalculationRequest, DealCalculationResponse, TaxSystemEnum
)
from app.services.kanban_service import kanban_service

logger = logging.getLogger(__name__)

# Фиксированное учебное допущение, не источник текущей ставки ЦБ.
CBR_KEY_RATE = 0.21


class MarginService:
    def calculate_deal(self, req: DealCalculationRequest, created_by: str = "manager") -> DealCalculationResponse:
        # 1. Расчет базовых показателей строк заказа
        revenue_gross = 0.0
        cost_goods_sold = 0.0

        for item in req.items:
            effective_price = item.selling_price * (1.0 - (item.discount_percent / 100.0))
            item_revenue = item.quantity * effective_price
            item_cost = item.quantity * item.purchase_price

            revenue_gross += item_revenue
            cost_goods_sold += item_cost

        revenue_gross = round(revenue_gross, 2)
        cost_goods_sold = round(cost_goods_sold, 2)
        gross_margin_rub = round(revenue_gross - cost_goods_sold, 2)

        # 2. Стоимость капитала при отсрочке платежа (Cost of Capital Delay)
        # Формула: Выручка * Дни_отсрочки * (Ставка_ЦБ / 365)
        cost_of_capital = 0.0
        if req.payment_delay_days > 0:
            cost_of_capital = round(revenue_gross * req.payment_delay_days * (CBR_KEY_RATE / 365.0), 2)

        # 3. Бонус менеджера по продажам (от валовой маржи)
        sales_commission = 0.0
        if gross_margin_rub > 0:
            sales_commission = round(gross_margin_rub * req.sales_commission_rate, 2)

        # 4. Расчет налогов в зависимости от системы налогообложения
        if req.tax_system == TaxSystemEnum.OSNO:
            # ОСНО: НДС 20% + Налог на прибыль 20%
            # НДС с реализации: Выручка * 20/120
            vat_out = revenue_gross * (20.0 / 120.0)
            # НДС к вычету с закупки: Себестоимость * 20/120
            vat_in = cost_goods_sold * (20.0 / 120.0)
            vat_amount = max(0.0, vat_out - vat_in)

            revenue_net_vat = revenue_gross - vat_out
            cost_net_vat = cost_goods_sold - vat_in

            # Налогооблагаемая прибыль
            ebit = revenue_net_vat - cost_net_vat - req.logistics_cost - sales_commission - cost_of_capital
            profit_tax = max(0.0, ebit * 0.20)
            tax_amount = round(vat_amount + profit_tax, 2)
            vat_amount = round(vat_amount, 2)
            revenue_net_vat = round(revenue_net_vat, 2)

        elif req.tax_system == TaxSystemEnum.USN_INCOME:
            # УСН 6% с выручки (без НДС)
            vat_amount = 0.0
            revenue_net_vat = revenue_gross
            tax_amount = round(revenue_gross * 0.06, 2)

        else: # USN_INCOME_EXPENSE
            # УСН 15% (доходы минус расходы), но не менее 1% от выручки (минимальный налог по НК РФ)
            vat_amount = 0.0
            revenue_net_vat = revenue_gross
            tax_base = max(0.0, revenue_gross - cost_goods_sold - req.logistics_cost - sales_commission - cost_of_capital)
            tax_amount = round(max(revenue_gross * 0.01, tax_base * 0.15), 2)

        # 5. Итоговая чистая прибыль и чистая рентабельность
        net_profit = round(
            revenue_gross - cost_goods_sold - req.logistics_cost - tax_amount - sales_commission - cost_of_capital,
            2
        )

        net_margin_percent = 0.0
        if revenue_gross > 0:
            net_margin_percent = round((net_profit / revenue_gross) * 100.0, 2)

        # 6. Проверка политики маржинальности
        rejection_reasons = []
        if net_profit <= 0:
            rejection_reasons.append(f"Сделка убыточна! Чистый финансовый результат: {net_profit:,.2f} ₽")
        if net_margin_percent < req.min_allowed_margin_percent:
            rejection_reasons.append(
                f"Чистая рентабельность {net_margin_percent:.2f}% ниже минимального норматива {req.min_allowed_margin_percent:.2f}%"
            )
        if cost_of_capital > (net_profit * 0.5) and cost_of_capital > 0:
            rejection_reasons.append(
                f"Высокая стоимость кассовой заморозки при отсрочке {req.payment_delay_days} дн. ({cost_of_capital:,.2f} ₽ съедает более 50% чистой прибыли)"
            )

        is_approved = len(rejection_reasons) == 0
        approval_task_id = None

        # 7. Автоматическое создание задачи в 1С Канбан при пробитии порога
        if not is_approved and req.auto_create_kanban_approval:
            task_desc = (
                f"⚠️ **ТРЕБУЕТСЯ СОГЛАСОВАНИЕ СКИДКИ / УСЛОВИЙ СДЕЛКИ**\n\n"
                f"👤 Клиент: **{req.customer_name}**\n"
                f"💰 Выручка: **{revenue_gross:,.2f} ₽**\n"
                f"📉 Чистая прибыль: **{net_profit:,.2f} ₽** (Маржа: **{net_margin_percent:.2f}%** при лимите {req.min_allowed_margin_percent}%)\n"
                f"🚚 Логистика: {req.logistics_cost:,.2f} ₽ | 🏛 Налоги: {tax_amount:,.2f} ₽\n"
                f"⏳ Отсрочка: {req.payment_delay_days} дн. (потеря на процентах ЦБ: {cost_of_capital:,.2f} ₽)\n\n"
                f"Причины отклонения автоматом:\n• " + "\n• ".join(rejection_reasons)
            )
            created_task = kanban_service.create_task(
                title=f"Согласование маржи: {req.customer_name} ({net_margin_percent:.1f}%)",
                description=task_desc,
                column="todo",
                priority="urgent",
                assignee="Филиппова (CFO)",
                due_date=None,
                tags=["Маржинальность", "СогласованиеСкидки", "1С:Заказ"],
                source="margin_guard",
                department_id=1,
                created_by=created_by,
            )
            approval_task_id = created_task.get("id")

        summary = (
            f"Сделка с {req.customer_name}: Выручка {revenue_gross:,.2f} ₽, "
            f"Себестоимость {cost_goods_sold:,.2f} ₽, Чистая прибыль {net_profit:,.2f} ₽ "
            f"({net_margin_percent:.2f}%). "
            f"Статус: {'✅ Согласовано' if is_approved else '⛔ Заблокировано (отправлено на согласование CFO)'}."
        )

        return DealCalculationResponse(
            customer_name=req.customer_name,
            revenue_gross=revenue_gross,
            revenue_net_vat=revenue_net_vat,
            vat_amount=vat_amount,
            cost_goods_sold=cost_goods_sold,
            gross_margin_rub=gross_margin_rub,
            logistics_cost=req.logistics_cost,
            tax_amount=tax_amount,
            sales_commission=sales_commission,
            cost_of_capital_delay=cost_of_capital,
            net_profit=net_profit,
            net_margin_percent=net_margin_percent,
            is_approved=is_approved,
            rejection_reasons=rejection_reasons,
            approval_task_id=approval_task_id,
            summary=summary,
        )


margin_service = MarginService()
