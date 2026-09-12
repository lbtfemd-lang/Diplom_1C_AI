"""Hand-calculated arithmetic checks; not validation of legal rate history."""

import pytest
from pydantic import ValidationError

from app.models.debt_models import PenaltyCalculationRequest
from app.services.debt_service import debt_service


@pytest.mark.parametrize("amount,due,end,rate,expected,denominators", [
    (36500, "2023-12-30", "2024-01-01", 10, 19.97, [365, 366]),
    (36500, "2024-12-30", "2025-01-01", 10, 19.97, [366, 365]),
    (36600, "2023-12-31", "2024-12-31", 10, 3660.00, [366]),
    (36600, "2024-02-28", "2024-02-29", 10, 10.00, [366]),
    (36500, "2025-01-01", "2025-01-02", 10, 10.00, [365]),
    (36500, "2024-12-30", "2025-01-01", 0, 0.00, [366, 365]),
    (36500, "2025-01-01", "2025-01-01", 10, 0.00, []),
])
def test_custom_annual_rate_calendar_boundaries(amount, due, end, rate, expected, denominators):
    result = debt_service.calculate_penalty(PenaltyCalculationRequest(
        debt_amount=amount, due_date=due, calculation_date=end, custom_key_rate=rate))
    assert result.total_penalty == expected
    assert [p.days_in_year for p in result.periods] == denominators
    assert sum(p.days for p in result.periods) == result.overdue_days


@pytest.mark.parametrize("due,end,expected", [
    ("2024-07-27", "2024-07-29", 34.00),  # 36600 * (16 + 18) / 100 / 366
    ("2024-09-14", "2024-09-16", 37.00),
    ("2024-10-26", "2024-10-28", 40.00),
])
def test_local_table_period_boundaries(due, end, expected):
    result = debt_service.calculate_penalty(PenaltyCalculationRequest(
        debt_amount=36600, due_date=due, calculation_date=end))
    assert result.total_penalty == expected
    assert [p.days for p in result.periods] == [1, 1]


@pytest.mark.parametrize("rate", [-1, float("inf"), float("nan")])
def test_invalid_custom_rate_rejected(rate):
    with pytest.raises(ValidationError):
        PenaltyCalculationRequest(debt_amount=100, due_date="2024-01-01", custom_key_rate=rate)
