"""Тесты ConfigBuilder.

Покрывают: парсинг диапазонов напряжений, чистые функции совместимости,
расчёт времени полёта, успешную сборку для учебного дрона на ИПК1,
fallback на партнёра при отсутствии собственного компонента, неполную
сборку при пустом каталоге батарей, проверку приоритета own-бренда.
"""

from __future__ import annotations

import pytest

from app.models.tender_models import TenderRequirements
from app.services.component_index_service import ComponentIndexService
from app.services.config_builder import (
    BatterySpec,
    ConfigBuilder,
    EscSpec,
    FrameSpec,
    MotorSpec,
    PropellerSpec,
    _parse_voltage_range,
    compat_esc_battery,
    compat_frame_motor,
    compat_frame_prop,
    compat_motor_battery,
    compat_motor_esc,
    compat_motor_prop,
    compute_flight_time_minutes,
)


# --- Парсинг диапазона напряжений -----------------------------------------

class TestVoltageRangeParsing:
    def test_lipo_cells_format(self):
        result = _parse_voltage_range("3S-6S")
        assert result is not None
        v_min, v_max = result
        assert abs(v_min - 11.1) < 0.01  # 3S = 3*3.7
        assert abs(v_max - 22.2) < 0.01  # 6S = 6*3.7

    def test_volt_format(self):
        result = _parse_voltage_range("11.1-22.2V")
        assert result is not None
        v_min, v_max = result
        assert abs(v_min - 11.1) < 0.01
        assert abs(v_max - 22.2) < 0.01

    def test_invalid_string_returns_none(self):
        assert _parse_voltage_range("not a voltage") is None
        assert _parse_voltage_range(None) is None
        assert _parse_voltage_range("") is None

    def test_no_separator_returns_none(self):
        assert _parse_voltage_range("4S") is None


# --- Чистые функции совместимости ----------------------------------------

class TestCompatFrameMotor:
    def test_matching_mount_size(self):
        frame = FrameSpec(motor_mount_size_mm=16)
        motor = MotorSpec(mount_size_mm=16)
        assert compat_frame_motor(frame, motor) is True

    def test_mismatched_mount_size(self):
        frame = FrameSpec(motor_mount_size_mm=16)
        motor = MotorSpec(mount_size_mm=19)
        assert compat_frame_motor(frame, motor) is False

    def test_unknown_size_does_not_block(self):
        frame = FrameSpec(motor_mount_size_mm=None)
        motor = MotorSpec(mount_size_mm=16)
        assert compat_frame_motor(frame, motor) is True


class TestCompatMotorEsc:
    def test_esc_with_margin(self):
        # мотор 38 А, ESC 60 А — 60/38 = 1.58 > 1.2
        motor = MotorSpec(max_current_a=38)
        esc = EscSpec(current_continuous_a=60)
        assert compat_motor_esc(motor, esc) is True

    def test_esc_without_margin(self):
        # мотор 50 А, ESC 55 А — 55/50 = 1.1 < 1.2
        motor = MotorSpec(max_current_a=50)
        esc = EscSpec(current_continuous_a=55)
        assert compat_motor_esc(motor, esc) is False

    def test_unknown_does_not_block(self):
        motor = MotorSpec(max_current_a=None)
        esc = EscSpec(current_continuous_a=60)
        assert compat_motor_esc(motor, esc) is True


class TestCompatEscBattery:
    def test_in_range(self):
        esc = EscSpec(voltage_v="3S-6S")
        battery = BatterySpec(cells_s=4)  # 14.8 В попадает в 11.1..22.2
        assert compat_esc_battery(esc, battery) is True

    def test_out_of_range(self):
        esc = EscSpec(voltage_v="2S-3S")
        battery = BatterySpec(cells_s=6)  # 22.2 В выше диапазона
        assert compat_esc_battery(esc, battery) is False


