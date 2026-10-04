"""Русские подписи. Интерфейс продукта полностью на русском, английский
остаётся только в коде — поэтому ни одна подпись не собирается из имени поля.
"""

from app.schema import Dimension, Metric, PeriodGrain, StepKind, Unit, ViewMode

DIMENSION_LABELS: dict[Dimension, str] = {
    Dimension.MONTH: "Месяц",
    Dimension.QUARTER: "Квартал",
    Dimension.YEAR: "Год",
    Dimension.REGION: "Регион",
    Dimension.OUTLET: "Торговая точка",
    Dimension.CITY: "Город",
    Dimension.OUTLET_TYPE: "Тип точки",
    Dimension.PRODUCT: "Продукт",
    Dimension.CATEGORY: "Категория",
}

METRIC_LABELS: dict[Metric, str] = {
    Metric.PLAN_AMOUNT: "План",
    Metric.FACT_AMOUNT: "Факт",
    Metric.PLAN_QTY: "План, шт",
    Metric.FACT_QTY: "Факт, шт",
    Metric.SALES_COUNT: "Сделок",
    Metric.DISCOUNT_AMOUNT: "Скидки",
}

METRIC_UNITS: dict[Metric, Unit] = {
    Metric.PLAN_AMOUNT: "rub",
    Metric.FACT_AMOUNT: "rub",
    Metric.PLAN_QTY: "qty",
    Metric.FACT_QTY: "qty",
    Metric.SALES_COUNT: "count",
    Metric.DISCOUNT_AMOUNT: "rub",
}

UNIT_AXIS_LABELS: dict[str, str] = {
    "rub": "₽",
    "qty": "штуки",
    "count": "количество",
    "percent": "%",
    "rank": "место",
    "none": "",
}

GRAIN_LABELS: dict[PeriodGrain, str] = {
    PeriodGrain.MONTH: "Месяц",
    PeriodGrain.QUARTER: "Квартал",
    PeriodGrain.YEAR: "Год",
}

MODE_LABELS: dict[ViewMode, str] = {
    ViewMode.ABSOLUTE: "Абсолютные",
    ViewMode.PERCENT: "Проценты",
    ViewMode.GROWTH: "Динамика",
}

STEP_LABELS: dict[StepKind, str] = {
    StepKind.DEVIATION: "Отклонение",
    StepKind.COMPLETION: "Выполнение плана",
    StepKind.SHARE: "Доля в объёме",
    StepKind.GROWTH: "Динамика к прошлому периоду",
    StepKind.CUMULATIVE: "Накопительный итог",
    StepKind.RANK: "Ранг",
    StepKind.ARITHMETIC: "Произвольная формула",
}

# Родительный падеж метрик: «Структура факта», «Динамика скидок».
METRIC_GENITIVE: dict[Metric, str] = {
    Metric.PLAN_AMOUNT: "плана",
    Metric.FACT_AMOUNT: "факта",
    Metric.PLAN_QTY: "плана в штуках",
    Metric.FACT_QTY: "факта в штуках",
    Metric.SALES_COUNT: "сделок",
    Metric.DISCOUNT_AMOUNT: "скидок",
}

GENITIVE: dict[Dimension, str] = {
    Dimension.MONTH: "месяцам",
    Dimension.QUARTER: "кварталам",
    Dimension.YEAR: "годам",
    Dimension.REGION: "регионам",
    Dimension.OUTLET: "торговым точкам",
    Dimension.CITY: "городам",
    Dimension.OUTLET_TYPE: "типам точек",
    Dimension.PRODUCT: "продуктам",
    Dimension.CATEGORY: "категориям",
}

# Единственное число в предложном падеже: «в Центральном регионе» не собрать
# из «Регион», а подписи фильтров и инсайтов без него звучат как машинный перевод.
SINGULAR: dict[Dimension, str] = {
    Dimension.REGION: "регион",
    Dimension.OUTLET: "точка",
    Dimension.CITY: "город",
    Dimension.OUTLET_TYPE: "тип точки",
    Dimension.PRODUCT: "продукт",
    Dimension.CATEGORY: "категория",
    Dimension.MONTH: "месяц",
    Dimension.QUARTER: "квартал",
    Dimension.YEAR: "год",
}


# Род разрезов. Собирать «Лучший» + «точка» нельзя — получается «Лучший
# точка». Прилагательное хранится вместе с существительным.
BEST: dict[Dimension, str] = {
    Dimension.REGION: "Лучший регион",
    Dimension.OUTLET: "Лучшая точка",
    Dimension.CITY: "Лучший город",
    Dimension.OUTLET_TYPE: "Лучший тип точки",
    Dimension.PRODUCT: "Лучший продукт",
    Dimension.CATEGORY: "Лучшая категория",
    Dimension.MONTH: "Лучший месяц",
    Dimension.QUARTER: "Лучший квартал",
    Dimension.YEAR: "Лучший год",
}

WORST: dict[Dimension, str] = {
    Dimension.REGION: "худший",
    Dimension.OUTLET: "худшая",
    Dimension.CITY: "худший",
    Dimension.OUTLET_TYPE: "худший",
    Dimension.PRODUCT: "худший",
    Dimension.CATEGORY: "худшая",
    Dimension.MONTH: "худший",
    Dimension.QUARTER: "худший",
    Dimension.YEAR: "худший",
}


def dimension_label(dimension: Dimension) -> str:
    return DIMENSION_LABELS[dimension]


def metric_label(metric: Metric) -> str:
    return METRIC_LABELS[metric]


def genitive(dimension: Dimension) -> str:
    """Для заголовков вида «План-факт по регионам»."""
    return GENITIVE[dimension]
