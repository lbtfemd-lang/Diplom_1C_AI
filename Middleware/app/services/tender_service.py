"""
Координатор подбора по тендерной заявке.

Объединяет три подсистемы прикладного расширения:
    - LLM-парсинг текста тендера в структуру TenderRequirements,
    - семантический отбор кандидатов через DroneIndexService,
    - LLM-реранжирование с финальным взвешенным скорингом,
    - детерминированную сборку BoM через ConfigBuilder при intent=build_config или auto.

Все обращения к внешней LLM выполняются через приватные методы
`_call_llm_parse` и `_call_llm_rerank`, чтобы тесты могли подменять их
через monkeypatch без обращения к сети.
"""

from __future__ import annotations

import json
import time
from typing import Callable, List, Optional

from app.core import get_drone_topk, get_match_topn, get_match_weights
from app.models.tender_models import (
    BoMResult,
    MatchIntent,
    MatchResponse,
    MatchResult,
    TenderRequirements,
)

from .config_builder import ConfigBuilder
from .drone_index_service import DroneCandidate, DroneIndexService
from .llm_service import LLMService
from .tender_prompts import PARSE_PROMPT, RERANK_PROMPT


# --- Исключения -----------------------------------------------------------

class TenderParseError(Exception):
    """LLM не вернула валидный JSON по схеме TenderRequirements."""


# --- Таймаут rerank в секундах. Используется только для документации;
#     фактический таймаут реализуется на уровне LLM-клиента.
RERANK_TIMEOUT_SEC = 12.0


