"""Спецификация выборки + таблица → описание графика.

Тип графика выбирает код, а не модель: правил здесь на десяток строк, и
детерминированный выбор проще отлаживать, чем капризы промпта.
"""

from app.labels import (
    METRIC_UNITS,
    UNIT_AXIS_LABELS,
    dimension_label,
    genitive,
    metric_label,
)
from app.schema import ChartSpec, Dimension, Metric, QuerySpec, Series

PLAN_FACT = {Metric.PLAN_AMOUNT, Metric.FACT_AMOUNT}


def _title(spec: QuerySpec) -> str:
    dimension = spec.dimensions[0]
    metrics = set(spec.metrics)
    if PLAN_FACT <= metrics:
        subject = "План-факт"
    elif len(spec.metrics) == 1:
        subject = metric_label(spec.metrics[0])
    else:
        subject = "Продажи"
    return f"{subject} по {genitive(dimension)}"


def build(spec: QuerySpec) -> ChartSpec | None:
    if not spec.dimensions:
        return None

    dimension = spec.dimensions[0]
    kind = "line" if dimension.is_temporal and len(spec.metrics) == 1 else "bar"

    units = {METRIC_UNITS[m] for m in spec.metrics}
    y_label = UNIT_AXIS_LABELS[units.pop()] if len(units) == 1 else ""

    return ChartSpec(
        kind=kind,
        title=_title(spec),
        x_field=dimension.value,
        x_label=dimension_label(dimension),
        y_label=y_label,
        series=[Series(field=m.value, label=metric_label(m)) for m in spec.metrics],
    )
