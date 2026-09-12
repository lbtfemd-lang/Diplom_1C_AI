# -*- coding: utf-8 -*-
"""
Общая настройка подключения к SQLite для сервисов middleware.

Проект использует один файл БД (`kanban.db`) из двух модулей — `auth_service`
и `kanban_service`, каждый со своим engine. При журнале по умолчанию (DELETE)
писатель блокирует читателей на всё время транзакции, что под конкурентной
нагрузкой давало задержки в десятки секунд.

Режим WAL (Write-Ahead Logging) снимает эту блокировку: читатели работают
параллельно с писателем. `synchronous=NORMAL` — рекомендованный для WAL
компромисс между надёжностью и скоростью (fsync только при контрольной точке),
`busy_timeout` заставляет соединение ждать освобождения блокировки вместо
немедленной ошибки «database is locked».
"""

from sqlalchemy import event
from sqlalchemy.engine import Engine


def enable_sqlite_wal(engine: Engine, busy_timeout_ms: int = 5000) -> Engine:
    """Включает WAL и сопутствующие прагмы для каждого нового соединения engine."""

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
        finally:
            cursor.close()

    return engine
