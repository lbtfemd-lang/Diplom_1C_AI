import pytest
from app.models.compliance_models import CounterpartyCheckRequest, PaymentAuditRequest, ComplianceRiskLevel
from app.services.compliance_service import compliance_service

from app.models.margin_models import DealCalculationRequest, DealItem, TaxSystemEnum
from app.services.margin_service import margin_service

from app.models.debt_models import PenaltyCalculationRequest, PreTrialClaimRequest
from app.services.debt_service import debt_service

from app.models.stock_models import InventoryAnalysisRequest, StockItemInput, StockStatusEnum
from app.services.stock_rebalancing_service import stock_service

from app.models.ocr_models import InvoiceParseRequest
from app.services.ocr_service import ocr_service


class TestCompliance115FZ:
    def test_inn_validation_checksums(self):
        # Реальный ИНН ЮЛ (ПАО Сбербанк: 7707083893)
        valid_ul, desc_ul = compliance_service.validate_inn("7707083893")
        assert valid_ul is True
        assert "ЮЛ" in desc_ul

        # Заведомо ложный ИНН ЮЛ (ошибка в последней цифре)
        invalid_ul, desc_inv = compliance_service.validate_inn("7707083894")
        assert invalid_ul is False
        assert "Неверная контрольная сумма" in desc_inv

        # Нецифровой ИНН
        inv_str, _ = compliance_service.validate_inn("770708389A")
        assert inv_str is False

    def test_counterparty_scoring_stop_factors(self):
        # Благонадежный контрагент
        req_good = CounterpartyCheckRequest(
            inn="7707083893",
            name="ПАО Сбербанк",
            registration_date="2010-01-01",
            authorized_capital=1000000000.0,
        )
        res_good = compliance_service.check_counterparty(req_good)
        assert res_good.is_inn_valid is True
        assert res_good.risk_level == ComplianceRiskLevel.LOW
        assert res_good.can_conclude_contract is True

        # Фирма-однодневка с массовым директором и долгами
        req_bad = CounterpartyCheckRequest(
            inn="7707083893", # valid checksum
            name="ООО Вектор Финанс",
            registration_date="2026-07-01", # < 90 days
            is_mass_director=True,
            is_mass_address=True,
            tax_debts=250000.0,
            arbitration_cases_count=6,
        )
        res_bad = compliance_service.check_counterparty(req_bad)
        assert res_bad.risk_level == ComplianceRiskLevel.CRITICAL
        assert res_bad.can_conclude_contract is False
        assert len(res_bad.stop_factors) >= 2

    def test_115_fz_payment_audit(self):
        # Обычный прозрачный платеж за товар с НДС
        req_ok = PaymentAuditRequest(
            payer_inn="7707083893",
            recipient_inn="7724123456",
            amount=150000.0,
            payment_purpose="Оплата по счету № 104 от 01.09.2026 за кабель силовой. В том числе НДС 20% 25000.00 руб.",
            contract_info="Договор поставки № 12-П",
        )
        res_ok = compliance_service.audit_payment(req_ok)
        assert res_ok.is_compliant_115_fz is True
        assert res_ok.risk_level == ComplianceRiskLevel.LOW

        # Сомнительный платеж: сумма 590 000 руб. (дробление до 600k), ключевое слово "заем беспроцентный", без НДС
        req_risk = PaymentAuditRequest(
            payer_inn="7707083893",
            recipient_inn="7724123456",
            amount=590000.0,
            payment_purpose="Выдача денежных средств: беспроцентный заем директору на хоз нужды",
            contract_info=None,
        )
        res_risk = compliance_service.audit_payment(req_risk)
        assert res_risk.is_compliant_115_fz is False
        assert res_risk.is_splitting_detected is True
        assert len(res_risk.triggers) >= 2
        assert "Красная зона" in res_risk.verdict or "Повышенный комплаенс-риск" in res_risk.verdict


class TestMarginProtection:
    def test_profitable_deal_approval(self):
        # Выгодная сделка с рентабельностью > 25%
        req = DealCalculationRequest(
            customer_name="ООО ЭлектроМонтаж",
            items=[
                DealItem(
                    sku="00-0000124",
                    name="Кабель силовой ВВГнг-LS 3x2.5",
                    quantity=1000.0,
                    purchase_price=80.0,
                    selling_price=140.0, # хорошая наценка
                    discount_percent=0.0,
                )
            ],
            tax_system=TaxSystemEnum.OSNO,
            logistics_cost=2000.0,
            payment_delay_days=0,
            min_allowed_margin_percent=15.0,
            auto_create_kanban_approval=False,
        )
        res = margin_service.calculate_deal(req)
        assert res.is_approved is True
        assert res.net_profit > 0
        assert res.net_margin_percent >= 15.0

    def test_low_margin_deal_blocked_and_kanban_routed(self):
        # Сделка со скидкой 40%, роняющей маржу ниже 15%
        req = DealCalculationRequest(
            customer_name="ООО ДемпингСтрой",
            items=[
                DealItem(
                    sku="00-0000189",
                    name="Светильник светодиодный LED 36W",
                    quantity=100.0,
                    purchase_price=850.0,
                    selling_price=900.0, # наценка всего 50 руб при себестоимости 850
                    discount_percent=0.0,
                )
            ],
            tax_system=TaxSystemEnum.OSNO,
            logistics_cost=3000.0,
            payment_delay_days=30, # отсрочка 30 дней съест прибыль
            min_allowed_margin_percent=15.0,
            auto_create_kanban_approval=True,
        )
        res = margin_service.calculate_deal(req)
        assert res.is_approved is False
        assert len(res.rejection_reasons) > 0
        assert res.approval_task_id is not None # задача в Канбан создана!


