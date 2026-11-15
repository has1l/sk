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
    Dimension.CLIENT: "Клиент",
    Dimension.CLIENT_SEGMENT: "Сегмент клиента",
    Dimension.DISCOUNT_REASON: "Причина скидки",
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
    StepKind.MEAN: "Среднее",
    StepKind.MEDIAN: "Медиана",
    StepKind.MIN: "Минимум",
    StepKind.MAX: "Максимум",
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
    Dimension.CLIENT: "клиентам",
    Dimension.CLIENT_SEGMENT: "сегментам клиентов",
    Dimension.DISCOUNT_REASON: "причинам скидок",
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
    Dimension.CLIENT: "клиент",
    Dimension.CLIENT_SEGMENT: "сегмент",
    Dimension.DISCOUNT_REASON: "причина скидки",
    Dimension.MONTH: "месяц",
    Dimension.QUARTER: "квартал",
    Dimension.YEAR: "год",
}


# «По всем …» — дательный множественного. Подпись разреза в единственном
# числе давала «все торговая точка в сумме вырос».
ACROSS_ALL: dict[Dimension, str] = {
    Dimension.REGION: "по всем регионам",
    Dimension.OUTLET: "по всем торговым точкам",
    Dimension.CITY: "по всем городам",
    Dimension.OUTLET_TYPE: "по всем типам точек",
    Dimension.PRODUCT: "по всем продуктам",
    Dimension.CATEGORY: "по всем категориям",
    Dimension.CLIENT: "по всем клиентам",
    Dimension.CLIENT_SEGMENT: "по всем сегментам",
    Dimension.DISCOUNT_REASON: "по всем причинам скидок",
    Dimension.MONTH: "по всем месяцам",
    Dimension.QUARTER: "по всем кварталам",
    Dimension.YEAR: "по всем годам",
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
    Dimension.CLIENT: "Лучший клиент",
    Dimension.CLIENT_SEGMENT: "Лучший сегмент",
    Dimension.DISCOUNT_REASON: "Лучшая причина скидки",
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
    Dimension.CLIENT: "худший",
    Dimension.CLIENT_SEGMENT: "худший",
    Dimension.DISCOUNT_REASON: "худшая",
    Dimension.MONTH: "худший",
    Dimension.QUARTER: "худший",
    Dimension.YEAR: "худший",
}


INTENT_LABELS: dict[str, str] = {
    "new_query": "новый вопрос",
    "refine": "правка выборки",
    "filter": "фильтр",
    "toggle": "переключатель",
    "calculate": "вычисление",
    "undo": "отмена",
    "show_table": "показать таблицу",
    "chart": "настройка графика",
    "explain": "выводы",
    "why": "разбор причин",
    "save": "сохранение",
    "list_saved": "список дашбордов",
    "open_saved": "открыть дашборд",
    "rename": "переименование",
    "copy": "копия",
    "delete": "удаление дашборда",
    "ui_help": "подсказка по интерфейсу",
    "out_of_scope": "за границей возможностей",
}


#: Виды графика, доступные своей панели. Водопад сюда не входит: он не
#: «вид графика», а мост от плана к факту, и собирается разбором причин.
CHART_LABELS: dict[str, str] = {
    "bar": "Столбцы",
    "hbar": "Полосы",
    "line": "Линия",
    "pie": "Круг",
}


def dimension_label(dimension: Dimension) -> str:
    return DIMENSION_LABELS[dimension]


def metric_label(metric: Metric) -> str:
    return METRIC_LABELS[metric]


def genitive(dimension: Dimension) -> str:
    """Для заголовков вида «План-факт по регионам»."""
    return GENITIVE[dimension]
