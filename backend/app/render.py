"""Сессия анализа → снимок того, что показывает интерфейс.

Единственное место, где собирается ответ клиенту: таблица, дашборд, выводы.
И веб, и iOS получают один и тот же снимок — поэтому ни один клиент не
считает ничего сам.
"""

from __future__ import annotations

from datetime import date

from app import aggregate, calculations, dashboard, diagnose, insights, numbers
from app.calculations import Context
from app.config import settings
from app.labels import DIMENSION_LABELS, GRAIN_LABELS, METRIC_LABELS, genitive
from app.schema import (
    CalcStep,
    Formula,
    Metric,
    Provenance,
    QuerySpec,
    SessionView,
    StepView,
    TimelineEntry,
    ViewState,
)
from app.session import Analysis


def context_for(view: ViewState) -> Context:
    period = next((d for d in view.table_dimensions if d.is_temporal), None)
    return Context(
        period_field=aggregate.FIELD[period] if period else None,
        group_fields=[aggregate.FIELD[d] for d in view.table_dimensions if not d.is_temporal],
    )


def step_views(analysis: Analysis) -> list[StepView]:
    return [
        StepView(
            id=step.id,
            title=calculations.step_title(step),
            field=step.field,
            formula=calculations.formula_text(step),
        )
        for step in analysis.steps
    ]


def table_of(analysis: Analysis) -> tuple[object, list[str]]:
    view = analysis.view
    scope = aggregate.window(analysis.frame, view)
    grouped = aggregate.group(scope, view.table_dimensions)
    grouped, notes = dashboard.apply_steps(grouped, analysis.steps, context_for(view))

    if view.sort_field and view.sort_field in grouped.columns and len(grouped):
        grouped = grouped.sort_values(
            view.sort_field,
            ascending=view.sort_order.value == "asc",
            na_position="last",
        ).reset_index(drop=True)

    if view.limit and len(grouped) > view.limit:
        grouped = grouped.head(view.limit)

    fields = [m.value for m in analysis.spec.metrics]
    fields += [s.field for s in analysis.steps if s.field not in fields]
    table = dashboard.to_table(
        grouped, view.table_dimensions, fields, analysis.steps, limit=settings.row_limit
    )
    return table, notes


def title_for(spec: QuerySpec, view: ViewState) -> str:
    """Название, которое бот предлагает при сохранении: кейс требует, чтобы
    предлагал бот, а переименовать мог пользователь.
    """
    metrics = set(spec.metrics)
    if {Metric.PLAN_AMOUNT, Metric.FACT_AMOUNT} <= metrics:
        subject = "План-факт"
    elif len(spec.metrics) == 1:
        subject = METRIC_LABELS[spec.metrics[0]]
    else:
        subject = "Продажи"

    entity = aggregate.entity_of(spec.dimensions)
    where = f" по {genitive(entity)}" if entity else ""
    window = numbers.range_label(view.date_from, view.date_to)
    return f"{subject}{where}, {window}"


def build(analysis: Analysis, horizon: date, message: str = "") -> SessionView:
    table, step_notes = table_of(analysis)
    board, board_notes = dashboard.build(
        analysis.frame, analysis.view, analysis.steps, analysis.config
    )
    lines = insights.build(analysis.frame, analysis.view, horizon)
    scope = aggregate.window(analysis.frame, analysis.view)

    # Первая строка выводов — это и есть ответ: она уходит репликой в чат и
    # повторяется карточками KPI. В списке выводов ей делать нечего.
    summary = lines[0] if lines else ""
    rest = lines[1:]

    notes = list(dict.fromkeys([*analysis.notes, *step_notes, *board_notes]))
    return SessionView(
        session_id=analysis.id,
        title=analysis.title,
        question=analysis.question,
        spec=analysis.spec,
        view=analysis.view,
        recipe=analysis.state(),
        steps=step_views(analysis),
        table=table,
        dashboard=board,
        summary=summary,
        insights=rest,
        anomalies=diagnose.anomalies(scope, analysis.view),
        decomposition=diagnose.decompose(scope, analysis.view),
        provenance=provenance(analysis, table.row_count),
        timeline=timeline(analysis),
        notes=notes,
        sql=analysis.sql,
        saved_id=analysis.saved_id,
        dirty=analysis.dirty,
    )


