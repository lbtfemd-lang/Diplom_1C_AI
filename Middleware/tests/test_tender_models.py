"""Unit-тесты Pydantic-моделей прикладного расширения подбора БПЛА.

Покрывают: валидацию диапазонов числовых полей, кросс-проверку
motor_count_min ≤ motor_count_max, дефолтные значения, сериализацию и
десериализацию в JSON, обработку extra-полей.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.models.tender_models import (
    BoMItem,
    BoMResult,
    MatchRequest,
    MatchResponse,
    MatchResult,
    TenderParseRequest,
    TenderParseResponse,
    TenderRequirements,
)


# --- TenderRequirements: дефолты и базовая валидация ----------------------

class TestTenderRequirementsDefaults:
    def test_empty_payload_uses_defaults(self):
        req = TenderRequirements()
        assert req.intent == "auto"
        assert req.purpose is None
        assert req.drone_type is None
        assert req.motor_count_min is None
        assert req.motor_count_max is None
        assert req.programmable_languages == []
        assert req.required_payloads == []
        assert req.compatible_software == []
        assert req.notes == ""
        assert req.confidence == 0.5

    def test_lists_are_independent_per_instance(self):
        a = TenderRequirements()
        b = TenderRequirements()
        a.programmable_languages.append("Python")
        assert b.programmable_languages == []


class TestTenderRequirementsRanges:
    def test_motor_count_below_min_rejected(self):
        with pytest.raises(ValidationError):
            TenderRequirements(motor_count_min=0)

    def test_motor_count_above_max_rejected(self):
        with pytest.raises(ValidationError):
            TenderRequirements(motor_count_min=13)

    def test_payload_negative_rejected(self):
        with pytest.raises(ValidationError):
            TenderRequirements(payload_min_kg=-1)

    def test_payload_too_large_rejected(self):
        with pytest.raises(ValidationError):
            TenderRequirements(payload_min_kg=300)

    def test_flight_time_zero_rejected(self):
        with pytest.raises(ValidationError):
            TenderRequirements(flight_time_min_minutes=0)

    def test_propeller_size_too_small_rejected(self):
        with pytest.raises(ValidationError):
            TenderRequirements(propeller_size_inch=0.5)

    def test_quantity_zero_rejected(self):
        with pytest.raises(ValidationError):
            TenderRequirements(quantity=0)

    def test_budget_negative_rejected(self):
        with pytest.raises(ValidationError):
            TenderRequirements(budget_per_unit_rub=-100)

    def test_confidence_above_one_rejected(self):
        with pytest.raises(ValidationError):
            TenderRequirements(confidence=1.5)


class TestTenderRequirementsMotorCrossCheck:
    def test_valid_range_accepted(self):
        req = TenderRequirements(motor_count_min=4, motor_count_max=6)
        assert req.motor_count_min == 4
        assert req.motor_count_max == 6

    def test_equal_min_max_accepted(self):
        req = TenderRequirements(motor_count_min=4, motor_count_max=4)
        assert req.motor_count_min == 4
        assert req.motor_count_max == 4

    def test_inverted_range_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            TenderRequirements(motor_count_min=6, motor_count_max=4)
        assert "motor_count_max" in str(exc_info.value)

    def test_only_min_specified(self):
        req = TenderRequirements(motor_count_min=4)
        assert req.motor_count_min == 4
        assert req.motor_count_max is None

    def test_only_max_specified(self):
        req = TenderRequirements(motor_count_max=8)
        assert req.motor_count_min is None
        assert req.motor_count_max == 8


class TestTenderRequirementsEnums:
    def test_valid_intent_values(self):
        for intent in ("ready_model", "build_config", "auto"):
            req = TenderRequirements(intent=intent)
            assert req.intent == intent

    def test_invalid_intent_rejected(self):
        with pytest.raises(ValidationError):
            TenderRequirements(intent="unknown_mode")

    def test_invalid_drone_type_rejected(self):
        with pytest.raises(ValidationError):
            TenderRequirements(drone_type="ufo")

    def test_invalid_purpose_rejected(self):
        with pytest.raises(ValidationError):
            TenderRequirements(purpose="military")

    def test_payload_filter(self):
        req = TenderRequirements(required_payloads=["thermal_camera", "lidar"])
        assert "thermal_camera" in req.required_payloads
        assert "lidar" in req.required_payloads

    def test_invalid_payload_rejected(self):
        with pytest.raises(ValidationError):
            TenderRequirements(required_payloads=["nuclear_warhead"])


class TestTenderRequirementsExtraIgnored:
    def test_unknown_field_ignored(self):
        req = TenderRequirements.model_validate({
            "intent": "ready_model",
            "unknown_field": "some_value",
            "another_unknown": 42,
        })
        assert req.intent == "ready_model"
        assert not hasattr(req, "unknown_field")


class TestTenderRequirementsRoundtrip:
    def test_json_roundtrip_full(self):
        original = TenderRequirements(
            intent="ready_model",
            purpose="educational",
            drone_type="quadcopter",
            motor_count_min=4,
            motor_count_max=4,
            payload_min_kg=2.0,
            flight_time_min_minutes=15,
            range_min_km=2.0,
            propeller_size_inch=7.0,
            programmable_languages=["Python", "Lua"],
            required_payloads=["rgb_camera"],
            compatible_software=["Коптра Studio"],
            quantity=30,
            budget_per_unit_rub=60_000,
            notes="Школа №42",
            confidence=0.9,
        )
        as_json = original.model_dump_json()
        restored = TenderRequirements.model_validate_json(as_json)
        assert restored == original

    def test_json_roundtrip_empty(self):
        original = TenderRequirements()
        as_json = original.model_dump_json()
        restored = TenderRequirements.model_validate_json(as_json)
        assert restored == original

    def test_dict_roundtrip(self):
        original = TenderRequirements(
            drone_type="hexacopter",
            motor_count_min=6,
            motor_count_max=6,
            quantity=5,
        )
        as_dict = original.model_dump()
        restored = TenderRequirements.model_validate(as_dict)
        assert restored == original


# --- MatchResult / BoMItem / BoMResult / MatchResponse --------------------

class TestMatchResult:
    def test_valid_match_result(self):
        result = MatchResult(
            model_id="DRONE-001",
            model_name="Коптра Орлёнок",
            score=92,
            cosine_score=0.85,
            llm_score=95,
            coverage=0.9,
            matches=["поддерживает Python"],
            gaps=[],
            explanation="Полностью соответствует требованиям тендера.",
            price_rub=55_000,
            out_of_budget=False,
            catalog_source="own",
        )
        assert result.score == 92
        assert result.catalog_source == "own"

    def test_score_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            MatchResult(
                model_id="X",
                model_name="X",
                score=150,
                cosine_score=0.5,
                llm_score=80,
                coverage=0.5,
            )

    def test_cosine_above_one_rejected(self):
        with pytest.raises(ValidationError):
            MatchResult(
                model_id="X",
                model_name="X",
                score=80,
                cosine_score=1.5,
                llm_score=80,
                coverage=0.5,
            )

    def test_invalid_catalog_source_rejected(self):
        with pytest.raises(ValidationError):
            MatchResult(
                model_id="X",
                model_name="X",
                score=80,
                cosine_score=0.5,
                llm_score=80,
                coverage=0.5,
                catalog_source="external",
            )


class TestBoMItem:
    def test_valid_bom_item(self):
        item = BoMItem(
            category="frame",
            component_id="FRM-220",
            component_name="Рама Коптра 220 мм",
            quantity=1,
            unit_price_rub=2500,
            catalog_source="own",
        )
        assert item.category == "frame"
        assert item.compatibility_notes == []

    def test_invalid_category_rejected(self):
        with pytest.raises(ValidationError):
            BoMItem(
                category="weapon",
                component_id="X",
                component_name="X",
                quantity=1,
            )

    def test_zero_quantity_rejected(self):
        with pytest.raises(ValidationError):
            BoMItem(
                category="motor",
                component_id="X",
                component_name="X",
                quantity=0,
            )


class TestBoMResult:
    def test_default_bom_result(self):
        bom = BoMResult()
        assert bom.items == []
        assert bom.score == 0
        assert bom.is_complete is True
        assert bom.own_brand_share == 0.0
        assert bom.compatibility_warnings == []

    def test_full_bom_result_roundtrip(self):
        bom = BoMResult(
            items=[
                BoMItem(category="frame", component_id="FR-1",
                        component_name="Рама", quantity=1),
                BoMItem(category="motor", component_id="MT-1",
                        component_name="Мотор", quantity=4),
            ],
            total_price_rub=12_000,
            total_weight_g=420,
            predicted_flight_time_minutes=18.5,
            compatibility_warnings=["Батарея на пределе тока ESC"],
            score=85,
            is_complete=True,
            own_brand_share=0.72,
        )
        as_json = bom.model_dump_json()
        restored = BoMResult.model_validate_json(as_json)
        assert restored == bom

    def test_own_brand_share_above_one_rejected(self):
        with pytest.raises(ValidationError):
            BoMResult(own_brand_share=1.2)


class TestMatchResponse:
    def test_minimal_match_response(self):
        resp = MatchResponse(
            requirements=TenderRequirements(),
            intent_used="ready_model",
        )
        assert resp.results == []
        assert resp.bom is None
        assert resp.fallback_used is False
        assert resp.candidates_total == 0
        assert resp.elapsed_ms == 0

    def test_match_response_with_results(self):
        resp = MatchResponse(
            requirements=TenderRequirements(intent="ready_model"),
            intent_used="ready_model",
            results=[
                MatchResult(
                    model_id="DRONE-001",
                    model_name="Коптра Орлёнок",
                    score=92,
                    cosine_score=0.85,
                    llm_score=95,
                    coverage=0.9,
                    catalog_source="own",
                ),
            ],
            summary="Подобрана 1 модель",
            fallback_used=False,
            candidates_total=10,
            elapsed_ms=2400,
        )
        as_json = resp.model_dump_json()
        restored = MatchResponse.model_validate_json(as_json)
        assert restored == resp


class TestRequestEnvelopes:
    def test_tender_parse_request_requires_text(self):
        with pytest.raises(ValidationError):
            TenderParseRequest(tender_text="")

    def test_tender_parse_request_too_long_rejected(self):
        with pytest.raises(ValidationError):
            TenderParseRequest(tender_text="x" * 25_000)

    def test_match_request_carries_requirements(self):
        req = MatchRequest(requirements=TenderRequirements(intent="ready_model"))
        as_json = req.model_dump_json()
        restored = MatchRequest.model_validate_json(as_json)
        assert restored.requirements.intent == "ready_model"

    def test_tender_parse_response_default_summary(self):
        resp = TenderParseResponse(requirements=TenderRequirements())
        assert resp.summary == ""

    def test_request_serializes_to_dict(self):
        req = TenderParseRequest(tender_text="Нужен квадрокоптер")
        d = req.model_dump()
        assert d == {"tender_text": "Нужен квадрокоптер"}


# --- Корректность JSON-схемы для эндпоинтов FastAPI -----------------------

class TestJsonSchema:
    def test_tender_requirements_schema_has_all_fields(self):
        schema = TenderRequirements.model_json_schema()
        properties = set(schema["properties"].keys())
        expected_fields = {
            "intent", "purpose", "drone_type",
            "motor_count_min", "motor_count_max",
            "payload_min_kg", "flight_time_min_minutes",
            "range_min_km", "max_takeoff_weight_kg", "min_speed_km_h",
            "frame_diagonal_mm", "propeller_size_inch",
            "programmable_languages", "temperature_range", "ip_rating",
            "required_payloads", "compatible_software",
            "quantity", "budget_per_unit_rub",
            "notes", "confidence",
        }
        missing = expected_fields - properties
        assert not missing, f"Missing fields in schema: {missing}"

    def test_match_response_schema_has_required_fields(self):
        schema = MatchResponse.model_json_schema()
        properties = set(schema["properties"].keys())
        assert {"requirements", "intent_used", "results", "summary"}.issubset(properties)
