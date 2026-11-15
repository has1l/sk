"""Ответ на «почему», а не только на «сколько».

Разрыв плана и факта раскладывается на слагаемые: кто недобрал, сколько это в
деньгах и какая это доля всего отставания. Слагаемые считаются по уровням
разрезов и цепочкой вглубь — регион, внутри него точка, внутри неё продукт.

Здесь же живёт поиск аномалий: значения, выпадающие из своей же группы. Это
то, о чём пользователь не спрашивал, но ради чего он открывал дашборд.

Всё считается кодом по уже выгруженной таблице: ни модели, ни новой выборки.
Отношения берутся только после группировки — доля разрыва, посчитанная по
строкам детализации, даёт правдоподобное, но неверное число.
"""

from __future__ import annotations

import pandas as pd

from app import aggregate, numbers
from app.labels import ACROSS_ALL, DIMENSION_LABELS, SINGULAR
from app.schema import (
    Anomaly,
    Decomposition,
    Dimension,
    GapFactor,
    GapLevel,
    Metric,
    ViewState,
)

PLAN = Metric.PLAN_AMOUNT.value
FACT = Metric.FACT_AMOUNT.value

# Слагаемое меньше процента разрыва — это шум, а не объяснение.
MIN_SHARE = 1.0
MAX_FACTORS = 6
MAX_LIFTERS = 2
# Разрез, по которому у значения совсем нет плана, в объяснение не берём:
# «недобрал на 100%» при плане в тысячу рублей — не причина.
MIN_PLAN_SHARE = 0.005


def levels_for(view: ViewState) -> list[Dimension]:
    """Кто, что и когда. Три вопроса, на которые раскладывается разрыв."""
    wanted = [view.primary, Dimension.CATEGORY, view.period_grain.dimension]
    out: list[Dimension] = []
    for dimension in wanted:
        if dimension not in out:
            out.append(dimension)
    return out


# Цепочка вглубь: каждый следующий разрез сужается предыдущим.
DRILL: dict[Dimension, list[Dimension]] = {
    Dimension.REGION: [Dimension.OUTLET, Dimension.PRODUCT],
    Dimension.CITY: [Dimension.OUTLET, Dimension.PRODUCT],
    Dimension.OUTLET_TYPE: [Dimension.REGION, Dimension.OUTLET],
    Dimension.OUTLET: [Dimension.CATEGORY, Dimension.PRODUCT],
    Dimension.CATEGORY: [Dimension.PRODUCT, Dimension.REGION],
    Dimension.PRODUCT: [Dimension.REGION, Dimension.OUTLET],
}


def decompose(scope: pd.DataFrame, view: ViewState) -> Decomposition | None:
    """scope — уже суженная окном и фильтрами таблица, не вся сессия."""
    if not len(scope):
        return None

    total = aggregate.totals(scope)
    plan = total.get(PLAN, 0.0)
    fact = total.get(FACT, 0.0)
    gap = fact - plan
    if not plan:
        return None

    levels = [
        level
        for level in (_level(scope, dimension, gap) for dimension in levels_for(view))
        if level is not None
    ]
    if not levels:
        return None

    return Decomposition(
        headline=_headline(plan, fact, gap),
        total=gap,
        levels=levels,
        chain=_chain(scope, view, gap),
    )


def _headline(plan: float, fact: float, gap: float) -> str:
    completion = fact / plan * 100
    if gap >= 0:
        return (
            f"План выполнен на {numbers.percent(completion)} — перевес "
            f"{numbers.signed_money(gap)}. Вот кто его дал."
        )
    return (
        f"План выполнен на {numbers.percent(completion)} — разрыв "
        f"{numbers.signed_money(gap)}. Вот из чего он сложился."
    )


# Предлог «внутри» требует рода родителя: «внутри него» про регион, но
# «внутри неё» про точку. Собирать из рода существительного кодом — путь к
# «внутри него точка».
INSIDE: dict[Dimension, str] = {
    Dimension.REGION: "внутри него",
    Dimension.CITY: "внутри него",
    Dimension.OUTLET_TYPE: "внутри него",
    Dimension.PRODUCT: "внутри него",
    Dimension.OUTLET: "внутри неё",
    Dimension.CATEGORY: "внутри неё",
}


def _value_label(value, dimension: Dimension) -> str:
    if dimension.is_temporal:
        return numbers.period_label(pd.Timestamp(value).date(), dimension.value)
    return str(value)


