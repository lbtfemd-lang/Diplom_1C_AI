from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum


class StockStatusEnum(str, Enum):
    DEFICIT = "DEFICIT"          # Ниже точки заказа (риск остановки продаж)
    NORMAL = "NORMAL"            # Оптимальный остаток
    SURPLUS = "SURPLUS"          # Избыточный запас
    DEAD_STOCK = "DEAD_STOCK"    # Неликвид (без движения > 90 дней)


class StockItemInput(BaseModel):
    sku: str = Field(..., description="Артикул 1С")
    name: str = Field(..., description="Наименование номенклатуры")
    current_stock: float = Field(..., ge=0, description="Текущий свободный остаток на складе")
    daily_sales_avg: float = Field(..., ge=0, description="Среднедневной расход/продажи")
    daily_sales_std: float = Field(0.0, ge=0, description="Стандартное отклонение дневного спроса")
    lead_time_days: int = Field(5, ge=1, description="Срок поставки от поставщика в днях")
    unit_cost: float = Field(..., gt=0, description="Закупочная цена за ед. в рублях")
    order_fixed_cost: float = Field(1500.0, ge=0, description="Постоянные затраты на размещение заказа (руб)")
    annual_holding_cost_rate: float = Field(0.25, ge=0.01, le=1.0, description="Коэффициент затрат на хранение в год (по умолч. 25%)")
    days_without_sales: int = Field(0, ge=0, description="Количество дней без движения товара")
    supplier_name: Optional[str] = Field("Основной поставщик", description="Поставщик")


class StockRecommendation(BaseModel):
    sku: str
    name: str
    current_stock: float
    safety_stock: float = Field(..., description="Страховой буфер запаса")
    reorder_point_rop: float = Field(..., description="Точка возобновления заказа (ROP)")
    economic_order_quantity_eoq: float = Field(..., description="Оптимальная партия по формуле Уилсона (EOQ)")
    status: StockStatusEnum
    recommended_order_quantity: float
    estimated_purchase_cost: float
    frozen_capital_rub: float = Field(..., description="Объем замороженных оборотных средств")
    action_plan: str


class InventoryAnalysisRequest(BaseModel):
    items: List[StockItemInput] = Field(..., min_length=1)
    service_level_z: float = Field(1.65, description="Коэффициент уровня сервиса (1.65 = 95%, 2.33 = 99%)")
    dead_stock_threshold_days: int = Field(90, description="Порог признания товара неликвидом (дней)")
    generate_1c_order: bool = Field(True, description="Сформировать готовый JSON документа «ЗаказПоставщику» 1С")


class InventoryAnalysisResponse(BaseModel):
    total_items_analyzed: int
    deficit_items_count: int
    dead_stock_items_count: int
    total_frozen_capital_rub: float
    total_reorder_budget_rub: float
    items: List[StockRecommendation]
    purchase_order_1c: Optional[Dict[str, Any]] = None
    executive_summary: str
