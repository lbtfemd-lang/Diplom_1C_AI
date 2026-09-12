from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum


class TaxSystemEnum(str, Enum):
    USN_INCOME = "usn_income"                   # УСН Доходы (6%)
    USN_INCOME_EXPENSE = "usn_income_expense"   # УСН Доходы минус расходы (15%)
    OSNO = "osno"                               # ОСНО (НДС 20% + Налог на прибыль 20%)


class DealItem(BaseModel):
    sku: str = Field(..., description="Артикул 1С")
    name: str = Field(..., description="Номенклатура")
    quantity: float = Field(..., gt=0, description="Количество")
    purchase_price: float = Field(..., gt=0, description="Закупочная цена (себестоимость за ед.)")
    selling_price: float = Field(..., gt=0, description="Отпускная цена клиенту за ед.")
    discount_percent: float = Field(0.0, ge=0, le=90, description="Скидка клиенту в %")


class DealCalculationRequest(BaseModel):
    customer_name: str = Field(..., description="Наименование клиента")
    items: List[DealItem] = Field(..., min_length=1, description="Строки заказа / спецификации")
    tax_system: TaxSystemEnum = Field(TaxSystemEnum.OSNO, description="Система налогообложения предприятия")
    logistics_cost: float = Field(0.0, ge=0, description="Транспортные расходы на доставку клиенту")
    sales_commission_rate: float = Field(0.03, ge=0, le=0.5, description="Процент бонуса менеджера от маржи (по умолч. 3%)")
    payment_delay_days: int = Field(0, ge=0, description="Отсрочка платежа в днях (кассовая заморозка)")
    min_allowed_margin_percent: float = Field(15.0, description="Порог минимальной чистой маржинальности сделки в %")
    auto_create_kanban_approval: bool = Field(True, description="Автоматически создавать задачу в Канбан при пробитии порога маржи")


class DealCalculationResponse(BaseModel):
    customer_name: str
    revenue_gross: float = Field(..., description="Общая сумма сделки с НДС")
    revenue_net_vat: float = Field(..., description="Выручка без НДС")
    vat_amount: float = Field(..., description="Сумма НДС к уплате")
    cost_goods_sold: float = Field(..., description="Себестоимость закупки товара")
    gross_margin_rub: float = Field(..., description="Валовая прибыль (Выручка - Себестоимость)")
    logistics_cost: float = Field(..., description="Стоимость доставки")
    tax_amount: float = Field(..., description="Налоги (НДС + налог на прибыль или УСН)")
    sales_commission: float = Field(..., description="Бонус менеджера")
    cost_of_capital_delay: float = Field(..., description="Стоимость финансирования отсрочки по ставке ЦБ")
    net_profit: float = Field(..., description="Чистая прибыль сделки")
    net_margin_percent: float = Field(..., description="Чистая рентабельность продаж в %")
    is_approved: bool = Field(..., description="Сделка проходит автоматический гейт маржинальности")
    rejection_reasons: List[str] = Field(default_factory=list)
    approval_task_id: Optional[int] = Field(None, description="ID созданной задачи согласования в 1С Канбан")
    summary: str
