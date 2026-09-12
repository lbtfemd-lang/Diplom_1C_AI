from pydantic import BaseModel, Field
from typing import List, Optional


class InvoiceParsedLine(BaseModel):
    line_number: int
    raw_name: str
    matched_1c_sku: Optional[str] = None
    matched_1c_name: Optional[str] = None
    match_confidence: float = Field(..., description="Степень совпадения номенклатуры (0.0 - 1.0)")
    quantity: float
    unit: str = "шт"
    unit_price: float
    line_amount_without_vat: float
    vat_rate: str = "20%"
    vat_amount: float
    line_total_amount: float
    arithmetic_valid: bool = True
    discrepancy_note: Optional[str] = None


class InvoiceParseRequest(BaseModel):
    raw_text: Optional[str] = Field(None, description="Текст счета, акта или УПД")
    image_base64: Optional[str] = Field(None, description="Base64 изображения/скана документа")
    file_name: Optional[str] = Field("Счет-фактура_УПД.pdf", description="Имя исходного файла")


class InvoiceParseResponse(BaseModel):
    invoice_number: Optional[str]
    invoice_date: Optional[str]
    supplier_name: Optional[str]
    supplier_inn: Optional[str]
    buyer_inn: Optional[str]
    total_amount: float
    total_vat: float
    lines: List[InvoiceParsedLine]
    all_matched: bool
    is_arithmetic_valid: bool
    summary: str
