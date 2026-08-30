"""
Общие настройки и фича-флаги middleware.

Модуль предоставляет тонкий слой над переменными окружения с кэшированием значений
на время жизни процесса.
"""

from __future__ import annotations

import os
from functools import lru_cache


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


def reset_cache() -> None:
    """Сбросить кэш всех настроек. Используется в тестах при monkeypatch на os.environ."""


__all__ = [
    "reset_cache",
]
