"""Русские подписи. Интерфейс продукта полностью на русском, английский
остаётся только в коде — поэтому ни одна подпись не собирается из имени поля.
"""

from app.schema import Dimension, Metric

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
}

METRIC_UNITS: dict[Metric, str] = {
    Metric.PLAN_AMOUNT: "rub",
    Metric.FACT_AMOUNT: "rub",
    Metric.PLAN_QTY: "qty",
    Metric.FACT_QTY: "qty",
    Metric.SALES_COUNT: "count",
}

UNIT_AXIS_LABELS: dict[str, str] = {
    "rub": "₽",
    "qty": "штуки",
    "count": "количество",
    "none": "",
}


def dimension_label(dimension: Dimension) -> str:
    return DIMENSION_LABELS[dimension]


def metric_label(metric: Metric) -> str:
    return METRIC_LABELS[metric]


def genitive(dimension: Dimension) -> str:
    """Для заголовков вида «План-факт по регионам»."""
    forms = {
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
    return forms[dimension]
