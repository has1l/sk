"""Справочники значений разрезов.

Нужны в двух местах. Первое — промпт: модель должна видеть, что регион
называется «Северо-Западный», а не «Северо-Запад». Второе — сверка: модель
всё равно возвращает «напитки» вместо «Напитки», и такой фильтр молча дал бы
пустой график. Поэтому любое значение перед попаданием в SQL сверяется здесь.

Точек 300 — в промпт они не влезают, поэтому ищутся по базе подстрокой.
"""

from app.db import select
from app.schema import Dimension

COLUMNS: dict[Dimension, str] = {
    Dimension.REGION: "region_name",
    Dimension.OUTLET_TYPE: "outlet_type",
    Dimension.CATEGORY: "category",
    Dimension.CITY: "city",
    Dimension.PRODUCT: "product_name",
    Dimension.OUTLET: "outlet_name",
}

MAX_IN_PROMPT = 100

_values: dict[Dimension, list[str]] = {}


def load() -> None:
    _values.clear()
    for dimension, column in COLUMNS.items():
        rows = select(
            f"SELECT DISTINCT {column} AS v FROM plan_fact_flat ORDER BY v"  # noqa: S608
        )
        _values[dimension] = [r["v"] for r in rows]


def for_prompt() -> dict[Dimension, list[str]]:
    return {d: v for d, v in _values.items() if len(v) <= MAX_IN_PROMPT}


def resolve(dimension: Dimension, value: str) -> str | None:
    """Приводит значение от модели к тому, что реально лежит в базе."""
    known = _values.get(dimension)
    if not known:
        return None
    if value in known:
        return value
    folded = value.casefold().strip()
    for candidate in known:
        if candidate.casefold() == folded:
            return candidate
    matches = [c for c in known if folded in c.casefold()]
    return matches[0] if len(matches) == 1 else None
