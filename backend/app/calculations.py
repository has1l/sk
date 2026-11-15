"""Стек вычислений: упорядоченный список шагов поверх агрегированной таблицы.

Таблица не мутируется — она пересобирается прогоном стека от базовой выборки
(ADR-0002). Поэтому откат это удаление шага, а правка формулы — замена
параметров шага, и ни то ни другое не требует хранить снимки.

Почему вычисления идут ПОСЛЕ агрегации, а не до: «выполнение плана» — это
отношение, а отношения не складываются. Посчитать процент на детальных строках
и просуммировать его по региону — классическая ошибка, которая даёт
правдоподобное число. Здесь это невозможно по конструкции: стек видит только
уже сгруппированную таблицу.

Формулы не исполняются как код. Выражение разбирается в обратную польскую
запись и считается операциями pandas над колонками — eval не участвует
(ADR-0004).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.labels import METRIC_LABELS, STEP_LABELS
from app.schema import CalcStep, Metric, SortOrder, StepKind, Unit

ADDITIVE: list[str] = [m.value for m in Metric]

DEFAULT_SOURCES: dict[StepKind, list[str]] = {
    StepKind.DEVIATION: [Metric.FACT_AMOUNT.value, Metric.PLAN_AMOUNT.value],
    StepKind.COMPLETION: [Metric.FACT_AMOUNT.value, Metric.PLAN_AMOUNT.value],
    StepKind.SHARE: [Metric.FACT_AMOUNT.value],
    StepKind.GROWTH: [Metric.FACT_AMOUNT.value],
    StepKind.CUMULATIVE: [Metric.FACT_AMOUNT.value],
    StepKind.RANK: [Metric.FACT_AMOUNT.value],
    StepKind.MEAN: [Metric.FACT_AMOUNT.value],
    StepKind.MEDIAN: [Metric.FACT_AMOUNT.value],
    StepKind.MIN: [Metric.FACT_AMOUNT.value],
    StepKind.MAX: [Metric.FACT_AMOUNT.value],
}

# Статистики по группе. Единица у них — единица источника, а не своя:
# среднее рублей — рубли, среднее штук — штуки.
STATS: dict[StepKind, str] = {
    StepKind.MEAN: "mean",
    StepKind.MEDIAN: "median",
    StepKind.MIN: "min",
    StepKind.MAX: "max",
}
STAT_WORDS: dict[StepKind, str] = {
    StepKind.MEAN: "среднее",
    StepKind.MEDIAN: "медиана",
    StepKind.MIN: "минимум",
    StepKind.MAX: "максимум",
}

STEP_UNITS: dict[StepKind, Unit] = {
    StepKind.DEVIATION: "rub",
    StepKind.COMPLETION: "percent",
    StepKind.SHARE: "percent",
    StepKind.GROWTH: "percent",
    StepKind.CUMULATIVE: "rub",
    StepKind.RANK: "rank",
    StepKind.MEAN: "rub",
    StepKind.MEDIAN: "rub",
    StepKind.MIN: "rub",
    StepKind.MAX: "rub",
    StepKind.ARITHMETIC: "none",
}


# Роли операндов. «Выполнение плана» — это факт ÷ план, и наоборот это
# другое число. Модель порядок путает (возвращала [plan, fact]), поэтому
# для парных операций порядок задаётся здесь, а не приходит извне.
ACTUAL: dict[str, str] = {
    Metric.FACT_AMOUNT.value: "amount",
    Metric.FACT_QTY.value: "qty",
    Metric.SALES_COUNT.value: "count",
    Metric.DISCOUNT_AMOUNT.value: "amount",
}
PLANNED: dict[str, str] = {
    Metric.PLAN_AMOUNT.value: "amount",
    Metric.PLAN_QTY.value: "qty",
}
PAIRED = {StepKind.COMPLETION, StepKind.DEVIATION}


def normalize_source(kind: StepKind, source: list[str]) -> list[str]:
    """Приводит пару «факт, план» к правильному порядку и дополняет недостающую
    половину парой того же измерения: план в штуках к факту в штуках.
    """
    if kind not in PAIRED:
        return source
    actual = next((s for s in source if s in ACTUAL), None)
    planned = next((s for s in source if s in PLANNED), None)
    if actual is None and planned is None:
        return list(DEFAULT_SOURCES[kind])
    if actual is None:
        unit = PLANNED[planned]
        actual = next(f for f, u in ACTUAL.items() if u == unit)
    if planned is None:
        unit = ACTUAL[actual]
        planned = next((f for f, u in PLANNED.items() if u == unit), Metric.PLAN_AMOUNT.value)
    return [actual, planned]


class CalcError(ValueError):
    """Ошибка, которую можно показать пользователю как есть."""


@dataclass
class Context:
    """Что движку нужно знать о форме таблицы, чтобы считать по-разному.

    period_field — колонка периода, по ней упорядочены динамика и накопление.
    group_fields — сущностные разрезы: динамика считается внутри каждого
    региона отдельно, а не сквозным рядом по перемешанной таблице.
    """

    period_field: str | None = None
    group_fields: list[str] | None = None


def field_label(field: str) -> str:
    metric = _as_metric(field)
    return METRIC_LABELS[metric] if metric else field


def _as_metric(field: str) -> Metric | None:
    try:
        return Metric(field)
    except ValueError:
        return None


# Короткие подписи для шагов на стандартных источниках: «Выполнение плана, %»
# читается, «Выполнение плана (Факт, План)» — нет. Источники в подписи
# появляются только когда они отличаются от принятых по умолчанию.
STEP_SHORT: dict[StepKind, str] = {
    StepKind.DEVIATION: "Отклонение, ₽",
    StepKind.COMPLETION: "Выполнение плана, %",
    StepKind.SHARE: "Доля в объёме, %",
    StepKind.GROWTH: "Динамика к прошлому периоду, %",
    StepKind.CUMULATIVE: "Накопительный итог",
    StepKind.RANK: "Место в рейтинге",
}


def step_title(step: CalcStep) -> str:
    if step.title:
        return step.title
    base = STEP_LABELS[step.kind]
    if step.kind is StepKind.ARITHMETIC:
        return base
    default = DEFAULT_SOURCES.get(step.kind, [])
    if not step.source or step.source == default:
        return STEP_SHORT.get(step.kind, base)
    sources = ", ".join(field_label(s) for s in step.source)
    return f"{base} ({sources})"


def formula_text(step: CalcStep) -> str:
    """Человекочитаемая формула для истории вычислений: пользователь должен
    видеть, что именно посчитано, — это прямое требование кейса.
    """
    source = [field_label(s) for s in step.source or DEFAULT_SOURCES.get(step.kind, [])]
    match step.kind:
        case StepKind.DEVIATION:
            return f"{source[0]} − {source[1]}"
        case StepKind.COMPLETION:
            return f"{source[0]} ÷ {source[1]} × 100"
        case StepKind.SHARE:
            return f"{source[0]} ÷ итог × 100"
        case StepKind.GROWTH:
            return f"({source[0]} − прошлый период) ÷ прошлый период × 100"
        case StepKind.CUMULATIVE:
            return f"накопление {source[0]} по периодам"
        case StepKind.RANK:
            return f"место по {source[0]}"
        case kind if kind in STATS:
            return f"{STAT_WORDS[kind]} {source[0]} по периодам внутри каждой группы"
        case _:
            return step.expression or ""


# ─── разбор арифметики ────────────────────────────────────────────────────────

# Имена колонок у нас всегда латиницей, но модель иногда пишет формулу
# русскими словами. Пускаем их в разбор, чтобы ошибка была понятной
# («нет колонки «выручка»»), а не «не понимаю символ».
_TOKEN = re.compile(r"\s*(?:(\d+(?:[.,]\d+)?)|(\w[\w]*)|([-+*/()]))", re.UNICODE)
_PRECEDENCE = {"+": 1, "-": 1, "*": 2, "/": 2, "u-": 3}


def _tokenize(expression: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    position = 0
    while position < len(expression):
        match = _TOKEN.match(expression, position)
        if match is None:
            rest = expression[position:].strip()
            if not rest:
                break
            raise CalcError(f"не понимаю «{rest[:20]}» в формуле")
        number, name, operator = match.groups()
        if number is not None:
            tokens.append(("number", number.replace(",", ".")))
        elif name is not None:
            tokens.append(("name", name))
        else:
            tokens.append(("operator", operator))
        position = match.end()
    if not tokens:
        raise CalcError("формула пустая")
    return tokens


def to_rpn(expression: str) -> list[tuple[str, str]]:
    """Сортировочная станция. Выдаёт обратную польскую запись, которую потом
    считают операции pandas — исполняемого текста не возникает нигде.
    """
    output: list[tuple[str, str]] = []
    stack: list[str] = []
    previous: str | None = None

    for kind, value in _tokenize(expression):
        if kind in ("number", "name"):
            output.append((kind, value))
        elif value == "(":
            stack.append(value)
        elif value == ")":
            while stack and stack[-1] != "(":
                output.append(("operator", stack.pop()))
            if not stack:
                raise CalcError("лишняя закрывающая скобка")
            stack.pop()
        else:
            unary = value == "-" and previous in (None, "(", "operator")
            token = "u-" if unary else value
            while stack and stack[-1] != "(" and _PRECEDENCE[stack[-1]] >= _PRECEDENCE[token]:
                output.append(("operator", stack.pop()))
            stack.append(token)
        previous = value if kind == "operator" else kind

    while stack:
        top = stack.pop()
        if top == "(":
            raise CalcError("незакрытая скобка")
        output.append(("operator", top))
    return output


def evaluate(expression: str, frame: pd.DataFrame) -> pd.Series:
    stack: list[pd.Series] = []
    ones = pd.Series(np.ones(len(frame)), index=frame.index, dtype="float64")

    for kind, value in to_rpn(expression):
        if kind == "number":
            stack.append(ones * float(value))
        elif kind == "name":
            if value not in frame.columns:
                known = ", ".join(field_label(c) for c in frame.columns if c in ADDITIVE)
                raise CalcError(f"в таблице нет колонки «{value}». Есть: {known}")
            stack.append(pd.to_numeric(frame[value], errors="coerce").astype("float64"))
        elif value == "u-":
            if not stack:
                raise CalcError("формула оборвана")
            stack.append(-stack.pop())
        else:
            if len(stack) < 2:
                raise CalcError("формула оборвана")
            right, left = stack.pop(), stack.pop()
            match value:
                case "+":
                    stack.append(left + right)
                case "-":
                    stack.append(left - right)
                case "*":
                    stack.append(left * right)
                case "/":
                    stack.append(_divide(left, right))
    if len(stack) != 1:
        raise CalcError("формула неполная")
    return stack[0]


def _divide(left: pd.Series, right: pd.Series) -> pd.Series:
    """Деление на ноль даёт пропуск, а не бесконечность: план нулевой —
    процент выполнения не существует, и прочерк честнее любого числа.
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        result = left / right.replace(0, np.nan)
    return result.replace([np.inf, -np.inf], np.nan)


