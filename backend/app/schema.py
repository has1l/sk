"""Контракт API и спецификация выборки.

Разрезы, метрики и типы вычислений — закрытые перечисления. Это не удобство,
а граница безопасности: в SQL и в формулы попадают только перечисленные здесь
идентификаторы, а всё, что пришло от пользователя, уезжает параметрами
(ADR-0004).
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

Unit = Literal["rub", "qty", "count", "percent", "rank", "none"]


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
    DISCOUNT_AMOUNT = "discount_amount"


class RelativePeriod(StrEnum):
    LAST_MONTH = "last_month"
    LAST_QUARTER = "last_quarter"
    LAST_YEAR = "last_year"
    YEAR_TO_DATE = "year_to_date"
    ALL_TIME = "all_time"


class PeriodGrain(StrEnum):
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"

    @property
    def dimension(self) -> Dimension:
        return Dimension(self.value)


class ViewMode(StrEnum):
    ABSOLUTE = "absolute"
    PERCENT = "percent"
    GROWTH = "growth"


class Intent(StrEnum):
    """Что пользователь хочет сделать с сессией. Распознаёт модель, исполняет код."""

    NEW_QUERY = "new_query"
    REFINE = "refine"
    FILTER = "filter"
    TOGGLE = "toggle"
    CALCULATE = "calculate"
    UNDO = "undo"
    SHOW_TABLE = "show_table"
    CHART = "chart"
    EXPLAIN = "explain"
    SAVE = "save"
    LIST_SAVED = "list_saved"
    OPEN_SAVED = "open_saved"
    RENAME = "rename"
    COPY = "copy"
    DELETE = "delete"


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
    metrics: list[Metric] = Field(min_length=1, max_length=6)
    period: Period = Period(relative=RelativePeriod.ALL_TIME)
    filters: list[Filter] = []
    order_by: Metric | None = None
    order: SortOrder = SortOrder.DESC
    limit: int | None = Field(default=None, ge=1, le=1000)
    clip_to_fact_horizon: bool = True


# ─── вычисления ───────────────────────────────────────────────────────────────


class StepKind(StrEnum):
    DEVIATION = "deviation"
    COMPLETION = "completion"
    SHARE = "share"
    GROWTH = "growth"
    CUMULATIVE = "cumulative"
    RANK = "rank"
    ARITHMETIC = "arithmetic"


class CalcStep(BaseModel):
    """Шаг стека вычислений. Таблица не мутируется — пересобирается прогоном
    стека от базовой выборки, поэтому откат это удаление шага (ADR-0002).
    """

    id: str
    title: str
    kind: StepKind
    field: str
    source: list[str] = []
    expression: str | None = None
    unit: Unit = "none"
    order: SortOrder = SortOrder.DESC


# ─── состояние просмотра: фильтры и переключатели ─────────────────────────────


class ViewState(BaseModel):
    """Всё, что пользователь крутит руками. Меняется без похода в модель и в
    базу — пересчётом поверх уже выгруженной таблицы сессии (ADR-0006).
    """

    primary: Dimension = Dimension.REGION
    period_grain: PeriodGrain = PeriodGrain.MONTH
    metric: Metric = Metric.FACT_AMOUNT
    mode: ViewMode = ViewMode.ABSOLUTE
    table_dimensions: list[Dimension] = Field(default=[], max_length=3)
    filters: list[Filter] = []
    date_from: date | None = None
    date_to: date | None = None
    sort_field: str | None = None
    sort_order: SortOrder = SortOrder.DESC
    limit: int | None = None


# ─── вывод ────────────────────────────────────────────────────────────────────


class Column(BaseModel):
    field: str
    label: str
    kind: Literal["dimension", "metric", "calc"]
    unit: Unit = "none"


class Table(BaseModel):
    columns: list[Column]
    rows: list[dict[str, Any]]
    row_count: int


class Series(BaseModel):
    field: str
    label: str
    unit: Unit = "none"


class ChartSpec(BaseModel):
    kind: Literal["bar", "hbar", "line", "pie", "area"]
    title: str
    x_field: str
    x_label: str
    y_label: str
    series: list[Series]
    stacked: bool = False
    reference: float | None = None
    zoom_group: str | None = None


class ChartPanel(BaseModel):
    id: str
    spec: ChartSpec
    table: Table
    note: str | None = None


class Kpi(BaseModel):
    key: str
    label: str
    value: float | None
    unit: Unit
    kind: Literal["value", "delta", "percent"] = "value"
    status: Literal["good", "warning", "serious", "critical", "neutral"] = "neutral"
    hint: str | None = None


class FilterOption(BaseModel):
    dimension: Dimension
    label: str
    values: list[str]
    selected: list[str] = []
    parent: Dimension | None = None


class ToggleOption(BaseModel):
    key: str
    label: str
    value: str
    options: list[dict[str, str]]


class PanelKind(StrEnum):
    PLAN_FACT_PERIOD = "plan_fact_period"
    STRUCTURE = "structure"
    TOP = "top"
    COMPLETION_TREND = "completion_trend"
    CUSTOM = "custom"


class PanelConfig(BaseModel):
    id: str
    kind: PanelKind
    dimension: Dimension | None = None
    metric: Metric | None = None
    sort_field: str | None = None
    order: SortOrder = SortOrder.DESC
    limit: int = 10
    chart: Literal["bar", "hbar", "line", "pie", "area"] | None = None
    title: str | None = None


class DashboardConfig(BaseModel):
    panels: list[PanelConfig] = []


class Dashboard(BaseModel):
    kpis: list[Kpi] = []
    panels: list[ChartPanel] = []
    filters: list[FilterOption] = []
    toggles: list[ToggleOption] = []


class Clarification(BaseModel):
    question: str
    reason: str


class StepView(BaseModel):
    id: str
    title: str
    field: str
    formula: str


class SessionView(BaseModel):
    """Полный снимок того, что показывает интерфейс."""

    session_id: str
    title: str
    question: str
    spec: QuerySpec
    view: ViewState
    steps: list[StepView] = []
    table: Table
    dashboard: Dashboard
    insights: list[str] = []
    notes: list[str] = []
    sql: str | None = None
    saved_id: str | None = None
    dirty: bool = False


class SavedDashboard(BaseModel):
    id: str
    title: str
    question: str
    version: int
    created_at: datetime
    updated_at: datetime


class SavedVersion(BaseModel):
    version: int
    title: str
    note: str
    created_at: datetime


class QueryTemplate(BaseModel):
    group: str
    question: str


# ─── запросы ──────────────────────────────────────────────────────────────────


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    session_id: str | None = None


class ViewRequest(BaseModel):
    session_id: str
    view: ViewState


class SaveRequest(BaseModel):
    session_id: str
    title: str | None = Field(default=None, max_length=120)
    as_new: bool = False


class RenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class AskResponse(BaseModel):
    message: str
    session: SessionView | None = None
    clarification: Clarification | None = None
    saved: list[SavedDashboard] | None = None
    action: str | None = None