def _level(scope: pd.DataFrame, dimension: Dimension, gap: float) -> GapLevel | None:
    """Вклад каждого значения разреза в разрыв.

    Доля считается от суммы однонаправленных вкладов, а не от итога: при
    разрыве −10, сложенном из −30 и +20, вклад −30 это 100% отставания, а не
    300% — иначе проценты выглядят как ошибка.
    """
    grouped = aggregate.group(scope, [dimension])
    if len(grouped) < 2:
        return None

    column = aggregate.FIELD[dimension]
    plan_total = grouped[PLAN].sum()
    if not plan_total:
        return None

    grouped = grouped.copy()
    grouped["gap"] = grouped[FACT] - grouped[PLAN]
    grouped = grouped[grouped[PLAN] >= plan_total * MIN_PLAN_SHARE]
    if len(grouped) < 2:
        return None

    drags = grouped[grouped["gap"] < 0].sort_values("gap")
    lifts = grouped[grouped["gap"] > 0].sort_values("gap", ascending=False)
    drag_total = abs(drags["gap"].sum())
    lift_total = lifts["gap"].sum()

    factors: list[GapFactor] = []
    for _, row in drags.head(MAX_FACTORS).iterrows():
        share = abs(row["gap"]) / drag_total * 100 if drag_total else 0.0
        if share < MIN_SHARE:
            continue
        factors.append(
            GapFactor(
                label=_value_label(row[column], dimension),
                value=float(row["gap"]),
                share=float(share),
                direction="drag",
            )
        )
    for _, row in lifts.head(MAX_LIFTERS).iterrows():
        share = row["gap"] / lift_total * 100 if lift_total else 0.0
        if share < MIN_SHARE:
            continue
        factors.append(
            GapFactor(
                label=_value_label(row[column], dimension),
                value=float(row["gap"]),
                share=float(share),
                direction="lift",
            )
        )

    if not factors:
        return None
    return GapLevel(dimension=dimension, label=DIMENSION_LABELS[dimension], factors=factors)


def _chain(scope: pd.DataFrame, view: ViewState, gap: float) -> list[str]:
    """Цепочка вглубь: кто недобрал больше всех, а внутри него — кто.

    Каждый шаг сужает выборку предыдущим победителем, поэтому вторая строка
    говорит про точки внутри региона, а не про точки вообще.
    """
    if gap >= 0:
        return []

    out: list[str] = []
    narrowed = scope
    dimensions = [view.primary, *DRILL.get(view.primary, [Dimension.OUTLET, Dimension.PRODUCT])]
    seen: set[Dimension] = set()
    parent: Dimension | None = None

    for depth, dimension in enumerate(dimensions[:3]):
        if dimension in seen:
            continue
        seen.add(dimension)
        column = aggregate.FIELD[dimension]
        if column not in narrowed.columns:
            continue

        grouped = aggregate.group(narrowed, [dimension])
        if len(grouped) < 2:
            continue
        grouped = grouped.copy()
        grouped["gap"] = grouped[FACT] - grouped[PLAN]
        worst = grouped.loc[grouped["gap"].idxmin()]
        if worst["gap"] >= 0:
            break

        local_gap = float(grouped[grouped["gap"] < 0]["gap"].sum())
        share = abs(worst["gap"]) / abs(local_gap) * 100 if local_gap else 0.0
        name = _value_label(worst[column], dimension)
        money = numbers.money(abs(worst["gap"]))
        word = SINGULAR.get(dimension, DIMENSION_LABELS[dimension].lower())

        if depth == 0 or parent is None:
            out.append(
                f"Сильнее всех отстаёт {word} {name}: недобор {money} — "
                f"{numbers.percent(share)} отставания."
            )
        else:
            out.append(
                f"{_capitalize(INSIDE[parent])} тянет вниз {word} {name}: {money} "
                f"({numbers.percent(share)} отставания на этом уровне)."
            )
        parent = dimension
        narrowed = narrowed[narrowed[column] == worst[column]]
        if not len(narrowed):
            break

    return out


def waterfall(decomposition: Decomposition, plan: float, fact: float) -> list[dict]:
    """Мост от плана к факту: план, слагаемые разрыва, факт.

    Хвост мелких вкладов сворачивается в «Прочее», иначе мост из сорока
    ступенек не читается, а сумма обязана сойтись с фактом.
    """
    if not decomposition.levels:
        return []
    factors = decomposition.levels[0].factors
    rows: list[dict] = [{"label": "План", "value": plan, "measure": "absolute"}]
    named = 0.0
    for factor in factors:
        rows.append({"label": factor.label, "value": factor.value, "measure": "relative"})
        named += factor.value
    rest = (fact - plan) - named
    if abs(rest) > abs(plan) * 0.001:
        rows.append({"label": "Прочее", "value": rest, "measure": "relative"})
    rows.append({"label": "Факт", "value": fact, "measure": "total"})
    return rows


# ─── аномалии ─────────────────────────────────────────────────────────────────

