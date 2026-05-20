"""
Pydantic-модели прикладного расширения «Подбор моделей БПЛА по тендерной заявке».

Описывают контракты данных между LLM-парсером, сервисом подбора, эндпоинтами
middleware и расширением 1С. Все enum-литералы согласованы со справочниками
конфигурации УНФ (`Справочник.МоделиБПЛА`, `Справочник.Комплектующие`) и со
схемой ответа LLM в `tender_prompts.PARSE_PROMPT` / `RERANK_PROMPT`.

Поля числовых ТТХ опциональны и сопровождаются ограничениями диапазона через
`Field(ge=…, le=…)` — это предотвращает попадание невалидных значений из ответа
LLM в дальнейшую обработку. Перекрёстная проверка `motor_count_min ≤ motor_count_max`
выполняется в `field_validator` после Pydantic-валидации одиночных полей.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# --- Литералы перечислений -------------------------------------------------

DroneType = Literal[
    "quadcopter",   # квадрокоптер
    "hexacopter",   # гексакоптер
    "octocopter",   # октокоптер
    "fixed_wing",   # самолёт
    "helicopter",   # вертолёт
    "vtol_hybrid",  # гибрид VTOL
]

DronePurpose = Literal[
    "educational",   # учебный (программируемый, для образовательных целей)
    "fpv_racing",    # FPV-гонки
    "logistics",     # логистика, доставка грузов
    "aerial_photo",  # аэрофотосъёмка
    "surveillance",  # наблюдение, мониторинг
    "general",       # общего назначения
]

PayloadType = Literal[
    "rgb_camera",
    "thermal_camera",
    "lidar",
    "multispectral",
    "delivery_box",
    "speaker",
    "other",
]

MatchIntent = Literal[
    "ready_model",   # подбирать только готовые модели из каталога
    "build_config",  # собирать конфигурацию из комплектующих
    "auto",          # запустить оба алгоритма и вернуть наиболее уверенный результат
]

ComponentCategory = Literal[
    "frame",
    "flight_controller",
    "esc",
    "motor",
    "battery",
    "propeller",
    "gps",
    "video_system",
    "receiver",
    "payload",
    "accessory",
]

CatalogSource = Literal[
    "own",      # собственная разработка ООО «АТС Технологии» (Коптра)
    "partner",  # партнёрский каталог
]


# --- Извлечённые требования из текста тендера ------------------------------

class TenderRequirements(BaseModel):
    """Структурированный список требований, извлечённый LLM из текста тендера.

    Все технические поля опциональны — LLM заполняет только то, что явно
    упомянуто в тексте. Поле `confidence` оценивает полноту извлечения.
    """

    model_config = ConfigDict(extra="ignore")

    intent: MatchIntent = "auto"
    purpose: Optional[DronePurpose] = None
    drone_type: Optional[DroneType] = None

    motor_count_min: Optional[int] = Field(default=None, ge=1, le=12)
    motor_count_max: Optional[int] = Field(default=None, ge=1, le=12)

    payload_min_kg: Optional[float] = Field(default=None, ge=0, le=200)
    flight_time_min_minutes: Optional[int] = Field(default=None, ge=1, le=600)
    range_min_km: Optional[float] = Field(default=None, ge=0, le=1000)
    max_takeoff_weight_kg: Optional[float] = Field(default=None, ge=0, le=500)
    min_speed_km_h: Optional[float] = Field(default=None, ge=0, le=500)
    frame_diagonal_mm: Optional[int] = Field(default=None, ge=50, le=2000)
    propeller_size_inch: Optional[float] = Field(default=None, ge=1.0, le=30.0)

    programmable_languages: List[str] = Field(default_factory=list)
    temperature_range: Optional[str] = None
    ip_rating: Optional[str] = None
    required_payloads: List[PayloadType] = Field(default_factory=list)
    compatible_software: List[str] = Field(default_factory=list)

    quantity: Optional[int] = Field(default=None, ge=1)
    budget_per_unit_rub: Optional[float] = Field(default=None, ge=0)

    notes: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("motor_count_max")
    @classmethod
    def _check_motor_range(cls, v: Optional[int], info) -> Optional[int]:
        mn = info.data.get("motor_count_min")
        if v is not None and mn is not None and v < mn:
            raise ValueError("motor_count_max must be >= motor_count_min")
        return v


# --- Результат подбора готовой модели --------------------------------------

class MatchResult(BaseModel):
    """Одна позиция в ранжированном списке готовых моделей."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    model_id: str                           # GUID или артикул из 1С
    model_name: str
    score: int = Field(ge=0, le=100)
    cosine_score: float = Field(ge=0.0, le=1.0)
    llm_score: int = Field(ge=0, le=100)
    coverage: float = Field(ge=0.0, le=1.0)  # доля выполненных требований
    matches: List[str] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
    explanation: str = ""
    price_rub: Optional[float] = None
    out_of_budget: bool = False
    catalog_source: CatalogSource = "own"


# --- Результат сборки конфигурации (BoM) -----------------------------------

class BoMItem(BaseModel):
    """Одна позиция собранной конфигурации (Bill of Materials)."""

    model_config = ConfigDict(extra="ignore")

    category: ComponentCategory
    component_id: str
    component_name: str
    quantity: int = Field(ge=1)
    unit_price_rub: Optional[float] = None
    catalog_source: CatalogSource = "own"
    compatibility_notes: List[str] = Field(default_factory=list)


class BoMResult(BaseModel):
    """Результат сборки конфигурации из комплектующих."""

    model_config = ConfigDict(extra="ignore")

    items: List[BoMItem] = Field(default_factory=list)
    total_price_rub: Optional[float] = None
    total_weight_g: Optional[float] = None
    predicted_flight_time_minutes: Optional[float] = None
    compatibility_warnings: List[str] = Field(default_factory=list)
    score: int = Field(default=0, ge=0, le=100)
    is_complete: bool = True
    own_brand_share: float = Field(default=0.0, ge=0.0, le=1.0)


# --- Финальный ответ POST /tender/match ------------------------------------

class MatchResponse(BaseModel):
    """Ответ сервиса подбора, возвращаемый расширению 1С."""

    model_config = ConfigDict(extra="ignore")

    requirements: TenderRequirements
    intent_used: MatchIntent
    results: List[MatchResult] = Field(default_factory=list)
    bom: Optional[BoMResult] = None
    summary: str = ""
    fallback_used: bool = False
    candidates_total: int = Field(default=0, ge=0)
    elapsed_ms: int = Field(default=0, ge=0)


# --- Контракты HTTP-эндпоинтов ---------------------------------------------

class TenderParseRequest(BaseModel):
    """Запрос на парсинг текста тендера: POST /tender/parse."""

    model_config = ConfigDict(extra="ignore")

    tender_text: str = Field(min_length=1, max_length=20000)


class TenderParseResponse(BaseModel):
    """Ответ парсера тендера."""

    model_config = ConfigDict(extra="ignore")

    requirements: TenderRequirements
    summary: str = ""


class MatchRequest(BaseModel):
    """Запрос на подбор по структурированным требованиям: POST /tender/match."""

    model_config = ConfigDict(extra="ignore")

    requirements: TenderRequirements


__all__ = [
    "DroneType",
    "DronePurpose",
    "PayloadType",
    "MatchIntent",
    "ComponentCategory",
    "CatalogSource",
    "TenderRequirements",
    "MatchResult",
    "BoMItem",
    "BoMResult",
    "MatchResponse",
    "TenderParseRequest",
    "TenderParseResponse",
    "MatchRequest",
]
