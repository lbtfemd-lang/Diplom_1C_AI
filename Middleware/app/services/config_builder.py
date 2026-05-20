"""
Детерминированный сборщик конфигурации БПЛА из комплектующих.

Алгоритм работает в пять последовательных этапов:
    1) выбор рамы (frame),
    2) выбор полётного контроллера (flight_controller),
    3) подбор N моторов (motor),
    4) подбор N ESC (esc),
    5) подбор батареи и пропеллеров (battery + propeller).

На каждом этапе фильтруются кандидаты, удовлетворяющие физическим
ограничениям предыдущих этапов: посадочные размеры рамы и моторов,
диапазоны напряжений батареи и регуляторов, ток с запасом 20% над
максимальным током мотора, диаметр пропеллера в пределах рамы.

LLM на этапе сборки не используется намеренно — все правила задокументированы
как чистые функции, легко покрываются unit-тестами, и физические ошибки
(несовместимые компоненты) исключены.

См. подраздел 2.7.5 главы 2 диплома и требование 5 спецификации.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Tuple

from app.core import get_bom_weights
from app.models.tender_models import BoMItem, BoMResult, TenderRequirements

from .component_index_service import ComponentCatalogItem, ComponentIndexService


# --- Константы алгоритма --------------------------------------------------

# Запас по току ESC относительно максимального тока мотора (>=120%).
ESC_CURRENT_MARGIN = 1.2

# Допустимая глубина разряда LiPo для расчёта времени полёта.
DEFAULT_DISCHARGE_DEPTH = 0.8

# Доля максимального тока моторов, потребляемая в крейсерском режиме.
DEFAULT_CRUISE_CURRENT_RATIO = 0.35

# Список обязательных категорий BoM для расчёта coverage.
REQUIRED_CATEGORIES: Tuple[str, ...] = (
    "frame",
    "flight_controller",
    "motor",
    "esc",
    "battery",
    "propeller",
)

# Допустимые диапазоны KV → подходящий диаметр пропеллера в дюймах
# (упрощённая таблица для рекомендации, не строгий фильтр).
KV_TO_PROP_INCH_RANGE = {
    (2200, 2600): (4.0, 5.5),    # FPV race 5"
    (1700, 2000): (6.5, 7.5),    # 7" cinematic / freestyle
    (1300, 1700): (8.0, 10.0),   # 8-10" long range
    (600, 1100): (10.0, 13.0),   # 12" logistics
}


# --- Типизированные представления compatibility --------------------------

@dataclass
class FrameSpec:
    motor_mount_count: Optional[int] = None
    motor_mount_size_mm: Optional[float] = None
    max_motor_diameter_mm: Optional[float] = None
    prop_size_inch_max: Optional[float] = None
    diagonal_mm: Optional[int] = None
    mass_g: Optional[float] = None


@dataclass
class FlightControllerSpec:
    mcu: Optional[str] = None
    firmware: List[str] = field(default_factory=list)
    voltage_input_v: Optional[str] = None
    uart_count: Optional[int] = None
    programmable_languages: List[str] = field(default_factory=list)


@dataclass
class EscSpec:
    current_continuous_a: Optional[float] = None
    current_burst_a: Optional[float] = None
    voltage_v: Optional[str] = None
    protocol: List[str] = field(default_factory=list)
    bec_v: Optional[float] = None


@dataclass
class MotorSpec:
    kv: Optional[int] = None
    stator_size: Optional[str] = None
    mount_size_mm: Optional[float] = None
    weight_g: Optional[float] = None
    max_current_a: Optional[float] = None
    voltage_v: Optional[str] = None


@dataclass
class BatterySpec:
    chemistry: Optional[str] = None
    cells_s: Optional[int] = None
    capacity_mah: Optional[int] = None
    c_rating: Optional[int] = None
    weight_g: Optional[float] = None
    connector: Optional[str] = None


@dataclass
class PropellerSpec:
    diameter_inch: Optional[float] = None
    pitch: Optional[float] = None
    blade_count: Optional[int] = None
    material: Optional[str] = None
    mount_hole_mm: Optional[float] = None


def _parse_voltage_range(text: Optional[str]) -> Optional[Tuple[float, float]]:
    """Распарсить диапазон напряжений типа "3S-6S" или "11.1-22.2V" в (min_v, max_v).

    Использует упрощённое допущение «1S = 3.7 В» для LiPo.
    Возвращает None при невозможности распарсить.
    """
    if not text:
        return None
    raw = text.replace(" ", "").replace(",", ".").lower()
    sep = "-" if "-" in raw else ("…" if "…" in raw else None)
    if sep is None:
        return None
    parts = raw.split(sep)
    if len(parts) != 2:
        return None
    try:
        return _parse_single_voltage(parts[0]), _parse_single_voltage(parts[1])
    except (ValueError, TypeError):
        return None


def _parse_single_voltage(text: str) -> float:
    """Распарсить одиночное напряжение, '4S' → 14.8 В, '14.8' → 14.8 В."""
    text = text.strip().lower().rstrip("v").rstrip("в")
    if text.endswith("s"):
        cells = float(text[:-1])
        return cells * 3.7
    return float(text)


def _ranges_overlap(a: Tuple[float, float], b: Tuple[float, float]) -> bool:
    return max(a[0], b[0]) <= min(a[1], b[1])


def _parse_frame(item: ComponentCatalogItem) -> FrameSpec:
    c = item.compatibility
    return FrameSpec(
        motor_mount_count=_as_int(c.get("motor_mount_count")),
        motor_mount_size_mm=_as_float(c.get("motor_mount_size_mm")),
        max_motor_diameter_mm=_as_float(c.get("max_motor_diameter_mm")),
        prop_size_inch_max=_as_float(c.get("prop_size_inch_max")),
        diagonal_mm=_as_int(c.get("diagonal_mm")),
        mass_g=_as_float(c.get("mass_g")),
    )


def _parse_fc(item: ComponentCatalogItem) -> FlightControllerSpec:
    c = item.compatibility
    return FlightControllerSpec(
        mcu=c.get("mcu"),
        firmware=list(c.get("firmware", []) or []),
        voltage_input_v=c.get("voltage_input_v"),
        uart_count=_as_int(c.get("uart_count")),
        programmable_languages=list(c.get("programmable_languages", []) or []),
    )


def _parse_esc(item: ComponentCatalogItem) -> EscSpec:
    c = item.compatibility
    return EscSpec(
        current_continuous_a=_as_float(c.get("current_continuous_a")),
        current_burst_a=_as_float(c.get("current_burst_a")),
        voltage_v=c.get("voltage_v"),
        protocol=list(c.get("protocol", []) or []),
        bec_v=_as_float(c.get("bec_v")),
    )


def _parse_motor(item: ComponentCatalogItem) -> MotorSpec:
    c = item.compatibility
    return MotorSpec(
        kv=_as_int(c.get("kv")),
        stator_size=c.get("stator_size"),
        mount_size_mm=_as_float(c.get("mount_size_mm")),
        weight_g=_as_float(c.get("weight_g")),
        max_current_a=_as_float(c.get("max_current_a")),
        voltage_v=c.get("voltage_v"),
    )


def _parse_battery(item: ComponentCatalogItem) -> BatterySpec:
    c = item.compatibility
    return BatterySpec(
        chemistry=c.get("chemistry"),
        cells_s=_as_int(c.get("cells_s")),
        capacity_mah=_as_int(c.get("capacity_mah")),
        c_rating=_as_int(c.get("c_rating")),
        weight_g=_as_float(c.get("weight_g")),
        connector=c.get("connector"),
    )


def _parse_propeller(item: ComponentCatalogItem) -> PropellerSpec:
    c = item.compatibility
    return PropellerSpec(
        diameter_inch=_as_float(c.get("diameter_inch")),
        pitch=_as_float(c.get("pitch")),
        blade_count=_as_int(c.get("blade_count")),
        material=c.get("material"),
        mount_hole_mm=_as_float(c.get("mount_hole_mm")),
    )


def _as_int(value) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# --- Проверки совместимости (чистые функции) -----------------------------

def compat_fc_motor_count(fc_spec: FlightControllerSpec, frame_spec: FrameSpec) -> bool:
    """Полётный контроллер совместим с количеством моторов рамы.

    В текущей версии проверяем только наличие поддерживаемой прошивки —
    для всех современных контроллеров поддержка 4/6/8 моторов прошивкой
    обеспечивается автоматически (Betaflight, INAV, Ardupilot).
    """
    return True


def compat_frame_motor(frame_spec: FrameSpec, motor_spec: MotorSpec) -> bool:
    """Мотор подходит к раме по посадочному размеру."""
    if frame_spec.motor_mount_size_mm is None or motor_spec.mount_size_mm is None:
        return True  # неизвестно — не блокируем, но и не повышаем уверенность
    return abs(frame_spec.motor_mount_size_mm - motor_spec.mount_size_mm) < 0.5


def compat_motor_battery(motor_spec: MotorSpec, battery_spec: BatterySpec) -> bool:
    """Диапазон напряжений мотора пересекается с напряжением батареи."""
    motor_range = _parse_voltage_range(motor_spec.voltage_v)
    if motor_range is None or battery_spec.cells_s is None:
        return True
    battery_v = battery_spec.cells_s * 3.7
    return motor_range[0] - 0.4 <= battery_v <= motor_range[1] + 0.4


def compat_motor_esc(motor_spec: MotorSpec, esc_spec: EscSpec) -> bool:
    """ESC выдерживает максимальный ток мотора с запасом 20%."""
    if motor_spec.max_current_a is None or esc_spec.current_continuous_a is None:
        return True
    return esc_spec.current_continuous_a >= motor_spec.max_current_a * ESC_CURRENT_MARGIN


def compat_esc_battery(esc_spec: EscSpec, battery_spec: BatterySpec) -> bool:
    """Диапазон напряжений ESC включает напряжение батареи."""
    esc_range = _parse_voltage_range(esc_spec.voltage_v)
    if esc_range is None or battery_spec.cells_s is None:
        return True
    battery_v = battery_spec.cells_s * 3.7
    return esc_range[0] - 0.4 <= battery_v <= esc_range[1] + 0.4


def compat_motor_prop(motor_spec: MotorSpec, prop_spec: PropellerSpec) -> bool:
    """KV мотора согласован с диаметром пропеллера по таблице."""
    if motor_spec.kv is None or prop_spec.diameter_inch is None:
        return True
    for (kv_min, kv_max), (prop_min, prop_max) in KV_TO_PROP_INCH_RANGE.items():
        if kv_min <= motor_spec.kv <= kv_max:
            return prop_min <= prop_spec.diameter_inch <= prop_max
    return True  # неизвестный диапазон KV — не блокируем


def compat_frame_prop(frame_spec: FrameSpec, prop_spec: PropellerSpec) -> bool:
    """Диаметр пропеллера ≤ предельного для рамы."""
    if frame_spec.prop_size_inch_max is None or prop_spec.diameter_inch is None:
        return True
    return prop_spec.diameter_inch <= frame_spec.prop_size_inch_max + 0.1


# --- Расчёт времени полёта -----------------------------------------------

def compute_flight_time_minutes(
    battery_spec: BatterySpec,
    total_max_current_a: float,
    cruise_ratio: float = DEFAULT_CRUISE_CURRENT_RATIO,
    discharge_depth: float = DEFAULT_DISCHARGE_DEPTH,
) -> Optional[float]:
    """Прогноз времени полёта по формуле capacity × discharge × 60 / I_cruise / 1000.

    total_max_current_a — суммарный максимальный ток N моторов.
    cruise_ratio — доля от максимума, потребляемая в крейсерском режиме.
    """
    if battery_spec.capacity_mah is None or total_max_current_a <= 0:
        return None
    cruise_current_a = total_max_current_a * cruise_ratio
    if cruise_current_a <= 0:
        return None
    flight_time = battery_spec.capacity_mah * discharge_depth * 60.0 / cruise_current_a / 1000.0
    return round(flight_time, 1)


# --- Вспомогательные структуры -------------------------------------------

@dataclass
class _StageResult:
    item: Optional[ComponentCatalogItem]
    quantity: int = 1
    notes: List[str] = field(default_factory=list)


# --- Основной класс ------------------------------------------------------

class ConfigBuilder:
    """Детерминированный сборщик BoM из каталога комплектующих.

    Принимает `ComponentIndexService` и флаг `prefer_own_brand`. При
    `prefer_own_brand=True` (по умолчанию) собственные комплектующие Коптры
    выбираются перед партнёрскими при сопоставимом скоринге, и финальный
    score конфигурации повышается за счёт own_brand_share (см. требование 5.3).
    """

    def __init__(
        self,
        components: ComponentIndexService,
        prefer_own_brand: bool = True,
    ):
        self._components = components
        self._prefer_own = prefer_own_brand

    # --- Публичный метод --------------------------------------------------

    def build(self, req: TenderRequirements) -> BoMResult:
        warnings: List[str] = []
        items: List[BoMItem] = []
        is_complete = True

        # 1) Выбор рамы
        frame = self._pick_frame(req)
        if frame is None:
            warnings.append("Нет совместимой рамы в каталоге.")
            is_complete = False
            return self._finalize(items, warnings, is_complete, req, frame_spec=None,
                                  motor_spec=None, battery_spec=None)
        items.append(self._make_bom_item(frame, quantity=1))
        frame_spec = _parse_frame(frame)
        motor_count = self._resolve_motor_count(req, frame_spec)

        # 2) Выбор полётного контроллера
        fc = self._pick_fc(req, frame_spec)
        if fc is None:
            warnings.append("Нет совместимого полётного контроллера в каталоге.")
            is_complete = False
        else:
            items.append(self._make_bom_item(fc, quantity=1))

        # 3) Моторы
        motor = self._pick_motor(req, frame_spec)
        motor_spec: Optional[MotorSpec] = None
        if motor is None:
            warnings.append("Нет совместимых моторов в каталоге.")
            is_complete = False
        else:
            motor_spec = _parse_motor(motor)
            items.append(self._make_bom_item(motor, quantity=motor_count))

        # 4) ESC
        esc = self._pick_esc(req, motor_spec) if motor_spec else None
        if esc is None:
            warnings.append("Нет совместимых регуляторов оборотов (ESC) в каталоге.")
            is_complete = False
        else:
            items.append(self._make_bom_item(esc, quantity=motor_count))

        # 5) Батарея и пропеллеры
        battery = self._pick_battery(req, motor_spec, esc)
        battery_spec: Optional[BatterySpec] = None
        if battery is None:
            warnings.append("Нет совместимой батареи в каталоге.")
            is_complete = False
        else:
            battery_spec = _parse_battery(battery)
            items.append(self._make_bom_item(battery, quantity=1))

        prop = self._pick_propeller(req, frame_spec, motor_spec)
        if prop is None:
            warnings.append("Нет совместимых пропеллеров в каталоге.")
            is_complete = False
        else:
            # Двухлопастный пропеллер: 2 шт. на мотор; для 4 моторов — 8 шт.
            items.append(self._make_bom_item(prop, quantity=motor_count * 2))

        return self._finalize(
            items, warnings, is_complete, req,
            frame_spec=frame_spec, motor_spec=motor_spec, battery_spec=battery_spec,
        )

    # --- Стадии подбора ---------------------------------------------------

    def _pick_frame(self, req: TenderRequirements) -> Optional[ComponentCatalogItem]:
        candidates = self._components.items_by_category("frame")
        candidates = [c for c in candidates if not c.discontinued]
        if not candidates:
            return None

        target_count = req.motor_count_min or req.motor_count_max
        target_prop = req.propeller_size_inch
        target_diag = req.frame_diagonal_mm

        def score(item: ComponentCatalogItem) -> float:
            spec = _parse_frame(item)
            s = 0.0
            if target_count is not None and spec.motor_mount_count == target_count:
                s += 3.0
            if target_diag is not None and spec.diagonal_mm:
                # квадратичное наказание за отклонение
                diff = abs(spec.diagonal_mm - target_diag)
                if diff <= 20:
                    s += 2.0
                elif diff <= 50:
                    s += 1.0
            if target_prop is not None and spec.prop_size_inch_max:
                if spec.prop_size_inch_max + 0.1 >= target_prop:
                    s += 1.5
            if self._prefer_own and item.catalog_source == "own":
                s += 1.0
            return s

        candidates_with_count = [
            c for c in candidates
            if target_count is None or _parse_frame(c).motor_mount_count == target_count
        ]
        pool = candidates_with_count or candidates
        return max(pool, key=score, default=None)

    def _pick_fc(
        self, req: TenderRequirements, frame_spec: FrameSpec
    ) -> Optional[ComponentCatalogItem]:
        candidates = [
            c for c in self._components.items_by_category("flight_controller")
            if not c.discontinued
        ]
        if not candidates:
            return None

        required_languages = {lang.lower() for lang in req.programmable_languages}
        required_software = {sw.lower() for sw in req.compatible_software}

        def score(item: ComponentCatalogItem) -> float:
            spec = _parse_fc(item)
            s = 0.0
            if required_languages:
                supported = {l.lower() for l in spec.programmable_languages}
                hit = required_languages & supported
                s += 3.0 * len(hit)
                if not hit:
                    s -= 2.0
            if required_software:
                fw = {f.lower() for f in spec.firmware}
                hit_sw = required_software & fw
                s += 1.5 * len(hit_sw)
            if self._prefer_own and item.catalog_source == "own":
                s += 1.0
            return s

        return max(candidates, key=score, default=None)

    def _pick_motor(
        self, req: TenderRequirements, frame_spec: FrameSpec
    ) -> Optional[ComponentCatalogItem]:
        candidates = [
            c for c in self._components.items_by_category("motor")
            if not c.discontinued
        ]
        if not candidates:
            return None

        compatible = [c for c in candidates if compat_frame_motor(frame_spec, _parse_motor(c))]
        pool = compatible or candidates

        def score(item: ComponentCatalogItem) -> float:
            spec = _parse_motor(item)
            s = 0.0
            if frame_spec.motor_mount_size_mm and spec.mount_size_mm:
                if abs(frame_spec.motor_mount_size_mm - spec.mount_size_mm) < 0.5:
                    s += 2.0
            # KV согласован с пропом (если задан)
            if req.propeller_size_inch and spec.kv:
                ok = False
                for (kv_min, kv_max), (prop_min, prop_max) in KV_TO_PROP_INCH_RANGE.items():
                    if kv_min <= spec.kv <= kv_max and prop_min <= req.propeller_size_inch <= prop_max:
                        ok = True
                        break
                if ok:
                    s += 1.5
            if self._prefer_own and item.catalog_source == "own":
                s += 1.0
            return s

        return max(pool, key=score, default=None)

    def _pick_esc(
        self, req: TenderRequirements, motor_spec: Optional[MotorSpec]
    ) -> Optional[ComponentCatalogItem]:
        if motor_spec is None:
            return None
        candidates = [
            c for c in self._components.items_by_category("esc")
            if not c.discontinued
        ]
        if not candidates:
            return None
        compatible = [c for c in candidates if compat_motor_esc(motor_spec, _parse_esc(c))]
        pool = compatible or candidates

        def score(item: ComponentCatalogItem) -> float:
            spec = _parse_esc(item)
            s = 0.0
            if motor_spec.max_current_a and spec.current_continuous_a:
                margin = spec.current_continuous_a / motor_spec.max_current_a
                if margin >= ESC_CURRENT_MARGIN:
                    s += 2.0 + min(margin - ESC_CURRENT_MARGIN, 1.0)
            if self._prefer_own and item.catalog_source == "own":
                s += 1.0
            return s

        return max(pool, key=score, default=None)

    def _pick_battery(
        self,
        req: TenderRequirements,
        motor_spec: Optional[MotorSpec],
        esc: Optional[ComponentCatalogItem],
    ) -> Optional[ComponentCatalogItem]:
        candidates = [
            c for c in self._components.items_by_category("battery")
            if not c.discontinued
        ]
        if not candidates:
            return None

        esc_spec = _parse_esc(esc) if esc else None

        def is_compatible(item: ComponentCatalogItem) -> bool:
            spec = _parse_battery(item)
            if motor_spec and not compat_motor_battery(motor_spec, spec):
                return False
            if esc_spec and not compat_esc_battery(esc_spec, spec):
                return False
            return True

        compatible = [c for c in candidates if is_compatible(c)]
        pool = compatible or candidates

        def score(item: ComponentCatalogItem) -> float:
            spec = _parse_battery(item)
            s = 0.0
            if req.flight_time_min_minutes and spec.capacity_mah and motor_spec:
                if motor_spec.max_current_a:
                    total_current = motor_spec.max_current_a * 4  # упрощённо для 4 моторов
                    ft = compute_flight_time_minutes(spec, total_current)
                    if ft and ft >= req.flight_time_min_minutes:
                        s += 3.0 + min((ft - req.flight_time_min_minutes) / 10.0, 2.0)
                    elif ft:
                        s += 0.5  # хоть какое-то время полёта
            if self._prefer_own and item.catalog_source == "own":
                s += 1.0
            return s

        return max(pool, key=score, default=None)

    def _pick_propeller(
        self,
        req: TenderRequirements,
        frame_spec: FrameSpec,
        motor_spec: Optional[MotorSpec],
    ) -> Optional[ComponentCatalogItem]:
        candidates = [
            c for c in self._components.items_by_category("propeller")
            if not c.discontinued
        ]
        if not candidates:
            return None

        def is_compatible(item: ComponentCatalogItem) -> bool:
            spec = _parse_propeller(item)
            if not compat_frame_prop(frame_spec, spec):
                return False
            if motor_spec and not compat_motor_prop(motor_spec, spec):
                return False
            return True

        compatible = [c for c in candidates if is_compatible(c)]
        pool = compatible or candidates

        def score(item: ComponentCatalogItem) -> float:
            spec = _parse_propeller(item)
            s = 0.0
            if req.propeller_size_inch and spec.diameter_inch:
                if abs(req.propeller_size_inch - spec.diameter_inch) <= 0.25:
                    s += 2.0
                elif abs(req.propeller_size_inch - spec.diameter_inch) <= 1.0:
                    s += 1.0
            if frame_spec.prop_size_inch_max and spec.diameter_inch:
                if spec.diameter_inch <= frame_spec.prop_size_inch_max + 0.1:
                    s += 1.0
            if self._prefer_own and item.catalog_source == "own":
                s += 1.0
            return s

        return max(pool, key=score, default=None)

    # --- Расчёт скоринга и финализация -----------------------------------

    def _finalize(
        self,
        items: List[BoMItem],
        warnings: List[str],
        is_complete: bool,
        req: TenderRequirements,
        frame_spec: Optional[FrameSpec],
        motor_spec: Optional[MotorSpec],
        battery_spec: Optional[BatterySpec],
    ) -> BoMResult:
        # coverage = доля закрытых обязательных категорий
        present_categories = {item.category for item in items}
        coverage = sum(
            1 for cat in REQUIRED_CATEGORIES if cat in present_categories
        ) / len(REQUIRED_CATEGORIES)

        # compat_score = 1.0 если нет warnings, иначе пропорциональное снижение
        # за каждое warning отнимаем по 1/(N этапов проверки)
        max_warnings = len(REQUIRED_CATEGORIES)
        compat_score = max(0.0, 1.0 - len(warnings) / max_warnings)

        total_price = self._sum_price(items)
        own_brand_share = self._compute_own_share(items)

        if req.budget_per_unit_rub and total_price:
            budget = req.budget_per_unit_rub
            if total_price <= budget:
                price_fit = 1.0
            else:
                # пропорциональное снижение, при 2× бюджета — 0
                excess = (total_price - budget) / budget
                price_fit = max(0.0, 1.0 - excess)
        else:
            price_fit = 1.0  # бюджет не задан — не штрафуем

        w_cov, w_compat, w_own, w_price = get_bom_weights()
        score = round(100 * (
            w_cov * coverage +
            w_compat * compat_score +
            w_own * own_brand_share +
            w_price * price_fit
        ))

        # Расчёт массы и времени полёта
        total_weight = self._compute_total_weight(items, frame_spec, motor_spec, battery_spec)
        flight_time = self._compute_flight_time(req, motor_spec, battery_spec)

        return BoMResult(
            items=items,
            total_price_rub=total_price,
            total_weight_g=total_weight,
            predicted_flight_time_minutes=flight_time,
            compatibility_warnings=warnings,
            score=max(0, min(score, 100)),
            is_complete=is_complete,
            own_brand_share=round(own_brand_share, 2),
        )

    # --- Утилиты финализации ---------------------------------------------

    def _make_bom_item(self, item: ComponentCatalogItem, quantity: int) -> BoMItem:
        return BoMItem(
            category=item.category,
            component_id=item.component_id,
            component_name=item.component_name,
            quantity=quantity,
            unit_price_rub=item.price_rub,
            catalog_source=item.catalog_source,
            compatibility_notes=[],
        )

    def _sum_price(self, items: Iterable[BoMItem]) -> Optional[float]:
        total = 0.0
        any_price = False
        for it in items:
            if it.unit_price_rub is None:
                continue
            any_price = True
            total += it.unit_price_rub * it.quantity
        return round(total, 2) if any_price else None

    def _compute_own_share(self, items: Iterable[BoMItem]) -> float:
        own_total = 0.0
        any_total = 0.0
        for it in items:
            if it.unit_price_rub is None:
                continue
            line = it.unit_price_rub * it.quantity
            any_total += line
            if it.catalog_source == "own":
                own_total += line
        if any_total <= 0:
            return 0.0
        return own_total / any_total

    def _compute_total_weight(
        self,
        items: Iterable[BoMItem],
        frame_spec: Optional[FrameSpec],
        motor_spec: Optional[MotorSpec],
        battery_spec: Optional[BatterySpec],
    ) -> Optional[float]:
        total = 0.0
        known = False
        if frame_spec and frame_spec.mass_g is not None:
            total += frame_spec.mass_g
            known = True
        if motor_spec and motor_spec.weight_g is not None:
            motor_count = sum(it.quantity for it in items if it.category == "motor")
            total += motor_spec.weight_g * motor_count
            known = True
        if battery_spec and battery_spec.weight_g is not None:
            total += battery_spec.weight_g
            known = True
        return round(total, 1) if known else None

    def _compute_flight_time(
        self,
        req: TenderRequirements,
        motor_spec: Optional[MotorSpec],
        battery_spec: Optional[BatterySpec],
    ) -> Optional[float]:
        if motor_spec is None or battery_spec is None:
            return None
        if motor_spec.max_current_a is None:
            return None
        n = req.motor_count_min or req.motor_count_max or 4
        return compute_flight_time_minutes(battery_spec, motor_spec.max_current_a * n)

    def _resolve_motor_count(self, req: TenderRequirements, frame_spec: FrameSpec) -> int:
        if frame_spec.motor_mount_count:
            return frame_spec.motor_mount_count
        return req.motor_count_min or req.motor_count_max or 4
