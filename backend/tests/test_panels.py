"""Панели обязаны объяснять пустоту, а не рисовать голые оси.

Принцип проекта: неполный период и пустая выборка обрабатываются явно. Пустой
график без единого столбца и без подписи — это молчание, а не честность.
"""

from datetime import date

import pandas as pd

from app import aggregate, dashboard
from app.schema import (
    CalcStep,
    StepKind,
    DashboardConfig,
    Dimension,
    Metric,
    PanelConfig,
    PanelKind,
    PeriodGrain,
    ViewMode,
    ViewState,
)

METRICS = [m.value for m in Metric]


def frame(rows: list[dict]) -> pd.DataFrame:
    filled = []
    for row in rows:
        item = {
            "month": row["month"],
            "region_name": row.get("region", "Центральный"),
            "outlet_name": "Точка 1",
            "city": "Москва",
            "outlet_type": "Магазин",
            "product_name": "Продукт 1",
            "category": "Напитки",
        }
        for metric in METRICS:
            item[metric] = float(row.get(metric, 0.0))
        filled.append(item)
    return aggregate.prepare(pd.DataFrame(filled))


def view(**over) -> ViewState:
    base = dict(
        primary=Dimension.REGION.value,
        period_grain=PeriodGrain.MONTH,
        metric=Metric.FACT_AMOUNT.value,
        mode=ViewMode.GROWTH,
        table_dimensions=[Dimension.REGION.value],
        filters=[],
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 1),
        sort_field=None,
        sort_order="asc",
        limit=None,
    )
    base.update(over)
    return ViewState(**base)


ONE_MONTH = [{"month": date(2026, 9, 1), "plan_amount": 100.0, "fact_amount": 90.0}]
TWO_MONTHS = [
    {"month": date(2026, 8, 1), "plan_amount": 100.0, "fact_amount": 80.0},
    {"month": date(2026, 9, 1), "plan_amount": 100.0, "fact_amount": 90.0},
]


def growth_panel(rows: list[dict], window: tuple[date, date]):
    board, _ = dashboard.build(
        frame(rows),
        view(date_from=window[0], date_to=window[1]),
        [],
        DashboardConfig(panels=[PanelConfig(id="p1", kind=PanelKind.PLAN_FACT_PERIOD)]),
    )
    return board.panels[0]


def test_growth_over_a_single_period_says_why_it_is_empty():
    """Прирост считается к предыдущему периоду. Если период один, сравнивать
    не с чем — и это надо сказать, а не показывать пустые оси."""
    panel = growth_panel(ONE_MONTH, (date(2026, 9, 1), date(2026, 9, 1)))
    values = [row.get("growth_pct") for row in panel.table.rows]
    assert all(v is None for v in values), "прирост первого периода не с чем считать"
    assert panel.note, "пустая панель обязана объяснить пустоту"
    assert "сравн" in panel.note.lower() or "период" in panel.note.lower()


def test_growth_over_two_periods_has_a_number_and_no_excuse():
    panel = growth_panel(TWO_MONTHS, (date(2026, 8, 1), date(2026, 9, 1)))
    values = [row.get("growth_pct") for row in panel.table.rows]
    assert values[0] is None, "первому периоду по-прежнему не с чем сравниваться"
    assert values[1] is not None and abs(values[1] - 12.5) < 0.01, values
    assert not (panel.note or "").lower().count("сравн"), panel.note


# ─── своя панель ──────────────────────────────────────────────────────────────

MIX = [
    {"month": date(2026, 8, 1), "region": "Центральный", "plan_amount": 100.0, "fact_amount": 80.0},
    {"month": date(2026, 9, 1), "region": "Центральный", "plan_amount": 100.0, "fact_amount": 90.0},
    {"month": date(2026, 9, 1), "region": "Южный", "plan_amount": 200.0, "fact_amount": 250.0},
]
WINDOW = dict(date_from=date(2026, 8, 1), date_to=date(2026, 9, 1))


