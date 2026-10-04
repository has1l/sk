"""Дашборд: четыре связанных графика, фильтры и переключатели.

Панели описаны конфигом, а не жёстко: «перестрой третий график» меняет поле
сортировки у третьей панели, а не переписывает код. Данные для каждой панели —
своя группировка одной и той же таблицы сессии, поэтому фильтр применяется ко
всем графикам одновременно сам собой.

Вычисленные колонки доступны панелям: сортировка ТОПа по проценту выполнения
работает именно так. Шаг, который на данной группировке посчитать нельзя
(динамика без разреза по периоду), пропускается с примечанием, а не роняет
весь дашборд.
"""

from __future__ import annotations

import pandas as pd

from app import aggregate, calculations, kpi, numbers
from app.calculations import CalcError, Context
from app.labels import (
    DIMENSION_LABELS,
    METRIC_GENITIVE,
    GRAIN_LABELS,
    METRIC_LABELS,
    METRIC_UNITS,
    MODE_LABELS,
    UNIT_AXIS_LABELS,
    genitive,
)
from app.schema import (
    CalcStep,
    ChartPanel,
    ChartSpec,
    Column,
    Dashboard,
    DashboardConfig,
    Dimension,
    FilterOption,
    Metric,
    PanelConfig,
    PanelKind,
    PeriodGrain,
    Series,
    SortOrder,
    StepKind,
    Table,
    ToggleOption,
    Unit,
    ViewMode,
    ViewState,
)

PLAN_FACT = [Metric.PLAN_AMOUNT, Metric.FACT_AMOUNT]

COMPLETION_FIELD = "completion_pct"
GROWTH_FIELD = "growth_pct"

# Метрики, которые имеет смысл ставить на переключатель.
TOGGLE_METRICS = [
    Metric.FACT_AMOUNT,
    Metric.PLAN_AMOUNT,
    Metric.DISCOUNT_AMOUNT,
    Metric.SALES_COUNT,
    Metric.FACT_QTY,
]

TOGGLE_DIMENSIONS = [
    Dimension.REGION,
    Dimension.OUTLET,
    Dimension.CITY,
    Dimension.OUTLET_TYPE,
    Dimension.CATEGORY,
    Dimension.PRODUCT,
]

FILTER_DIMENSIONS = [
    Dimension.REGION,
    Dimension.OUTLET,
    Dimension.CITY,
    Dimension.OUTLET_TYPE,
    Dimension.CATEGORY,
    Dimension.PRODUCT,
]


def default_config(view: ViewState) -> DashboardConfig:
    return DashboardConfig(
        panels=[
            PanelConfig(id="p1", kind=PanelKind.PLAN_FACT_PERIOD),
            PanelConfig(id="p2", kind=PanelKind.STRUCTURE, limit=8),
            PanelConfig(id="p3", kind=PanelKind.TOP, limit=10),
            PanelConfig(id="p4", kind=PanelKind.COMPLETION_TREND),
        ]
    )


def apply_steps(
    frame: pd.DataFrame, steps: list[CalcStep], context: Context
) -> tuple[pd.DataFrame, list[str]]:
    notes: list[str] = []
    out = frame
    for step in steps:
        try:
            out = calculations.apply(out, [step], context)
        except CalcError as error:
            notes.append(f"«{calculations.step_title(step)}» здесь не посчитать: {error}")
    return out, notes


def column_of(field: str, steps: list[CalcStep]) -> Column:
    for step in steps:
        if step.field == field:
            return Column(
                field=field,
                label=calculations.step_title(step),
                kind="calc",
                unit=step.unit,
            )
    try:
        metric = Metric(field)
    except ValueError:
        return Column(field=field, label=field, kind="dimension")
    return Column(field=field, label=METRIC_LABELS[metric], kind="metric", unit=METRIC_UNITS[metric])


def _dimension_column(dimension: Dimension) -> Column:
    return Column(
        field=aggregate.FIELD[dimension],
        label=DIMENSION_LABELS[dimension],
        kind="dimension",
    )


def to_table(
    frame: pd.DataFrame,
    dimensions: list[Dimension],
    value_fields: list[str],
    steps: list[CalcStep],
    limit: int | None = None,
) -> Table:
    columns = [_dimension_column(d) for d in dimensions]
    columns += [column_of(f, steps) for f in value_fields]
    fields = [c.field for c in columns]
    present = [f for f in fields if f in frame.columns]
    data = frame[present] if len(frame) else frame.reindex(columns=present)
    if limit is not None:
        data = data.head(limit)
    return Table(
        columns=[c for c in columns if c.field in present],
        rows=_rows(data),
        row_count=int(len(frame)),
    )


