"""Текстовое резюме с инсайтами.

Считается кодом, а не моделью — по трём причинам: цифры в тексте обязаны
совпадать с цифрами на графике, лишний вызов модели стоит денег, а
придуманный моделью «рост на 15%» нечем проверить.

Инсайт здесь — это не пересказ таблицы, а то, что в таблице само не видно:
кто вытягивает, кто тянет вниз, развернулся ли тренд, и не врёт ли период.
"""

from __future__ import annotations

import pandas as pd

from app import aggregate, numbers
from app.labels import BEST, DIMENSION_LABELS, WORST
from app.schema import Dimension, Metric, ViewState

MIN_SHARE_FOR_DRIVER = 5.0


def _capitalize(text: str) -> str:
    """str.capitalize() портит «III кв. 2026» в «Iii кв. 2026»."""
    return text[:1].upper() + text[1:]


def build(
    frame: pd.DataFrame,
    view: ViewState,
    horizon,
    previous: pd.DataFrame | None = None,
) -> list[str]:
    scope = aggregate.window(frame, view)
    if not len(scope):
        return [
            "По такой выборке данных нет. Снимите часть фильтров или расширьте период — "
            "ни одна строка под условия не попала."
        ]

    if aggregate.is_fact_only(scope):
        out = [_fact_headline(scope, view)]
        out += _fact_leaders(scope, view)
        out += _trend(scope, view)
        out += _discount_reasons(scope)
        return [line for line in out if line]

    out: list[str] = [_headline(scope, view)]
    out += _leaders(scope, view)
    out += _trend(scope, view)
    out += _discounts(scope)
    out += _horizon_warning(view, horizon)
    return [line for line in out if line]


def _headline(scope: pd.DataFrame, view: ViewState) -> str:
    total = aggregate.totals(scope)
    plan = total.get(Metric.PLAN_AMOUNT.value, 0.0)
    fact = total.get(Metric.FACT_AMOUNT.value, 0.0)
    window = numbers.range_label(view.date_from, view.date_to)
    if not plan:
        return f"За {window} факт {numbers.money(fact)}; плана на этот отрезок нет."
    completion = fact / plan * 100
    gap = fact - plan
    return (
        f"За {window}: план {numbers.money(plan)}, факт {numbers.money(fact)}, "
        f"план выполнен на {numbers.percent(completion)} "
        f"({numbers.signed_money(gap)})."
    )


def _fact_headline(scope: pd.DataFrame, view: ViewState) -> str:
    total = aggregate.totals(scope)
    fact = total.get(Metric.FACT_AMOUNT.value, 0.0)
    discount = total.get(Metric.DISCOUNT_AMOUNT.value, 0.0)
    deals = int(total.get(Metric.SALES_COUNT.value, 0.0))
    window = numbers.range_label(view.date_from, view.date_to)
    line = f"За {window}: факт {numbers.money(fact)}, сделок {numbers.grouped(deals)}"
    if discount and fact:
        line += f", скидок {numbers.money(discount)} ({numbers.percent(discount / fact * 100)} от факта)"
    return line + ". Плана по клиентам в данных нет — сравнивать не с чем."


def _fact_leaders(scope: pd.DataFrame, view: ViewState) -> list[str]:
    """Без плана лидер — тот, на кого приходится больше всего факта."""
    dimension = view.primary
    # По причинам скидок «лидер по факту» — почти всегда «Без скидки»: это не
    # инсайт. Про причины говорит _discount_reasons, по сумме скидки.
    if dimension is Dimension.DISCOUNT_REASON:
        return []
    grouped = aggregate.group(scope, [dimension])
    total = grouped[Metric.FACT_AMOUNT.value].sum() if len(grouped) else 0.0
    if len(grouped) < 2 or not total:
        return []
    column = aggregate.FIELD[dimension]
    top = grouped.loc[grouped[Metric.FACT_AMOUNT.value].idxmax()]
    share = top[Metric.FACT_AMOUNT.value] / total * 100
    return [
        f"Крупнейшая доля факта — {top[column]}: "
        f"{numbers.money(top[Metric.FACT_AMOUNT.value])}, {numbers.percent(share)} от всего."
    ]


def _discount_reasons(scope: pd.DataFrame) -> list[str]:
    """Ответ на «какие скидки делались и почему»: причины считаются по сумме
    скидки, продажи без скидки в разбор не идут."""
    if "discount_reason" not in scope.columns:
        return []
    given = scope[scope[Metric.DISCOUNT_AMOUNT.value] > 0]
    if not len(given):
        return ["Скидок за этот отрезок не было."]
    by_reason = (
        given.groupby("discount_reason")[Metric.DISCOUNT_AMOUNT.value].sum().sort_values(ascending=False)
    )
    total = by_reason.sum()
    parts = [
        f"{reason.lower()} — {numbers.percent(value / total * 100)}"
        for reason, value in by_reason.head(3).items()
    ]
    head = by_reason.index[0]
    return [
        f"Главная причина скидок — {head.lower()}: {numbers.money(by_reason.iloc[0])}. "
        f"Разбивка по сумме: {', '.join(parts)}."
    ]


