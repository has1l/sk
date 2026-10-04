"""Спецификация выборки и контракт API.

Разрезы и метрики — закрытые перечисления. Это не удобство, а граница
безопасности: в SQL попадают только те идентификаторы, что перечислены здесь,
а всё, что пришло от пользователя, уезжает параметрами (ADR-0004).
"""

from datetime import date
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Dimension(StrEnum):
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"
    REGION = "region"
    OUTLET = "outlet"
    CITY = "city"
    OUTLET_TYPE = "outlet_type"
    PRODUCT = "product"
    CATEGORY = "category"

    @property
    def is_temporal(self) -> bool:
        return self in (Dimension.MONTH, Dimension.QUARTER, Dimension.YEAR)


class Metric(StrEnum):
    PLAN_AMOUNT = "plan_amount"
    FACT_AMOUNT = "fact_amount"
    PLAN_QTY = "plan_qty"
    FACT_QTY = "fact_qty"
    SALES_COUNT = "sales_count"


class RelativePeriod(StrEnum):
    LAST_MONTH = "last_month"
    LAST_QUARTER = "last_quarter"
    LAST_YEAR = "last_year"
    YEAR_TO_DATE = "year_to_date"
    ALL_TIME = "all_time"


class Period(BaseModel):
    """Либо относительный период, либо явные границы.

    Относительный считается от горизонта факта, а не от сегодняшней даты:
    данные обрываются 2026-09-30, и «последний месяц» от календарного сегодня
    дал бы пустую выборку.
    """

    relative: RelativePeriod | None = None
    date_from: date | None = None
    date_to: date | None = None


class Filter(BaseModel):
    dimension: Dimension
    values: list[str] = Field(min_length=1)


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


class QuerySpec(BaseModel):
    dimensions: list[Dimension] = Field(default=[], max_length=3)
    metrics: list[Metric] = Field(min_length=1, max_length=5)
    period: Period = Period(relative=RelativePeriod.ALL_TIME)
    filters: list[Filter] = []
    order_by: Metric | None = None
    order: SortOrder = SortOrder.DESC
    limit: int | None = Field(default=None, ge=1, le=1000)
    clip_to_fact_horizon: bool = True


class Column(BaseModel):
    field: str
    label: str
    kind: Literal["dimension", "metric"]
    unit: Literal["rub", "qty", "count", "none"] = "none"


class Table(BaseModel):
    columns: list[Column]
    rows: list[dict[str, Any]]
    row_count: int


class Series(BaseModel):
    field: str
    label: str


class ChartSpec(BaseModel):
    kind: Literal["bar", "line"]
    title: str
    x_field: str
    x_label: str
    y_label: str
    series: list[Series]
    stacked: bool = False


class Clarification(BaseModel):
    question: str
    reason: str


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class AskResponse(BaseModel):
    message: str
    spec: QuerySpec | None = None
    table: Table | None = None
    chart: ChartSpec | None = None
    clarification: Clarification | None = None
    notes: list[str] = []
    sql: str | None = None
