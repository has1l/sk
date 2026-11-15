"""Разбор причин: мост обязан сходиться, доли — складываться, шум — отсеиваться."""

from datetime import date

import pandas as pd
import pytest

from app import aggregate, diagnose
from app.schema import Dimension, Metric, PeriodGrain, ViewState

METRICS = [m.value for m in Metric]


def frame(rows: list[dict]) -> pd.DataFrame:
    filled = []
    for row in rows:
        item = {
            "month": row["month"],
            "region_name": row.get("region", "Центральный"),
            "outlet_name": row.get("outlet", "Точка 1"),
            "city": row.get("city", "Москва"),
            "outlet_type": row.get("outlet_type", "Магазин"),
            "product_name": row.get("product", "Продукт 1"),
            "category": row.get("category", "Напитки"),
        }
        for metric in METRICS:
            item[metric] = float(row.get(metric, 0.0))
        filled.append(item)
    return aggregate.prepare(pd.DataFrame(filled))


def view(primary: Dimension = Dimension.REGION) -> ViewState:
    return ViewState(
        primary=primary,
        period_grain=PeriodGrain.MONTH,
        metric=Metric.FACT_AMOUNT,
        table_dimensions=[Dimension.MONTH, primary],
        date_from=date(2026, 1, 1),
        date_to=date(2026, 3, 1),
    )


def spread(regions: dict[str, tuple[float, float]], months: int = 3) -> pd.DataFrame:
    rows = []
    for index in range(months):
        for name, (plan, fact) in regions.items():
            rows.append(
                {
                    "month": date(2026, index + 1, 1),
                    "region": name,
                    "plan_amount": plan,
                    "fact_amount": fact,
                }
            )
    return frame(rows)


def test_bridge_from_plan_to_fact_adds_up():
    """Главное свойство моста: сумма ступенек равна факту.

    Если хвост свёрнут неверно, мост показывает правдоподобную, но неверную
    картину — а проверить её на глаз нельзя, в этом и ценность теста.
    """
    scope = spread({"А": (100.0, 60.0), "Б": (100.0, 90.0), "В": (100.0, 120.0)})
    decomposition = diagnose.decompose(scope, view())
    totals = aggregate.totals(scope)

    rows = diagnose.waterfall(
        decomposition, totals[Metric.PLAN_AMOUNT.value], totals[Metric.FACT_AMOUNT.value]
    )
    steps = sum(r["value"] for r in rows if r["measure"] == "relative")
    assert rows[0]["value"] == pytest.approx(totals[Metric.PLAN_AMOUNT.value])
    assert rows[-1]["value"] == pytest.approx(totals[Metric.FACT_AMOUNT.value])
    assert rows[0]["value"] + steps == pytest.approx(rows[-1]["value"])


def test_drag_shares_sum_to_a_hundred_percent():
    """Доля считается от суммы однонаправленных вкладов.

    Делить отставание на итоговый разрыв нельзя: при разрыве −10 из −30 и +20
    первый же вклад дал бы 300%, и проценты выглядели бы как ошибка.
    """
    scope = spread({"А": (100.0, 70.0), "Б": (100.0, 80.0), "В": (100.0, 120.0)})
    level = diagnose.decompose(scope, view()).levels[0]

    drags = [f for f in level.factors if f.direction == "drag"]
    assert len(drags) == 2
    assert sum(f.share for f in drags) == pytest.approx(100.0)


def test_member_without_meaningful_plan_is_not_a_reason():
    """Точка с планом в копейки не объясняет разрыв в миллионы."""
    scope = spread({"А": (1_000_000.0, 500_000.0), "Б": (10.0, 0.0), "В": (900_000.0, 880_000.0)})
    labels = [f.label for f in diagnose.decompose(scope, view()).levels[0].factors]
    assert "Б" not in labels
    assert "А" in labels


def test_nothing_to_decompose_without_a_plan():
    scope = spread({"А": (0.0, 100.0), "Б": (0.0, 200.0)})
    assert diagnose.decompose(scope, view()) is None


def test_empty_scope_does_not_explode():
    """Пустая выборка с размеченными колонками — ровно то, что отдаёт база,
    когда под фильтры не попало ни строки.
    """
    empty = frame([{"month": date(2026, 1, 1)}]).iloc[0:0]
    assert diagnose.decompose(empty, view()) is None
    assert diagnose.anomalies(empty, view()) == []


