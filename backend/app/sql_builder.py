"""Спецификация выборки → SQL.

Запрос собирается здесь, а не моделью. Идентификаторы берутся только из
таблиц ниже, значения уезжают параметрами — поэтому ни инъекция, ни запись
невозможны по конструкции, а не по договорённости (ADR-0004).

Источников два. Основной — plan_fact_flat: в ней закрыты обе ловушки джойна
плана с фактом. Клиентская ветка — client_fact_flat: факт на зерне клиента и
причины скидки, плана в ней нет, потому что плана по клиентам не существует.
Выбирает источник код по разрезам и фильтрам спецификации, а не модель.
"""

from dataclasses import dataclass, field
from datetime import date

from app.config import settings
from app.schema import Dimension, Filter, Metric, Period, QuerySpec, RelativePeriod

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
    Dimension.CLIENT: "client_name",
    Dimension.CLIENT_SEGMENT: "client_segment",
    Dimension.DISCOUNT_REASON: "discount_reason",
}

MAIN_SOURCE = "plan_fact_flat"
CLIENT_SOURCE = "client_fact_flat"


def needs_client_branch(spec: QuerySpec) -> bool:
    used = [*spec.dimensions, *(f.dimension for f in spec.filters)]
    return any(d.is_fact_only for d in used)


def source_for(spec: QuerySpec) -> str:
    return CLIENT_SOURCE if needs_client_branch(spec) else MAIN_SOURCE

METRIC_SQL: dict[Metric, str] = {
    Metric.PLAN_AMOUNT: "sum(plan_amount)",
    Metric.FACT_AMOUNT: "sum(fact_amount)",
    Metric.PLAN_QTY: "sum(plan_qty)",
    Metric.FACT_QTY: "sum(fact_qty)",
    Metric.SALES_COUNT: "sum(sales_count)",
    Metric.DISCOUNT_AMOUNT: "sum(discount_amount)",
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

    if period.last_months:
        start = _shift_months(horizon_month, -(period.last_months - 1))
        notes.append(
            f"«Последние {period.last_months} мес.» — это {start:%m.%Y}–{horizon_month:%m.%Y}, "
            "считая от последнего месяца с фактом."
        )
        return start, horizon_month, notes

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

    sql = f"SELECT {', '.join(select_parts)}\nFROM {source_for(spec)}"
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


# Атрибуты, которые едут в плоскую таблицу сессии. Зерно вьюхи уже
# «месяц × точка × продукт», поэтому агрегировать тут нечего — только отобрать.
DETAIL_COLUMNS: list[str] = [
    "month",
    "region_name",
    "outlet_name",
    "city",
    "outlet_type",
    "product_name",
    "category",
]

CLIENT_DETAIL_COLUMNS: list[str] = ["client_name", "client_segment", "discount_reason"]

DETAIL_METRICS: list[Metric] = list(Metric)

# client_count в детальной таблице отсутствует намеренно: это count(distinct),
# складывать его нельзя, а в pandas число активных клиентов всё равно не
# восстановить из суммы. Активные точки и продукты считаются по атрибутам.


def detail_columns(spec: QuerySpec) -> list[str]:
    """Колонки таблицы сессии. У клиентской ветки их больше — и это
    единственный список: таблица, собранная по другому, молча теряла бы
    клиента, а дальше всё падало бы на группировке по нему."""
    attributes = DETAIL_COLUMNS + (CLIENT_DETAIL_COLUMNS if needs_client_branch(spec) else [])
    return attributes + [m.value for m in DETAIL_METRICS]


def build_detail(
    spec: QuerySpec,
    horizon_month: date,
    lookback_months: int = 12,
) -> BuiltQuery:
    """Плоская таблица сессии: детальные строки без группировки.

    Окно расширено назад на lookback_months — иначе «динамика к прошлому
    периоду» и шаг growth не на чем считать: предыдущего периода в выборке нет.
    """
    notes: list[str] = []
    date_from, date_to, period_notes = resolve_period(spec.period, horizon_month)
    notes += period_notes

    if spec.clip_to_fact_horizon and (date_to is None or date_to > horizon_month):
        # В клиентской ветке плана нет, и обрезать нечего — фраза про план
        # там только сбивала бы с толку. Граница при этом та же.
        if not needs_client_branch(spec):
            notes.append(
                f"План обрезан по {horizon_month:%m.%Y} — дальше факта ещё нет, "
                "иначе выполнение выглядело бы заниженным."
            )
        date_to = horizon_month

    where_parts: list[str] = []
    params: list[object] = []
    if date_from is not None:
        where_parts.append("month >= %s")
        params.append(_shift_months(date_from, -lookback_months))
    if date_to is not None:
        where_parts.append("month <= %s")
        params.append(date_to)
    for flt in spec.filters:
        column = FILTERABLE.get(flt.dimension)
        if column is None:
            continue
        where_parts.append(f"{column} = ANY(%s)")
        params.append(flt.values)

    source = source_for(spec)
    columns = ", ".join(detail_columns(spec))
    sql = f"SELECT {columns}\nFROM {source}"
    if source == CLIENT_SOURCE:
        notes.append(
            "Плана по клиентам в данных нет — он ставится на точку и продукт. "
            "Здесь только факт: продажи, скидки и сделки."
        )
    if where_parts:
        sql += "\nWHERE " + "\n  AND ".join(where_parts)
    sql += f"\nLIMIT {settings.detail_row_limit}"

    return BuiltQuery(sql=sql, params=params, date_from=date_from, date_to=date_to, notes=notes)


def filter_values(dimension: Dimension, narrow: list[Filter]) -> BuiltQuery:
    """Список значений одного разреза, суженный другими фильтрами.

    Нужен каскаду регион→точка: список точек должен показывать только те,
    что лежат в выбранных регионах.
    """
    column = FILTERABLE[dimension]
    where_parts: list[str] = []
    params: list[object] = []
    for flt in narrow:
        other = FILTERABLE.get(flt.dimension)
        if other is None or flt.dimension is dimension:
            continue
        where_parts.append(f"{other} = ANY(%s)")
        params.append(flt.values)

    source = CLIENT_SOURCE if dimension.is_fact_only else MAIN_SOURCE
    sql = f"SELECT DISTINCT {column} AS value\nFROM {source}"
    if where_parts:
        sql += "\nWHERE " + "\n  AND ".join(where_parts)
    sql += "\nORDER BY value"
    return BuiltQuery(sql=sql, params=params, date_from=None, date_to=None)