# ─── прогон стека ─────────────────────────────────────────────────────────────


def apply(frame: pd.DataFrame, steps: list[CalcStep], context: Context | None = None) -> pd.DataFrame:
    """Прогоняет стек по порядку. Шаг может ссылаться на колонку предыдущего —
    зависимости держатся порядком списка, отдельного графа не нужно.
    """
    context = context or Context()
    out = frame.copy()
    for step in steps:
        out[step.field] = _compute(out, step, context)
    return out


def _compute(frame: pd.DataFrame, step: CalcStep, context: Context) -> pd.Series:
    source = step.source or DEFAULT_SOURCES.get(step.kind, [])
    for name in source:
        if name not in frame.columns:
            raise CalcError(f"шаг «{step_title(step)}» ссылается на колонку «{name}», которой нет")

    match step.kind:
        case StepKind.ARITHMETIC:
            if not step.expression:
                raise CalcError("для произвольной формулы нужно само выражение")
            return evaluate(step.expression, frame)
        case StepKind.DEVIATION:
            return _numeric(frame, source[0]) - _numeric(frame, source[1])
        case StepKind.COMPLETION:
            return _divide(_numeric(frame, source[0]), _numeric(frame, source[1])) * 100
        case StepKind.SHARE:
            values = _numeric(frame, source[0])
            total = values.sum()
            if not total:
                return pd.Series(np.nan, index=frame.index, dtype="float64")
            return values / total * 100
        case StepKind.GROWTH:
            return _ordered(frame, context, source[0], "growth")
        case StepKind.CUMULATIVE:
            return _ordered(frame, context, source[0], "cumulative")
        case StepKind.RANK:
            ascending = step.order is SortOrder.ASC
            return _numeric(frame, source[0]).rank(ascending=ascending, method="min")
        case kind if kind in STATS:
            return _group_stat(frame, context, source[0], STATS[kind])
    raise CalcError(f"неизвестный тип шага: {step.kind}")


