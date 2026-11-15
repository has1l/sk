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
    CLIENT = "client"
    CLIENT_SEGMENT = "client_segment"
    DISCOUNT_REASON = "discount_reason"

    @property
    def is_temporal(self) -> bool:
        return self in (Dimension.MONTH, Dimension.QUARTER, Dimension.YEAR)

    @property
    def is_fact_only(self) -> bool:
        """Разрез, у которого нет плана: план живёт на зерне «месяц × точка ×
        продукт», клиента и причины скидки в нём нет (ADR-0009)."""
        return self in (Dimension.CLIENT, Dimension.CLIENT_SEGMENT, Dimension.DISCOUNT_REASON)


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
    WHY = "why"
    UI_HELP = "ui_help"
    OUT_OF_SCOPE = "out_of_scope"


class UiFeature(StrEnum):
    """Элементы дашборда, о которых спрашивают как о новой функции, хотя они
    уже на экране: «добавь фильтр с поиском», «покажи итоговые цифры сверху»."""

    FILTERS = "filters"
    CASCADE = "cascade"
    TOGGLE_PRIMARY = "toggle_primary"
    TOGGLE_METRIC = "toggle_metric"
    TOGGLE_PERIOD = "toggle_period"
    TOGGLE_MODE = "toggle_mode"
    KPI = "kpi"
    ZOOM = "zoom"
    EXPORT = "export"


class Period(BaseModel):
    """Либо относительный период, либо явные границы.

    Относительный считается от горизонта факта, а не от сегодняшней даты:
    данные обрываются 2026-09-30, и «последний месяц» от календарного сегодня
    дал бы пустую выборку.
    """

    relative: RelativePeriod | None = None
    date_from: date | None = None
    date_to: date | None = None
    # «За последние три года» — число месяцев до горизонта факта. Границы
    # считает код: модель на такой арифметике ошибалась на целый год.
    last_months: int | None = Field(default=None, ge=1, le=120)


class Filter(BaseModel):
    dimension: Dimension
    values: list[str] = Field(min_length=1, max_length=500)


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
    MEAN = "mean"
    MEDIAN = "median"
    MIN = "min"
    MAX = "max"
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
    kind: Literal["bar", "hbar", "line", "pie", "area", "waterfall"]
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
    WATERFALL = "waterfall"
    CUSTOM = "custom"


class PanelConfig(BaseModel):
    id: str
    kind: PanelKind
    dimension: Dimension | None = None
    metric: Metric | None = None
    sort_field: str | None = None
    # Что рисует линия панели 4 вместо выполнения плана: вычисленная колонка
    # из стека («покажи четвёртый график с учётом динамики»).
    series_field: str | None = None
    order: SortOrder = SortOrder.DESC
    limit: int = 10
    chart: Literal["bar", "hbar", "line", "pie", "area", "waterfall"] | None = None
    title: str | None = None


class Slot(BaseModel):
    """Ячейка раскладки — одна коробка на дашборде.

    Координат у ячейки нет: место задаётся порядком в списке, а строки
    считает укладка. Поэтому дырок в сетке не бывает по построению, а
    «перетащить панель» — это «вставить на другое место в списке».

    Несколько панелей в ячейке означают, что они склеены в одну коробку и
    переключаются вкладками внутри неё.
    """

    id: str
    w: int = 1
    panels: list[str] = []
    active: int = 0


class BoardTab(BaseModel):
    """Вкладка дашборда: своя страница с собственным набором ячеек."""

    id: str
    title: str
    slots: list[Slot] = []


class Layout(BaseModel):
    columns: int = 2
    tabs: list[BoardTab] = []
    active: str = ""


class DashboardConfig(BaseModel):
    panels: list[PanelConfig] = []
    # Пусто у дашбордов, сохранённых до появления раскладки: там был только
    # список панелей. Согласование построит раскладку с нуля, поэтому старые
    # сохранения открываются без миграции.
    layout: Layout | None = None


class Dashboard(BaseModel):
    kpis: list[Kpi] = []
    panels: list[ChartPanel] = []
    filters: list[FilterOption] = []
    toggles: list[ToggleOption] = []
    layout: Layout = Layout()


