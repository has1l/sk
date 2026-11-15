"""KPI-карточки: итоговые цифры над дашбордом.

Числа отдаются сырыми, с единицей измерения — форматирует их клиент, потому
что русские числа и падежи у него уже есть. Сервер отвечает за смысл и за
цвет: зелёный значит выполнение, красный — отставание.
"""

from __future__ import annotations

import pandas as pd

from app import aggregate, numbers
from app.schema import Kpi, Metric, ViewState

# Границы статусов. Планка 100% — выполнение; ниже 85% уже не «чуть-чуть».
GOOD, WARNING, SERIOUS = 100.0, 95.0, 85.0


def _status(completion: float | None) -> str:
    if completion is None:
        return "neutral"
    if completion >= GOOD:
        return "good"
    if completion >= WARNING:
        return "warning"
    if completion >= SERIOUS:
        return "serious"
    return "critical"


def build(
    frame: pd.DataFrame, view: ViewState, previous: pd.DataFrame, fact_only: bool = False
) -> list[Kpi]:
    total = aggregate.totals(frame)
    counts = aggregate.distinct_counts(frame)

    plan = total.get(Metric.PLAN_AMOUNT.value, 0.0)
    fact = total.get(Metric.FACT_AMOUNT.value, 0.0)
    completion = fact / plan * 100 if plan else None
    deviation = fact - plan
    deviation_pct = deviation / plan * 100 if plan else None

    previous_fact = aggregate.totals(previous).get(Metric.FACT_AMOUNT.value, 0.0)
    growth = (fact - previous_fact) / previous_fact * 100 if previous_fact else None

    growth_card = Kpi(
        key="growth",
        label="Динамика",
        value=growth,
        unit="percent",
        kind="delta",
        status="neutral" if growth is None else ("good" if growth >= 0 else "critical"),
        hint="к предыдущему такому же отрезку"
        if growth is not None
        else "предыдущего отрезка в выборке нет",
    )
    if fact_only:
        return _fact_only_cards(total, counts, fact, growth_card)

    cards = [
        Kpi(key="plan", label="План", value=plan, unit="rub"),
        Kpi(key="fact", label="Факт", value=fact, unit="rub"),
        Kpi(
            key="completion",
            label="Выполнение",
            value=completion,
            unit="percent",
            kind="percent",
            status=_status(completion),
            hint=None if plan else "Плана на этот отрезок нет",
        ),
        Kpi(
            key="deviation",
            label="Отклонение",
            value=deviation,
            unit="rub",
            kind="delta",
            status="good" if deviation >= 0 else "critical",
            hint=None if deviation_pct is None else f"{numbers.signed_percent(deviation_pct)} к плану",
        ),
        growth_card,
        Kpi(
            key="outlets",
            label="Активных точек",
            value=float(counts["outlets"]),
            unit="count",
            hint=f"продуктов — {counts['products']}, городов — {counts['cities']}",
        ),
    ]
    return cards


def _fact_only_cards(total: dict, counts: dict, fact: float, growth_card: Kpi) -> list[Kpi]:
    """Клиентская ветка. Плана по клиентам нет, и карточки «План»,
    «Выполнение», «Отклонение» были бы нулями и прочерками — вместо них то,
    что про клиента действительно известно: скидки и их доля в факте."""
    discount = total.get(Metric.DISCOUNT_AMOUNT.value, 0.0)
    share = discount / fact * 100 if fact else None
    return [
        Kpi(key="fact", label="Факт", value=fact, unit="rub", hint="плана по клиентам нет"),
        Kpi(key="discount", label="Скидки", value=discount, unit="rub"),
        Kpi(
            key="discount_share",
            label="Доля скидок",
            value=share,
            unit="percent",
            kind="percent",
            hint="от факта",
        ),
        Kpi(
            key="deals",
            label="Сделок",
            value=total.get(Metric.SALES_COUNT.value, 0.0),
            unit="count",
        ),
        growth_card,
        Kpi(
            key="clients",
            label="Активных клиентов",
            value=float(counts["clients"]),
            unit="count",
            hint=f"точек — {counts['outlets']}, продуктов — {counts['products']}",
        ),
    ]