def custom(mode: ViewMode = ViewMode.ABSOLUTE, **panel):
    config = PanelConfig(
        id="c1",
        kind=PanelKind.CUSTOM,
        dimension=panel.pop("dimension", Dimension.REGION),
        metric=panel.pop("metric", Metric.FACT_AMOUNT),
        **panel,
    )
    board, _ = dashboard.build(
        frame(MIX),
        view(mode=mode, **WINDOW),
        [],
        DashboardConfig(panels=[config]),
    )
    return board.panels[0]


def test_custom_panel_plots_the_chosen_dimension_and_metric():
    panel = custom(dimension=Dimension.REGION, metric=Metric.FACT_AMOUNT, chart="hbar")
    assert panel.spec.kind == "hbar"
    assert panel.spec.x_field == "region_name"
    assert [s.field for s in panel.spec.series] == ["fact_amount"]
    assert panel.spec.title == "Факт по регионам"
    assert {row["region_name"] for row in panel.table.rows} == {"Центральный", "Южный"}


def test_custom_panel_follows_the_view_mode_like_every_other_panel():
    """Переключатель «Вид» — общий для дашборда. Своя панель, оставшаяся в
    рублях, когда все остальные показывают проценты, читается как сбой."""
    panel = custom(ViewMode.PERCENT, dimension=Dimension.REGION)
    assert [s.field for s in panel.spec.series] == ["completion_pct"]
    assert panel.spec.reference == 100.0
    assert panel.spec.title == "Выполнение плана по регионам"


def test_growth_on_a_dimension_without_order_shows_the_metric_and_says_so():
    """Прирост считается к предыдущему периоду, а регионы в ряд не
    выстраиваются. Нарисовать пустоту или молча подменить величину — обе
    неправды; показываем метрику и объясняем."""
    panel = custom(ViewMode.GROWTH, dimension=Dimension.REGION)
    assert [s.field for s in panel.spec.series] == ["fact_amount"]
    assert panel.note and "прирост" in panel.note.lower()


def test_pie_never_shows_percentages_of_plan():
    """Круг — доли одного целого. Сектор «70 %» рядом с сектором «130 %» не
    складывается ни во что."""
    panel = custom(ViewMode.PERCENT, dimension=Dimension.REGION, chart="pie")
    assert [s.field for s in panel.spec.series] == ["fact_amount"]


def test_custom_panel_by_month_keeps_time_in_order():
    panel = custom(dimension=Dimension.MONTH, chart="line")
    months = [row["month"] for row in panel.table.rows]
    assert months == sorted(months), months
    assert panel.spec.zoom_group == "period"


# ─── панель 4 с вычисленной колонкой ──────────────────────────────────────────


def trend(series_field: str | None, steps):
    board, _ = dashboard.build(
        frame(TWO_MONTHS),
        view(mode=ViewMode.ABSOLUTE, date_from=date(2026, 8, 1), date_to=date(2026, 9, 1)),
        steps,
        DashboardConfig(
            panels=[PanelConfig(id="p4", kind=PanelKind.COMPLETION_TREND, series_field=series_field)]
        ),
    )
    return board.panels[0]


GROWTH_STEP = CalcStep(
    id="s1",
    title="Динамика к прошлому месяцу",
    kind=StepKind.GROWTH,
    field="calc_abc123",
    source=[Metric.FACT_AMOUNT.value],
    unit="percent",
)


def test_trend_panel_draws_the_calculated_column_it_was_asked_for():
    """Сценарий кейса: «Покажи четвёртый график с учётом динамики». Раньше
    просьба превращалась в сортировку линии — график не менялся, а бот
    отчитывался, что всё сделал."""
    panel = trend("calc_abc123", [GROWTH_STEP])
    assert [s.field for s in panel.spec.series] == ["calc_abc123"]
    assert panel.spec.title.startswith("Динамика к прошлому месяцу")
    assert abs(panel.table.rows[1]["calc_abc123"] - 12.5) < 0.01


def test_trend_panel_falls_back_to_completion_when_the_step_was_undone():
    panel = trend("calc_abc123", [])
    assert [s.field for s in panel.spec.series] == ["completion_pct"]
    assert panel.spec.reference == 100.0