class TestCompatMotorProp:
    def test_kv_2400_with_5inch(self):
        motor = MotorSpec(kv=2400)
        prop = PropellerSpec(diameter_inch=5.0)
        assert compat_motor_prop(motor, prop) is True

    def test_kv_2400_with_10inch(self):
        motor = MotorSpec(kv=2400)
        prop = PropellerSpec(diameter_inch=10.0)
        assert compat_motor_prop(motor, prop) is False

    def test_unknown_kv_does_not_block(self):
        motor = MotorSpec(kv=900)  # выходит за все таблицы (если 600..1100 не покрыто)
        prop = PropellerSpec(diameter_inch=12.0)
        # 900 ∈ (600, 1100), prop ∈ (10..13) → совместимо
        assert compat_motor_prop(motor, prop) is True


class TestCompatFrameProp:
    def test_within_max(self):
        frame = FrameSpec(prop_size_inch_max=5.5)
        prop = PropellerSpec(diameter_inch=5.0)
        assert compat_frame_prop(frame, prop) is True

    def test_exceeds_max(self):
        frame = FrameSpec(prop_size_inch_max=5.5)
        prop = PropellerSpec(diameter_inch=7.0)
        assert compat_frame_prop(frame, prop) is False


# --- Расчёт времени полёта -----------------------------------------------

class TestComputeFlightTime:
    def test_basic_calculation(self):
        battery = BatterySpec(capacity_mah=4000)
        # 4 мотора × 38А = 152А максимум, крейсер 35% = 53.2А
        # 4000 × 0.8 × 60 / 53.2 / 1000 = 3.6 минут — слишком мало для 4S 4000mAh,
        # но формула верна и масштаб реальный.
        ft = compute_flight_time_minutes(battery, total_max_current_a=152)
        assert ft is not None
        assert 3.0 < ft < 4.5

    def test_zero_current_returns_none(self):
        battery = BatterySpec(capacity_mah=4000)
        assert compute_flight_time_minutes(battery, total_max_current_a=0) is None

    def test_no_capacity_returns_none(self):
        battery = BatterySpec(capacity_mah=None)
        assert compute_flight_time_minutes(battery, total_max_current_a=100) is None


# --- Полная сборка с реальным каталогом ----------------------------------

OWN_FRAME = {
    "component_id": "FR-300", "component_name": "Рама Коптра 300",
    "category": "frame", "catalog_source": "own", "price_rub": 3000,
    "compatibility": {
        "motor_mount_count": 4,
        "motor_mount_size_mm": 16,
        "max_motor_diameter_mm": 28,
        "prop_size_inch_max": 7.5,
        "diagonal_mm": 300,
        "mass_g": 110,
    },
}

OWN_FC_IPK1 = {
    "component_id": "FC-IPK1", "component_name": "Полётный контроллер ИПК1",
    "category": "flight_controller", "catalog_source": "own", "price_rub": 5500,
    "compatibility": {
        "mcu": "STM32F405",
        "firmware": ["Betaflight", "INAV"],
        "voltage_input_v": "2S-6S",
        "uart_count": 5,
        "programmable_languages": ["Python"],
    },
}

OWN_MOTOR = {
    "component_id": "MT-2207", "component_name": "Мотор Коптра 2207 1700KV",
    "category": "motor", "catalog_source": "own", "price_rub": 1800,
    "compatibility": {
        "kv": 1700, "stator_size": "2207", "mount_size_mm": 16,
        "weight_g": 32, "max_current_a": 38, "voltage_v": "3S-6S",
    },
}

OWN_ESC = {
    "component_id": "ESC-60", "component_name": "Коптра ESC 60А",
    "category": "esc", "catalog_source": "own", "price_rub": 2200,
    "compatibility": {
        "current_continuous_a": 60, "current_burst_a": 80,
        "voltage_v": "3S-6S", "protocol": ["DShot600"],
    },
}

OWN_BATTERY = {
    "component_id": "BAT-4S-4000", "component_name": "Аккумулятор Коптра 4S 4000",
    "category": "battery", "catalog_source": "own", "price_rub": 3800,
    "compatibility": {
        "chemistry": "LiPo", "cells_s": 4, "capacity_mah": 4000,
        "c_rating": 50, "weight_g": 380, "connector": "XT60",
    },
}

