"""Hand-calculated examples of the educational model, not tax-law certification."""
import pytest
from app.services.compliance_service import compliance_service
from app.services.margin_service import margin_service
from app.services.stock_rebalancing_service import stock_service
from app.models.margin_models import DealCalculationRequest, DealItem
from app.models.stock_models import InventoryAnalysisRequest, StockItemInput


@pytest.mark.parametrize("inn,valid", [
    ("1234567894", True), ("123456789047", True),
    ("1234567895", False), ("123456789057", False), ("123456789048", False),
    ("0000000000", False), ("000000000000", False),
    ("123456789", False), ("²" * 10, False), ("１２３４５６７８９４", False),
])
def test_inn_control_digits(inn, valid):
    # Synthetic fixtures: weighted sums 279 -> 4; 257 -> 4; 282 -> 7.
    assert compliance_service.validate_inn(inn)[0] is valid


@pytest.mark.parametrize("stock,status,order", [(7, "DEFICIT", 191), (8, "NORMAL", 0), (390, "SURPLUS", 0)])
def test_exact_eoq_rop_threshold(stock, status, order):
    # D=365, S=100, H=2 -> sqrt(36500)=191.05 -> 191.
    # LTD=1*4=4, SS=1.5*1*sqrt(4)=3, ROP=7.
    item = StockItemInput(sku="fixture", name="Synthetic", current_stock=stock,
                         daily_sales_avg=1, daily_sales_std=1, lead_time_days=4,
                         unit_cost=10, order_fixed_cost=100, annual_holding_cost_rate=.2)
    result = stock_service.analyze_inventory(InventoryAnalysisRequest(items=[item], service_level_z=1.5))
    rec = result.items[0]
    assert rec.safety_stock == 3
    assert rec.reorder_point_rop == 7
    assert rec.economic_order_quantity_eoq == 191
    assert rec.status == status
    assert rec.recommended_order_quantity == order
    if stock == 7:
        assert result.purchase_order_1c["СуммаНДС"] == 382
        assert result.purchase_order_1c["СуммаДокумента"] == 2292
    else:
        assert result.purchase_order_1c is None


@pytest.mark.parametrize("tax,taxes,profit", [("osno", 180, 320), ("usn_income", 72, 428), ("usn_income_expense", 75, 425)])
def test_tax_arithmetic_at_fixed_educational_rates(tax, taxes, profit):
    # Sale 1200, purchase 600, logistics 100, no bonus/delay.
    # OSNO: VAT difference 100; EBIT 400; profit tax 80.
    request = DealCalculationRequest(customer_name="Synthetic", items=[
        DealItem(sku="fixture", name="Synthetic", quantity=1, purchase_price=600, selling_price=1200)
    ], tax_system=tax, logistics_cost=100, sales_commission_rate=0,
        auto_create_kanban_approval=False)
    result = margin_service.calculate_deal(request)
    assert result.tax_amount == taxes
    assert result.net_profit == profit
    if tax == "osno":
        assert result.vat_amount == 100
        assert result.revenue_net_vat == 1000
