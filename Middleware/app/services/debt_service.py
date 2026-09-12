# -*- coding: utf-8 -*-
"""
DebtService — Сервис урегулирования дебиторской задолженности и расчета процентов 
по статье 395 Гражданского кодекса РФ (Ответственность за неисполнение денежного обязательства).
Учитывает официальную историю ключевой ставки Банка России (16% -> 18% -> 19% -> 21%) 
и количество дней в високосном (366) и невисокосном (365) году.
Генерирует юридически безупречные тексты досудебных претензий с автоматической 
отправкой должникам через корпоративную почту.
"""

import datetime
import logging
from typing import List, Dict, Any, Tuple, Optional
import calendar

from app.models.debt_models import (
    PenaltyCalculationRequest, PenaltyCalculationResponse, PenaltyPeriodCalculation,
    PreTrialClaimRequest, PreTrialClaimResponse
)
from app.services.email_service import email_service

logger = logging.getLogger(__name__)


class DebtService:
    # Официальные периоды действия ключевой ставки ЦБ РФ (актуален по 31.12.2025)
    CBR_RATES_VALID_UNTIL = datetime.date(2025, 12, 31)
    CBR_RATE_HISTORY = [
        {"start": "2023-12-18", "end": "2024-07-28", "rate": 16.0},
        {"start": "2024-07-29", "end": "2024-09-15", "rate": 18.0},
        {"start": "2024-09-16", "end": "2024-10-27", "rate": 19.0},
        {"start": "2024-10-28", "end": "2025-12-31", "rate": 21.0},
    ]

    @staticmethod
    def _parse_date(d_str: str) -> datetime.date:
        """Парсинг даты из ISO (YYYY-MM-DD) или RU (DD.MM.YYYY)"""
        d_str = d_str.strip()
        if "." in d_str:
            return datetime.datetime.strptime(d_str, "%d.%m.%Y").date()
        return datetime.datetime.strptime(d_str, "%Y-%m-%d").date()

    @staticmethod
    def _days_in_year(year: int) -> int:
        return 366 if calendar.isleap(year) else 365

    def calculate_penalty(self, req: PenaltyCalculationRequest) -> PenaltyCalculationResponse:
        """
        Расчет процентов по ст. 395 ГК РФ с разбивкой по периодам действия ключевой ставки ЦБ РФ.
        Формула периода: Сумма_долга * Дни_просрочки * (Ставка_ЦБ / 100) / Дней_в_году
        """
        due_date = self._parse_date(req.due_date)
        calc_date = self._parse_date(req.calculation_date) if req.calculation_date else datetime.date.today()

        # Просрочка начинается на следующий день после установленного срока платежа
        start_overdue = due_date + datetime.timedelta(days=1)
        if start_overdue > calc_date:
            return PenaltyCalculationResponse(
                debt_amount=req.debt_amount,
                overdue_days=0,
                total_penalty=0.0,
                effective_key_rate_percent=21.0,
                periods=[],
                formula_explanation="Срок оплаты еще не наступил. Просрочка отсутствует.",
                rate_valid_until=self.CBR_RATES_VALID_UNTIL.isoformat(),
            )

        total_days = (calc_date - start_overdue).days + 1
        periods: List[PenaltyPeriodCalculation] = []
        total_penalty = 0.0
        is_estimated = False
        warning_msg = None

        # Договорная ставка задаётся в процентах годовых.
        if req.custom_key_rate is not None:
            curr = start_overdue
            while curr <= calc_date:
                period_end = min(calc_date, datetime.date(curr.year, 12, 31))
                period_days = (period_end - curr).days + 1
                days_year = self._days_in_year(curr.year)
                penalty = round(req.debt_amount * period_days * (req.custom_key_rate / 100.0) / days_year, 2)
                periods.append(PenaltyPeriodCalculation(
                    start_date=curr.isoformat(),
                    end_date=period_end.isoformat(),
                    days=period_days,
                    key_rate_percent=req.custom_key_rate,
                    days_in_year=days_year,
                    penalty_rub=penalty,
                ))
                total_penalty += penalty
                curr = period_end + datetime.timedelta(days=1)
            effective_rate = req.custom_key_rate
        else:
            # Разбиваем интервал просрочки по периодам действия ключевой ставки ЦБ РФ
            curr = start_overdue
            while curr <= calc_date:
                # Находим ставку для текущего дня
                rate = 21.0
                found = False
                p_end = calc_date
                for r in self.CBR_RATE_HISTORY:
                    r_start = self._parse_date(r["start"])
                    r_end = self._parse_date(r["end"])
                    if r_start <= curr <= r_end:
                        rate = r["rate"]
                        p_end = min(calc_date, r_end)
                        found = True
                        break

                if not found:
                    is_estimated = True
                    warning_msg = (
                        f"Внимание: ставка ЦБ РФ на дату {curr.isoformat()} отсутствует в локальном справочнике "
                        f"(актуален по {self.CBR_RATES_VALID_UNTIL.strftime('%d.%m.%Y')}). "
                        f"Расчет выполнен ориентировочно."
                    )
                    p_end = calc_date

                # Также разделяем, если меняется год (365 vs 366 дней)
                year_end = datetime.date(curr.year, 12, 31)
                p_end = min(p_end, year_end)

                period_days = (p_end - curr).days + 1
                days_year = self._days_in_year(curr.year)
                period_penalty = round(req.debt_amount * period_days * (rate / 100.0) / days_year, 2)

                periods.append(PenaltyPeriodCalculation(
                    start_date=curr.isoformat(),
                    end_date=p_end.isoformat(),
                    days=period_days,
                    key_rate_percent=rate,
                    days_in_year=days_year,
                    penalty_rub=period_penalty,
                ))
                total_penalty += period_penalty
                curr = p_end + datetime.timedelta(days=1)

            effective_rate = periods[-1].key_rate_percent if periods else 21.0

        total_penalty = round(total_penalty, 2)
        rate_source = "договорной годовой ставке" if req.custom_key_rate is not None else "локальному справочнику ключевой ставки"
        formula_exp = (
            f"Расчет по {rate_source}; применённая ставка последнего периода: {effective_rate}%. "
            f"Формула периода: Долг × Дни × Ставка_процентов / 100 / Дней_в_году. "
            f"Просрочка: {total_days} дн., начислено процентов: {total_penalty:,.2f} ₽."
        )

        return PenaltyCalculationResponse(
            debt_amount=req.debt_amount,
            overdue_days=total_days,
            total_penalty=total_penalty,
            effective_key_rate_percent=effective_rate,
            periods=periods,
            formula_explanation=formula_exp,
            is_estimated=is_estimated,
            warning=warning_msg,
            rate_valid_until=self.CBR_RATES_VALID_UNTIL.isoformat(),
        )

    def generate_pre_trial_claim(self, req: PreTrialClaimRequest) -> PreTrialClaimResponse:
        """
        Формирование официального юридического текста досудебной претензии с отправкой должнику.
        """
        penalty_calc = self.calculate_penalty(PenaltyCalculationRequest(
            debt_amount=req.principal_debt,
            due_date=req.due_date,
        ))

        total_claim = round(req.principal_debt + penalty_calc.total_penalty, 2)
        claim_number = f"ПРЕТ-{datetime.date.today().strftime('%Y%m%d')}-{abs(hash(req.debtor_inn)) % 1000:03d}"
        claim_date_str = datetime.date.today().strftime("%d.%m.%Y")

        # Детализация расчета для текста претензии
        calc_lines = []
        for p in penalty_calc.periods:
            calc_lines.append(
                f"  • с {p.start_date} по {p.end_date} ({p.days} дн.): "
                f"{req.principal_debt:,.2f} ₽ × {p.days} дн. × {p.key_rate_percent}% / {p.days_in_year} = {p.penalty_rub:,.2f} ₽"
            )
        calc_block = "\n".join(calc_lines)

        legal_text = f"""ИСХОДЯЩИЙ № {claim_number} от {claim_date_str} г.

Кому: Руководителю {req.debtor_name}
ИНН: {req.debtor_inn}
От кого: {req.creditor_name}

ДОСУДЕБНАЯ ПРЕТЕНЗИЯ
о погашении задолженности и уплате процентов за пользование чужими денежными средствами
(в порядке ст. 395 ГК РФ и ч. 5 ст. 4 АПК РФ)

Между {req.creditor_name} («Кредитор») и {req.debtor_name} («Должник») был заключен Договор № {req.contract_number} от {req.contract_date} г.
Во исполнение своих договорных обязательств Кредитор своевременно и в полном объеме осуществил поставку товарно-материальных ценностей / оказание услуг по первичному документу {req.invoice_number} от {req.invoice_date} г. на общую сумму {req.principal_debt:,.2f} (включая НДС).

Согласно условиям Договора и нормам гражданского законодательства РФ, оплата подлежала перечислению в срок до {req.due_date} г. До настоящего момента денежные средства на расчетный счет Кредитора не поступили.

В соответствии со ст. 309 Гражданского кодекса РФ обязательства должны исполняться надлежащим образом в соответствии с условиями обязательства и требованиями закона. Односторонний отказ от исполнения обязательства не допускается (ст. 310 ГК РФ).

Согласно п. 1 ст. 395 ГК РФ, в случаях неправомерного удержания денежных средств, уклонения от их возврата, иной просрочки в их уплате подлежат уплате проценты на сумму долга в размере ключевой ставки Банка России, действовавшей в соответствующие периоды.

Период просрочки составляет {penalty_calc.overdue_days} календарных дней.
РАСЧЕТ СУММЫ ТРЕБОВАНИЙ:
1. Основной долг: {req.principal_debt:,.2f} руб.
2. Проценты по ст. 395 ГК РФ: {penalty_calc.total_penalty:,.2f} руб.
Детализация расчета процентов по ключевой ставке ЦБ РФ:
{calc_block}

ИТОГО К УПЛАТЕ: {total_claim:,.2f} ({req.principal_debt:,.2f} руб. долга + {penalty_calc.total_penalty:,.2f} руб. процентов).

НА ОСНОВАНИИ ИЗЛОЖЕННОГО, ТРЕБУЕМ:
В течение {req.payment_deadline_days} (десяти) календарных дней с момента направления настоящей претензии погасить задолженность в полном объеме в размере {total_claim:,.2f} руб. путем перечисления на банковские реквизиты {req.creditor_name}.

В случае неудовлетворения требований в установленный срок Кредитор оставляет за собой право обратиться с исковым заявлением в {req.arbitration_court_name} с возложением на Должника всех судебных расходов, включая государственную пошлину и расходы на оплату услуг представителей.

Генеральный директор {req.creditor_name}
/ Абдулов Р.Ф. /
"""

        email_sent = False
        email_status = "not_requested"

        if req.send_email_immediately and req.debtor_email:
            subject = f"Досудебная претензия № {claim_number} по Договору {req.contract_number}"
            email_res = email_service.send_email(
                to_email=req.debtor_email,
                subject=subject,
                body=legal_text,
            )
            email_sent = email_res.get("status") in ("sent", "queued")
            email_status = f"{email_res.get('status')}: {email_res.get('details', '')}"

        return PreTrialClaimResponse(
            claim_number=claim_number,
            claim_date=claim_date_str,
            debtor_name=req.debtor_name,
            debtor_inn=req.debtor_inn,
            principal_debt=req.principal_debt,
            penalty_amount=penalty_calc.total_penalty,
            total_claim_amount=total_claim,
            overdue_days=penalty_calc.overdue_days,
            legal_claim_text=legal_text,
            email_sent=email_sent,
            email_status=email_status,
        )


debt_service = DebtService()