def _unique(fields: list[str]) -> list[str]:
    seen: list[str] = []
    for field in fields:
        if field not in seen:
            seen.append(field)
    return seen


def _rows(frame: pd.DataFrame) -> list[dict]:
    if not len(frame):
        return []
    out = frame.copy()
    for column in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[column]):
            out[column] = out[column].dt.strftime("%Y-%m-%d")
    return out.astype(object).where(pd.notna(out), None).to_dict("records")


def _unit_axis(fields: list[str], steps: list[CalcStep]) -> str:
    units = {column_of(f, steps).unit for f in fields}
    return UNIT_AXIS_LABELS[units.pop()] if len(units) == 1 else ""


def _series(fields: list[str], steps: list[CalcStep]) -> list[Series]:
    out = []
    for field in fields:
        column = column_of(field, steps)
        out.append(Series(field=field, label=column.label, unit=column.unit))
    return out


# ─── панели ───────────────────────────────────────────────────────────────────


def _period_panel(
    config: PanelConfig, scope: pd.DataFrame, view: ViewState, steps: list[CalcStep]
) -> ChartPanel:
    """Панель 1. План-факт по периодам, в режиме процентов — выполнение,
    в режиме динамики — прирост факта.
    """
    grain = view.period_grain
    dimension = grain.dimension
    grouped = aggregate.group(scope, [dimension])
    context = Context(period_field=aggregate.FIELD[dimension], group_fields=[])
    grouped, notes = apply_steps(grouped, steps, context)

    if view.mode is ViewMode.PERCENT:
        grouped = calculations.apply(grouped, [_completion_step()], context)
        fields, kind, reference = [COMPLETION_FIELD], "bar", 100.0
        title = f"Выполнение плана по {genitive(dimension)}"
    elif view.mode is ViewMode.GROWTH:
        grouped = calculations.apply(grouped, [_growth_step()], context)
        fields, kind, reference = [GROWTH_FIELD], "bar", 0.0
        title = f"Прирост факта по {genitive(dimension)}"
    else:
        fields, kind, reference = [m.value for m in PLAN_FACT], "bar", None
        title = f"План-факт по {genitive(dimension)}"

    local = steps + [_completion_step(), _growth_step()]
    return ChartPanel(
        id=config.id,
        spec=ChartSpec(
            kind=kind,
            title=config.title or title,
            x_field=aggregate.FIELD[dimension],
            x_label=GRAIN_LABELS[grain],
            y_label=_unit_axis(fields, local),
            series=_series(fields, local),
            reference=reference,
            zoom_group="period",
        ),
        table=to_table(grouped, [dimension], fields, local),
        note="; ".join(notes) or None,
    )


def _structure_panel(
    config: PanelConfig, scope: pd.DataFrame, view: ViewState, steps: list[CalcStep]
) -> ChartPanel:
    """Панель 2. Структура за последний период выборки — круговая.

    Круг оправдан только здесь: один период, одна метрика, доли одного целого.
    Остальное — столбцы.
    """
    dimension = config.dimension or view.primary
    metric = config.metric or view.metric
    grain = view.period_grain
    period_field = aggregate.FIELD[grain.dimension]

    last = scope
    label = ""
    if len(scope):
        edge = scope[period_field].max()
        last = scope[scope[period_field] == edge]
        label = numbers.period_label(pd.Timestamp(edge).date(), grain.value)

    grouped = aggregate.group(last, [dimension])
    if len(grouped):
        grouped = grouped.sort_values(metric.value, ascending=False).reset_index(drop=True)
        if config.limit and len(grouped) > config.limit:
            grouped = _collapse_tail(grouped, dimension, config.limit)

    fields = [metric.value]
    return ChartPanel(
        id=config.id,
        spec=ChartSpec(
            kind="pie",
            title=config.title or f"Структура {METRIC_GENITIVE[metric]} по {genitive(dimension)}",
            x_field=aggregate.FIELD[dimension],
            x_label=DIMENSION_LABELS[dimension],
            y_label=UNIT_AXIS_LABELS[METRIC_UNITS[metric]],
            series=_series(fields, steps),
        ),
        table=to_table(grouped, [dimension], fields, steps),
        note=f"Последний период выборки — {label}" if label else None,
    )


