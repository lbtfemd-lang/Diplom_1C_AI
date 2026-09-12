# -*- coding: utf-8 -*-
"""
ComplianceService — Сервис финансового контроля по Федеральному закону № 115-ФЗ 
«О противодействии легализации (отмыванию) доходов, полученных преступным путем...»
и должной осмотрительности ФНС РФ (ст. 54.1 НК РФ).
"""

import re
import datetime
import logging
from typing import Tuple, List, Dict, Any
from app.models.compliance_models import (
    CounterpartyCheckRequest, CounterpartyCheckResponse,
    PaymentAuditRequest, PaymentAuditResponse,
    ComplianceRiskLevel
)

logger = logging.getLogger(__name__)


class ComplianceService:
    # Весовые коэффициенты для контрольного разряда ИНН ЮЛ (10 знаков)
    _WEIGHTS_10 = [2, 4, 10, 3, 5, 9, 4, 6, 8]

    # Весовые коэффициенты для 11-го разряда ИНН ИП (12 знаков)
    _WEIGHTS_12_1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8, 0]

    # Весовые коэффициенты для 12-го разряда ИНН ИП (12 знаков)
    _WEIGHTS_12_2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8, 0]

    # Ключевые слова повышенного внимания Росфинмониторинга (115-ФЗ)
    _RISK_KEYWORDS = {
        "обналичивание": 40,
        "обнал": 40,
        "беспроцентный заем": 35,
        "беспроцентный займ": 35,
        "заем учредителю": 30,
        "займ учредителю": 30,
        "вексель": 35,
        "покупка векселя": 40,
        "уступка права требования": 25,
        "цессия": 25,
        "консультационные услуги": 20,
        "маркетинговые услуги": 20,
        "агентское вознаграждение без ндс": 30,
        "субагент": 20,
        "информационные услуги": 15,
        "возврат займа": 15,
    }

    @classmethod
    def validate_inn(cls, inn: str) -> Tuple[bool, str]:
        """
        Проверка контрольной суммы ИНН по официальному алгоритму ФНС РФ.
        Возвращает (is_valid, entity_type).
        """
        inn = str(inn).strip()
        if re.fullmatch(r"[0-9]+", inn) is None or not inn.strip("0"):
            return False, "Некорректный формат (содержит нецифровые символы)"

        digits = [int(ch) for ch in inn]

        # 10 знаков — Юридическое лицо
        if len(digits) == 10:
            ctrl = sum(d * w for d, w in zip(digits[:9], cls._WEIGHTS_10)) % 11 % 10
            if ctrl == digits[9]:
                return True, "Юридическое лицо (ЮЛ)"
            return False, "Неверная контрольная сумма ИНН ЮЛ"

        # 12 знаков — Индивидуальный предприниматель или Физлицо
        elif len(digits) == 12:
            ctrl1 = sum(d * w for d, w in zip(digits[:10], cls._WEIGHTS_12_1)) % 11 % 10
            ctrl2 = sum(d * w for d, w in zip(digits[:11], cls._WEIGHTS_12_2)) % 11 % 10
            if ctrl1 == digits[10] and ctrl2 == digits[11]:
                return True, "Индивидуальный предприниматель (ИП) / Физлицо"
            return False, "Неверная контрольная сумма ИНН ИП"

        return False, f"Неверная длина ИНН: {len(inn)} (ожидалось 10 или 12 знаков)"

    def check_counterparty(self, req: CounterpartyCheckRequest) -> CounterpartyCheckResponse:
        """
        Комплексная скоринговая оценка благонадежности контрагента (ст. 54.1 НК РФ).
        """
        is_valid, entity_type = self.validate_inn(req.inn)
        score = 0.0
        stop_factors: List[str] = []
        warnings: List[str] = []
        recs: List[str] = []

        if not is_valid:
            score += 100.0
            stop_factors.append(f"Невалидный ИНН: {entity_type}")
            return CounterpartyCheckResponse(
                inn=req.inn,
                name=req.name,
                is_inn_valid=False,
                entity_type=entity_type,
                risk_level=ComplianceRiskLevel.CRITICAL,
                risk_score=100.0,
                stop_factors=stop_factors,
                warnings=[],
                recommendations=["Прекратить оформление сделки. Контрагент с таким ИНН не может быть зарегистрирован в ЕГРЮЛ/ЕГРИП."],
                can_conclude_contract=False,
            )

        # Проверка срока регистрации (компании-однодневки моложе 6 месяцев)
        if req.registration_date:
            try:
                reg_dt = datetime.datetime.strptime(req.registration_date, "%Y-%m-%d")
                age_days = (datetime.datetime.now() - reg_dt).days
                if age_days < 90:
                    score += 30.0
                    warnings.append(f"Организация зарегистрирована менее 3 месяцев назад ({age_days} дн.) — фактор фирмы-однодневки")
                elif age_days < 180:
                    score += 15.0
                    warnings.append(f"Молодая организация (возраст {age_days} дн.)")
            except Exception:
                warnings.append("Не удалось распарсить дату регистрации")

        # Признак массового руководителя / учредителя
        if req.is_mass_director:
            score += 35.0
            stop_factors.append("Руководитель числится в реестре дисквалифицированных / массовых руководителей ФНС")

        # Признак массового адреса
        if req.is_mass_address:
            score += 25.0
            warnings.append("Юридический адрес входит в список адресов массовой регистрации (> 10 организаций)")

        # Уставный капитал
        if entity_type.startswith("Юридическое") and req.authorized_capital <= 10000.0:
            score += 10.0
            warnings.append("Минимальный уставный капитал (10 000 руб.) при отсутствии истории")

        # Арбитражные дела
        if req.arbitration_cases_count >= 5:
            score += 30.0
            stop_factors.append(f"Высокая судебная нагрузка: {req.arbitration_cases_count} активных арбитражных дел в роли ответчика")
        elif req.arbitration_cases_count >= 2:
            score += 15.0
            warnings.append(f"Имеются арбитражные споры ({req.arbitration_cases_count} дел)")

        # Задолженность перед бюджетом
        if req.tax_debts > 100000.0:
            score += 35.0
            stop_factors.append(f"Крупная налоговая задолженность по данным ФНС: {req.tax_debts:,.2f} ₽")
        elif req.tax_debts > 10000.0:
            score += 15.0
            warnings.append(f"Наличие текущей задолженности по налогам: {req.tax_debts:,.2f} ₽")

        score = min(score, 100.0)

        # Определение уровня риска
        if score >= 70.0 or len(stop_factors) >= 2:
            risk_level = ComplianceRiskLevel.CRITICAL
            can_contract = False
            recs.append("БЛОКИРОВКА СДЕЛКИ: Высокий налоговый риск по ст. 54.1 НК РФ.")
            recs.append("Запросить нотариальные копии Устава, паспорта директора, налоговую декларацию по НДС за прошлый квартал и справку об отсутствии задолженности.")
        elif score >= 45.0:
            risk_level = ComplianceRiskLevel.HIGH
            can_contract = False
            recs.append("Заключение договора возможно только по согласованию с финдиректором и на условиях 100% постоплаты.")
            recs.append("Запросить договор аренды склада/офиса и подтверждение наличия материальных ресурсов.")
        elif score >= 20.0:
            risk_level = ComplianceRiskLevel.MEDIUM
            can_contract = True
            recs.append("Контрагент умеренного риска. Рекомендуется работать по стандартным договорам с обязательным актом сверки.")
        else:
            risk_level = ComplianceRiskLevel.LOW
            can_contract = True
            if req.fns_verified and req.egrul_verified:
                recs.append("Контрагент благонадежен по данным внешних реестров ФНС. Сделка согласована без ограничений.")
            else:
                recs.append("ПРЕДВАРИТЕЛЬНЫЙ ЭВРИСТИЧЕСКИЙ СКОРИНГ: во введенных реквизитах негативные стоп-факторы не заявлены. Прямой опрос реестров ФНС не производился. Для окончательного согласования сделки рекомендуется запросить свежую выписку ЕГРЮЛ.")

        return CounterpartyCheckResponse(
            inn=req.inn,
            name=req.name,
            is_inn_valid=True,
            entity_type=entity_type,
            risk_level=risk_level,
            risk_score=round(score, 1),
            stop_factors=stop_factors,
            warnings=warnings,
            recommendations=recs,
            can_conclude_contract=can_contract,
            fns_verified=req.fns_verified,
            egrul_verified=req.egrul_verified,
            evaluation_type="Подтвержденная проверка ФНС" if (req.fns_verified and req.egrul_verified) else "Эвристический скоринг по введенным сведениям",
        )

    def audit_payment(self, req: PaymentAuditRequest) -> PaymentAuditResponse:
        """
        Аудит платежного поручения на соответствие 115-ФЗ и критериям Росфинмониторинга.
        """
        score = 0.0
        triggers: List[str] = []
        required_docs: List[str] = []

        purpose_lower = req.payment_purpose.lower().strip()

        # 1. Пороговый контроль Росфинмониторинга (115-ФЗ ст. 6)
        # 1 000 000 руб. для безналичных расчетов, 600 000 руб. для снятия наличных / займов
        is_mandatory = req.amount >= 1000000.0 or (req.is_cash_withdrawal and req.amount >= 600000.0)
        if is_mandatory:
            score += 35.0
            triggers.append(f"Операция подлежит обязательному контролю Росфинмониторинга по ст. 6 115-ФЗ (сумма {req.amount:,.2f} ₽)")
            required_docs.extend(["Оригинал договора с приложениями", "Спецификация к договору", "Товарные накладные / УПД", "Транспортная накладная (ТТН)"])

        # 2. Выявление признаков дробления платежей (Sum splitting)
        # Платежи в диапазоне 550k-599k или 950k-999k, чтобы обойти пороговый лимит
        is_splitting = (550000.0 <= req.amount < 600000.0) or (950000.0 <= req.amount < 1000000.0)
        if is_splitting:
            score += 35.0
            triggers.append(f"Подозрение на дробление платежа для обхода лимита 115-ФЗ (сумма {req.amount:,.2f} ₽)")
            required_docs.append("Обоснование разделения платежей от контрагента")

        # 3. Снятие наличных денег
        if req.is_cash_withdrawal:
            score += 40.0
            triggers.append("Операция снятия наличных денежных средств с расчетного счета")
            required_docs.extend(["Кассовый чек", "Авансовый отчет", "Заявление на выдачу под отчет"])

        # 4. Проверка назначения платежа на ключевые слова 115-ФЗ
        for kw, weight in self._RISK_KEYWORDS.items():
            if kw in purpose_lower:
                score += weight
                triggers.append(f"Рисковое назначение платежа: маркер «{kw}» (+{weight} к риску)")
                if "заем" in kw or "займ" in kw:
                    required_docs.append("Договор процентного займа с графиком возврата")
                if "консультацион" in kw or "маркетинг" in kw:
                    required_docs.append("Детализированный отчет исполнителя об оказанных услугах с подтверждением объемов")

        # 5. Проверка указания НДС (типичный признак транзитных фирм при выводе средств)
        has_vat_mention = any(v in purpose_lower for v in ["ндс", "в т.ч.", "в том числе", "без ндс", "не облагается"])
        if not has_vat_mention:
            score += 20.0
            triggers.append("В назначении платежа отсутствует обязательное указание ставки и суммы НДС")
            required_docs.append("Уточнение назначения платежа с выделением НДС 20% или указанием основания освобождения")

        # 6. Отсутствие ссылки на договор или счет
        has_doc_reference = bool(req.contract_info) or any(d in purpose_lower for d in ["договор", "счет", "счёт", "акт", "накладн", "упд", "№", "от "])
        if not has_doc_reference:
            score += 25.0
            triggers.append("Отсутствует ссылка на первичный документ (договор, счет-фактуру, накладную)")
            required_docs.append("Копия счета на оплату или договора")

        score = min(score, 100.0)

        if score >= 65.0:
            risk_level = ComplianceRiskLevel.CRITICAL
            is_compliant = False
            verdict = "ВНИМАНИЕ: Критический уровень комплаенс-риска (Красная зона 115-ФЗ). Обнаружены множественные стоп-факторы; рекомендуется приостановить проведение платежа до проверки полного пакета первичных документов специалистом финмониторинга."
        elif score >= 40.0:
            risk_level = ComplianceRiskLevel.HIGH
            is_compliant = False
            verdict = "ВНИМАНИЕ: Повышенный комплаенс-риск. Рекомендуется предварительный аудит первичных документов контролером перед авторизацией платежа."
        elif score >= 20.0:
            risk_level = ComplianceRiskLevel.MEDIUM
            is_compliant = True
            verdict = "СОГЛАСОВАНО С ЗАМЕЧАНИЯМИ: Платеж допустим при наличии стандартного договора и закрывающего акта/счета."
        else:
            risk_level = ComplianceRiskLevel.LOW
            is_compliant = True
            verdict = "НИЗКИЙ РИСК: Признаков нарушений 115-ФЗ не выявлено. Операция соответствует типовым правилам расчетов."

        return PaymentAuditResponse(
            is_compliant_115_fz=is_compliant,
            risk_level=risk_level,
            risk_score=round(score, 1),
            triggers=triggers,
            is_mandatory_control_threshold=is_mandatory,
            is_splitting_detected=is_splitting,
            requires_document_request=len(required_docs) > 0,
            required_documents=list(dict.fromkeys(required_docs)),
            verdict=verdict,
        )


compliance_service = ComplianceService()