def _leaders(scope: pd.DataFrame, view: ViewState) -> list[str]:
    """Кто вытягивает и кто тянет вниз — по проценту выполнения, но только
    среди тех, у кого есть заметный план. Иначе в лидеры попадёт точка с
    планом в тысячу рублей и выполнением 400%.
    """
    dimension = view.primary
    grouped = aggregate.group(scope, [dimension])
    if len(grouped) < 2:
        return []

    column = aggregate.FIELD[dimension]
    plan_total = grouped[Metric.PLAN_AMOUNT.value].sum()
    if not plan_total:
        return []

    grouped = grouped[grouped[Metric.PLAN_AMOUNT.value] > plan_total * 0.01].copy()
    if len(grouped) < 2:
        return []

    grouped["completion"] = (
        grouped[Metric.FACT_AMOUNT.value] / grouped[Metric.PLAN_AMOUNT.value] * 100
    )
    best = grouped.loc[grouped["completion"].idxmax()]
    worst = grouped.loc[grouped["completion"].idxmin()]
    if best[column] == worst[column]:
        return []

    lines = [
        f"{BEST[dimension]} — {best[column]} ({numbers.percent(best['completion'])}), "
        f"{WORST[dimension]} — {worst[column]} ({numbers.percent(worst['completion'])}); "
        f"разрыв {numbers.percent(best['completion'] - worst['completion'])}."
    ]

    gap = grouped[Metric.PLAN_AMOUNT.value] - grouped[Metric.FACT_AMOUNT.value]
    shortfall = gap[gap > 0]
    if len(shortfall):
        total_gap = shortfall.sum()
        top = grouped.loc[gap.idxmax()]
        share = gap.max() / total_gap * 100 if total_gap else 0
        if share >= MIN_SHARE_FOR_DRIVER:
            lines.append(
                f"Больше всего недобрал {top[column]}: "
                f"{numbers.money(gap.max())} — это {numbers.percent(share)} всего отставания."
            )
    return lines


def _trend(scope: pd.DataFrame, view: ViewState) -> list[str]:
    grain = view.period_grain
    dimension = grain.dimension
    grouped = aggregate.group(scope, [dimension])
    if len(grouped) < 2:
        return []

    column = aggregate.FIELD[dimension]
    grouped = grouped.sort_values(column)
    last = grouped.iloc[-1]
    before = grouped.iloc[-2]
    previous_fact = float(before[Metric.FACT_AMOUNT.value])
    if not previous_fact:
        return []

    change = (float(last[Metric.FACT_AMOUNT.value]) - previous_fact) / previous_fact * 100
    direction = "вырос" if change >= 0 else "упал"
    label = numbers.period_label(pd.Timestamp(last[column]).date(), grain.value)
    before_label = numbers.period_genitive(pd.Timestamp(before[column]).date(), grain.value)
    if abs(change) < 0.5:
        line = f"{_capitalize(label)} против {before_label}: факт практически не изменился."
    else:
        line = (
            f"{_capitalize(label)} против {before_label}: факт {direction} на "
            f"{numbers.percent(abs(change))}."
        )

    if len(grouped) >= 4:
        tail = grouped[Metric.FACT_AMOUNT.value].tail(4).tolist()
        falling = all(b < a for a, b in zip(tail, tail[1:]))
        rising = all(b > a for a, b in zip(tail, tail[1:]))
        if falling:
            line += " Падение идёт четвёртый период подряд — это уже тренд, а не колебание."
        elif rising:
            line += " Рост идёт четвёртый период подряд."
    return [line]


def _discounts(scope: pd.DataFrame) -> list[str]:
    if Metric.DISCOUNT_AMOUNT.value not in scope.columns:
        return []
    total = aggregate.totals(scope)
    discount = total.get(Metric.DISCOUNT_AMOUNT.value, 0.0)
    fact = total.get(Metric.FACT_AMOUNT.value, 0.0)
    if not discount or not fact:
        return []
    share = discount / fact * 100
    if share < 1:
        return []
    return [f"Скидок отдано {numbers.money(discount)} — {numbers.percent(share)} от факта."]


def _horizon_warning(view: ViewState, horizon) -> list[str]:
    """Главная мина датасета: факт обрывается сентябрём 2026, план размечен
    до декабря. Если выборка упирается в горизонт — сказать об этом текстом.
    """
    if view.date_to is None or horizon is None:
        return []
    if view.date_to < horizon:
        return []
    return [
        f"Факт заканчивается {numbers.period_label(horizon, 'month')} — "
        "это последний месяц с продажами, а не провал. План дальше обрезан, "
        "чтобы выполнение не выглядело заниженным."
    ]
