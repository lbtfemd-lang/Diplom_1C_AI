from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class ComplianceRiskLevel(str, Enum):
    LOW = "LOW"            # Зеленая зона (благонадежный)
    MEDIUM = "MEDIUM"      # Желтая зона (требует внимания)
    HIGH = "HIGH"          # Оранжевая зона (повышенный риск)
    CRITICAL = "CRITICAL"  # Красная зона (блокировка/стоп-фактор)


class CounterpartyCheckRequest(BaseModel):
    inn: str = Field(..., description="ИНН контрагента (10 цифр для ЮЛ, 12 цифр для ИП)")
    name: Optional[str] = Field(None, description="Наименование организации или ФИО ИП")
    ogrn: Optional[str] = Field(None, description="ОГРН / ОГРНИП")
    registration_date: Optional[str] = Field(None, description="Дата регистрации (YYYY-MM-DD)")
    is_mass_director: bool = Field(False, description="Признак массового руководителя/учредителя")
    is_mass_address: bool = Field(False, description="Признак адреса массовой регистрации")
    authorized_capital: float = Field(10000.0, description="Уставный капитал в рублях")
    arbitration_cases_count: int = Field(0, description="Количество текущих арбитражных дел")
    tax_debts: float = Field(0.0, description="Задолженность по налогам и сборам (ФНС)")
    fns_verified: bool = Field(False, description="Признак подтвержденного прямого опроса сервисов ФНС РФ")
    egrul_verified: bool = Field(False, description="Признак подтвержденного анализа выписки ЕГРЮЛ")
    data_source: str = Field("пользовательские реквизиты", description="Источник сведений для оценки")


class CounterpartyCheckResponse(BaseModel):
    inn: str
    name: Optional[str] = None
    is_inn_valid: bool
    entity_type: str
    risk_level: ComplianceRiskLevel
    risk_score: float = Field(..., description="Балл риска от 0 до 100")
    stop_factors: List[str]
    warnings: List[str]
    recommendations: List[str]
    can_conclude_contract: bool
    fns_verified: bool = False
    egrul_verified: bool = False
    evaluation_type: str = "Эвристический скоринг по введенным сведениям"


class PaymentAuditRequest(BaseModel):
    payer_inn: str = Field(..., description="ИНН плательщика")
    recipient_inn: str = Field(..., description="ИНН получателя")
    amount: float = Field(..., gt=0, description="Сумма платежа в рублях")
    payment_purpose: str = Field(..., description="Назначение платежа")
    contract_info: Optional[str] = Field(None, description="Реквизиты договора / счета")
    is_cash_withdrawal: bool = Field(False, description="Операция снятия наличных денежных средств")


class PaymentAuditResponse(BaseModel):
    is_compliant_115_fz: bool
    risk_level: ComplianceRiskLevel
    risk_score: float
    triggers: List[str]
    is_mandatory_control_threshold: bool = Field(..., description="Подлежит обязательному контролю Росфинмониторинга (>= 1 000 000 ₽ или эквивалент)")
    is_splitting_detected: bool = Field(..., description="Выявлены признаки дробления платежей (около 600k / 1M)")
    requires_document_request: bool
    required_documents: List[str]
    verdict: str
