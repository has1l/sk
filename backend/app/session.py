"""Сессия анализа — центральный объект продукта (ADR-0001).

Сессия = плоская таблица + стек вычислений + состояние просмотра + конфиг
дашборда. Реплики чата это команды, которые её меняют; сообщения состояния
не несут. Поэтому «отмени вычисление» и «сохрани дашборд» выражаются как
операции над полями, а не как разбор переписки.

Таблица живёт в памяти процесса: интерактив пересчитывается по ней без
похода в базу. Сохранение хранит рецепт — заказ выборки, стек и конфиг, —
а не данные, поэтому открытие дашборда пересобирает таблицу заново.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from threading import Lock
from typing import Any

import pandas as pd

from app import aggregate, dashboard, db, sql_builder
from app.config import settings
from app.schema import (
    CalcStep,
    DashboardConfig,
    Dimension,
    Metric,
    PeriodGrain,
    QuerySpec,
    ViewState,
)

LOOKBACK_MONTHS = 12


@dataclass
class Snapshot:
    """Состояние, к которому возвращает «отмени». Таблица в снимок не входит:
    она пересобирается стеком, поэтому хранить её незачем.
    """

    label: str
    steps: list[CalcStep]
    view: ViewState
    config: DashboardConfig


@dataclass
class Analysis:
    id: str
    question: str
    title: str
    spec: QuerySpec
    frame: pd.DataFrame
    view: ViewState
    steps: list[CalcStep] = field(default_factory=list)
    config: DashboardConfig = field(default_factory=DashboardConfig)
    notes: list[str] = field(default_factory=list)
    sql: str = ""
    saved_id: str | None = None
    dirty: bool = False
    history: list[Snapshot] = field(default_factory=list)
    touched_at: datetime = field(default_factory=datetime.now)

    def checkpoint(self, label: str) -> None:
        self.history.append(
            Snapshot(
                label=label,
                steps=[s.model_copy(deep=True) for s in self.steps],
                view=self.view.model_copy(deep=True),
                config=self.config.model_copy(deep=True),
            )
        )
        del self.history[:-20]

    def undo(self) -> str | None:
        if not self.history:
            return None
        snapshot = self.history.pop()
        self.steps = snapshot.steps
        self.view = snapshot.view
        self.config = snapshot.config
        self.dirty = True
        return snapshot.label

    def state(self) -> dict[str, Any]:
        """Рецепт для сохранения. Данных здесь нет — только то, как их получить."""
        return {
            "question": self.question,
            "title": self.title,
            "spec": self.spec.model_dump(mode="json"),
            "view": self.view.model_dump(mode="json"),
            "steps": [s.model_dump(mode="json") for s in self.steps],
            "config": self.config.model_dump(mode="json"),
        }


_sessions: dict[str, Analysis] = {}
_lock = Lock()


def default_view(spec: QuerySpec, date_from: date | None, date_to: date | None) -> ViewState:
    primary = aggregate.entity_of(spec.dimensions) or Dimension.REGION
    grain = aggregate.grain_of(spec.dimensions) or PeriodGrain.MONTH
    metric = next(
        (m for m in spec.metrics if m is not Metric.PLAN_AMOUNT),
        spec.metrics[0] if spec.metrics else Metric.FACT_AMOUNT,
    )
    return ViewState(
        primary=primary,
        period_grain=grain,
        metric=metric,
        table_dimensions=list(spec.dimensions),
        filters=[f.model_copy(deep=True) for f in spec.filters],
        date_from=date_from,
        date_to=date_to,
        limit=spec.limit,
        sort_field=spec.order_by.value if spec.order_by else None,
        sort_order=spec.order,
    )


def load_frame(spec: QuerySpec, horizon: date) -> tuple[pd.DataFrame, str, list[str], date, date]:
    built = sql_builder.build_detail(spec, horizon, LOOKBACK_MONTHS)
    rows = db.select(built.sql, built.params)
    frame = aggregate.prepare(pd.DataFrame(rows, columns=_frame_columns()))
    window_from = built.date_from
    window_to = built.date_to
    if window_from is None or window_to is None:
        low, high = aggregate.bounds(frame)
        window_from = window_from or low or horizon
        window_to = window_to or high or horizon
    return frame, built.sql, built.notes, window_from, window_to


def _frame_columns() -> list[str]:
    return sql_builder.DETAIL_COLUMNS + [m.value for m in sql_builder.DETAIL_METRICS]


def create(question: str, spec: QuerySpec, horizon: date, title: str) -> Analysis:
    frame, sql, notes, window_from, window_to = load_frame(spec, horizon)
    view = default_view(spec, window_from, window_to)
    analysis = Analysis(
        id=uuid.uuid4().hex,
        question=question,
        title=title,
        spec=spec,
        frame=frame,
        view=view,
        config=dashboard.default_config(view),
        notes=list(notes),
        sql=sql,
    )
    _remember(analysis)
    return analysis


def rebase(analysis: Analysis, spec: QuerySpec, horizon: date, question: str) -> Analysis:
    """Правка заказа выборки: новая база, стек и конфиг остаются.

    Так «а теперь по точкам» меняет разрез, не теряя добавленные вычисления.
    """
    frame, sql, notes, window_from, window_to = load_frame(spec, horizon)
    analysis.checkpoint("изменение выборки")
    analysis.spec = spec
    analysis.frame = frame
    analysis.sql = sql
    analysis.notes = list(notes)
    analysis.question = question
    fresh = default_view(spec, window_from, window_to)
    # Переключатели вида — выбор пользователя, а не часть заказа выборки.
    # Правка периода не повод сбрасывать «в процентах» и метрику.
    fresh.mode = analysis.view.mode
    if not spec.metrics or analysis.view.metric in spec.metrics:
        fresh.metric = analysis.view.metric
    analysis.view = fresh
    analysis.dirty = True
    analysis.touched_at = datetime.now()
    return analysis


def get(session_id: str) -> Analysis | None:
    with _lock:
        analysis = _sessions.get(session_id)
        if analysis is not None:
            analysis.touched_at = datetime.now()
        return analysis


def _remember(analysis: Analysis) -> None:
    with _lock:
        _sessions[analysis.id] = analysis
        _evict()


def _evict() -> None:
    """Сессии держат датафреймы, поэтому живут недолго и в ограниченном числе."""
    deadline = datetime.now() - timedelta(minutes=settings.session_ttl_minutes)
    for key, value in list(_sessions.items()):
        if value.touched_at < deadline:
            del _sessions[key]
    while len(_sessions) > settings.max_sessions:
        oldest = min(_sessions.values(), key=lambda a: a.touched_at)
        del _sessions[oldest.id]


def restore(state: dict[str, Any], horizon: date, saved_id: str | None) -> Analysis:
    """Открытие сохранённого дашборда: рецепт → таблица → тот же вид."""
    spec = QuerySpec.model_validate(state["spec"])
    frame, sql, notes, window_from, window_to = load_frame(spec, horizon)
    view = ViewState.model_validate(state["view"])
    if view.date_from is None:
        view.date_from = window_from
    if view.date_to is None:
        view.date_to = window_to
    analysis = Analysis(
        id=uuid.uuid4().hex,
        question=state.get("question", ""),
        title=state.get("title", "Дашборд"),
        spec=spec,
        frame=frame,
        view=view,
        steps=[CalcStep.model_validate(s) for s in state.get("steps", [])],
        config=DashboardConfig.model_validate(state.get("config", {"panels": []})),
        notes=list(notes),
        sql=sql,
        saved_id=saved_id,
    )
    if not analysis.config.panels:
        analysis.config = dashboard.default_config(analysis.view)
    _remember(analysis)
    return analysis


def count() -> int:
    with _lock:
        return len(_sessions)