def test_chain_narrows_into_the_worst_branch():
    """Вторая строка цепочки — про точки ВНУТРИ худшего региона, а не вообще.

    Без сужения выборки цепочка называла бы самую слабую точку страны, и
    объяснение разваливалось бы: она может лежать в благополучном регионе.
    """
    rows = []
    for index in range(3):
        rows += [
            {"month": date(2026, index + 1, 1), "region": "Плохой", "outlet": "Провал",
             "plan_amount": 1000.0, "fact_amount": 100.0},
            {"month": date(2026, index + 1, 1), "region": "Плохой", "outlet": "Норма",
             "plan_amount": 1000.0, "fact_amount": 950.0},
            {"month": date(2026, index + 1, 1), "region": "Хороший", "outlet": "Лучшая",
             "plan_amount": 1000.0, "fact_amount": 1100.0},
            {"month": date(2026, index + 1, 1), "region": "Хороший", "outlet": "Слабая",
             "plan_amount": 1000.0, "fact_amount": 980.0},
        ]
    chain = diagnose.decompose(frame(rows), view()).chain
    assert "Плохой" in chain[0]
    assert "Провал" in chain[1]


def test_outlier_is_measured_against_the_median_not_the_mean():
    """Один гигант не должен прятать аномалию.

    Со средним как точкой отсчёта выброс 400% растягивает шкалу так, что
    отстающий перестаёт быть аномалией.
    """
    scope = spread(
        {
            "А": (100.0, 95.0),
            "Б": (100.0, 97.0),
            "В": (100.0, 96.0),
            "Г": (100.0, 94.0),
            "Провал": (100.0, 10.0),
        }
    )
    found = diagnose.anomalies(scope, view())
    assert any(a.label == "Провал" for a in found)


def test_against_the_group_is_reported():
    """Группа выросла, а один упал — самая дорогая находка для руководителя."""
    rows = []
    for name, first, second in [
        ("А", 100.0, 130.0),
        ("Б", 100.0, 125.0),
        ("В", 100.0, 140.0),
        ("Г", 100.0, 135.0),
        ("Падает", 100.0, 40.0),
    ]:
        rows += [
            {"month": date(2026, 1, 1), "region": name, "plan_amount": 100.0, "fact_amount": first},
            {"month": date(2026, 2, 1), "region": name, "plan_amount": 100.0, "fact_amount": second},
        ]
    state = view()
    state.date_to = date(2026, 2, 1)
    texts = [a.text for a in diagnose.anomalies(frame(rows), state)]
    assert any("Падает" in text for text in texts)


def _against_rows(dimension_key: str, months: list[date]) -> list[dict]:
    rows = []
    for name, first, second in [
        ("А", 100.0, 130.0),
        ("Б", 100.0, 125.0),
        ("В", 100.0, 140.0),
        ("Г", 100.0, 135.0),
        ("Падает", 100.0, 40.0),
    ]:
        rows += [
            {"month": months[0], dimension_key: name, "plan_amount": 100.0, "fact_amount": first},
            {"month": months[1], dimension_key: name, "plan_amount": 100.0, "fact_amount": second},
        ]
    return rows


def test_against_the_group_reads_as_russian_for_a_feminine_dimension():
    """«все торговая точка в сумме вырос» — склейка из единственного числа и
    мужского глагола. Фраза обязана читаться при любом роде разреза."""
    state = view(Dimension.OUTLET)
    state.date_to = date(2026, 2, 1)
    rows = _against_rows("outlet", [date(2026, 1, 1), date(2026, 2, 1)])
    text = next(a.text for a in diagnose.anomalies(frame(rows), state) if "2026:" in a.text)
    assert "по всем торговым точкам" in text
    assert "все торговая точка" not in text
    assert " упал " not in text and " вырос " not in text


def test_against_the_group_keeps_roman_quarter_numerals():
    """str.capitalize() превращал «III кв.» в «Iii кв.»."""
    state = view()
    state.period_grain = PeriodGrain.QUARTER
    state.date_from = date(2026, 1, 1)
    state.date_to = date(2026, 6, 1)
    rows = _against_rows("region", [date(2026, 1, 1), date(2026, 4, 1)])
    text = next(a.text for a in diagnose.anomalies(frame(rows), state) if "2026:" in a.text)
    assert text.replace("\xa0", " ").startswith("II кв. 2026")


def test_period_values_are_labelled_in_russian():
    """В разборе по месяцам подпись — «январь 2026», а не «2026-01-01 00:00:00»."""
    scope = spread({"А": (100.0, 50.0), "Б": (100.0, 60.0)})
    state = view()
    levels = {level.dimension: level for level in diagnose.decompose(scope, state).levels}
    labels = [f.label for f in levels[Dimension.MONTH].factors]
    assert any("январь" in label for label in labels)
