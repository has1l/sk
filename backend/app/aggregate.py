"""Плоская таблица сессии → сгруппированная таблица под текущий вид.

Здесь живёт весь пересчёт интерактива. Фильтр, переключатель разреза, смена
зерна периода — это повторная группировка уже выгруженного датафрейма: ни
модели, ни базы (ADR-0006).

Метрики складываются только те, что складываются. Отношения считает стек
вычислений — после группировки, см. calculations.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.calculations import ADDITIVE
from app.schema import Dimension, Filter, PeriodGrain, ViewState

FIELD: dict[Dimension, str] = {
    Dimension.MONTH: "month",
    Dimension.QUARTER: "quarter",
    Dimension.YEAR: "year",
    Dimension.REGION: "region_name",
    Dimension.OUTLET: "outlet_name",
    Dimension.CITY: "city",
    Dimension.OUTLET_TYPE: "outlet_type",
    Dimension.PRODUCT: "product_name",
    Dimension.CATEGORY: "category",
}

ENTITY_DIMENSIONS: list[Dimension] = [d for d in Dimension if not d.is_temporal]

# Каскад фильтров: выбор слева сужает список справа.
CASCADE: dict[Dimension, Dimension] = {
    Dimension.OUTLET: Dimension.REGION,
    Dimension.CITY: Dimension.REGION,
    Dimension.PRODUCT: Dimension.CATEGORY,
}


def prepare(frame: pd.DataFrame) -> pd.DataFrame:
    """Доводит выгрузку до рабочего вида: типы и производные колонки периода.

    Кварталы и годы считаются один раз при загрузке, а не на каждый клик
    переключателя периода.
    """
    out = frame.copy()
    out["month"] = pd.to_datetime(out["month"])
    out["quarter"] = out["month"].dt.to_period("Q").dt.start_time
    out["year"] = out["month"].dt.to_period("Y").dt.start_time
    for column in ADDITIVE:
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0.0).astype("float64")
    return out


def window(frame: pd.DataFrame, view: ViewState) -> pd.DataFrame:
    """Активное окно: границы периода и выбранные значения фильтров.

    Таблица сессии шире окна — она загружена с запасом назад, чтобы было от
    чего считать динамику к прошлому периоду.
    """
    out = frame
    if view.date_from is not None:
        out = out[out["month"] >= pd.Timestamp(view.date_from)]
    if view.date_to is not None:
        out = out[out["month"] <= pd.Timestamp(view.date_to)]
    return apply_filters(out, view.filters)


def apply_filters(frame: pd.DataFrame, filters: list[Filter]) -> pd.DataFrame:
    out = frame
    for flt in filters:
        column = FIELD.get(flt.dimension)
        if column is None or column not in out.columns or not flt.values:
            continue
        out = out[out[column].isin(flt.values)]
    return out


def group(frame: pd.DataFrame, dimensions: list[Dimension]) -> pd.DataFrame:
    metrics = [m for m in ADDITIVE if m in frame.columns]
    if not dimensions:
        totals = frame[metrics].sum().to_frame().T if len(frame) else _empty(metrics)
        return totals.reset_index(drop=True)

    keys = [FIELD[d] for d in dimensions]
    if not len(frame):
        return pd.DataFrame(columns=[*keys, *metrics])
    grouped = frame.groupby(keys, as_index=False, observed=True)[metrics].sum()
    return grouped.sort_values(keys).reset_index(drop=True)


def _empty(metrics: list[str]) -> pd.DataFrame:
    return pd.DataFrame([{m: 0.0 for m in metrics}])


def totals(frame: pd.DataFrame) -> dict[str, float]:
    metrics = [m for m in ADDITIVE if m in frame.columns]
    if not len(frame):
        return {m: 0.0 for m in metrics}
    return {m: float(frame[m].sum()) for m in metrics}


def distinct_counts(frame: pd.DataFrame) -> dict[str, int]:
    """Активные точки и продукты — те, где факт был. Иначе в счёт попадут
    строки, где есть только план: 11 711 ключей плана без единой продажи.
    """
    if not len(frame):
        return {"outlets": 0, "products": 0, "cities": 0, "regions": 0}
    sold = frame[frame["fact_amount"] > 0]
    return {
        "outlets": int(sold["outlet_name"].nunique()),
        "products": int(sold["product_name"].nunique()),
        "cities": int(sold["city"].nunique()),
        "regions": int(sold["region_name"].nunique()),
    }


def grain_of(dimensions: list[Dimension]) -> PeriodGrain | None:
    for dimension in dimensions:
        if dimension.is_temporal:
            return PeriodGrain(dimension.value)
    return None


def entity_of(dimensions: list[Dimension]) -> Dimension | None:
    for dimension in dimensions:
        if not dimension.is_temporal:
            return dimension
    return None


def bounds(frame: pd.DataFrame) -> tuple[date | None, date | None]:
    if not len(frame):
        return None, None
    return frame["month"].min().date(), frame["month"].max().date()


def previous_window(frame: pd.DataFrame, view: ViewState) -> pd.DataFrame:
    """Тот же отрезок, сдвинутый на свою длину назад. Нужен KPI «динамика к
    прошлому периоду»: сравнивать сентябрь с годом нельзя.
    """
    if view.date_from is None or view.date_to is None:
        return frame.iloc[0:0]
    start = pd.Timestamp(view.date_from)
    end = pd.Timestamp(view.date_to)
    months = (end.year - start.year) * 12 + (end.month - start.month) + 1
    shifted_end = start - pd.DateOffset(months=1)
    shifted_start = start - pd.DateOffset(months=months)
    out = frame[(frame["month"] >= shifted_start) & (frame["month"] <= shifted_end)]
    return apply_filters(out, view.filters)