def _collapse_tail(frame: pd.DataFrame, dimension: Dimension, limit: int) -> pd.DataFrame:
    """Хвост круговой диаграммы сворачивается в «Прочее»: двадцать секторов
    по два процента читать нельзя.
    """
    column = aggregate.FIELD[dimension]
    head = frame.head(limit - 1).copy()
    tail = frame.tail(len(frame) - (limit - 1))
    metrics = [m for m in calculations.ADDITIVE if m in frame.columns]
    rest = {column: "Прочее", **{m: float(tail[m].sum()) for m in metrics}}
    return pd.concat([head, pd.DataFrame([rest])], ignore_index=True)


def _top_panel(
    config: PanelConfig, scope: pd.DataFrame, view: ViewState, steps: list[CalcStep]
) -> ChartPanel:
    """Панель 3. ТОП по основному разрезу. Сортируется по любой колонке,
    включая вычисленную, — отсюда «отсортируй по проценту выполнения».
    """
    dimension = config.dimension or view.primary
    grouped = aggregate.group(scope, [dimension])
    context = Context(period_field=None, group_fields=[])
    grouped, notes = apply_steps(grouped, steps, context)
    grouped = calculations.apply(grouped, [_completion_step(), _deviation_step()], context)

    local = steps + [_completion_step(), _deviation_step()]
    # Переключатель вида действует и здесь: в режиме процентов ТОП строится по
    # выполнению плана, иначе — по выбранной метрике. Явная сортировка из
    # «отсортируй третий график по…» сильнее обоих.
    if config.sort_field:
        sort_field = config.sort_field
    elif view.mode is ViewMode.PERCENT:
        sort_field = COMPLETION_FIELD
    else:
        sort_field = view.metric.value
    if sort_field not in grouped.columns:
        notes.append(f"Сортировать по «{sort_field}» не получилось — такой колонки нет.")
        sort_field = Metric.FACT_AMOUNT.value

    ordered = grouped
    if len(ordered):
        ordered = ordered.sort_values(
            sort_field, ascending=config.order is SortOrder.ASC, na_position="last"
        ).reset_index(drop=True)
        ordered = ordered.head(config.limit).reset_index(drop=True)

    fields = [sort_field]
    columns = _unique([sort_field, Metric.PLAN_AMOUNT.value, Metric.FACT_AMOUNT.value])
    sorted_label = column_of(sort_field, local).label
    # «ТОП-10» из восьми регионов — вранье: заголовок называет ТОПом только
    # урезанный список.
    body = f"{sorted_label} по {genitive(dimension)}"
    title = f"ТОП-{config.limit} — {body}" if len(grouped) > config.limit else body
    return ChartPanel(
        id=config.id,
        spec=ChartSpec(
            kind="hbar",
            title=config.title or title,
            x_field=aggregate.FIELD[dimension],
            x_label=DIMENSION_LABELS[dimension],
            y_label=_unit_axis(fields, local),
            series=_series(fields, local),
            reference=100.0 if sort_field == COMPLETION_FIELD else None,
        ),
        # Порядок один — по убыванию, как читается. Разворот снизу вверх для
        # горизонтальных столбцов делает рисовальщик: это дело отображения.
        table=to_table(ordered, [dimension], columns, local),
        note="; ".join(notes) or None,
    )


def _trend_panel(
    config: PanelConfig, scope: pd.DataFrame, view: ViewState, steps: list[CalcStep]
) -> ChartPanel:
    """Панель 4. Динамика выполнения плана с отметкой 100%."""
    grain = view.period_grain
    dimension = grain.dimension
    period_field = aggregate.FIELD[dimension]
    grouped = aggregate.group(scope, [dimension])
    context = Context(period_field=period_field, group_fields=[])
    grouped, notes = apply_steps(grouped, steps, context)
    grouped = calculations.apply(grouped, [_completion_step()], context)

    local = steps + [_completion_step()]
    fields = [COMPLETION_FIELD]
    if view.mode is ViewMode.GROWTH:
        grouped = calculations.apply(grouped, [_growth_step()], context)
        fields = [GROWTH_FIELD]
        local = local + [_growth_step()]

    return ChartPanel(
        id=config.id,
        spec=ChartSpec(
            kind="line",
            title=config.title or f"{_trend_subject(fields[0])} по {genitive(dimension)}",
            x_field=period_field,
            x_label=GRAIN_LABELS[grain],
            y_label="%",
            series=_series(fields, local),
            reference=100.0 if fields[0] == COMPLETION_FIELD else 0.0,
            zoom_group="period",
        ),
        table=to_table(grouped, [dimension], [*fields, *[m.value for m in PLAN_FACT]], local),
        note="; ".join(notes) or None,
    )


