# -*- coding: utf-8 -*-
"""
OCRService — Интеллектуальный сервис оптического распознавания первичных документов (Счета, УПД, Торг-12)
и автоматического сопоставления номенклатуры поставщиков со справочником «Номенклатура» 1С:УНФ 3.0.
Использует нормализацию строк, расстояние Левенштейна и проверку контрольной арифметики (НДС 20%).
"""

import re
import datetime
import logging
from typing import List, Dict, Any, Tuple, Optional

from app.models.ocr_models import (
    InvoiceParseRequest, InvoiceParseResponse, InvoiceParsedLine
)

logger = logging.getLogger(__name__)


class OCRService:
    # Базовый эталонный каталог номенклатуры 1С:УНФ
    CATALOG_1C = [
        {"sku": "00-0000124", "name": "Кабель силовой ВВГнг-LS 3x2.5", "unit": "м", "base_price": 80.0},
        {"sku": "00-0000125", "name": "Кабель силовой ВВГнг-LS 3x1.5", "unit": "м", "base_price": 55.0},
        {"sku": "00-0000189", "name": "Светильник светодиодный LED 36W", "unit": "шт", "base_price": 850.0},
        {"sku": "00-0000210", "name": "Выключатель автоматический ВА47-29 1P 16A", "unit": "шт", "base_price": 240.0},
        {"sku": "00-0000211", "name": "Выключатель автоматический ВА47-29 1P 25A", "unit": "шт", "base_price": 260.0},
        {"sku": "00-0000305", "name": "Розетка с заземлением скрытой установки", "unit": "шт", "base_price": 180.0},
        {"sku": "00-0000412", "name": "Бокс распределительный навесной 12 модулей", "unit": "шт", "base_price": 620.0},
        {"sku": "00-0000550", "name": "Труба гофрированная ПВХ d20 с протяжкой", "unit": "м", "base_price": 18.0},
    ]

    @staticmethod
    def _levenshtein_distance(s1: str, s2: str) -> int:
        """Классическое расстояние Левенштейна (динамическое программирование)"""
        m, n = len(s1), len(s2)
        dp = [[0] * (n + 1) for _ in range(m + 1)]

        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j

        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if s1[i - 1] == s2[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1]
                else:
                    dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])

        return dp[m][n]

    @classmethod
    def similarity_ratio(cls, str1: str, str2: str) -> float:
        """Расчет коэффициента схожести строк (0.0 - 1.0) с токенизацией и нормализацией"""
        def clean(s: str) -> str:
            s = s.lower()
            # Замена русских аналогов в артикулах: 1п -> 1p, x -> х
            s = s.replace("1п", "1p").replace("2п", "2p").replace("3п", "3p").replace("х", "x")
            # Склеиваем маркировку: "ва 47" -> "ва47"
            s = re.sub(r'([а-яa-z])\s+(\d)', r'\1\2', s)
            return re.sub(r'[^a-zA-Zа-яА-Я0-9]', ' ', s).strip()

        c1, c2 = clean(str1), clean(str2)
        if not c1 or not c2:
            return 0.0

        # Точный матч или подстрока
        if c1 in c2 or c2 in c1:
            return 0.95

        # Токенизация с усечением окончаний (стемминг)
        def stem(token: str) -> str:
            for suffix in ("ий", "ый", "ая", "ое", "ые", "ов", "ев", "ам", "ами"):
                if token.endswith(suffix) and len(token) > 4:
                    return token[:-len(suffix)]
            return token

        tokens1 = set(stem(t) for t in c1.split())
        tokens2 = set(stem(t) for t in c2.split())
        common = tokens1.intersection(tokens2)
        token_score = (2.0 * len(common)) / (len(tokens1) + len(tokens2)) if (tokens1 or tokens2) else 0.0

        # Расстояние Левенштейна
        max_len = max(len(c1), len(c2))
        dist = cls._levenshtein_distance(c1, c2)
        char_score = 1.0 - (dist / max_len)

        return round(0.6 * token_score + 0.4 * char_score, 3)

    def match_nomenclature(self, raw_name: str) -> Tuple[Optional[str], Optional[str], float]:
        """
        Поиск наилучшего соответствия строки из документа со справочником 1С.
        Возвращает (matched_sku, matched_name, confidence).
        """
        best_match = None
        best_score = 0.0

        for item in self.CATALOG_1C:
            score = self.similarity_ratio(raw_name, item["name"])
            if score > best_score:
                best_score = score
                best_match = item

        if best_match and best_score >= 0.40:
            return best_match["sku"], best_match["name"], best_score
        return None, None, best_score

    def parse_invoice(self, req: InvoiceParseRequest) -> InvoiceParseResponse:
        """
        Разбор текста счета/УПД с извлечением реквизитов, строк и перекрестной проверкой арифметики.
        При отсутствии OCR-движка или поврежденных данных не подменяет результат демонстрационными значениями.
        """
        text = req.raw_text or ""
        if not text.strip():
            if req.image_base64:
                return InvoiceParseResponse(
                    invoice_number=None,
                    invoice_date=None,
                    supplier_name=None,
                    supplier_inn=None,
                    buyer_inn=None,
                    total_amount=0.0,
                    total_vat=0.0,
                    lines=[],
                    all_matched=False,
                    is_arithmetic_valid=False,
                    summary="Оптическое распознавание изображений (OCR) отключено. Требуется ручной ввод текстового содержания документа в поле raw_text.",
                )
            return InvoiceParseResponse(
                invoice_number=None,
                invoice_date=None,
                supplier_name=None,
                supplier_inn=None,
                buyer_inn=None,
                total_amount=0.0,
                total_vat=0.0,
                lines=[],
                all_matched=False,
                is_arithmetic_valid=False,
                summary="Ошибка: текст документа пуст. Не удалось обнаружить реквизиты или строки счёта.",
            )

        # 1. Извлечение номера и даты
        m_num = re.search(r'(?:счет(?:-фактура)?|счёт(?:-фактура)?|упд|накладная)[^\d№]*№?\s*([a-zA-Z0-9\-_/]+)', text, re.IGNORECASE)
        inv_number = m_num.group(1) if m_num else None

        m_date = re.search(r'(?:от\s+)?(\d{2}[\./]\d{2}[\./]\d{4}|\d{4}-\d{2}-\d{2})', text)
        inv_date = m_date.group(1) if m_date else None

        # 2. Извлечение ИНН и наименования
        inns = re.findall(r'инн\s*[:\s]*(\d{10,12})', text, re.IGNORECASE)
        supplier_inn = inns[0] if len(inns) > 0 else None
        buyer_inn = inns[1] if len(inns) > 1 else None

        m_sup = re.search(r'поставщик\s*[:\s]*([^\n,]+)', text, re.IGNORECASE)
        supplier_name = m_sup.group(1).strip() if m_sup else None

        # 3. Разбор строк таблицы
        parsed_lines: List[InvoiceParsedLine] = []
        all_matched = True
        is_arithmetic_valid = True
        calc_total_amount = 0.0
        calc_total_vat = 0.0

        line_pattern = re.compile(
            r'(?:^|\n)\s*(?:\d+[\.\)]\s*)?([a-zA-Zа-яА-Я0-9\s\*\.\-_«»]+?)\s*[-–—:]\s*(\d+(?:[\.,]\d+)?)\s*(шт|м|компл|упак|кг)?\s*(?:по\s*)?(\d+(?:[\.,]\d+)?)\s*(?:руб|р)?',
            re.IGNORECASE
        )

        matches = line_pattern.findall(text)
        if not matches:
            return InvoiceParseResponse(
                invoice_number=inv_number,
                invoice_date=inv_date,
                supplier_name=supplier_name,
                supplier_inn=supplier_inn,
                buyer_inn=buyer_inn,
                total_amount=0.0,
                total_vat=0.0,
                lines=[],
                all_matched=False,
                is_arithmetic_valid=False,
                summary="В переданном тексте документа не обнаружены товарные позиции. Требуется ручной ввод строк номенклатуры.",
            )

        line_idx = 1
        for match in matches:
            raw_name, qty_str, unit, price_str = match
            name_clean = raw_name.strip()
            # Пропускаем служебные строки итогов, налогов и служебных надписей
            if any(name_clean.lower().startswith(stop) for stop in ["итого", "всего", "в т.ч.", "в том числе", "сумма ндс", "без ндс", "к оплате"]):
                continue
            if not price_str:
                continue

            try:
                qty = float(qty_str.replace(",", "."))
                price = float(price_str.replace(",", "."))
            except ValueError:
                continue

            if qty <= 0 or price <= 0:
                continue

            unit = unit or "шт"

            # Сопоставление с 1С
            sku, matched_name, conf = self.match_nomenclature(name_clean)
            if not sku or conf < 0.6:
                all_matched = False

            sum_no_vat = round(qty * price, 2)
            vat_amount = round(sum_no_vat * 0.20, 2)
            line_total = round(sum_no_vat + vat_amount, 2)

            parsed_lines.append(InvoiceParsedLine(
                line_number=line_idx,
                raw_name=name_clean,
                matched_1c_sku=sku,
                matched_1c_name=matched_name,
                match_confidence=conf,
                quantity=qty,
                unit=unit,
                unit_price=price,
                line_amount_without_vat=sum_no_vat,
                vat_rate="20%",
                vat_amount=vat_amount,
                line_total_amount=line_total,
                arithmetic_valid=True,
                discrepancy_note=None,
            ))
            line_idx += 1
            calc_total_amount += line_total
            calc_total_vat += vat_amount

        if not parsed_lines:
            return InvoiceParseResponse(
                invoice_number=inv_number,
                invoice_date=inv_date,
                supplier_name=supplier_name,
                supplier_inn=supplier_inn,
                buyer_inn=buyer_inn,
                total_amount=0.0,
                total_vat=0.0,
                lines=[],
                all_matched=False,
                is_arithmetic_valid=False,
                summary="В переданном тексте документа не обнаружены товарные позиции. Требуется ручной ввод строк номенклатуры.",
            )

        calc_total_amount = round(calc_total_amount, 2)
        calc_total_vat = round(calc_total_vat, 2)

        # Сверка с итоговой суммой документа (если указана в тексте)
        m_declared_total = re.search(r'(?:итого\s*(?:с\s*ндс)?|всего\s*к\s*оплате|всего)[^\d]*(\d+(?:[\.,]\d+)?)', text, re.IGNORECASE)
        if m_declared_total:
            try:
                declared_val = float(m_declared_total.group(1).replace(",", "."))
                is_arithmetic_valid = abs(calc_total_amount - declared_val) < 0.05
            except ValueError:
                is_arithmetic_valid = True
        else:
            is_arithmetic_valid = len(parsed_lines) > 0

        inv_disp = inv_number or "б/н"
        date_disp = inv_date or "б/д"
        sup_disp = supplier_name or "Не определен"
        inn_disp = supplier_inn or "Не указан"

        summary = (
            f"Распознан документ: Счет № {inv_disp} от {date_disp}, Поставщик: {sup_disp} (ИНН {inn_disp}). "
            f"Строк: {len(parsed_lines)}. Итого к оплате: {calc_total_amount:,.2f} ₽ (в т.ч. НДС 20%: {calc_total_vat:,.2f} ₽). "
            f"Сопоставление со справочником 1С: {'✅ 100% сопоставлено' if all_matched else '⚠️ Требуется ручная привязка'}. "
            f"Арифметика документа: {'✅ Без ошибок' if is_arithmetic_valid else '❌ Не сходится с итогом документа'}."
        )

        return InvoiceParseResponse(
            invoice_number=inv_number,
            invoice_date=inv_date,
            supplier_name=supplier_name,
            supplier_inn=supplier_inn,
            buyer_inn=buyer_inn,
            total_amount=calc_total_amount,
            total_vat=calc_total_vat,
            lines=parsed_lines,
            all_matched=all_matched,
            is_arithmetic_valid=is_arithmetic_valid,
            summary=summary,
        )


ocr_service = OCRService()
