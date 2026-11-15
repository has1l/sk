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

from app import aggregate, calculations, diagnose, kpi, layout, numbers
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
    Dimension.CLIENT_SEGMENT,
    Dimension.CLIENT,
    Dimension.DISCOUNT_REASON,
]

# Разрезы клиентской ветки. На переключатель они попадают, только когда
# таблица сессии клиентская: в основной таблице этих колонок нет.
CLIENT_DIMENSIONS = [Dimension.CLIENT, Dimension.CLIENT_SEGMENT, Dimension.DISCOUNT_REASON]

NO_PLAN_NOTE = "Плана по клиентам нет — показан факт."


def default_config(view: ViewState) -> DashboardConfig:
    return DashboardConfig(
        panels=[
            PanelConfig(id="p1", kind=PanelKind.PLAN_FACT_PERIOD),
            PanelConfig(id="p2", kind=PanelKind.STRUCTURE, limit=8),
            PanelConfig(id="p3", kind=PanelKind.TOP, limit=10),
            PanelConfig(id="p4", kind=PanelKind.COMPLETION_TREND),
            PanelConfig(id="p5", kind=PanelKind.WATERFALL, limit=6),
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

#: Сколько периодов план-факт ещё выдерживает столбцами. Выше — переходим на
#: линию: на каждый период приходится по две полоски, и к пятнадцати периодам
#: их уже тридцать.
_BARS_MAX = 14


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
    fact_only = aggregate.is_fact_only(scope)

    if fact_only and view.mode is not ViewMode.GROWTH:
        # Плана по клиентам нет: вторая серия была бы нулями, а «выполнение»
        # — прочерками. Рисуем то, что есть, и говорим, почему так.
        kind = "bar" if len(grouped) <= _BARS_MAX else "line"
        fields, reference = [Metric.FACT_AMOUNT.value], None
        title = f"Факт по {genitive(dimension)}"
        if view.mode is ViewMode.PERCENT:
            notes.append(NO_PLAN_NOTE)
    elif view.mode is ViewMode.PERCENT:
        grouped = calculations.apply(grouped, [_completion_step()], context)
        fields, kind, reference = [COMPLETION_FIELD], "bar", 100.0
        title = f"Выполнение плана по {genitive(dimension)}"
    elif view.mode is ViewMode.GROWTH:
        grouped = calculations.apply(grouped, [_growth_step()], context)
        fields, kind, reference = [GROWTH_FIELD], "bar", 0.0
        title = f"Прирост факта по {genitive(dimension)}"
        # Прирост считается к предыдущему периоду, и у первого его нет. Если
        # период в выборке один, пустыми окажутся все значения — и без
        # объяснения панель показывает голые оси, а человек думает, что
        # сломалось.
        if not grouped[GROWTH_FIELD].notna().any():
            notes.append(
                f"Прирост считается к предыдущему периоду, а в выборке "
                f"{'он один' if len(grouped) == 1 else 'их не с чем сравнивать'} — "
                f"сравнивать не с чем. Возьмите более длинный период или "
                f"укрупните его зерно."
            )
    else:
        # Две серии столбцами читаются, пока периодов немного. На тридцати трёх
        # месяцах это шестьдесят шесть полосок в палец шириной — частокол, по
        # которому ничего не сравнить. Длинный ряд во времени — это линия.
        kind = "bar" if len(grouped) <= _BARS_MAX else "line"
        fields, reference = [m.value for m in PLAN_FACT], None
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
    fact_only = aggregate.is_fact_only(scope)
    if config.sort_field:
        sort_field = config.sort_field
    elif view.mode is ViewMode.PERCENT and not fact_only:
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
    columns = _unique(
        [sort_field, Metric.FACT_AMOUNT.value]
        if fact_only
        else [sort_field, Metric.PLAN_AMOUNT.value, Metric.FACT_AMOUNT.value]
    )
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
    if aggregate.is_fact_only(scope) and config.series_field is None:
        return _discount_trend(config, grouped, grain, steps, notes)
    grouped = calculations.apply(grouped, [_completion_step()], context)

    local = steps + [_completion_step()]
    fields = [COMPLETION_FIELD]
    chosen = next((st for st in steps if st.field == config.series_field), None)
    if chosen is not None and chosen.field in grouped.columns:
        return ChartPanel(
            id=config.id,
            spec=ChartSpec(
                kind="line",
                title=config.title or f"{calculations.step_title(chosen)} по {genitive(dimension)}",
                x_field=period_field,
                x_label=GRAIN_LABELS[grain],
                y_label="%" if chosen.unit == "percent" else column_of(chosen.field, local).label,
                series=_series([chosen.field], local),
                reference=0.0 if chosen.unit == "percent" else None,
                zoom_group="period",
            ),
            table=to_table(grouped, [dimension], [chosen.field, *[m.value for m in PLAN_FACT]], local),
            note="; ".join(notes) or None,
        )
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


DISCOUNT_SHARE_FIELD = "discount_share_pct"


def _discount_share_step() -> CalcStep:
    return CalcStep(
        id="__discount_share",
        title="Доля скидок, %",
        kind=StepKind.ARITHMETIC,
        field=DISCOUNT_SHARE_FIELD,
        expression="discount_amount / fact_amount * 100",
        unit="percent",
    )


def _discount_trend(
    config: PanelConfig,
    grouped: pd.DataFrame,
    grain: PeriodGrain,
    steps: list[CalcStep],
    notes: list[str],
) -> ChartPanel:
    """Панель 4 клиентской ветки. Выполнения плана тут нет, а вопрос про
    клиента почти всегда про скидки — поэтому линия показывает, какую долю
    факта отдали скидками в каждом периоде."""
    dimension = grain.dimension
    period_field = aggregate.FIELD[dimension]
    grouped = calculations.apply(grouped, [_discount_share_step()])
    local = steps + [_discount_share_step()]
    return ChartPanel(
        id=config.id,
        spec=ChartSpec(
            kind="line",
            title=config.title or f"Доля скидок в факте по {genitive(dimension)}",
            x_field=period_field,
            x_label=GRAIN_LABELS[grain],
            y_label="%",
            series=_series([DISCOUNT_SHARE_FIELD], local),
            zoom_group="period",
        ),
        table=to_table(
            grouped,
            [dimension],
            [DISCOUNT_SHARE_FIELD, Metric.DISCOUNT_AMOUNT.value, Metric.FACT_AMOUNT.value],
            local,
        ),
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


def _waterfall_panel(
    config: PanelConfig, scope: pd.DataFrame, view: ViewState, steps: list[CalcStep]
) -> ChartPanel | None:
    """Панель 5. Из чего сложился разрыв плана и факта.

    Ступеньки — вклад каждого значения разреза, хвост свёрнут в «Прочее».
    Сумма ступенек обязана сходиться с фактом, иначе мост врёт: за это
    отвечает diagnose.waterfall, а не рисовальщик.
    """
    total = aggregate.totals(scope)
    plan = total.get(Metric.PLAN_AMOUNT.value, 0.0)
    fact = total.get(Metric.FACT_AMOUNT.value, 0.0)
    if not plan or not len(scope):
        return None

    decomposition = diagnose.decompose(scope, view)
    if decomposition is None:
        return None

    rows = diagnose.waterfall(decomposition, plan, fact)
    if not rows:
        return None

    dimension = decomposition.levels[0].dimension
    frame = pd.DataFrame(rows)
    table = Table(
        columns=[
            Column(field="label", label=DIMENSION_LABELS[dimension], kind="dimension"),
            Column(field="value", label="Вклад в разрыв", kind="metric", unit="rub"),
            Column(field="measure", label="Тип ступени", kind="dimension"),
        ],
        rows=frame.to_dict("records"),
        row_count=len(rows),
    )
    gap = fact - plan
    verdict = "перевес" if gap >= 0 else "разрыв"
    return ChartPanel(
        id=config.id,
        spec=ChartSpec(
            kind="waterfall",
            title=config.title or f"Из чего сложился {verdict} {numbers.signed_money(gap)}",
            x_field="label",
            x_label=DIMENSION_LABELS[dimension],
            y_label=UNIT_AXIS_LABELS["rub"],
            series=[Series(field="value", label="Вклад", unit="rub")],
        ),
        table=table,
        note=decomposition.chain[0] if decomposition.chain else None,
    )


def _custom_panel(
    config: PanelConfig, scope: pd.DataFrame, view: ViewState, steps: list[CalcStep]
) -> ChartPanel:
    """Панель, собранная руками: разрез, метрика и вид графика выбраны в меню.

    У остальных панелей смысл задан вопросом пользователя. У этой своего
    смысла нет — есть только выбор, и всё невыбранное берётся из текущего
    вида. Поэтому она и подчиняется переключателю «Вид» наравне с панелью
    план-факта: иначе на одном экране половина панелей показывала бы
    проценты, а половина рубли.
    """
    dimension = config.dimension or view.primary
    metric = config.metric or view.metric
    temporal = dimension.is_temporal
    period_field = aggregate.FIELD[dimension] if temporal else None

    grouped = aggregate.group(scope, [dimension])
    context = Context(period_field=period_field, group_fields=[])
    grouped, notes = apply_steps(grouped, steps, context)
    local = steps + [_completion_step(), _growth_step()]

    kind = config.chart or ("line" if temporal else "bar")
    field, reference = metric.value, None
    title = f"{METRIC_LABELS[metric]} по {genitive(dimension)}"

    # Круг показывает доли одного целого, поэтому ему нужна складываемая
    # величина. Проценты выполнения в доли не складываются: сектор «70 %»
    # рядом с сектором «130 %» не значит ничего.
    shares = kind == "pie"
    if view.mode is ViewMode.PERCENT and not shares:
        grouped = calculations.apply(grouped, [_completion_step()], context)
        field, reference = COMPLETION_FIELD, 100.0
        title = f"Выполнение плана по {genitive(dimension)}"
    elif view.mode is ViewMode.GROWTH and not shares:
        if temporal:
            grouped = calculations.apply(grouped, [_growth_step()], context)
            field, reference = GROWTH_FIELD, 0.0
            title = f"Прирост {METRIC_GENITIVE[metric]} по {genitive(dimension)}"
            if not grouped[GROWTH_FIELD].notna().any():
                notes.append(
                    "Прирост считается к предыдущему периоду, а в выборке он один — "
                    "сравнивать не с чем. Возьмите более длинный период или "
                    "укрупните его зерно."
                )
        else:
            # Прирост требует предыдущего периода, а регионы в ряд не
            # выстраиваются. Молча показать метрику нельзя: подпись сказала бы
            # «прирост», а цифры были бы абсолютные.
            notes.append(
                f"Прирост считается к предыдущему периоду, а {genitive(dimension)} "
                "в ряд не выстраиваются — здесь показана сама метрика."
            )

    if len(grouped):
        if temporal:
            grouped = grouped.sort_values(period_field).reset_index(drop=True)
        else:
            grouped = grouped.sort_values(
                field, ascending=config.order is SortOrder.ASC, na_position="last"
            ).reset_index(drop=True)
            if config.limit and len(grouped) > config.limit:
                grouped = (
                    _collapse_tail(grouped, dimension, config.limit)
                    if shares
                    else grouped.head(config.limit).reset_index(drop=True)
                )

    return ChartPanel(
        id=config.id,
        spec=ChartSpec(
            kind=kind,
            title=config.title or title,
            x_field=aggregate.FIELD[dimension],
            x_label=GRAIN_LABELS[PeriodGrain(dimension.value)]
            if temporal
            else DIMENSION_LABELS[dimension],
            y_label=_unit_axis([field], local),
            series=_series([field], local),
            reference=reference,
            # Синхронный зум только у временных осей: совмещать зум месяцев с
            # зумом регионов нечего.
            zoom_group="period" if temporal else None,
        ),
        table=to_table(grouped, [dimension], [field], local),
        note="; ".join(notes) or None,
    )


def builtin_steps() -> list[CalcStep]:
    """Вычисления, которые дашборд делает сам, без просьбы. Показываются в
    происхождении цифр наравне со стеком пользователя: на экране они есть.
    """
    return [_completion_step(), _deviation_step(), _growth_step()]


BUILDERS = {
    PanelKind.PLAN_FACT_PERIOD: _period_panel,
    PanelKind.STRUCTURE: _structure_panel,
    PanelKind.TOP: _top_panel,
    PanelKind.COMPLETION_TREND: _trend_panel,
    PanelKind.WATERFALL: _waterfall_panel,
    PanelKind.CUSTOM: _custom_panel,
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


def toggle_options(view: ViewState, fact_only: bool = False) -> list[ToggleOption]:
    dimensions = TOGGLE_DIMENSIONS + (CLIENT_DIMENSIONS if fact_only else [])
    metrics = [m for m in TOGGLE_METRICS if not (fact_only and m is Metric.PLAN_AMOUNT)]
    return [
        ToggleOption(
            key="primary",
            label="Разрез",
            value=view.primary.value,
            options=[{"value": d.value, "label": DIMENSION_LABELS[d]} for d in dimensions],
        ),
        ToggleOption(
            key="metric",
            label="Метрика",
            value=view.metric.value,
            options=[{"value": m.value, "label": METRIC_LABELS[m]} for m in metrics],
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
        if built is None:
            continue
        panels.append(built)

    # Раскладка сводится с тем, что реально собралось, и записывается обратно
    # в конфиг: оттуда она попадёт и в снимок машины времени, и в сохранённый
    # дашборд — тем же путём, что и остальной рецепт.
    config.layout = layout.reconcile(
        config,
        [p.id for p in panels],
        wide={p.id for p in panels if p.spec.kind == "waterfall"},
    )

    dashboard = Dashboard(
        kpis=kpi.build(scope, view, previous, fact_only=aggregate.is_fact_only(frame)),
        panels=panels,
        filters=filter_options(frame, view),
        toggles=toggle_options(view, aggregate.is_fact_only(frame)),
        layout=config.layout,
    )
    return dashboard, notes