def _numeric(frame: pd.DataFrame, field: str) -> pd.Series:
    return pd.to_numeric(frame[field], errors="coerce").astype("float64")


def _ordered(frame: pd.DataFrame, context: Context, field: str, what: str) -> pd.Series:
    """Динамика и накопление требуют порядка по времени и разделения по
    сущности: рост Центрального региона нельзя считать от предыдущей строки,
    если предыдущая строка — другой регион.
    """
    values = _numeric(frame, field)
    period = context.period_field
    if period is None or period not in frame.columns:
        raise CalcError(
            "динамику и накопительный итог можно считать только когда в таблице "
            "есть разрез по периоду — добавьте месяц, квартал или год"
        )

    groups = [g for g in (context.group_fields or []) if g in frame.columns]
    order = frame.sort_values([*groups, period]).index

    if groups:
        grouped = values.loc[order].groupby([frame.loc[order, g] for g in groups], sort=False)
        shifted = grouped.pct_change() * 100 if what == "growth" else grouped.cumsum()
    else:
        series = values.loc[order]
        shifted = series.pct_change() * 100 if what == "growth" else series.cumsum()

    result = shifted.reindex(frame.index)
    return result.replace([np.inf, -np.inf], np.nan)


def _group_stat(frame: pd.DataFrame, context: Context, field: str, stat: str) -> pd.Series:
    """Среднее, медиана, минимум, максимум внутри каждой группы.

    Группа — сущностные разрезы таблицы, значения внутри неё — периоды:
    «среднее факта по региону» это среднемесячный факт региона. Без
    сущностных разрезов считаем по всей колонке — одна строка на группу дала
    бы статистику, равную самому значению, то есть ничего.
    """
    values = _numeric(frame, field)
    groups = [g for g in (context.group_fields or []) if g in frame.columns]
    if groups:
        return values.groupby([frame[g] for g in groups], sort=False).transform(stat)
    return pd.Series(getattr(values, stat)(), index=frame.index, dtype="float64")
