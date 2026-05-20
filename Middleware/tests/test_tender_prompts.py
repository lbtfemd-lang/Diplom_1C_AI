"""Тест синхронизации промптов с Pydantic-схемой TenderRequirements.

Проверяет, что в PARSE_PROMPT упомянуты все поля схемы TenderRequirements и
все enum-значения. Это страховка от ситуации, когда схему расширили, а промпт
забыли обновить (или наоборот).
"""

from __future__ import annotations

import re

from app.models.tender_models import TenderRequirements
from app.services.tender_prompts import PARSE_PROMPT, RERANK_PROMPT


# --- Базовые свойства промптов --------------------------------------------

class TestPromptIntegrity:
    def test_parse_prompt_is_non_empty_string(self):
        assert isinstance(PARSE_PROMPT, str)
        assert len(PARSE_PROMPT) > 500

    def test_rerank_prompt_is_non_empty_string(self):
        assert isinstance(RERANK_PROMPT, str)
        assert len(RERANK_PROMPT) > 500

    def test_parse_prompt_demands_pure_json(self):
        lower = PARSE_PROMPT.lower()
        assert "json" in lower
        assert "markdown" in lower

    def test_rerank_prompt_demands_pure_json(self):
        lower = RERANK_PROMPT.lower()
        assert "json" in lower
        assert "markdown" in lower


# --- Синхронизация с TenderRequirements -----------------------------------

class TestParsePromptSchemaSync:
    def test_parse_prompt_contains_all_schema_fields(self):
        """Все поля TenderRequirements должны быть упомянуты в промпте."""
        schema = TenderRequirements.model_json_schema()
        fields = set(schema["properties"].keys())
        missing = [f for f in fields if f not in PARSE_PROMPT]
        assert not missing, f"Fields not mentioned in PARSE_PROMPT: {missing}"

    def test_parse_prompt_mentions_all_intents(self):
        for value in ("ready_model", "build_config", "auto"):
            assert value in PARSE_PROMPT, f"Missing intent value: {value}"

    def test_parse_prompt_mentions_all_drone_types(self):
        for value in ("quadcopter", "hexacopter", "octocopter",
                      "fixed_wing", "helicopter", "vtol_hybrid"):
            assert value in PARSE_PROMPT, f"Missing drone_type: {value}"

    def test_parse_prompt_mentions_all_purposes(self):
        for value in ("educational", "fpv_racing", "logistics",
                      "aerial_photo", "surveillance", "general"):
            assert value in PARSE_PROMPT, f"Missing purpose: {value}"

    def test_parse_prompt_mentions_all_payloads(self):
        for value in ("rgb_camera", "thermal_camera", "lidar",
                      "multispectral", "delivery_box", "speaker", "other"):
            assert value in PARSE_PROMPT, f"Missing payload: {value}"

    def test_parse_prompt_explains_motor_count_range(self):
        """Промпт должен явно объяснять разницу min/max для motor_count."""
        for marker in ("motor_count_min", "motor_count_max"):
            assert marker in PARSE_PROMPT
        # хотя бы один пример с диапазоном моторов
        assert "не менее" in PARSE_PROMPT or "не более" in PARSE_PROMPT

    def test_parse_prompt_has_few_shot_examples(self):
        """В промпте должно быть не меньше двух few-shot-примеров."""
        # каждый пример помечен словом "ПРИМЕР"
        examples = re.findall(r"ПРИМЕР\s*\d+", PARSE_PROMPT)
        assert len(examples) >= 2, f"Expected >=2 examples, got {len(examples)}"

    def test_parse_prompt_examples_contain_pure_json_blocks(self):
        """Каждый пример заканчивается JSON-объектом, начинающимся с '{'."""
        # Простая эвристика — в тексте промпта есть строки, начинающиеся с {"intent":
        json_starts = re.findall(r'\{\s*"intent"\s*:', PARSE_PROMPT)
        assert len(json_starts) >= 2, "Expected at least 2 example JSON objects"


class TestRerankPromptSchemaSync:
    def test_rerank_prompt_lists_required_response_fields(self):
        for field in ("ranking", "summary", "model_id", "model_name",
                      "score", "matches", "gaps", "explanation"):
            assert field in RERANK_PROMPT, f"Missing field in RERANK_PROMPT: {field}"

    def test_rerank_prompt_warns_about_phantom_ids(self):
        """Промпт должен явно требовать брать model_id только из списка кандидатов."""
        lower = RERANK_PROMPT.lower()
        assert "model_id" in lower
        assert "кандидат" in lower

    def test_rerank_prompt_explains_score_ranges(self):
        """Промпт должен задавать шкалу score: 90..100, 70..89 и т.д."""
        # ищем хотя бы две границы
        ranges = re.findall(r"\d{2}\.\.\d{2,3}", RERANK_PROMPT)
        assert len(ranges) >= 3, f"Expected >=3 score ranges, got {ranges}"

    def test_rerank_prompt_has_example(self):
        assert "ПРИМЕР" in RERANK_PROMPT
        # пример содержит JSON с ranking
        assert '"ranking"' in RERANK_PROMPT