OWN_PROPELLER = {
    "component_id": "PRP-7", "component_name": "Пропеллер Коптра 7\"",
    "category": "propeller", "catalog_source": "own", "price_rub": 250,
    "compatibility": {
        "diameter_inch": 7.0, "pitch": 4.5, "blade_count": 2,
        "material": "carbon", "mount_hole_mm": 5.0,
    },
}

PARTNER_BATTERY = {
    "component_id": "BAT-PARTNER", "component_name": "Tattu 4S 4000",
    "category": "battery", "catalog_source": "partner", "price_rub": 4500,
    "compatibility": {
        "chemistry": "LiPo", "cells_s": 4, "capacity_mah": 4000,
        "c_rating": 75, "weight_g": 360, "connector": "XT60",
    },
}

PARTNER_FRAME = {
    "component_id": "FR-PARTNER", "component_name": "TBS Source 300",
    "category": "frame", "catalog_source": "partner", "price_rub": 4000,
    "compatibility": {
        "motor_mount_count": 4,
        "motor_mount_size_mm": 16,
        "prop_size_inch_max": 7.5,
        "diagonal_mm": 300,
        "mass_g": 100,
    },
}


@pytest.fixture
def full_catalog(tmp_path):
    """Сервис компонентов с полным каталогом для основных тестов сборки."""
    svc = ComponentIndexService(
        index_path=str(tmp_path / "components_index.json"),
        embeddings_path=str(tmp_path / "components_embeddings.npy"),
    )
    svc.rebuild_from_components([
        OWN_FRAME, OWN_FC_IPK1, OWN_MOTOR, OWN_ESC, OWN_BATTERY, OWN_PROPELLER,
        PARTNER_BATTERY, PARTNER_FRAME,
    ])
    return svc


@pytest.fixture
def empty_battery_catalog(tmp_path):
    """Каталог без батарей — для теста неполной сборки."""
    svc = ComponentIndexService(
        index_path=str(tmp_path / "components_index.json"),
        embeddings_path=str(tmp_path / "components_embeddings.npy"),
    )
    svc.rebuild_from_components([
        OWN_FRAME, OWN_FC_IPK1, OWN_MOTOR, OWN_ESC, OWN_PROPELLER,
    ])
    return svc


class TestSuccessfulBuild:
    def test_educational_build_picks_own_brand(self, full_catalog):
        builder = ConfigBuilder(full_catalog, prefer_own_brand=True)
        req = TenderRequirements(
            intent="build_config",
            purpose="educational",
            drone_type="quadcopter",
            motor_count_min=4,
            motor_count_max=4,
            frame_diagonal_mm=300,
            propeller_size_inch=7.0,
            programmable_languages=["Python"],
        )
        bom = builder.build(req)
        assert bom.is_complete is True
        # Проверяем категории
        categories = {item.category for item in bom.items}
        assert {"frame", "flight_controller", "motor",
                "esc", "battery", "propeller"}.issubset(categories)
        # Все собственные комплектующие в приоритете
        own_items = [it for it in bom.items if it.catalog_source == "own"]
        assert len(own_items) >= 5  # все 6 own-компонентов выиграли в приоритете
        # ИПК1 как контроллер
        fc_item = next(it for it in bom.items if it.category == "flight_controller")
        assert fc_item.component_id == "FC-IPK1"
        # Доля собственного бренда высокая
        assert bom.own_brand_share >= 0.9
        # Скоринг разумный
        assert bom.score >= 70
        # Цена и масса посчитаны
        assert bom.total_price_rub is not None
        assert bom.total_weight_g is not None and bom.total_weight_g > 100
        # Время полёта посчитано
        assert bom.predicted_flight_time_minutes is not None

    def test_motor_quantity_matches_frame(self, full_catalog):
        builder = ConfigBuilder(full_catalog)
        req = TenderRequirements(motor_count_min=4, motor_count_max=4,
                                 frame_diagonal_mm=300)
        bom = builder.build(req)
        motor_item = next(it for it in bom.items if it.category == "motor")
        esc_item = next(it for it in bom.items if it.category == "esc")
        assert motor_item.quantity == 4
        assert esc_item.quantity == 4

    def test_propeller_quantity_doubled(self, full_catalog):
        builder = ConfigBuilder(full_catalog)
        req = TenderRequirements(motor_count_min=4, motor_count_max=4,
                                 frame_diagonal_mm=300, propeller_size_inch=7.0)
        bom = builder.build(req)
        prop_item = next(it for it in bom.items if it.category == "propeller")
        # 4 мотора × 2 пропа = 8 шт.
        assert prop_item.quantity == 8


