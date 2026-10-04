"""HTTP API. Один на все клиенты: веб и iOS получают одинаковые снимки сессии.

Реплика чата проходит через модель один раз — она определяет намерение, —
дальше работает код. Интерактив (фильтры, переключатели) идёт отдельным
эндпоинтом и модель не трогает вовсе.
"""

from contextlib import asynccontextmanager
from datetime import date
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from app import (
    aggregate,
    calculations,
    dashboard,
    db,
    export,
    insights,
    planner,
    render,
    session,
    store,
    templates,
    vocabulary,
)
from app.calculations import CalcError
from app.config import settings
from app.labels import (
    DIMENSION_LABELS,
    GRAIN_LABELS,
    METRIC_LABELS,
    MODE_LABELS,
)
from app.schema import (
    AskRequest,
    AskResponse,
    Dimension,
    Filter,
    Intent,
    PanelKind,
    QueryTemplate,
    RenameRequest,
    SaveRequest,
    SavedDashboard,
    SavedVersion,
    SessionView,
    StepKind,
    ViewRequest,
    ViewState,
)
from app.session import Analysis


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.open_pool()
    vocabulary.load()
    planner._load_cache()
    yield
    db.close_pool()


app = FastAPI(title="Puzzle RPA — BI в чате", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _horizon() -> date:
    return db.fact_horizon()


def _need(session_id: str | None) -> Analysis:
    analysis = session.get(session_id) if session_id else None
    if analysis is None:
        raise HTTPException(404, "сессия не найдена — задайте вопрос заново")
    return analysis


def _ok(analysis: Analysis, message: str, action: str | None = None) -> AskResponse:
    view = render.build(analysis, _horizon())
    return AskResponse(message=message, session=view, action=action)


# ─── разбор реплики ───────────────────────────────────────────────────────────


@app.post("/api/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    if not settings.has_openai:
        raise HTTPException(503, "OPENAI_API_KEY не задан — понимание запросов недоступно")

    horizon = _horizon()
    current = session.get(request.session_id) if request.session_id else None
    context = render.describe(current) if current else ""

    try:
        plan = planner.interpret(request.question, horizon, context)
    except Exception as error:
        raise HTTPException(502, f"не удалось разобрать запрос: {error}") from error

    if plan.needs_clarification and plan.clarification_question:
        clarification = plan.clarification()
        return AskResponse(message=clarification.question, clarification=clarification)

    intent = plan.intent
    if current is None and intent in _NEEDS_SESSION:
        intent = Intent.NEW_QUERY

    handler = _HANDLERS.get(intent, _new_query)
    return handler(request, plan, current, horizon)


_NEEDS_SESSION = {
    Intent.REFINE,
    Intent.FILTER,
    Intent.TOGGLE,
    Intent.CALCULATE,
    Intent.UNDO,
    Intent.SHOW_TABLE,
    Intent.CHART,
    Intent.EXPLAIN,
    Intent.SAVE,
    Intent.COPY,
}


def _new_query(request: AskRequest, plan, current, horizon) -> AskResponse:
    spec = plan.to_spec()
    spec.filters, notes = planner.resolve_filters(spec.filters)
    analysis = session.create(request.question, spec, horizon, title="")
    analysis.notes = notes + analysis.notes
    analysis.title = render.title_for(spec, analysis.view)
    lines = insights.build(analysis.frame, analysis.view, horizon)
    return _ok(analysis, lines[0] if lines else "Готово.")


def _refine(request: AskRequest, plan, current: Analysis, horizon) -> AskResponse:
    spec = plan.to_spec()
    spec.filters, notes = planner.resolve_filters(spec.filters)
    session.rebase(current, spec, horizon, request.question)
    current.notes = notes + current.notes
    _apply_toggles(current.view, plan)
    current.title = render.title_for(spec, current.view)
    lines = insights.build(current.frame, current.view, horizon)
    return _ok(current, lines[0] if lines else "Перестроил.")


def _filter(request: AskRequest, plan, current: Analysis, horizon) -> AskResponse:
    filters, notes = planner.resolve_filters(plan.filters)
    current.checkpoint("фильтры")
    if filters:
        existing = {f.dimension: f for f in current.view.filters}
        for flt in filters:
            existing[flt.dimension] = flt
        current.view.filters = list(existing.values())
        applied = "; ".join(
            f"{f.dimension.value}: {', '.join(f.values)}" for f in current.view.filters
        )
        message = f"Отфильтровал: {applied}."
    else:
        current.view.filters = []
        message = "Снял все фильтры."
    current.dirty = True
    current.notes = notes
    return _ok(current, message, action="filter")


def _apply_toggles(view: ViewState, plan) -> list[str]:
    changed: list[str] = []
    if plan.set_primary is not None and not plan.set_primary.is_temporal:
        view.primary = plan.set_primary
        _swap_entity(view, plan.set_primary)
        changed.append(f"разрез — {DIMENSION_LABELS[plan.set_primary].lower()}")
    if plan.set_period_grain is not None:
        view.period_grain = plan.set_period_grain
        _swap_period(view, plan.set_period_grain.dimension)
        changed.append(f"период — {GRAIN_LABELS[plan.set_period_grain].lower()}")
    if plan.set_metric is not None:
        view.metric = plan.set_metric
        changed.append(f"метрика — {METRIC_LABELS[plan.set_metric].lower()}")
    if plan.set_mode is not None:
        view.mode = plan.set_mode
        changed.append(f"вид — {MODE_LABELS[plan.set_mode].lower()}")
    return changed


def _toggle(request: AskRequest, plan, current: Analysis, horizon) -> AskResponse:
    current.checkpoint("переключатели")
    changed = _apply_toggles(current.view, plan)

    if not changed:
        current.undo()
        return _ok(current, "Не понял, что переключить. Скажите: разрез, метрика, период или вид.")

    current.dirty = True
    return _ok(current, "Переключил: " + ", ".join(changed) + ".", action="toggle")


def _swap_entity(view: ViewState, dimension: Dimension) -> None:
    dimensions = [d for d in view.table_dimensions if d.is_temporal]
    dimensions.append(dimension)
    view.table_dimensions = dimensions


def _swap_period(view: ViewState, dimension: Dimension) -> None:
    dimensions = [d for d in view.table_dimensions if not d.is_temporal]
    if any(d.is_temporal for d in view.table_dimensions):
        view.table_dimensions = [dimension, *dimensions]


NEEDS_PERIOD = {StepKind.GROWTH, StepKind.CUMULATIVE}


def _calculate(request: AskRequest, plan, current: Analysis, horizon) -> AskResponse:
    step = plan.to_step()
    current.checkpoint(f"вычисление «{calculations.step_title(step)}»")
    extra = ""

    # Динамику и накопление не на чем считать без разреза по периоду. Просьба
    # от этого не перестаёт быть осмысленной — добавляем период сами и говорим
    # об этом, а не отказываем.
    if step.kind in NEEDS_PERIOD and not any(
        d.is_temporal for d in current.view.table_dimensions
    ):
        grain = current.view.period_grain.dimension
        current.view.table_dimensions = [grain, *current.view.table_dimensions]
        extra = f" Добавил в таблицу разрез по {DIMENSION_LABELS[grain].lower()}ам — без него динамику не посчитать."

    probe = aggregate.group(
        aggregate.window(current.frame, current.view), current.view.table_dimensions
    )
    try:
        calculations.apply(probe, [*current.steps, step], render.context_for(current.view))
    except CalcError as error:
        current.undo()
        return _ok(current, f"Так не посчитать: {error}")

    current.steps.append(step)
    current.dirty = True
    return _ok(
        current,
        f"Добавил колонку «{calculations.step_title(step)}»: "
        f"{calculations.formula_text(step)}.{extra} Отменить — скажите «отмени».",
        action="calculate",
    )


def _undo(request: AskRequest, plan, current: Analysis, horizon) -> AskResponse:
    label = current.undo()
    if label is None:
        return _ok(current, "Отменять нечего — это исходное состояние.")
    return _ok(current, f"Отменил: {label}.", action="undo")


def _show_table(request: AskRequest, plan, current: Analysis, horizon) -> AskResponse:
    return _ok(current, "Таблица с данными и всеми вычислениями.", action="table")


def _chart(request: AskRequest, plan, current: Analysis, horizon) -> AskResponse:
    index = (plan.panel or 3) - 1
    panels = current.config.panels
    if not 0 <= index < len(panels):
        return _ok(current, f"На дашборде {len(panels)} графика — укажите номер от 1 до {len(panels)}.")

    current.checkpoint(f"настройка графика {index + 1}")
    panel = panels[index]
    changed: list[str] = []

    if plan.sort_field:
        panel.sort_field = _resolve_field(plan.sort_field, current)
        panel.order = plan.order
        changed.append(f"сортировка по «{_field_label(panel.sort_field, current)}»")
    if plan.set_primary is not None and panel.kind in (PanelKind.TOP, PanelKind.STRUCTURE):
        panel.dimension = plan.set_primary
        changed.append(f"разрез — {plan.set_primary.value}")
    if plan.set_metric is not None and panel.kind is PanelKind.STRUCTURE:
        panel.metric = plan.set_metric
        changed.append(f"метрика — {plan.set_metric.value}")
    if plan.limit:
        panel.limit = plan.limit
        changed.append(f"ТОП-{plan.limit}")

    if not changed:
        current.undo()
        return _ok(current, "Не понял, что поменять в графике. Можно: сортировку, разрез, метрику, размер ТОПа.")

    current.dirty = True
    return _ok(current, f"График {index + 1}: {', '.join(changed)}.", action="chart")


def _resolve_field(name: str, analysis: Analysis) -> str:
    """Модель может назвать колонку словами. Сначала ищем среди шагов стека,
    потом среди метрик, потом отдаём как есть — панель скажет, если не нашла.
    """
    folded = name.strip().casefold()
    for step in analysis.steps:
        if folded in (step.field.casefold(), calculations.step_title(step).casefold()):
            return step.field
    if folded in {"completion", "выполнение", "процент выполнения", "completion_pct"}:
        return dashboard.COMPLETION_FIELD
    if folded in {"deviation", "отклонение"}:
        return "deviation_rub"
    return name


def _field_label(field: str, analysis: Analysis) -> str:
    """Внутреннее имя колонки пользователю не показываем: «calc_710f78» — это
    не ответ на «отсортируй по проценту выполнения».
    """
    for step in analysis.steps:
        if step.field == field:
            return calculations.step_title(step)
    return dashboard.column_of(field, analysis.steps).label


def _explain(request: AskRequest, plan, current: Analysis, horizon) -> AskResponse:
    lines = insights.build(current.frame, current.view, horizon)
    return _ok(current, " ".join(lines) if lines else "Пока нечего пояснять.", action="explain")


# ─── сохранение ───────────────────────────────────────────────────────────────


def _save(request: AskRequest, plan, current: Analysis, horizon) -> AskResponse:
    title = (plan.new_title or plan.target_title or current.title).strip()
    current.title = title or current.title
    state = current.state()

    if current.saved_id and not plan.new_title:
        version = store.update(current.saved_id, current.title, current.question, state)
        current.dirty = False
        return _ok(current, f"Обновил дашборд «{current.title}», версия {version}.", action="save")

    current.saved_id = store.save_new(current.title, current.question, state)
    current.dirty = False
    return _ok(current, f"Сохранил дашборд «{current.title}».", action="save")


def _list_saved(request: AskRequest, plan, current, horizon) -> AskResponse:
    items = store.listing(query=plan.target_title)
    if not items:
        return AskResponse(message="Сохранённых дашбордов пока нет.", saved=[], action="list")
    names = ", ".join(f"«{item.title}»" for item in items[:5])
    tail = f" и ещё {len(items) - 5}" if len(items) > 5 else ""
    return AskResponse(
        message=f"Сохранённых дашбордов {len(items)}: {names}{tail}.",
        saved=items,
        action="list",
    )


def _open_saved(request: AskRequest, plan, current, horizon) -> AskResponse:
    title = (plan.target_title or plan.new_title or "").strip()
    if not title:
        return _list_saved(request, plan, current, horizon)
    found = store.find_by_title(title)
    if found is None:
        return AskResponse(
            message=f"Дашборда с названием «{title}» не нашёл.",
            saved=store.listing(),
            action="list",
        )
    saved_title, state = store.load(found.id)
    analysis = session.restore(state, horizon, found.id)
    analysis.title = saved_title
    return _ok(analysis, f"Открыл дашборд «{saved_title}».", action="open")


def _rename(request: AskRequest, plan, current, horizon) -> AskResponse:
    title = (plan.new_title or "").strip()
    if not title:
        return AskResponse(message="Как назвать дашборд?", action="rename")

    target = current.saved_id if current else None
    if target is None and plan.target_title:
        found = store.find_by_title(plan.target_title)
        target = found.id if found else None
    if target is None:
        return AskResponse(message="Сначала сохраните дашборд, потом его можно переименовать.")

    store.rename(target, title)
    if current and current.saved_id == target:
        current.title = title
        return _ok(current, f"Переименовал в «{title}».", action="rename")
    return AskResponse(message=f"Переименовал в «{title}».", saved=store.listing(), action="rename")


def _copy(request: AskRequest, plan, current: Analysis, horizon) -> AskResponse:
    if current.saved_id is None:
        current.title = plan.new_title or current.title
        current.saved_id = store.save_new(current.title, current.question, current.state())
    new_id = store.copy(current.saved_id, plan.new_title)
    saved_title, state = store.load(new_id)
    analysis = session.restore(state, horizon, new_id)
    analysis.title = saved_title
    return _ok(analysis, f"Сделал копию: «{saved_title}». Работаем в ней.", action="copy")


def _delete(request: AskRequest, plan, current, horizon) -> AskResponse:
    """Удаление по названию, а не по догадке: если название не названо,
    спрашиваем. Это необратимо, и промахнуться здесь дорого.
    """
    title = (plan.target_title or "").strip()
    if not title:
        return AskResponse(
            message="Какой дашборд удалить? Назовите его — удаление необратимо.",
            saved=store.listing(),
            action="list",
        )
    found = store.find_by_title(title)
    if found is None:
        return AskResponse(message=f"Дашборда «{title}» не нашёл.", saved=store.listing())
    if found.title.casefold() != title.casefold():
        return AskResponse(
            message=f"Точного совпадения нет. Ближайший — «{found.title}». "
            "Повторите название точно, если удалять нужно именно его.",
            saved=store.listing(),
            action="list",
        )
    store.delete(found.id)
    return AskResponse(
        message=f"Удалил дашборд «{found.title}».", saved=store.listing(), action="delete"
    )


_HANDLERS = {
    Intent.NEW_QUERY: _new_query,
    Intent.REFINE: _refine,
    Intent.FILTER: _filter,
    Intent.TOGGLE: _toggle,
    Intent.CALCULATE: _calculate,
    Intent.UNDO: _undo,
    Intent.SHOW_TABLE: _show_table,
    Intent.CHART: _chart,
    Intent.EXPLAIN: _explain,
    Intent.SAVE: _save,
    Intent.LIST_SAVED: _list_saved,
    Intent.OPEN_SAVED: _open_saved,
    Intent.RENAME: _rename,
    Intent.COPY: _copy,
    Intent.DELETE: _delete,
}


# ─── интерактив: ни модели, ни новой выборки ──────────────────────────────────


@app.post("/api/view", response_model=SessionView)
def set_view(request: ViewRequest) -> SessionView:
    analysis = _need(request.session_id)
    incoming = request.view
    if not incoming.table_dimensions:
        incoming.table_dimensions = analysis.view.table_dimensions
    # Границы окна задаёт выборка, а не клиент: иначе можно уехать за пределы
    # загруженной таблицы и получить пустой дашборд без объяснений.
    incoming.date_from = analysis.view.date_from
    incoming.date_to = analysis.view.date_to
    analysis.view = incoming
    analysis.dirty = True
    return render.build(analysis, _horizon())


@app.get("/api/session/{session_id}", response_model=SessionView)
def get_session(session_id: str) -> SessionView:
    return render.build(_need(session_id), _horizon())


@app.post("/api/session/{session_id}/undo", response_model=AskResponse)
def undo_session(session_id: str) -> AskResponse:
    analysis = _need(session_id)
    label = analysis.undo()
    if label is None:
        return _ok(analysis, "Отменять нечего.")
    return _ok(analysis, f"Отменил: {label}.", action="undo")


@app.delete("/api/session/{session_id}/step/{step_id}", response_model=AskResponse)
def drop_step(session_id: str, step_id: str) -> AskResponse:
    analysis = _need(session_id)
    step = next((s for s in analysis.steps if s.id == step_id), None)
    if step is None:
        raise HTTPException(404, "шага нет")
    analysis.checkpoint(f"удаление «{calculations.step_title(step)}»")
    analysis.steps = [s for s in analysis.steps if s.id != step_id]
    analysis.dirty = True
    return _ok(analysis, f"Убрал «{calculations.step_title(step)}».", action="calculate")


# ─── дашборды ─────────────────────────────────────────────────────────────────


@app.get("/api/dashboards", response_model=list[SavedDashboard])
def dashboards(q: str | None = None, sort: str = "updated") -> list[SavedDashboard]:
    return store.listing(query=q, sort=sort)


@app.post("/api/dashboards", response_model=AskResponse)
def save_dashboard(request: SaveRequest) -> AskResponse:
    analysis = _need(request.session_id)
    if request.title:
        analysis.title = request.title.strip()
    state = analysis.state()

    if analysis.saved_id and not request.as_new:
        version = store.update(analysis.saved_id, analysis.title, analysis.question, state)
        analysis.dirty = False
        return _ok(analysis, f"Обновил «{analysis.title}», версия {version}.", action="save")

    analysis.saved_id = store.save_new(analysis.title, analysis.question, state)
    analysis.dirty = False
    return _ok(analysis, f"Сохранил «{analysis.title}».", action="save")


@app.get("/api/dashboards/{dashboard_id}/open", response_model=AskResponse)
def open_dashboard(dashboard_id: str) -> AskResponse:
    try:
        title, state = store.load(dashboard_id)
    except KeyError:
        raise HTTPException(404, "дашборд не найден") from None
    analysis = session.restore(state, _horizon(), dashboard_id)
    analysis.title = title
    return _ok(analysis, f"Открыл «{title}».", action="open")


@app.patch("/api/dashboards/{dashboard_id}", response_model=list[SavedDashboard])
def rename_dashboard(dashboard_id: str, request: RenameRequest) -> list[SavedDashboard]:
    store.rename(dashboard_id, request.title.strip())
    return store.listing()


@app.post("/api/dashboards/{dashboard_id}/copy", response_model=AskResponse)
def copy_dashboard(dashboard_id: str) -> AskResponse:
    try:
        new_id = store.copy(dashboard_id)
    except KeyError:
        raise HTTPException(404, "дашборд не найден") from None
    title, state = store.load(new_id)
    analysis = session.restore(state, _horizon(), new_id)
    analysis.title = title
    return _ok(analysis, f"Сделал копию: «{title}».", action="copy")


@app.delete("/api/dashboards/{dashboard_id}", response_model=list[SavedDashboard])
def delete_dashboard(dashboard_id: str) -> list[SavedDashboard]:
    store.delete(dashboard_id)
    return store.listing()


@app.get("/api/dashboards/{dashboard_id}/versions", response_model=list[SavedVersion])
def dashboard_versions(dashboard_id: str) -> list[SavedVersion]:
    return store.versions(dashboard_id)


@app.post("/api/dashboards/{dashboard_id}/versions/{version}/open", response_model=AskResponse)
def open_version(dashboard_id: str, version: int) -> AskResponse:
    try:
        title, state = store.load_version(dashboard_id, version)
    except KeyError:
        raise HTTPException(404, "версии нет") from None
    analysis = session.restore(state, _horizon(), dashboard_id)
    analysis.title = title
    analysis.dirty = True
    return _ok(
        analysis,
        f"Открыл версию {version} дашборда «{title}». Сохранение запишет её поверх текущей.",
        action="open",
    )


# ─── выгрузка и прочее ────────────────────────────────────────────────────────


@app.get("/api/export/csv/{session_id}")
def export_csv(session_id: str) -> Response:
    analysis = _need(session_id)
    table, _ = render.table_of(analysis)
    body = export.to_csv(table)
    return Response(
        content=body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": _attachment(analysis.title, "csv")},
    )


@app.get("/api/export/html/{session_id}")
def export_html(session_id: str) -> Response:
    analysis = _need(session_id)
    view = render.build(analysis, _horizon())
    return Response(
        content=export.to_html(view),
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": _attachment(analysis.title, "html")},
    )


def _attachment(title: str, extension: str) -> str:
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in title).strip() or "dashboard"
    return f"attachment; filename*=UTF-8''{quote(safe)}.{extension}"


@app.get("/api/templates", response_model=list[QueryTemplate])
def query_templates() -> list[QueryTemplate]:
    return templates.all()


@app.get("/api/health")
def health() -> dict[str, Any]:
    horizon = _horizon()
    return {
        "status": "ok",
        "fact_horizon": horizon.isoformat(),
        "model": settings.openai_model,
        "openai_configured": settings.has_openai,
        "cached_questions": planner.cache_size(),
        "sessions": session.count(),
    }
