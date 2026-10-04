"""Стек вычислений. Проверяем ровно то, что ломается молча: отношения,
деление на ноль, порядок периодов и то, что формула не исполняется как код.
"""

from datetime import date

import pandas as pd
import pytest

from app.calculations import CalcError, Context, apply, evaluate, to_rpn
from app.schema import CalcStep, SortOrder, StepKind


def step(kind: StepKind, field: str, **kwargs) -> CalcStep:
    return CalcStep(id="s1", title="", kind=kind, field=field, **kwargs)


@pytest.fixture
def regions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "region": ["Центральный", "Южный", "Уральский"],
            "plan_amount": [100.0, 200.0, 0.0],
            "fact_amount": [90.0, 240.0, 50.0],
        }
    )


@pytest.fixture
def months() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "month": [date(2026, 1, 1), date(2026, 2, 1), date(2026, 1, 1), date(2026, 2, 1)],
            "region": ["Центральный", "Центральный", "Южный", "Южный"],
            "fact_amount": [100.0, 150.0, 200.0, 100.0],
            "plan_amount": [100.0, 100.0, 100.0, 100.0],
        }
    )


def test_deviation_is_fact_minus_plan(regions):
    out = apply(regions, [step(StepKind.DEVIATION, "deviation")])
    assert list(out["deviation"]) == [-10.0, 40.0, 50.0]


def test_completion_is_a_ratio_in_percent(regions):
    out = apply(regions, [step(StepKind.COMPLETION, "completion")])
    assert out["completion"][0] == pytest.approx(90.0)
    assert out["completion"][1] == pytest.approx(120.0)


def test_zero_plan_gives_no_completion_instead_of_infinity(regions):
    out = apply(regions, [step(StepKind.COMPLETION, "completion")])
    assert pd.isna(out["completion"][2])


def test_share_sums_to_hundred(regions):
    out = apply(regions, [step(StepKind.SHARE, "share")])
    assert out["share"].sum() == pytest.approx(100.0)


def test_growth_is_counted_inside_each_entity_not_across_the_table(months):
    out = apply(
        months,
        [step(StepKind.GROWTH, "growth")],
        Context(period_field="month", group_fields=["region"]),
    )
    # Центральный: 100 → 150 это +50%. Южный: 200 → 100 это −50%.
    by_key = {(r.region, r.month): r.growth for r in out.itertuples()}
    assert pd.isna(by_key[("Центральный", date(2026, 1, 1))])
    assert by_key[("Центральный", date(2026, 2, 1))] == pytest.approx(50.0)
    assert by_key[("Южный", date(2026, 2, 1))] == pytest.approx(-50.0)


def test_cumulative_accumulates_by_period_inside_entity(months):
    out = apply(
        months,
        [step(StepKind.CUMULATIVE, "running")],
        Context(period_field="month", group_fields=["region"]),
    )
    by_key = {(r.region, r.month): r.running for r in out.itertuples()}
    assert by_key[("Центральный", date(2026, 2, 1))] == pytest.approx(250.0)
    assert by_key[("Южный", date(2026, 2, 1))] == pytest.approx(300.0)


def test_growth_without_a_period_column_says_so_instead_of_guessing(regions):
    with pytest.raises(CalcError, match="период"):
        apply(regions, [step(StepKind.GROWTH, "growth")], Context())


def test_rank_orders_by_metric(regions):
    out = apply(regions, [step(StepKind.RANK, "rank")])
    assert list(out["rank"]) == [2.0, 1.0, 3.0]


def test_rank_ascending_when_asked(regions):
    out = apply(regions, [step(StepKind.RANK, "rank", order=SortOrder.ASC)])
    assert list(out["rank"]) == [2.0, 3.0, 1.0]


def test_steps_can_build_on_each_other(regions):
    out = apply(
        regions,
        [
            step(StepKind.DEVIATION, "deviation"),
            CalcStep(
                id="s2",
                title="",
                kind=StepKind.ARITHMETIC,
                field="deviation_pct",
                expression="deviation / plan_amount * 100",
            ),
        ],
    )
    assert out["deviation_pct"][0] == pytest.approx(-10.0)


def test_arithmetic_respects_precedence_and_brackets(regions):
    plain = evaluate("fact_amount - plan_amount / 2", regions)
    bracketed = evaluate("(fact_amount - plan_amount) / 2", regions)
    assert plain[0] == pytest.approx(40.0)
    assert bracketed[0] == pytest.approx(-5.0)


def test_arithmetic_handles_unary_minus_and_comma_decimals(regions):
    assert evaluate("-plan_amount * 0,5", regions)[0] == pytest.approx(-50.0)


def test_unknown_column_in_formula_is_reported_not_silently_zero(regions):
    with pytest.raises(CalcError, match="нет колонки"):
        evaluate("fact_amount / выручка", regions)


def test_formula_is_never_executed_as_code(regions):
    """Главная проверка безопасности: текст от модели не исполняется.

    Если бы под капотом был eval, этот вызов что-нибудь сделал бы. Здесь он
    обязан развалиться на разборе.
    """
    with pytest.raises(CalcError):
        evaluate("__import__('os').system('echo hacked')", regions)


def test_unbalanced_brackets_are_rejected(regions):
    with pytest.raises(CalcError, match="скобка"):
        evaluate("(fact_amount - plan_amount", regions)


def test_division_by_zero_in_formula_gives_blank(regions):
    result = evaluate("fact_amount / plan_amount", regions)
    assert pd.isna(result[2])


# ─── порядок операндов ────────────────────────────────────────────────────────


def test_completion_source_order_is_fixed_by_the_operation_not_by_the_caller():
    """Модель возвращала [plan, fact], и выполнение считалось наизнанку:
    90% превращались в 111%. Порядок задаёт смысл операции.
    """
    from app.calculations import normalize_source

    assert normalize_source(StepKind.COMPLETION, ["plan_amount", "fact_amount"]) == [
        "fact_amount",
        "plan_amount",
    ]
    assert normalize_source(StepKind.DEVIATION, ["plan_amount", "fact_amount"]) == [
        "fact_amount",
        "plan_amount",
    ]


def test_half_given_pair_is_completed_within_the_same_unit():
    from app.calculations import normalize_source

    assert normalize_source(StepKind.COMPLETION, ["fact_qty"]) == ["fact_qty", "plan_qty"]
    assert normalize_source(StepKind.COMPLETION, ["plan_qty"]) == ["fact_qty", "plan_qty"]


def test_unpaired_kinds_keep_their_source_untouched():
    from app.calculations import normalize_source

    assert normalize_source(StepKind.SHARE, ["plan_amount"]) == ["plan_amount"]
