"""Доступ к данным. Две роли, два пула, разные права.

bi_reader — всё, что построено из запроса пользователя: только чтение,
read-only транзакция, таймаут 10с. app — сохранённые дашборды: пишет только
в свою схему, к данным ходит так же на чтение.

Транзакция чтения помечается read-only и на стороне клиента: роль это уже
гарантирует, но дублирование здесь стоит одной строки и закрывает случай,
когда кто-то подменит DSN в конфиге.
"""

from datetime import date
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import settings

_pool: ConnectionPool | None = None
_app_pool: ConnectionPool | None = None


def open_pool() -> None:
    global _pool, _app_pool
    if _pool is None:
        _pool = ConnectionPool(settings.bi_reader_dsn, min_size=1, max_size=4, open=True)
    if _app_pool is None:
        _app_pool = ConnectionPool(settings.app_dsn, min_size=1, max_size=2, open=True)


def close_pool() -> None:
    global _pool, _app_pool
    if _pool is not None:
        _pool.close()
        _pool = None
    if _app_pool is not None:
        _app_pool.close()
        _app_pool = None


def select(sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    if _pool is None:
        raise RuntimeError("пул соединений не открыт")
    with _pool.connection() as conn:
        conn.read_only = True
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params or [])
            return cur.fetchall()


def app_query(sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    """Запрос под ролью app. Единственный путь к схеме app."""
    if _app_pool is None:
        raise RuntimeError("пул соединений app не открыт")
    with _app_pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params or [])
            if cur.description is None:
                return []
            return cur.fetchall()


def fact_horizon() -> date:
    """Последний месяц, в котором есть факт. От него считаются все
    относительные периоды — см. sql_builder.resolve_period.
    """
    rows = select("SELECT last_full_month FROM fact_horizon")
    return rows[0]["last_full_month"]
