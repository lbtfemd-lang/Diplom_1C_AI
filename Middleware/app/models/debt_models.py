from pydantic import BaseModel, Field
from typing import List, Optional


class PenaltyPeriodCalculation(BaseModel):
    start_date: str
    end_date: str
    days: int
    key_rate_percent: float
    days_in_year: int
    penalty_rub: float


class PenaltyCalculationRequest(BaseModel):
    debt_amount: float = Field(..., gt=0, description="Основная сумма долга в рублях")
    due_date: str = Field(..., description="Срок оплаты по договору (YYYY-MM-DD)")
    calculation_date: Optional[str] = Field(None, description="Дата расчета (YYYY-MM-DD, по умолч. сегодня)")
    custom_key_rate: Optional[float] = Field(None, ge=0, allow_inf_nan=False, description="Фиксированная договорная ставка в процентах годовых, не дневная")


class PenaltyCalculationResponse(BaseModel):
    debt_amount: float
    overdue_days: int
    total_penalty: float
    effective_key_rate_percent: float
    periods: List[PenaltyPeriodCalculation]
    formula_explanation: str
    is_estimated: bool = False
    warning: Optional[str] = None
    rate_valid_until: Optional[str] = None


class PreTrialClaimRequest(BaseModel):
    debtor_name: str = Field(..., description="Полное наименование должника")
    debtor_inn: str = Field(..., description="ИНН должника")
    debtor_email: Optional[str] = Field(None, description="Email должника для отправки")
    creditor_name: str = Field("ООО «УНФ Трейд Сервис»", description="Наименование кредитора")
    contract_number: str = Field(..., description="Номер договора поставки/услуг")
    contract_date: str = Field(..., description="Дата договора (YYYY-MM-DD или DD.MM.YYYY)")
    invoice_number: str = Field(..., description="Номер неоплаченного счета / УПД")
    invoice_date: str = Field(..., description="Дата счета / УПД")
    principal_debt: float = Field(..., gt=0, description="Сумма основного долга")
    due_date: str = Field(..., description="Дата, до которой должна была пройти оплата")
    payment_deadline_days: int = Field(10, ge=1, le=60, description="Срок для добровольного удовлетворения претензии (раб. дней)")
    arbitration_court_name: str = Field("Арбитражный суд города Москвы", description="Суд договорной подсудности")
    send_email_immediately: bool = Field(False, description="Отправить письмо на email должника через EmailService")


class PreTrialClaimResponse(BaseModel):
    claim_number: str
    claim_date: str
    debtor_name: str
    debtor_inn: str
    principal_debt: float
    penalty_amount: float
    total_claim_amount: float
    overdue_days: int
    legal_claim_text: str
    email_sent: bool
    email_status: Optional[str] = None