MAD_THRESHOLD = 3.0
AGAINST_GROUP = 15.0
OWN_HISTORY = 40.0
MAX_ANOMALIES = 4


def anomalies(scope: pd.DataFrame, view: ViewState) -> list[Anomaly]:
    if not len(scope):
        return []
    found = _outliers(scope, view) + _against_group(scope, view)
    return found[:MAX_ANOMALIES]


def _outliers(scope: pd.DataFrame, view: ViewState) -> list[Anomaly]:
    """Выполнение, выпадающее из своей же группы.

    Порог — медианное отклонение, а не среднее: одна точка с выполнением 300%
    растягивает среднее так, что аномалией не оказывается никто.
    """
    dimension = view.primary
    grouped = aggregate.group(scope, [dimension])
    if len(grouped) < 4:
        return []

    column = aggregate.FIELD[dimension]
    plan_total = grouped[PLAN].sum()
    if not plan_total:
        return []

    grouped = grouped[grouped[PLAN] >= plan_total * MIN_PLAN_SHARE].copy()
    if len(grouped) < 4:
        return []

    grouped["completion"] = grouped[FACT] / grouped[PLAN] * 100
    median = grouped["completion"].median()
    deviation = (grouped["completion"] - median).abs().median()
    if not deviation:
        return []

    grouped["score"] = (grouped["completion"] - median).abs() / deviation
    hits = grouped[grouped["score"] >= MAD_THRESHOLD].sort_values("score", ascending=False)

    word = SINGULAR.get(dimension, DIMENSION_LABELS[dimension].lower())
    out: list[Anomaly] = []
    for _, row in hits.head(2).iterrows():
        behind = row["completion"] < median
        verdict = "отстаёт от остальных" if behind else "идёт заметно выше остальных"
        out.append(
            Anomaly(
                label=str(row[column]),
                text=(
                    f"{_capitalize(word)} {row[column]} {verdict}: выполнение "
                    f"{numbers.percent(row['completion'])} при медиане "
                    f"{numbers.percent(median)} по остальным."
                ),
                severity="high" if behind and row["score"] >= MAD_THRESHOLD * 1.5 else "medium",
                dimension=dimension,
            )
        )
    return out


def _against_group(scope: pd.DataFrame, view: ViewState) -> list[Anomaly]:
    """Кто пошёл против общего движения: группа выросла, а он упал.

    Сравниваются два последних периода текущего зерна. Это самая дорогая
    находка для руководителя: общий рост прячет локальный провал.
    """
    grain_column = aggregate.FIELD[view.period_grain.dimension]
    periods = sorted(scope[grain_column].dropna().unique())
    if len(periods) < 2:
        return []

    last, before = periods[-1], periods[-2]
    dimension = view.primary
    column = aggregate.FIELD[dimension]

    recent = aggregate.group(scope[scope[grain_column] == last], [dimension])
    earlier = aggregate.group(scope[scope[grain_column] == before], [dimension])
    if not len(recent) or not len(earlier):
        return []

    merged = recent.merge(earlier, on=column, suffixes=("_now", "_was"))
    merged = merged[merged[f"{FACT}_was"] > 0]
    if len(merged) < 4:
        return []

    merged["change"] = (merged[f"{FACT}_now"] - merged[f"{FACT}_was"]) / merged[f"{FACT}_was"] * 100
    overall_was = merged[f"{FACT}_was"].sum()
    overall = (merged[f"{FACT}_now"].sum() - overall_was) / overall_was * 100 if overall_was else 0.0

    if overall >= 0:
        against = merged[merged["change"] <= -AGAINST_GROUP].sort_values("change")
        direction, verb = "рост", "падение"
    else:
        against = merged[merged["change"] >= AGAINST_GROUP].sort_values("change", ascending=False)
        direction, verb = "падение", "рост"
    if not len(against):
        return []

    word = SINGULAR.get(dimension, DIMENSION_LABELS[dimension].lower())
    # Существительные «рост» и «падение» вместо глаголов: у разрезов разный род,
    # и «точка … упал» читалось машинным переводом.
    across = ACROSS_ALL.get(dimension, f"по всем: {DIMENSION_LABELS[dimension].lower()}")
    label = numbers.period_label(pd.Timestamp(last).date(), view.period_grain.value)
    out: list[Anomaly] = []
    for _, row in against.head(2).iterrows():
        out.append(
            Anomaly(
                label=str(row[column]),
                text=(
                    f"{_capitalize(label)}: {across} {direction} на "
                    f"{numbers.percent(abs(overall))}, а {word} {row[column]} — {verb} на "
                    f"{numbers.percent(abs(row['change']))}."
                ),
                severity="high",
                dimension=dimension,
            )
        )
    return out


def _capitalize(text: str) -> str:
    return text[:1].upper() + text[1:]
