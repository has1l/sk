"""Спецификация выборки → SQL.

Запрос собирается здесь, а не моделью. Идентификаторы берутся только из
таблиц ниже, значения уезжают параметрами — поэтому ни инъекция, ни запись
невозможны по конструкции, а не по договорённости (ADR-0004).

Источник всегда один — вьюха plan_fact_flat. В ней уже закрыты обе ловушки
джойна плана с фактом, так что собрать неправильный запрос нельзя.
"""

from dataclasses import dataclass, field
from datetime import date

from app.config import settings
from app.schema import Dimension, Metric, Period, QuerySpec, RelativePeriod

DIMENSION_SQL: dict[Dimension, str] = {
    Dimension.MONTH: "month",
    Dimension.QUARTER: "date_trunc('quarter', month)::date",
    Dimension.YEAR: "date_trunc('year', month)::date",
    Dimension.REGION: "region_name",
    Dimension.OUTLET: "outlet_name",
    Dimension.CITY: "city",
    Dimension.OUTLET_TYPE: "outlet_type",
    Dimension.PRODUCT: "product_name",
    Dimension.CATEGORY: "category",
}

METRIC_SQL: dict[Metric, str] = {
    Metric.PLAN_AMOUNT: "sum(plan_amount)",
    Metric.FACT_AMOUNT: "sum(fact_amount)",
    Metric.PLAN_QTY: "sum(plan_qty)",
    Metric.FACT_QTY: "sum(fact_qty)",
    Metric.SALES_COUNT: "sum(sales_count)",
}

# По времени фильтруем периодом, а не списком значений.
FILTERABLE: dict[Dimension, str] = {
    d: expr for d, expr in DIMENSION_SQL.items() if not d.is_temporal
}


@dataclass
class BuiltQuery:
    sql: str
    params: list[object]
    date_from: date | None
    date_to: date | None
    notes: list[str] = field(default_factory=list)


def _quarter_start(day: date) -> date:
    return date(day.year, 3 * ((day.month - 1) // 3) + 1, 1)


def _shift_months(day: date, months: int) -> date:
    total = day.year * 12 + (day.month - 1) + months
    return date(total // 12, total % 12 + 1, 1)


def resolve_period(period: Period, horizon_month: date) -> tuple[date | None, date | None, list[str]]:
    """Относительные периоды считаются от горизонта факта, не от сегодня.

    Данные обрываются сентябрём 2026: «последний месяц» от календарной
    сегодняшней даты дал бы пустую выборку.
    """
    notes: list[str] = []

    if period.date_from or period.date_to:
        return period.date_from, period.date_to, notes

    match period.relative:
        case RelativePeriod.LAST_MONTH:
            return horizon_month, horizon_month, notes
        case RelativePeriod.LAST_QUARTER:
            return _quarter_start(horizon_month), horizon_month, notes
        case RelativePeriod.LAST_YEAR:
            start = _shift_months(horizon_month, -11)
            notes.append(
                f"«Последний год» — это 12 месяцев, {start:%m.%Y}–{horizon_month:%m.%Y}, "
                "а не календарный год."
            )
            return start, horizon_month, notes
        case RelativePeriod.YEAR_TO_DATE:
            return date(horizon_month.year, 1, 1), horizon_month, notes
        case _:
            return None, None, notes


def build(spec: QuerySpec, horizon_month: date) -> BuiltQuery:
    notes: list[str] = []
    date_from, date_to, period_notes = resolve_period(spec.period, horizon_month)
    notes += period_notes

    if spec.clip_to_fact_horizon and (date_to is None or date_to > horizon_month):
        notes.append(
            f"План обрезан по {horizon_month:%m.%Y} — дальше факта ещё нет, "
            "иначе выполнение выглядело бы заниженным."
        )
        date_to = horizon_month

    select_parts: list[str] = []
    group_parts: list[str] = []
    for dimension in spec.dimensions:
        select_parts.append(f"{DIMENSION_SQL[dimension]} AS {dimension.value}")
        group_parts.append(DIMENSION_SQL[dimension])
    for metric in spec.metrics:
        select_parts.append(f"{METRIC_SQL[metric]} AS {metric.value}")

    where_parts: list[str] = []
    params: list[object] = []
    if date_from is not None:
        where_parts.append("month >= %s")
        params.append(date_from)
    if date_to is not None:
        where_parts.append("month <= %s")
        params.append(date_to)
    for flt in spec.filters:
        column = FILTERABLE.get(flt.dimension)
        if column is None:
            continue
        where_parts.append(f"{column} = ANY(%s)")
        params.append(flt.values)

    sql = f"SELECT {', '.join(select_parts)}\nFROM plan_fact_flat"
    if where_parts:
        sql += "\nWHERE " + "\n  AND ".join(where_parts)
    if group_parts:
        sql += "\nGROUP BY " + ", ".join(group_parts)

    if spec.order_by is not None:
        sql += f"\nORDER BY {METRIC_SQL[spec.order_by]} {spec.order.value.upper()}"
    elif group_parts:
        first = spec.dimensions[0]
        sql += f"\nORDER BY {DIMENSION_SQL[first]} ASC"

    limit = min(spec.limit or settings.row_limit, settings.row_limit)
    sql += f"\nLIMIT {limit}"

    return BuiltQuery(sql=sql, params=params, date_from=date_from, date_to=date_to, notes=notes)
