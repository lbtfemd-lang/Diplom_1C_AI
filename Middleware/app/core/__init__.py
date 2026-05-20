"""
Общие настройки и фича-флаги middleware.

Модуль предоставляет тонкий слой над переменными окружения с кэшированием значений
на время жизни процесса. Используется прикладным расширением «Подбор моделей БПЛА
по тендерной заявке» для согласованного чтения параметров из .env.

Функции:
    is_drone_feature_enabled() -> bool
        Возвращает True, если фича-флаг DRONE_FEATURE_ENABLED включён.

    get_drone_topk() -> int
        Размер top-K при семантическом отборе кандидатов в каталоге БПЛА.

    get_match_topn() -> int
        Лимит ранжированного списка готовых моделей в финальном ответе.

    get_match_weights() -> tuple[float, float, float]
        Веса финального скоринга готовой модели (W_COSINE, W_COVER, W_LLM).
        Сумма проверяется на равенство 1.0 с допустимым отклонением 1e-3;
        при нарушении баланса бросает ValueError.

    get_bom_weights() -> tuple[float, float, float, float]
        Веса скоринга собранной конфигурации BoM
        (BOM_W_COVER, BOM_W_COMPAT, BOM_W_OWN, BOM_W_PRICE_FIT).
        Сумма проверяется на равенство 1.0 с допустимым отклонением 1e-3.

    get_eval_mode() -> str
        Режим тестов качества подбора: "live", "offline" или "record".
        По умолчанию "live" (полные обращения к LLM).
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Tuple


_TRUE_VALUES = {"1", "true", "yes", "on", "y", "t"}


def _read_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUE_VALUES


def _read_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(
            f"Environment variable {name}={raw!r} is not a valid float"
        ) from exc


def _read_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(
            f"Environment variable {name}={raw!r} is not a valid int"
        ) from exc


@lru_cache(maxsize=1)
def is_drone_feature_enabled() -> bool:
    """Включён ли фича-флаг прикладного расширения подбора БПЛА.

    Значение читается один раз и кэшируется до перезапуска процесса.
    Для локального переопределения в тестах используйте reset_cache().
    """
    return _read_bool("DRONE_FEATURE_ENABLED", default=True)


@lru_cache(maxsize=1)
def get_drone_topk() -> int:
    value = _read_int("DRONE_TOPK", default=10)
    if value < 1:
        raise ValueError(f"DRONE_TOPK must be >= 1, got {value}")
    return value


@lru_cache(maxsize=1)
def get_match_topn() -> int:
    value = _read_int("MATCH_TOPN", default=5)
    if value < 1:
        raise ValueError(f"MATCH_TOPN must be >= 1, got {value}")
    return value


@lru_cache(maxsize=1)
def get_match_weights() -> Tuple[float, float, float]:
    w_cos = _read_float("W_COSINE", default=0.20)
    w_cov = _read_float("W_COVER", default=0.35)
    w_llm = _read_float("W_LLM", default=0.45)
    total = w_cos + w_cov + w_llm
    if abs(total - 1.0) > 1e-3:
        raise ValueError(
            "Match weights must sum to 1.0, got "
            f"W_COSINE={w_cos}, W_COVER={w_cov}, W_LLM={w_llm}, sum={total:.4f}"
        )
    return w_cos, w_cov, w_llm


@lru_cache(maxsize=1)
def get_bom_weights() -> Tuple[float, float, float, float]:
    w_cov = _read_float("BOM_W_COVER", default=0.35)
    w_compat = _read_float("BOM_W_COMPAT", default=0.30)
    w_own = _read_float("BOM_W_OWN", default=0.15)
    w_price = _read_float("BOM_W_PRICE_FIT", default=0.20)
    total = w_cov + w_compat + w_own + w_price
    if abs(total - 1.0) > 1e-3:
        raise ValueError(
            "BoM weights must sum to 1.0, got "
            f"BOM_W_COVER={w_cov}, BOM_W_COMPAT={w_compat}, "
            f"BOM_W_OWN={w_own}, BOM_W_PRICE_FIT={w_price}, sum={total:.4f}"
        )
    return w_cov, w_compat, w_own, w_price


@lru_cache(maxsize=1)
def get_eval_mode() -> str:
    raw = os.getenv("DRONE_EVAL_MODE", "live").strip().lower() or "live"
    if raw not in {"live", "offline", "record"}:
        raise ValueError(
            f"DRONE_EVAL_MODE must be one of: live, offline, record. Got: {raw!r}"
        )
    return raw


def reset_cache() -> None:
    """Сбросить кэш всех настроек. Используется в тестах при monkeypatch на os.environ."""
    is_drone_feature_enabled.cache_clear()
    get_drone_topk.cache_clear()
    get_match_topn.cache_clear()
    get_match_weights.cache_clear()
    get_bom_weights.cache_clear()
    get_eval_mode.cache_clear()


__all__ = [
    "is_drone_feature_enabled",
    "get_drone_topk",
    "get_match_topn",
    "get_match_weights",
    "get_bom_weights",
    "get_eval_mode",
    "reset_cache",
]