class TestPartnerFallback:
    def test_partner_battery_chosen_when_no_own(self, tmp_path):
        """Если нет own-батареи, должен выбраться партнёрский вариант."""
        svc = ComponentIndexService(
            index_path=str(tmp_path / "ci.json"),
            embeddings_path=str(tmp_path / "ce.npy"),
        )
        svc.rebuild_from_components([
            OWN_FRAME, OWN_FC_IPK1, OWN_MOTOR, OWN_ESC, OWN_PROPELLER,
            PARTNER_BATTERY,  # только партнёрская батарея доступна
        ])
        builder = ConfigBuilder(svc, prefer_own_brand=True)
        req = TenderRequirements(motor_count_min=4, motor_count_max=4,
                                 frame_diagonal_mm=300)
        bom = builder.build(req)
        assert bom.is_complete is True
        bat_item = next(it for it in bom.items if it.category == "battery")
        assert bat_item.catalog_source == "partner"
        # own_brand_share меньше 1.0
        assert bom.own_brand_share < 1.0


class TestIncompleteBuild:
    def test_no_battery_warns_and_marks_incomplete(self, empty_battery_catalog):
        builder = ConfigBuilder(empty_battery_catalog)
        req = TenderRequirements(motor_count_min=4, motor_count_max=4,
                                 frame_diagonal_mm=300)
        bom = builder.build(req)
        assert bom.is_complete is False
        assert any("батаре" in w.lower() for w in bom.compatibility_warnings)
        # Категория battery отсутствует, но остальные на месте
        categories = {item.category for item in bom.items}
        assert "battery" not in categories
        assert {"frame", "flight_controller", "motor", "esc", "propeller"}.issubset(categories)


class TestOwnBrandPriority:
    def test_own_frame_chosen_over_partner(self, full_catalog):
        builder = ConfigBuilder(full_catalog, prefer_own_brand=True)
        req = TenderRequirements(motor_count_min=4, motor_count_max=4,
                                 frame_diagonal_mm=300)
        bom = builder.build(req)
        frame_item = next(it for it in bom.items if it.category == "frame")
        assert frame_item.catalog_source == "own"
        assert frame_item.component_id == "FR-300"

    def test_prefer_own_disabled_still_picks_one(self, full_catalog):
        builder = ConfigBuilder(full_catalog, prefer_own_brand=False)
        req = TenderRequirements(motor_count_min=4, motor_count_max=4)
        bom = builder.build(req)
        # Сборка состоится — конкретный выбор может быть любым, но рама есть
        assert any(it.category == "frame" for it in bom.items)


class TestEmptyCatalog:
    def test_no_frames_returns_empty_bom(self, tmp_path):
        svc = ComponentIndexService(
            index_path=str(tmp_path / "ci.json"),
            embeddings_path=str(tmp_path / "ce.npy"),
        )
        # Пустой каталог
        svc.rebuild_from_components([])
        builder = ConfigBuilder(svc)
        req = TenderRequirements(motor_count_min=4)
        bom = builder.build(req)
        assert bom.is_complete is False
        assert len(bom.items) == 0
        assert any("рам" in w.lower() for w in bom.compatibility_warnings)