class TestDebtCollection395GK:
    def test_penalty_cbr_calculation(self):
        req = PenaltyCalculationRequest(
            debt_amount=1000000.0, # 1 млн руб
            due_date="2026-01-01",
            calculation_date="2026-02-01", # 31 день просрочки
        )
        res = debt_service.calculate_penalty(req)
        assert res.overdue_days == 31
        assert res.total_penalty > 0
        # 1 000 000 * 31 * 0.21 / 365 ~= 17 835.62
        assert 17000.0 < res.total_penalty < 19000.0

    def test_generate_pre_trial_claim(self):
        req = PreTrialClaimRequest(
            debtor_name="ООО «АльфаТрейд»",
            debtor_inn="7707083893",
            debtor_email="buh@alphatrade.ru",
            contract_number="01-П/2025",
            contract_date="15.01.2025",
            invoice_number="УПД-142",
            invoice_date="20.12.2025",
            principal_debt=500000.0,
            due_date="2026-01-10",
            payment_deadline_days=10,
            send_email_immediately=False,
        )
        res = debt_service.generate_pre_trial_claim(req)
        assert res.principal_debt == 500000.0
        assert res.penalty_amount > 0
        assert res.total_claim_amount == round(res.principal_debt + res.penalty_amount, 2)
        assert "ст. 395 ГК РФ" in res.legal_claim_text
        assert "ООО «АльфаТрейд»" in res.legal_claim_text


class TestSmartStockRebalancing:
    def test_rop_and_wilson_eoq(self):
        items = [
            # 1. Товар с дефицитом (остаток 10, среднедневной расход 5, срок поставки 5 дн -> ROP >= 25)
            StockItemInput(
                sku="00-0000124",
                name="Кабель силовой ВВГнг-LS 3x2.5",
                current_stock=10.0,
                daily_sales_avg=5.0,
                lead_time_days=5,
                unit_cost=80.0,
                days_without_sales=0,
            ),
            # 2. Неликвид (без продаж 120 дней, остаток 500 шт)
            StockItemInput(
                sku="00-0000550",
                name="Труба гофрированная ПВХ d20",
                current_stock=500.0,
                daily_sales_avg=0.0,
                lead_time_days=3,
                unit_cost=18.0,
                days_without_sales=120,
            )
        ]
        req = InventoryAnalysisRequest(items=items, generate_1c_order=True)
        res = stock_service.analyze_inventory(req)

        assert res.total_items_analyzed == 2
        assert res.deficit_items_count == 1
        assert res.dead_stock_items_count == 1
        assert res.total_frozen_capital_rub == 500 * 18.0 # 9000 руб в неликвиде
        assert res.purchase_order_1c is not None
        assert res.purchase_order_1c["Документ"] == "ЗаказПоставщику"
        assert len(res.purchase_order_1c["Строки"]) == 1


class TestOCRService:
    def test_nomenclature_fuzzy_matching(self):
        # Различные варианты написания кабеля от поставщиков
        sku1, name1, conf1 = ocr_service.match_nomenclature("Кабель силовой медный ВВГнг-LS 3х2,5 (ГОСТ)")
        assert sku1 == "00-0000124"
        assert conf1 >= 0.65

        sku2, name2, conf2 = ocr_service.match_nomenclature("Автоматический выключатель ВА 47-29 1п 16А")
        assert sku2 == "00-0000210"
        assert conf2 >= 0.60

    def test_invoice_parsing_and_arithmetic(self):
        req = InvoiceParseRequest(
            raw_text="""
            Счет-фактура № 55 от 10.08.2026
            Поставщик: ООО КабельСнаб ИНН 7707083893
            Покупатель: ООО УНФ Трейд ИНН 7724123456
            1. Кабель силовой ВВГнг-LS 3x2.5 - 200 м по 80.00 руб
            2. Выключатель автоматический ВА47-29 1P 16A - 20 шт по 240.00 руб
            """
        )
        res = ocr_service.parse_invoice(req)
        assert res.invoice_number == "55"
        assert len(res.lines) >= 2
        assert res.total_amount > 0
        assert res.is_arithmetic_valid is True

    def test_invoice_parsing_negative_cases(self):
        # 1. Некорректный текст без реквизитов и товаров не должен порождать фиктивные строки
        req_bad = InvoiceParseRequest(raw_text="not an invoice")
        res_bad = ocr_service.parse_invoice(req_bad)
        assert len(res_bad.lines) == 0
        assert res_bad.total_amount == 0.0
        assert res_bad.is_arithmetic_valid is False
        assert res_bad.supplier_name is None
        assert res_bad.supplier_inn is None
        assert "не обнаружены" in res_bad.summary

        # 2. Передача скана без текста не должна подставлять фиктивный демо-счет
        req_img = InvoiceParseRequest(raw_text=None, image_base64="not-an-image")
        res_img = ocr_service.parse_invoice(req_img)
        assert len(res_img.lines) == 0
        assert res_img.total_amount == 0.0
        assert res_img.is_arithmetic_valid is False
        assert "отключено" in res_img.summary

        # 3. Документ с явным расхождением арифметики итоговой суммы
        req_mismatch = InvoiceParseRequest(
            raw_text="""
            Счет № 99 от 01.09.2026
            1. Кабель силовой ВВГнг-LS 3x2.5 - 10 м по 80.00 руб
            Итого с НДС: 99999.00 руб
            """
        )
        res_mismatch = ocr_service.parse_invoice(req_mismatch)
        assert len(res_mismatch.lines) == 1
        assert res_mismatch.is_arithmetic_valid is False
        assert "Не сходится с итогом" in res_mismatch.summary