GUARANTEES = [
    "Модель не писала этот SQL: запрос собран кодом из закрытого списка полей (ADR-0004).",
    "Значения из реплики уехали параметрами запроса, а не текстом внутри него.",
    "Роль bi_reader: только SELECT, транзакция read-only, таймаут 10 с.",
    "Формулы разобраны в дерево операций и посчитаны pandas — eval не вызывается нигде.",
    "Отношения считаются после группировки: процент от суммы, а не сумма процентов.",
]


def provenance(analysis: Analysis, row_count: int) -> Provenance:
    """Происхождение каждой цифры на экране.

    Нужна не для отладки: граница безопасности, описанная в ADR-0004, иначе
    остаётся обещанием в документе, которое на защите нечем показать.
    """
    formulas = [_formula(step, "по просьбе") for step in analysis.steps]
    formulas += [_formula(step, "своё") for step in dashboard.builtin_steps()]
    return Provenance(
        sql=analysis.sql or None,
        role="bi_reader",
        statement_timeout="10s",
        read_only=True,
        row_count=int(len(analysis.frame)),
        load_ms=round(analysis.load_ms, 1),
        model=settings.openai_model,
        llm_calls=analysis.llm_calls,
        formulas=formulas,
        guarantees=GUARANTEES,
    )


def _formula(step: CalcStep, origin: str) -> Formula:
    return Formula(
        field=step.field,
        title=calculations.step_title(step),
        kind=origin,
        expression=calculations.formula_text(step),
        inputs=[calculations.field_label(f) for f in step.source],
    )


def timeline(analysis: Analysis) -> list[TimelineEntry]:
    """Лента возвратов: каждая правка оставила состояние, к которому можно
    вернуться. Последняя запись — то, что на экране сейчас.
    """
    # Снимок делается ПЕРЕД правкой, поэтому возврат к нему отменяет её.
    # Подпись обязана говорить об этом: «вычисление …» прочиталось бы как
    # состояние с вычислением, а там его как раз нет.
    out = [
        TimelineEntry(
            id=snapshot.id,
            label=f"до: {snapshot.label}",
            at=snapshot.at,
            summary=_state_summary(snapshot.steps, snapshot.view),
        )
        for snapshot in analysis.history
    ]
    out.append(
        TimelineEntry(
            id="current",
            label="сейчас",
            at=analysis.touched_at,
            summary=_state_summary(analysis.steps, analysis.view),
            current=True,
        )
    )
    return out


def _state_summary(steps: list[CalcStep], view: ViewState) -> str:
    parts = [DIMENSION_LABELS[view.primary], GRAIN_LABELS[view.period_grain].lower()]
    if steps:
        parts.append(f"вычислений: {len(steps)}")
    if view.filters:
        applied = ", ".join(
            f"{DIMENSION_LABELS[f.dimension].lower()} — {len(f.values)}" for f in view.filters
        )
        parts.append(f"фильтры: {applied}")
    return " · ".join(parts)


def describe(analysis: Analysis) -> str:
    """Компактное описание сессии для модели. Не переписка, а состояние —
    поэтому стоимость запроса не растёт с длиной диалога (ADR-0001).
    """
    view = analysis.view
    parts = [
        f"вопрос: {analysis.question}",
        "разрезы таблицы: "
        + (", ".join(DIMENSION_LABELS[d] for d in view.table_dimensions) or "нет"),
        "метрики: " + ", ".join(METRIC_LABELS[m] for m in analysis.spec.metrics),
        f"период: {numbers.range_label(view.date_from, view.date_to)}",
        f"зерно периода: {GRAIN_LABELS[view.period_grain]}",
        f"основной разрез: {DIMENSION_LABELS[view.primary]}",
        f"метрика переключателя: {METRIC_LABELS[view.metric]}",
    ]
    if view.filters:
        applied = "; ".join(
            f"{DIMENSION_LABELS[f.dimension]} = {', '.join(f.values)}" for f in view.filters
        )
        parts.append(f"фильтры: {applied}")
    if analysis.steps:
        stack = "; ".join(
            f"{i + 1}) {calculations.step_title(s)} [{s.field}]"
            for i, s in enumerate(analysis.steps)
        )
        parts.append(f"стек вычислений: {stack}")
    else:
        parts.append("стек вычислений: пуст")
    if analysis.saved_id:
        parts.append(f"сохранён как «{analysis.title}»")
    return "\n".join(parts)