def _trend_subject(field: str) -> str:
    """Заголовок четвёртой панели. Склонять подпись колонки кодом — путь к
    «Динамика выполнение плана», поэтому варианты перечислены явно.
    """
    return "Прирост факта" if field == GROWTH_FIELD else "Динамика выполнения плана"


def _completion_step() -> CalcStep:
    return CalcStep(
        id="__completion",
        title="Выполнение плана, %",
        kind=StepKind.COMPLETION,
        field=COMPLETION_FIELD,
        source=[Metric.FACT_AMOUNT.value, Metric.PLAN_AMOUNT.value],
        unit="percent",
    )


def _deviation_step() -> CalcStep:
    return CalcStep(
        id="__deviation",
        title="Отклонение",
        kind=StepKind.DEVIATION,
        field="deviation_rub",
        source=[Metric.FACT_AMOUNT.value, Metric.PLAN_AMOUNT.value],
        unit="rub",
    )


def _growth_step() -> CalcStep:
    return CalcStep(
        id="__growth",
        title="Прирост к прошлому периоду, %",
        kind=StepKind.GROWTH,
        field=GROWTH_FIELD,
        source=[Metric.FACT_AMOUNT.value],
        unit="percent",
    )


BUILDERS = {
    PanelKind.PLAN_FACT_PERIOD: _period_panel,
    PanelKind.STRUCTURE: _structure_panel,
    PanelKind.TOP: _top_panel,
    PanelKind.COMPLETION_TREND: _trend_panel,
}


# ─── фильтры и переключатели ──────────────────────────────────────────────────


def filter_options(frame: pd.DataFrame, view: ViewState) -> list[FilterOption]:
    """Списки значений для фильтров. Каскад: точка показывает только те,
    что лежат в выбранных регионах, продукт — только из выбранных категорий.
    """
    selected = {f.dimension: f.values for f in view.filters}
    options: list[FilterOption] = []

    for dimension in FILTER_DIMENSIONS:
        column = aggregate.FIELD[dimension]
        if column not in frame.columns:
            continue
        parent = aggregate.CASCADE.get(dimension)
        scope = frame
        if parent is not None and selected.get(parent):
            parent_column = aggregate.FIELD[parent]
            scope = frame[frame[parent_column].isin(selected[parent])]
        values = sorted(scope[column].dropna().unique().tolist())
        options.append(
            FilterOption(
                dimension=dimension,
                label=DIMENSION_LABELS[dimension],
                values=values,
                selected=[v for v in selected.get(dimension, []) if v in values],
                parent=parent,
            )
        )
    return options


def toggle_options(view: ViewState) -> list[ToggleOption]:
    return [
        ToggleOption(
            key="primary",
            label="Разрез",
            value=view.primary.value,
            options=[{"value": d.value, "label": DIMENSION_LABELS[d]} for d in TOGGLE_DIMENSIONS],
        ),
        ToggleOption(
            key="metric",
            label="Метрика",
            value=view.metric.value,
            options=[{"value": m.value, "label": METRIC_LABELS[m]} for m in TOGGLE_METRICS],
        ),
        ToggleOption(
            key="period_grain",
            label="Период",
            value=view.period_grain.value,
            options=[{"value": g.value, "label": GRAIN_LABELS[g]} for g in PeriodGrain],
        ),
        ToggleOption(
            key="mode",
            label="Вид",
            value=view.mode.value,
            options=[{"value": m.value, "label": MODE_LABELS[m]} for m in ViewMode],
        ),
    ]


def build(
    frame: pd.DataFrame,
    view: ViewState,
    steps: list[CalcStep],
    config: DashboardConfig,
) -> tuple[Dashboard, list[str]]:
    scope = aggregate.window(frame, view)
    previous = aggregate.previous_window(frame, view)

    panels: list[ChartPanel] = []
    notes: list[str] = []
    for panel in config.panels:
        builder = BUILDERS.get(panel.kind)
        if builder is None:
            continue
        built = builder(panel, scope, view, steps)
        panels.append(built)

    dashboard = Dashboard(
        kpis=kpi.build(scope, view, previous),
        panels=panels,
        filters=filter_options(frame, view),
        toggles=toggle_options(view),
    )
    return dashboard, notes