class Clarification(BaseModel):
    question: str
    reason: str


class StepView(BaseModel):
    id: str
    title: str
    field: str
    formula: str


# ─── разбор причин, аномалии, происхождение цифр ──────────────────────────────


class GapFactor(BaseModel):
    """Вклад одного значения разреза в общий разрыв плана и факта."""

    label: str
    value: float
    share: float
    direction: Literal["drag", "lift"]


class GapLevel(BaseModel):
    dimension: Dimension
    label: str
    factors: list[GapFactor] = []


class Decomposition(BaseModel):
    """Ответ на «почему»: из чего сложился разрыв, по уровням разрезов."""

    headline: str
    total: float
    unit: Unit = "rub"
    levels: list[GapLevel] = []
    chain: list[str] = []


class Anomaly(BaseModel):
    """То, о чём не спрашивали: выброс на фоне своей же группы."""

    label: str
    text: str
    severity: Literal["high", "medium"]
    dimension: Dimension


class Formula(BaseModel):
    field: str
    title: str
    kind: str
    expression: str
    inputs: list[str] = []


class Provenance(BaseModel):
    """Как получена каждая цифра на экране. Нужна не для отладки, а чтобы
    границу безопасности (ADR-0004) было видно, а не только обещано.
    """

    sql: str | None = None
    role: str = "bi_reader"
    statement_timeout: str = "10s"
    read_only: bool = True
    row_count: int = 0
    load_ms: float = 0.0
    model: str = ""
    llm_calls: int = 0
    formulas: list[Formula] = []
    guarantees: list[str] = []


class TimelineEntry(BaseModel):
    """Точка возврата. Каждый шаг диалога — состояние, к которому можно вернуться."""

    id: str
    label: str
    at: datetime
    summary: str
    current: bool = False


class SessionView(BaseModel):
    """Полный снимок того, что показывает интерфейс."""

    session_id: str
    title: str
    question: str
    spec: QuerySpec
    view: ViewState
    # Рецепт анализа целиком — то же, что уходит в сохранение. Клиент хранит
    # его черновиком: шагов стека в StepView недостаточно, чтобы собрать
    # сессию заново, там нет ни вида операции, ни единиц.
    recipe: dict[str, Any] = {}
    steps: list[StepView] = []
    table: Table
    dashboard: Dashboard
    summary: str = ""
    insights: list[str] = []
    anomalies: list[Anomaly] = []
    decomposition: Decomposition | None = None
    provenance: Provenance | None = None
    timeline: list[TimelineEntry] = []
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


class LayoutRequest(BaseModel):
    session_id: str
    layout: Layout


class PanelRequest(BaseModel):
    """Своя панель: человек выбрал разрез, метрику и вид графика.

    Ничего из этого не исполняется и не подставляется в текст — только
    перечисления, которые знает сборщик панелей.
    """

    session_id: str
    dimension: Dimension
    metric: Metric
    chart: Literal["bar", "hbar", "line", "pie"] = "bar"
    limit: int = Field(default=10, ge=2, le=30)
    title: str | None = Field(default=None, max_length=120)


class Choice(BaseModel):
    value: str
    label: str


class PanelOptions(BaseModel):
    """Из чего можно собрать свою панель. Подписи собирает сервер: клиент их
    никогда не строит из имени поля."""

    dimensions: list[Choice] = []
    metrics: list[Choice] = []
    charts: list[Choice] = []


class SaveRequest(BaseModel):
    session_id: str
    title: str | None = Field(default=None, max_length=120)
    as_new: bool = False


class DraftRequest(BaseModel):
    """Черновик, сохранённый браузером. Данных здесь нет — только рецепт,
    поэтому восстановление идёт тем же путём, что и открытие сохранённого.
    """

    recipe: dict[str, Any]


class RenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class AskResponse(BaseModel):
    message: str
    session: SessionView | None = None
    clarification: Clarification | None = None
    saved: list[SavedDashboard] | None = None
    action: str | None = None
