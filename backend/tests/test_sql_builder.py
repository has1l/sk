from datetime import date

import pytest

from app import sql_builder
from app.schema import (
    Dimension,
    Filter,
    Metric,
    Period,
    QuerySpec,
    RelativePeriod,
    SortOrder,
)

HORIZON = date(2026, 9, 1)


def spec(**kwargs) -> QuerySpec:
    base = {"dimensions": [Dimension.REGION], "metrics": [Metric.FACT_AMOUNT]}
    return QuerySpec(**(base | kwargs))


@pytest.mark.parametrize(
    "relative,expected_from,expected_to",
    [
        (RelativePeriod.LAST_MONTH, date(2026, 9, 1), date(2026, 9, 1)),
        (RelativePeriod.LAST_QUARTER, date(2026, 7, 1), date(2026, 9, 1)),
        (RelativePeriod.LAST_YEAR, date(2025, 10, 1), date(2026, 9, 1)),
        (RelativePeriod.YEAR_TO_DATE, date(2026, 1, 1), date(2026, 9, 1)),
    ],
)
def test_relative_periods_count_from_fact_horizon(relative, expected_from, expected_to):
    built = sql_builder.build(spec(period=Period(relative=relative)), HORIZON)
    assert (built.date_from, built.date_to) == (expected_from, expected_to)


def test_last_year_is_twelve_months_not_thirteen():
    built = sql_builder.build(spec(period=Period(relative=RelativePeriod.LAST_YEAR)), HORIZON)
    months = (built.date_to.year - built.date_from.year) * 12 + built.date_to.month - built.date_from.month + 1
    assert months == 12


def test_all_time_is_clipped_to_horizon_and_says_so():
    built = sql_builder.build(spec(period=Period(relative=RelativePeriod.ALL_TIME)), HORIZON)
    assert built.date_from is None
    assert built.date_to == HORIZON
    assert any("обрезан" in note for note in built.notes)


def test_explicit_period_beyond_horizon_is_clipped_with_note():
    built = sql_builder.build(
        spec(period=Period(date_from=date(2026, 1, 1), date_to=date(2026, 12, 1))), HORIZON
    )
    assert built.date_to == HORIZON
    assert any("обрезан" in note for note in built.notes)


def test_period_inside_horizon_is_left_alone_without_notes():
    built = sql_builder.build(
        spec(period=Period(date_from=date(2025, 1, 1), date_to=date(2025, 12, 1))), HORIZON
    )
    assert (built.date_from, built.date_to) == (date(2025, 1, 1), date(2025, 12, 1))
    assert built.notes == []


def test_clipping_can_be_turned_off():
    built = sql_builder.build(
        spec(period=Period(date_from=date(2026, 1, 1), date_to=date(2026, 12, 1)),
             clip_to_fact_horizon=False),
        HORIZON,
    )
    assert built.date_to == date(2026, 12, 1)


def test_filter_values_go_as_parameters_never_into_sql_text():
    built = sql_builder.build(
        spec(filters=[Filter(dimension=Dimension.REGION, values=["Центральный", "Южный"])]), HORIZON
    )
    assert "region_name = ANY(%s)" in built.sql
    assert "Центральный" not in built.sql
    assert ["Центральный", "Южный"] in built.params


def test_temporal_filters_are_ignored_period_handles_time():
    built = sql_builder.build(
        spec(filters=[Filter(dimension=Dimension.MONTH, values=["2026-01-01"])]), HORIZON
    )
    assert "ANY" not in built.sql


def test_query_without_dimensions_has_no_group_by():
    built = sql_builder.build(spec(dimensions=[]), HORIZON)
    assert "GROUP BY" not in built.sql
    assert "ORDER BY" not in built.sql


def test_order_by_metric_overrides_dimension_order():
    built = sql_builder.build(
        spec(order_by=Metric.FACT_AMOUNT, order=SortOrder.DESC, limit=10), HORIZON
    )
    assert "ORDER BY sum(fact_amount) DESC" in built.sql
    assert built.sql.rstrip().endswith("LIMIT 10")


def test_limit_is_capped_by_row_limit():
    built = sql_builder.build(spec(limit=1000), HORIZON)
    assert "LIMIT 1000" in built.sql


def test_quarter_boundaries():
    assert sql_builder._quarter_start(date(2026, 1, 15)) == date(2026, 1, 1)
    assert sql_builder._quarter_start(date(2026, 5, 1)) == date(2026, 4, 1)
    assert sql_builder._quarter_start(date(2026, 12, 31)) == date(2026, 10, 1)


def test_last_three_years_are_thirty_six_months_up_to_the_horizon():
    """Модель на «последние 3 года» отдавала октябрь 2024 — два года. Теперь
    она называет число месяцев, а границы считает код."""
    start, end, notes = sql_builder.resolve_period(Period(last_months=36), date(2026, 9, 1))
    assert (start, end) == (date(2023, 10, 1), date(2026, 9, 1))
    assert notes
