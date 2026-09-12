# -*- coding: utf-8 -*-
"""
StockRebalancingService — Сервис автоматического расчета запасов, точек возобновления заказа (ROP),
экономичного размера партии Уилсона (EOQ) и выявления неликвидов для 1С:УНФ 3.0.
Автоматически генерирует структурированный JSON документа «ЗаказПоставщику».
"""

import math
import datetime
import logging
from typing import List, Dict, Any, Optional

from app.models.stock_models import (
    InventoryAnalysisRequest, InventoryAnalysisResponse, StockItemInput,
    StockRecommendation, StockStatusEnum
)

logger = logging.getLogger(__name__)


class StockRebalancingService:
    def analyze_inventory(self, req: InventoryAnalysisRequest) -> InventoryAnalysisResponse:
        recommendations: List[StockRecommendation] = []
        deficit_count = 0
        dead_stock_count = 0
        total_frozen_capital = 0.0
        total_reorder_budget = 0.0

        for item in req.items:
            # 1. Расчет спроса в период поставки (Lead Time Demand)
            ltd = item.daily_sales_avg * item.lead_time_days

            # 2. Расчет страхового запаса (Safety Stock)
            # Формула: SS = Z * StdDev * sqrt(LeadTime)
            if item.daily_sales_std > 0:
                safety_stock = req.service_level_z * item.daily_sales_std * math.sqrt(item.lead_time_days)
            else:
                # Если дисперсия не задана, берем 3 дня средней реализации в качестве буфера
                safety_stock = item.daily_sales_avg * 3.0

            safety_stock = round(max(0.0, safety_stock), 1)

            # 3. Точка перезаказа ROP (Reorder Point)
            # Формула: ROP = LTD + SS
            rop = round(ltd + safety_stock, 1)

            # 4. Формула Уилсона (EOQ — Economic Order Quantity)
            # EOQ = sqrt((2 * D * S) / H)
            annual_demand = item.daily_sales_avg * 365.0
            holding_cost_per_unit = item.unit_cost * item.annual_holding_cost_rate

            if annual_demand > 0 and holding_cost_per_unit > 0:
                eoq_calc = math.sqrt((2.0 * annual_demand * item.order_fixed_cost) / holding_cost_per_unit)
                eoq = round(max(1.0, eoq_calc), 0)
            else:
                eoq = round(max(1.0, item.daily_sales_avg * 14.0), 0)

            # 5. Классификация статуса запаса
            frozen_rub = 0.0
            recommended_qty = 0.0

            # А. Неликвид (Dead stock)
            if item.days_without_sales >= req.dead_stock_threshold_days:
                status = StockStatusEnum.DEAD_STOCK
                dead_stock_count += 1
                frozen_rub = round(item.current_stock * item.unit_cost, 2)
                total_frozen_capital += frozen_rub
                action_plan = (
                    f"⛔ Неликвид (без движения {item.days_without_sales} дн.). "
                    f"Заморожено {frozen_rub:,.2f} ₽. Запустить распродажу со скидкой 25% или возврат поставщику."
                )

            # Б. Дефицит (Остаток <= ROP)
            elif item.current_stock <= rop:
                status = StockStatusEnum.DEFICIT
                deficit_count += 1
                # Рекомендуемый заказ: доведение до ROP + партия EOQ
                recommended_qty = round(max(eoq, (rop - item.current_stock) + eoq), 0)
                cost = round(recommended_qty * item.unit_cost, 2)
                total_reorder_budget += cost
                action_plan = (
                    f"🚨 ДЕФИЦИТ: Остаток ({item.current_stock:.0f}) ниже точки перезаказа ROP ({rop:.0f}). "
                    f"Сформирован заказ на {recommended_qty:.0f} ед. на сумму {cost:,.2f} ₽."
                )

            # В. Избыточный запас (Остаток > ROP + 2 * EOQ)
            elif item.current_stock > (rop + eoq * 2.0):
                status = StockStatusEnum.SURPLUS
                excess_units = item.current_stock - (rop + eoq)
                frozen_rub = round(excess_units * item.unit_cost, 2)
                total_frozen_capital += frozen_rub
                action_plan = (
                    f"⚠️ Избыток запаса: обеспечение превышает норму. "
                    f"Заморожено излишков на {frozen_rub:,.2f} ₽. Приостановить закупки."
                )

            # Г. Оптимальный остаток
            else:
                status = StockStatusEnum.NORMAL
                action_plan = "✅ Запас сбалансирован. Пополнение не требуется."

            recommendations.append(StockRecommendation(
                sku=item.sku,
                name=item.name,
                current_stock=item.current_stock,
                safety_stock=safety_stock,
                reorder_point_rop=rop,
                economic_order_quantity_eoq=eoq,
                status=status,
                recommended_order_quantity=recommended_qty,
                estimated_purchase_cost=round(recommended_qty * item.unit_cost, 2),
                frozen_capital_rub=frozen_rub,
                action_plan=action_plan,
            ))

        # 6. Формирование 1С-документа «ЗаказПоставщику» для позиций в дефиците
        purchase_order_1c = None
        if req.generate_1c_order and deficit_count > 0:
            lines = []
            line_idx = 1
            total_sum = 0.0
            vat_sum = 0.0

            for rec, inp in zip(recommendations, req.items):
                if rec.status == StockStatusEnum.DEFICIT and rec.recommended_order_quantity > 0:
                    sum_no_vat = round(rec.recommended_order_quantity * inp.unit_cost, 2)
                    vat = round(sum_no_vat * 0.20, 2)
                    line_total = round(sum_no_vat + vat, 2)

                    lines.append({
                        "НомерСтроки": line_idx,
                        "Артикул": rec.sku,
                        "Номенклатура": rec.name,
                        "Количество": rec.recommended_order_quantity,
                        "Цена": inp.unit_cost,
                        "СуммаБезНДС": sum_no_vat,
                        "СтавкаНДС": "20%",
                        "СуммаНДС": vat,
                        "Всего": line_total,
                        "Поставщик": inp.supplier_name or "Основной поставщик",
                    })
                    line_idx += 1
                    total_sum += line_total
                    vat_sum += vat

            now_str = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            purchase_order_1c = {
                "Документ": "ЗаказПоставщику",
                "Статус": "Черновик",
                "Дата": now_str,
                "Организация": "ООО «УНФ Трейд Сервис»",
                "Склад": "Основной склад",
                "Валюта": "руб.",
                "СуммаДокумента": round(total_sum, 2),
                "СуммаНДС": round(vat_sum, 2),
                "Строки": lines,
                "Комментарий": "Черновик подготовлен ИИ-модулем автозаказа по методике ROP/EOQ (Уилсон) для проверки и проведения в 1С",
            }

        summary = (
            f"Анализ складских запасов ({len(req.items)} поз.): "
            f"Дефицит: {deficit_count} поз. (требуется {total_reorder_budget:,.2f} ₽), "
            f"Неликвиды: {dead_stock_count} поз. (заморожено {total_frozen_capital:,.2f} ₽). "
            f"{'Подготовлен черновик документа «Заказ поставщику» для проверки и проведения в 1С.' if purchase_order_1c else ''}"
        )

        return InventoryAnalysisResponse(
            total_items_analyzed=len(req.items),
            deficit_items_count=deficit_count,
            dead_stock_items_count=dead_stock_count,
            total_frozen_capital_rub=round(total_frozen_capital, 2),
            total_reorder_budget_rub=round(total_reorder_budget, 2),
            items=recommendations,
            purchase_order_1c=purchase_order_1c,
            executive_summary=summary,
        )


stock_service = StockRebalancingService()