class TenderService:
    """Координатор парсинга, подбора и сборки конфигурации.

    Параметры:
        llm:           LLMService для вызовов внешней модели.
        drone_index:   DroneIndexService с каталогом моделей БПЛА.
        config_builder: ConfigBuilder с детерминированной сборкой BoM.
    """

    def __init__(
        self,
        llm: LLMService,
        drone_index: DroneIndexService,
        config_builder: ConfigBuilder,
    ):
        self._llm = llm
        self._drones = drone_index
        self._builder = config_builder

    # --- Публичные методы --------------------------------------------------

    async def parse(self, tender_text: str) -> TenderRequirements:
        """Извлечь структурированные требования из текста тендера.

        Один вызов LLM с детерминированными настройками. При невозможности
        распарсить результат бросает TenderParseError.
        """
        text = (tender_text or "").strip()
        if not text:
            raise TenderParseError("Empty tender text")
        raw = await self._call_llm_parse(text)
        parsed = self._llm._extract_json(raw) if raw else None
        if not parsed:
            raise TenderParseError("Failed to extract JSON from LLM response")
        try:
            return TenderRequirements.model_validate(parsed)
        except Exception as exc:
            raise TenderParseError(f"Validation failed: {exc}") from exc

    async def match(self, requirements: TenderRequirements) -> MatchResponse:
        """Главная точка входа подбора.

        Маршрутизирует по intent:
            - ready_model: только LLM-rerank готовых моделей;
            - build_config: только ConfigBuilder.build;
            - auto: оба алгоритма, в результат включаются и модели, и BoM.
        """
        started = time.monotonic()
        intent_used = requirements.intent

        results: List[MatchResult] = []
        bom: Optional[BoMResult] = None
        summary_parts: List[str] = []
        fallback_used = False
        candidates_total = 0

        if requirements.intent in ("ready_model", "auto"):
            ranked, total, llm_summary, fallback = await self._match_ready_models(requirements)
            results = ranked
            candidates_total = total
            fallback_used = fallback
            if llm_summary:
                summary_parts.append(llm_summary)
            elif results:
                top = results[0]
                summary_parts.append(
                    f"Лучший вариант: {top.model_name} (score {top.score})."
                )

        if requirements.intent in ("build_config", "auto"):
            bom = self._builder.build(requirements)
            if bom.items:
                summary_parts.append(
                    f"Сборка из {len(bom.items)} компонентов "
                    f"(score {bom.score}, комплектность {'полная' if bom.is_complete else 'частичная'})."
                )

        elapsed_ms = int((time.monotonic() - started) * 1000)
        summary = " ".join(summary_parts).strip() or "Подбор завершён."

        return MatchResponse(
            requirements=requirements,
            intent_used=intent_used,
            results=results,
            bom=bom,
            summary=summary,
            fallback_used=fallback_used,
            candidates_total=candidates_total,
            elapsed_ms=elapsed_ms,
        )

    async def parse_and_match(self, tender_text: str) -> MatchResponse:
        """Вспомогательный метод для тестов golden-set: parse → match."""
        requirements = await self.parse(tender_text)
        return await self.match(requirements)

    # --- Вспомогательные методы --------------------------------------------

    async def _match_ready_models(
        self, requirements: TenderRequirements
    ) -> tuple[List[MatchResult], int, str, bool]:
        """Семантический отбор + LLM-rerank + финальный скоринг."""
        if not self._drones.is_ready():
            return [], 0, "", False

        top_k = get_drone_topk()
        query_text = self._build_query_text(requirements)
        candidates = self._drones.find_top_matches(
            query_text=query_text,
            top_k=top_k,
            type_filter=requirements.drone_type,
            budget_per_unit_rub=requirements.budget_per_unit_rub,
        )
        if not candidates:
            return [], 0, "", False

        # Coverage считается локально, без LLM (Property 4).
        coverage_by_id = {
            c.item.model_id: self._compute_coverage(requirements, c) for c in candidates
        }

        # LLM-rerank
        try:
            rerank_payload = await self._call_llm_rerank(requirements, candidates)
            llm_data = self._llm._extract_json(rerank_payload) if rerank_payload else None
        except Exception as exc:  # pragma: no cover - сетевые ошибки
            print(f"TenderService: rerank exception: {exc}")
            llm_data = None

        if not llm_data or not llm_data.get("ranking"):
            # Fallback на cosine-сортировку
            results = self._fallback_results(candidates, coverage_by_id)
            summary = "Подбор выполнен по семантическому поиску (LLM-реранжирование недоступно)."
            return results, len(candidates), summary, True

        # Валидация ответа LLM
        candidate_ids = {c.item.model_id for c in candidates}
        ranking = llm_data.get("ranking", [])
        valid_entries = []
        for entry in ranking:
            if not isinstance(entry, dict):
                continue
            mid = entry.get("model_id")
            if not mid or mid not in candidate_ids:
                continue
            valid_entries.append(entry)

        if not valid_entries:
            results = self._fallback_results(candidates, coverage_by_id)
            summary = "Подбор выполнен по семантическому поиску (LLM вернула невалидный ответ)."
            return results, len(candidates), summary, True

        # Финальный взвешенный скоринг
        w_cos, w_cov, w_llm = get_match_weights()
        candidate_by_id = {c.item.model_id: c for c in candidates}
        results: List[MatchResult] = []
        for entry in valid_entries:
            mid = entry["model_id"]
            cand = candidate_by_id[mid]
            llm_score = int(entry.get("score", 0))
            llm_score = max(0, min(llm_score, 100))
            cosine = cand.cosine_score
            coverage = coverage_by_id.get(mid, 0.0)
            final = round(100 * (
                w_cos * cosine + w_cov * coverage + w_llm * (llm_score / 100.0)
            ))
            final = max(0, min(final, 100))
            results.append(MatchResult(
                model_id=mid,
                model_name=str(entry.get("model_name") or cand.item.model_name),
                score=final,
                cosine_score=float(cosine),
                llm_score=llm_score,
                coverage=float(coverage),
                matches=list(entry.get("matches", []) or []),
                gaps=list(entry.get("gaps", []) or []),
                explanation=str(entry.get("explanation", "") or ""),
                price_rub=cand.item.price_rub,
                out_of_budget=cand.out_of_budget,
                catalog_source=cand.item.catalog_source,
            ))

        # Сортировка и обрезка
        results.sort(key=lambda r: r.score, reverse=True)
        results = results[:get_match_topn()]
        summary = str(llm_data.get("summary") or "")
        return results, len(candidates), summary, False

    def _fallback_results(
        self,
        candidates: List[DroneCandidate],
        coverage_by_id: dict,
    ) -> List[MatchResult]:
        """Список результатов без LLM-rerank: только cosine + coverage."""
        results: List[MatchResult] = []
        w_cos, w_cov, _ = get_match_weights()
        # При отсутствии LLM присвоим веса cos и cov пропорционально их доле
        denom = w_cos + w_cov or 1.0
        wn_cos = w_cos / denom
        wn_cov = w_cov / denom
        for cand in candidates:
            cosine = cand.cosine_score
            coverage = coverage_by_id.get(cand.item.model_id, 0.0)
            final = round(100 * (wn_cos * cosine + wn_cov * coverage))
            final = max(0, min(final, 100))
            results.append(MatchResult(
                model_id=cand.item.model_id,
                model_name=cand.item.model_name,
                score=final,
                cosine_score=float(cosine),
                llm_score=round(cosine * 100),
                coverage=float(coverage),
                matches=[],
                gaps=[],
                explanation="Подобрано семантическим поиском (LLM-реранжирование недоступно).",
                price_rub=cand.item.price_rub,
                out_of_budget=cand.out_of_budget,
                catalog_source=cand.item.catalog_source,
            ))
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:get_match_topn()]

    def _compute_coverage(
        self, req: TenderRequirements, cand: DroneCandidate
    ) -> float:
        """Доля выполненных требований без участия LLM (Property 4)."""
        item = cand.item
        checks: List[bool] = []

        if req.drone_type is not None:
            checks.append(item.drone_type == req.drone_type)
        if req.purpose is not None:
            checks.append(item.purpose == req.purpose)
        if req.motor_count_min is not None and item.motor_count is not None:
            checks.append(item.motor_count >= req.motor_count_min)
        if req.motor_count_max is not None and item.motor_count is not None:
            checks.append(item.motor_count <= req.motor_count_max)
        if req.payload_min_kg is not None and item.payload_kg is not None:
            checks.append(item.payload_kg >= req.payload_min_kg)
        if req.flight_time_min_minutes is not None and item.flight_time_minutes is not None:
            checks.append(item.flight_time_minutes >= req.flight_time_min_minutes)
        if req.range_min_km is not None and item.range_km is not None:
            checks.append(item.range_km >= req.range_min_km)
        if req.min_speed_km_h is not None and item.max_speed_km_h is not None:
            checks.append(item.max_speed_km_h >= req.min_speed_km_h)
        if req.frame_diagonal_mm is not None and item.frame_diagonal_mm is not None:
            checks.append(abs(item.frame_diagonal_mm - req.frame_diagonal_mm) <= 50)
        if req.programmable_languages:
            req_set = {l.lower() for l in req.programmable_languages}
            item_set = {l.lower() for l in item.programmable_languages}
            checks.append(bool(req_set & item_set))
        if req.compatible_software:
            req_set = {s.lower() for s in req.compatible_software}
            item_set = {s.lower() for s in item.compatible_software}
            checks.append(bool(req_set & item_set))
        if req.required_payloads:
            req_set = {p.lower() for p in req.required_payloads}
            item_set = {p.lower() for p in item.supported_payloads}
            checks.append(bool(req_set & item_set))
        if req.budget_per_unit_rub is not None and item.price_rub is not None:
            checks.append(item.price_rub <= req.budget_per_unit_rub * 1.2)

        if not checks:
            return 0.5  # требования пустые — считаем половинку
        return sum(1 for c in checks if c) / len(checks)

    def _build_query_text(self, req: TenderRequirements) -> str:
        """Построить текстовый запрос для семантического поиска кандидатов.

        Тип конструкции и обязательные нагрузки повторяются для усиления вклада.
        """
        parts: List[str] = []
        if req.drone_type:
            parts.extend([req.drone_type, req.drone_type])
        if req.purpose:
            parts.extend([req.purpose, req.purpose])
        if req.motor_count_min:
            parts.append(f"{req.motor_count_min} мотор")
        if req.payload_min_kg:
            parts.append(f"грузоподъёмность {req.payload_min_kg} кг")
        if req.flight_time_min_minutes:
            parts.append(f"время полёта {req.flight_time_min_minutes} минут")
        if req.range_min_km:
            parts.append(f"дальность {req.range_min_km} км")
        if req.frame_diagonal_mm:
            parts.append(f"диагональ {req.frame_diagonal_mm} мм")
        if req.propeller_size_inch:
            parts.append(f"пропеллер {req.propeller_size_inch}\"")
        if req.programmable_languages:
            parts.append("программирование " + " ".join(req.programmable_languages))
        if req.required_payloads:
            # Двойной повтор требуемых нагрузок
            for p in req.required_payloads:
                parts.extend([p, p])
        if req.compatible_software:
            parts.extend(req.compatible_software)
        if req.notes:
            parts.append(req.notes[:200])
        return " ".join(parts) or "БПЛА"

    # --- Вызовы LLM (точки расширения для monkeypatch) ---------------------

    async def _call_llm_parse(self, tender_text: str) -> str:
        """Однократный вызов LLM для парсинга. Возвращает сырой ответ."""
        return await self._invoke_llm(
            system_prompt=PARSE_PROMPT,
            user_message=tender_text,
            temperature=0.0,
        )

    async def _call_llm_rerank(
        self,
        requirements: TenderRequirements,
        candidates: List[DroneCandidate],
    ) -> str:
        """Вызов LLM для реранжирования. Возвращает сырой ответ."""
        user_message = self._format_rerank_input(requirements, candidates)
        return await self._invoke_llm(
            system_prompt=RERANK_PROMPT,
            user_message=user_message,
            temperature=0.2,
        )

    async def _invoke_llm(
        self, system_prompt: str, user_message: str, temperature: float
    ) -> str:
        """Один вызов LLMService в стиле OpenAI ChatCompletions."""
        client = getattr(self._llm, "client", None)
        if client is None:
            return ""
        try:
            completion = client.chat.completions.create(
                model=self._llm.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=temperature,
                max_tokens=1500,
            )
            return completion.choices[0].message.content or ""
        except Exception as exc:  # pragma: no cover
            print(f"TenderService: LLM call failed: {exc}")
            return ""

    @staticmethod
    def _format_rerank_input(
        requirements: TenderRequirements,
        candidates: List[DroneCandidate],
    ) -> str:
        """Сформировать пользовательское сообщение для rerank-промпта."""
        lines: List[str] = ["ТРЕБОВАНИЯ:"]
        lines.append(json.dumps(requirements.model_dump(), ensure_ascii=False, indent=2))
        lines.append("")
        lines.append("КАНДИДАТЫ (model_id, name, type, purpose, motors, ttx, source, price):")
        for c in candidates:
            it = c.item
            ttx_parts = []
            if it.flight_time_minutes:
                ttx_parts.append(f"{it.flight_time_minutes} мин")
            if it.range_km:
                ttx_parts.append(f"{it.range_km} км")
            if it.max_speed_km_h:
                ttx_parts.append(f"{it.max_speed_km_h} км/ч")
            if it.payload_kg:
                ttx_parts.append(f"{it.payload_kg} кг")
            ttx = ", ".join(ttx_parts) or "—"
            lines.append(
                f"- {it.model_id} | {it.model_name} | {it.drone_type or '—'} | "
                f"{it.purpose or '—'} | {it.motor_count or '—'} моторов | {ttx} | "
                f"{it.catalog_source} | {it.price_rub or '—'} ₽ | "
                f"cosine={c.cosine_score:.3f}{' | вне бюджета' if c.out_of_budget else ''}"
            )
        return "\n".join(lines)


# --- Singleton ------------------------------------------------------------

# Импорты делаются на уровне модуля только при первом обращении к фабрике,
# чтобы тесты могли подменить компоненты до создания экземпляра.

_singleton: Optional[TenderService] = None


def get_tender_service() -> TenderService:
    """Ленивый singleton с дефолтными зависимостями."""
    global _singleton
    if _singleton is None:
        from .component_index_service import component_index_service
        from .drone_index_service import drone_index_service
        from .llm_service import llm_service

        builder = ConfigBuilder(component_index_service)
        _singleton = TenderService(llm_service, drone_index_service, builder)
    return _singleton


def reset_tender_service_for_tests() -> None:
    """Сбросить singleton — для unit-тестов."""
    global _singleton
    _singleton = None
