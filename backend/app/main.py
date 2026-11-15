"""HTTP API. Один на все клиенты: веб и iOS получают одинаковые снимки сессии.

Реплика чата проходит через модель один раз — она определяет намерение, —
дальше работает код. Интерактив (фильтры, переключатели) идёт отдельным
эндпоинтом и модель не трогает вовсе.
"""

import json
import logging
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import date
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from app import (
    aggregate,
    calculations,
    dashboard,
    db,
    diagnose,
    export,
    insights,
    layout,
    planner,
    render,
    session,
    sql_builder,
    store,
    templates,
    vocabulary,
)
from app.calculations import CalcError
from app.config import settings
from app.gate import PasswordGate
from app.labels import (
    CHART_LABELS,
    DIMENSION_LABELS,
    GENITIVE,
    GRAIN_LABELS,
    INTENT_LABELS,
    METRIC_LABELS,
    MODE_LABELS,
)
from app.schema import (
    AskRequest,
    AskResponse,
    Choice,
    Clarification,
    DraftRequest,
    Dimension,
    Filter,
    Intent,
    UiFeature,
    Layout,
    LayoutRequest,
    Metric,
    PanelConfig,
    PanelKind,
    PanelOptions,
    PanelRequest,
    QuerySpec,
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
app.add_middleware(PasswordGate, password=settings.site_password)


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


log = logging.getLogger("puzzle")
_asks: dict[str, deque[float]] = defaultdict(deque)


def _require_model(client: Request) -> None:
    if not settings.has_openai:
        raise HTTPException(503, "OPENAI_API_KEY не задан — понимание запросов недоступно")
    host = client.client.host if client.client else "?"
    now = time.monotonic()
    recent = _asks[host]
    while recent and now - recent[0] > 60:
        recent.popleft()
    if len(recent) >= settings.ask_per_minute:
        log.warning("лимит реплик: %s", host)
        raise HTTPException(429, "Слишком много вопросов подряд — подождите минуту.")
    recent.append(now)


# Намерения, которым нужна новая выгрузка из базы. Остальные считаются по
# таблице, уже лежащей в памяти сессии.
LOADS_DATA = {Intent.NEW_QUERY, Intent.REFINE, Intent.OPEN_SAVED, Intent.COPY}


def _pipeline(request: AskRequest) -> Iterator[tuple[str, Any]]:
    """Разбор реплики по шагам.

    Шаги выдаются наружу, а не пишутся в лог: спиннер не отличает работу от
    зависания, а «понял намерение → выгрузил 3 218 строк → собрал дашборд»
    показывает, что происходит, и чего при этом не происходит.
    """
    horizon = _horizon()
    current = session.get(request.session_id) if request.session_id else None
    context = render.describe(current) if current else ""

    yield "stage", {
        "text": "Понимаю вопрос",
        "detail": f"модель {settings.openai_model}, один вызов на реплику",
    }
    started = time.perf_counter()
    try:
        calc_fields = [step.field for step in current.steps] if current else []
        plan = planner.interpret(request.question, horizon, context, calc_fields)
    except Exception as error:
        log.exception("планировщик упал")
        raise HTTPException(502, "Не удалось разобрать вопрос — попробуйте ещё раз.") from error
    elapsed = (time.perf_counter() - started) * 1000

    if plan.needs_clarification and plan.clarification_question:
        clarification = plan.clarification()
        yield "result", AskResponse(message=clarification.question, clarification=clarification)
        return

    # Намерение показывается после поправки: без сессии «правка выборки»
    # превращается в новый запрос, и показывать нужно то, что произошло.
    intent = plan.intent
    if current is None and intent in _NEEDS_SESSION:
        intent = Intent.NEW_QUERY

    yield "stage", {
        "text": f"Намерение — {INTENT_LABELS.get(intent.value, intent.value)}",
        "detail": "ответ из кеша, без обращения к модели"
        if plan.from_cache
        else f"{elapsed:.0f} мс",
    }

    if intent in LOADS_DATA:
        yield "stage", {
            "text": "Беру данные из витрины",
            "detail": "роль bi_reader: один SELECT, только чтение, таймаут 10 с",
        }
    elif intent is not Intent.OUT_OF_SCOPE:
        yield "stage", {
            "text": "Считаю по уже выгруженной таблице",
            "detail": "без похода в базу и без модели",
        }

    handler = _HANDLERS.get(intent, _new_query)
    response = handler(request, plan, current, horizon)

    view = response.session
    if view is not None:
        analysis = session.get(view.session_id)
        if analysis is not None and not plan.from_cache:
            analysis.llm_calls += 1
            if view.provenance is not None:
                view.provenance.llm_calls = analysis.llm_calls
        if view.provenance is not None:
            rows = f"{view.provenance.row_count:,}".replace(",", " ")
            yield "stage", {
                "text": f"Готово: {rows} строк в памяти сессии",
                "detail": f"выгрузка {view.provenance.load_ms:.0f} мс, "
                f"панелей {len(view.dashboard.panels)}, показателей {len(view.dashboard.kpis)}",
            }

    yield "result", response


@app.post("/api/ask", response_model=AskResponse)
def ask(request: AskRequest, client: Request) -> AskResponse:
    _require_model(client)
    for kind, payload in _pipeline(request):
        if kind == "result":
            return payload
    raise HTTPException(500, "разбор не дал ответа")


@app.post("/api/ask/stream")
def ask_stream(request: AskRequest, client: Request) -> StreamingResponse:
    """То же самое, но шаги уходят клиенту по мере готовности."""
    _require_model(client)

    def events() -> Iterator[str]:
        try:
            for kind, payload in _pipeline(request):
                body = payload.model_dump(mode="json") if kind == "result" else payload
                yield f"event: {kind}\ndata: {json.dumps(body, ensure_ascii=False)}\n\n"
        except HTTPException as error:
            body = json.dumps({"detail": error.detail}, ensure_ascii=False)
            yield f"event: error\ndata: {body}\n\n"
        except Exception:  # поток уже начат, 500 клиенту не отдать
            log.exception("разбор реплики упал")
            body = json.dumps({"detail": "Внутренняя ошибка — попробуйте ещё раз."}, ensure_ascii=False)
            yield f"event: error\ndata: {body}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


_NEEDS_SESSION = {
    Intent.REFINE,
    Intent.FILTER,
    Intent.TOGGLE,
    Intent.CALCULATE,
    Intent.UNDO,
    Intent.SHOW_TABLE,
    Intent.CHART,
    Intent.EXPLAIN,
    Intent.WHY,
    Intent.SAVE,
    Intent.COPY,
}


PLAN_METRICS = {Metric.PLAN_AMOUNT, Metric.PLAN_QTY}


def _fit_spec(spec: QuerySpec) -> QuerySpec:
    """Клиентская ветка без плана: плановые колонки в её таблице были бы
    нулями, и человек прочитал бы их как «план ноль»."""
    if sql_builder.needs_client_branch(spec):
        kept = [m for m in spec.metrics if m not in PLAN_METRICS]
        spec.metrics = kept or [Metric.FACT_AMOUNT]
        if Metric.DISCOUNT_AMOUNT not in spec.metrics:
            spec.metrics.append(Metric.DISCOUNT_AMOUNT)
    return spec


def _not_found(requested: list[Filter], kept: list[Filter], notes: list[str]) -> AskResponse | None:
    """Названное значение не нашлось — строить дашборд «по всем данным» вместо
    него нельзя: ответ выглядел бы как ответ про клиента Х, а был бы про всех.
    Раньше так и происходило, с примечанием мелким шрифтом."""
    found = {f.dimension for f in kept}
    missing = [f for f in requested if f.dimension not in found]
    if not missing:
        return None
    named = "; ".join(
        f"{DIMENSION_LABELS[f.dimension].lower()} «{', '.join(f.values)}»" for f in missing
    )
    question = f"Не нашёл в данных: {named}. Проверьте название — можно частью, например одно слово."
    return AskResponse(
        message=question,
        clarification=Clarification(question=question, reason="значение не найдено в справочнике"),
    )


def _new_query(request: AskRequest, plan, current, horizon) -> AskResponse:
    spec = _fit_spec(plan.to_spec())
    requested = list(spec.filters)
    spec.filters, notes = planner.resolve_filters(spec.filters)
    if (refused := _not_found(requested, spec.filters, notes)) is not None:
        return refused
    analysis = session.create(request.question, spec, horizon, title="")
    analysis.notes = notes + analysis.notes
    analysis.title = render.title_for(spec, analysis.view)
    lines = insights.build(analysis.frame, analysis.view, horizon)
    return _ok(analysis, lines[0] if lines else "Готово.")


def _refine(request: AskRequest, plan, current: Analysis, horizon) -> AskResponse:
    spec = _fit_spec(plan.to_spec())
    requested = list(spec.filters)
    spec.filters, notes = planner.resolve_filters(spec.filters)
    if (refused := _not_found(requested, spec.filters, notes)) is not None:
        return refused
    session.rebase(current, spec, horizon, request.question)
    current.notes = notes + current.notes
    _apply_toggles(current.view, plan)
    current.title = render.title_for(spec, current.view)
    lines = insights.build(current.frame, current.view, horizon)
    return _ok(current, lines[0] if lines else "Перестроил.")


def _filter(request: AskRequest, plan, current: Analysis, horizon) -> AskResponse:
    filters, notes = planner.resolve_filters(plan.filters)
    if (refused := _not_found(list(plan.filters), filters, notes)) is not None:
        return refused
    if any(f.dimension.is_fact_only for f in filters) and not aggregate.is_fact_only(current.frame):
        return _to_client_branch(request, current, horizon, filters=filters)
    current.checkpoint("фильтры")
    if filters:
        existing = {f.dimension: f for f in current.view.filters}
        for flt in filters:
            existing[flt.dimension] = flt
        current.view.filters = list(existing.values())
        applied = "; ".join(
            f"{DIMENSION_LABELS[f.dimension].lower()} — {', '.join(f.values)}"
            for f in current.view.filters
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


def _to_client_branch(
    request: AskRequest,
    current: Analysis,
    horizon,
    filters: list[Filter] | None = None,
    primary: Dimension | None = None,
) -> AskResponse:
    """Клиента в основной таблице нет — фильтр по нему там молча ничего бы не
    сделал. Поэтому выборка перегружается из клиентской ветки, а вычисления
    и раскладка переезжают вместе с сессией."""
    spec = current.spec.model_copy(deep=True)
    merged = {f.dimension: f for f in [*current.view.filters, *(filters or [])]}
    spec.filters = list(merged.values())
    if primary is not None:
        spec.dimensions = [*(d for d in spec.dimensions if d.is_temporal), primary]
    spec = _fit_spec(spec)
    session.rebase(current, spec, horizon, request.question)
    current.title = render.title_for(spec, current.view)
    lines = insights.build(current.frame, current.view, horizon)
    head = lines[0] if lines else ""
    return _ok(
        current,
        f"Клиенты живут в отдельной выборке — плана по ним нет, поэтому перегрузил данные "
        f"только с фактом. {head}",
        action="refine",
    )


def _toggle(request: AskRequest, plan, current: Analysis, horizon) -> AskResponse:
    if (
        plan.set_primary is not None
        and plan.set_primary.is_fact_only
        and not aggregate.is_fact_only(current.frame)
    ):
        return _to_client_branch(request, current, horizon, primary=plan.set_primary)
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
    replaced = None
    # «Поменяй формулу» правит последнюю колонку на месте. Имя поля остаётся
    # прежним, чтобы сортировка и линия панели 4, построенные по ней, не потерялись.
    if plan.calc_replace and current.steps:
        replaced = current.steps.pop()
        step = step.model_copy(update={"field": replaced.field})

    # «Посчитай выполнение по гипермаркетам» — это и вычисление, и сужение.
    # Раньше названные значения молча терялись, и ответ приходил по всей базе.
    if plan.filters:
        narrowed, notes = planner.resolve_filters(plan.filters)
        if narrowed:
            existing = {f.dimension: f for f in current.view.filters}
            for flt in narrowed:
                existing[flt.dimension] = flt
            current.view.filters = list(existing.values())
            applied = "; ".join(
                f"{DIMENSION_LABELS[f.dimension].lower()} — {', '.join(f.values)}"
                for f in narrowed
            )
            extra = f" Заодно отфильтровал: {applied}."
        current.notes = notes + current.notes

    # Динамику и накопление не на чем считать без разреза по периоду. Просьба
    # от этого не перестаёт быть осмысленной — добавляем период сами и говорим
    # об этом, а не отказываем.
    has_period = any(d.is_temporal for d in current.view.table_dimensions)
    has_entity = any(not d.is_temporal for d in current.view.table_dimensions)
    # Статистика по группе без периода считала бы среднее из одного значения:
    # «среднее факта по региону» — это среднее по месяцам внутри региона.
    if not has_period and (
        step.kind in NEEDS_PERIOD or (step.kind in calculations.STATS and has_entity)
    ):
        grain = current.view.period_grain.dimension
        current.view.table_dimensions = [grain, *current.view.table_dimensions]
        why = "динамику не посчитать" if step.kind in NEEDS_PERIOD else "в группе было бы одно значение"
        extra = f" Добавил в таблицу разрез по {GENITIVE[grain]} — без него {why}."

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
    verb = (
        f"Заменил формулу «{calculations.step_title(replaced)}» — теперь «{calculations.step_title(step)}»"
        if replaced is not None
        else f"Добавил колонку «{calculations.step_title(step)}»"
    )
    return _ok(
        current,
        f"{verb}: "
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

    field = _resolve_field(plan.sort_field, current) if plan.sort_field else None
    is_step = any(step.field == field for step in current.steps)
    if field and panel.kind is PanelKind.COMPLETION_TREND:
        # Линию по периодам сортировать бессмысленно: просьба «с учётом
        # динамики» значит нарисовать вычисленную колонку вместо выполнения.
        if is_step:
            panel.series_field = field
            changed.append(f"показывает «{_field_label(field, current)}»")
        else:
            panel.series_field = None
            changed.append("показывает выполнение плана")
    elif field:
        panel.sort_field = field
        panel.order = plan.order
        changed.append(f"сортировка по «{_field_label(panel.sort_field, current)}»")
    if plan.set_primary is not None and panel.kind in (PanelKind.TOP, PanelKind.STRUCTURE):
        panel.dimension = plan.set_primary
        changed.append(f"разрез — {DIMENSION_LABELS[plan.set_primary].lower()}")
    if plan.set_metric is not None and panel.kind is PanelKind.STRUCTURE:
        panel.metric = plan.set_metric
        changed.append(f"метрика — {METRIC_LABELS[plan.set_metric].lower()}")
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
    builtin = {dashboard.COMPLETION_FIELD: "проценту выполнения плана", "deviation_rub": "отклонению"}
    if field in builtin:
        return builtin[field]
    return dashboard.column_of(field, analysis.steps).label


def _explain(request: AskRequest, plan, current: Analysis, horizon) -> AskResponse:
    lines = insights.build(current.frame, current.view, horizon)
    return _ok(current, " ".join(lines) if lines else "Пока нечего пояснять.", action="explain")


def _why(request: AskRequest, plan, current: Analysis, horizon) -> AskResponse:
    """Разбор причин: из чего сложился разрыв и кто внутри него тянет вниз."""
    scope = aggregate.window(current.frame, current.view)
    decomposition = diagnose.decompose(scope, current.view)
    if decomposition is None:
        return _ok(
            current,
            "Разложить не на что: в этой выборке нет плана, с которым сравнивать факт.",
            action="why",
        )

    parts = [decomposition.headline, *decomposition.chain]
    found = diagnose.anomalies(scope, current.view)
    if found:
        parts.append(found[0].text)
    return _ok(current, " ".join(parts), action="why")


def _out_of_scope(request: AskRequest, plan, current, horizon) -> AskResponse:
    """Отказ, который объясняет границу, а не просто упирается.

    Граница техническая: под ролью bi_reader изменить данные нельзя, даже
    если бы бот захотел. Поэтому отказ формулируется фактом, а не правилом.
    """
    message = (
        "Этого я не сделаю — и не смог бы, даже если бы захотел. К данным я хожу "
        "под ролью bi_reader: один SELECT, транзакция только на чтение, таймаут 10 секунд. "
        "Изменить, удалить или дописать что-то в витрину под ней нельзя технически. "
        "Запросы я тоже не пишу текстом: модель возвращает намерение из закрытого списка, "
        "а SQL собирает код. Могу показать, что в данных есть."
    )
    if current is None:
        return AskResponse(message=message, action="refused")
    return _ok(current, message, action="refused")


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
    query = (plan.target_title or "").strip() or None
    items = store.listing(query=query)
    if query and not items:
        everything = store.listing()
        return AskResponse(
            message=f"Про «{query}» ни в названиях, ни в запросах ничего не нашёл. "
            f"Всего сохранено {len(everything)} — список ниже.",
            saved=everything,
            action="list",
        )
    if not items:
        return AskResponse(message="Сохранённых дашбордов пока нет.", saved=[], action="list")
    if query:
        names = ", ".join(f"«{item.title}»" for item in items[:5])
        return AskResponse(
            message=f"Про «{query}» нашёл {len(items)}: {names}.",
            saved=items,
            action="list",
        )
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


UI_HELP = {
    UiFeature.FILTERS: "Фильтры уже на дашборде, в строке над графиками: регион, точка, "
    "продукт, категория и другие. Каждый — выпадающий список с поиском и множественным "
    "выбором, применяется сразу ко всем графикам и итоговым цифрам.",
    UiFeature.CASCADE: "Каскад уже работает: выберите регион — в фильтре точек останутся "
    "только точки этого региона. Так же категория сужает список продуктов.",
    UiFeature.TOGGLE_METRIC: "Переключатель «Метрика» — над графиками: объём, скидки, сделки, "
    "выполнение плана. План и факт на первом графике идут парой; легенда на графике "
    "прячет и показывает каждую серию щелчком.",
    UiFeature.TOGGLE_PRIMARY: "Переключатель «Разрез» — над графиками: регионы, точки, "
    "продукты, категории. Графики перестраиваются сразу, без нового запроса.",
    UiFeature.TOGGLE_PERIOD: "Переключатель «Период» — над графиками: месяц, квартал, год.",
    UiFeature.TOGGLE_MODE: "Переключатель «Вид» — над графиками: абсолютные значения, "
    "проценты выполнения или динамика к прошлому периоду.",
    UiFeature.KPI: "Итоговые цифры — карточки в самом верху дашборда: план, факт, выполнение, "
    "отклонение, динамика и активные точки. Зелёный — выполнение, красный — отставание; "
    "пересчитываются при любом фильтре.",
    UiFeature.ZOOM: "Зум есть на каждом графике: выделите область мышью, двойной щелчок "
    "возвращает масштаб. Графики по периодам зумятся синхронно.",
    UiFeature.EXPORT: "Скачать можно из меню дашборда: HTML-страница для отчёта, картинка "
    "или таблица CSV со всеми вычислениями.",
}


def _ui_help(request: AskRequest, plan, current: Analysis | None, horizon) -> AskResponse:
    text = UI_HELP.get(plan.ui_feature) if plan.ui_feature else None
    text = text or "Фильтры, переключатели и итоговые цифры уже на дашборде — над графиками."
    if current is None:
        return AskResponse(message=f"{text} Задайте вопрос — соберу дашборд, и всё это будет на нём.")
    return _ok(current, text, action="ui_help")


_HANDLERS = {
    Intent.UI_HELP: _ui_help,
    Intent.NEW_QUERY: _new_query,
    Intent.REFINE: _refine,
    Intent.FILTER: _filter,
    Intent.TOGGLE: _toggle,
    Intent.CALCULATE: _calculate,
    Intent.UNDO: _undo,
    Intent.SHOW_TABLE: _show_table,
    Intent.CHART: _chart,
    Intent.EXPLAIN: _explain,
    Intent.WHY: _why,
    Intent.OUT_OF_SCOPE: _out_of_scope,
    Intent.SAVE: _save,
    Intent.LIST_SAVED: _list_saved,
    Intent.OPEN_SAVED: _open_saved,
    Intent.RENAME: _rename,
    Intent.COPY: _copy,
    Intent.DELETE: _delete,
}


# ─── интерактив: ни модели, ни новой выборки ──────────────────────────────────


def _view_change(before: ViewState, after: ViewState) -> str | None:
    """Что именно поменялось руками. None — ничего значимого."""
    if before.filters != after.filters:
        return "фильтры"
    if (before.primary, before.period_grain, before.metric, before.mode) != (
        after.primary,
        after.period_grain,
        after.metric,
        after.mode,
    ):
        return "переключатели"
    if (before.sort_field, before.sort_order, before.limit) != (
        after.sort_field,
        after.sort_order,
        after.limit,
    ):
        return "сортировка"
    return None


@app.post("/api/layout", response_model=SessionView)
def set_layout(request: LayoutRequest) -> SessionView:
    """Перестановка панелей. Как и фильтры, идёт мимо модели и мимо базы:
    меняется только раскладка сессии, данные не трогаются.

    Присланная раскладка не принимается на веру — сборка всё равно сводит её с
    панелями, которые реально собрались, так что ссылка на несуществующую
    панель или ширина в девять колонок экран не сломают.
    """
    analysis = _need(request.session_id)
    # Перетаскивание — это десятки мелких правок подряд. Точка возврата нужна
    # одна на всю перестановку, иначе машина времени забьётся мусором.
    analysis.checkpoint("перестановку панелей", coalesce=True)
    analysis.config.layout = request.layout
    analysis.dirty = True
    return render.build(analysis, _horizon())


@app.get("/api/panel-options", response_model=PanelOptions)
def panel_options() -> PanelOptions:
    """Из чего собирается своя панель. Справочник, сессия ему не нужна.

    Выбор закрыт перечислениями: клиент не присылает имя поля, он выбирает из
    того, что сервер назвал и умеет построить.
    """
    return PanelOptions(
        dimensions=[Choice(value=d.value, label=DIMENSION_LABELS[d]) for d in Dimension],
        metrics=[Choice(value=m.value, label=METRIC_LABELS[m]) for m in Metric],
        charts=[Choice(value=k, label=label) for k, label in CHART_LABELS.items()],
    )


@app.post("/api/session/{session_id}/panel", response_model=SessionView)
def add_panel(session_id: str, request: PanelRequest) -> SessionView:
    """Своя панель. Как фильтры и перестановка — мимо модели и мимо базы:
    новая группировка считается по уже выгруженной таблице сессии.

    Ячейку в раскладке не создаём: согласование само допишет новую панель в
    конец открытой вкладки. Два места, создающих ячейки, разошлись бы.
    """
    analysis = _need(session_id)
    analysis.checkpoint("добавление панели")
    analysis.config.panels.append(
        PanelConfig(
            id=layout.fresh_id("c"),
            kind=PanelKind.CUSTOM,
            dimension=request.dimension,
            metric=request.metric,
            chart=request.chart,
            limit=request.limit,
            title=request.title,
        )
    )
    analysis.dirty = True
    return render.build(analysis, _horizon())


@app.delete("/api/session/{session_id}/panel/{panel_id}", response_model=SessionView)
def remove_panel(session_id: str, panel_id: str) -> SessionView:
    """Убрать панель с дашборда.

    Убирается описание панели, а не ссылка на неё в раскладке: ссылку
    согласование всё равно восстановило бы, потому что панель продолжала бы
    собираться. Пустая раскладка — законное состояние: человек вправе убрать
    всё, а машина времени вернёт.
    """
    analysis = _need(session_id)
    kept = [p for p in analysis.config.panels if p.id != panel_id]
    if len(kept) == len(analysis.config.panels):
        raise HTTPException(status_code=404, detail="Такой панели на дашборде нет.")
    analysis.checkpoint("удаление панели")
    analysis.config.panels = kept
    analysis.dirty = True
    return render.build(analysis, _horizon())


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

    # Крутилки тоже меняют состояние сессии, значит тоже оставляют точку
    # возврата. Без этого машина времени видит только реплики чата, а
    # фильтры и переключатели — основной способ работы — проходят мимо неё.
    changed = _view_change(analysis.view, incoming)
    if changed:
        analysis.checkpoint(changed, coalesce=True)

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


@app.post("/api/session/{session_id}/rewind/{snapshot_id}", response_model=AskResponse)
def rewind_session(session_id: str, snapshot_id: str) -> AskResponse:
    analysis = _need(session_id)
    label = analysis.rewind(snapshot_id)
    if label is None:
        raise HTTPException(404, "такой точки возврата нет")
    return _ok(analysis, f"Вернулся к состоянию до шага «{label}».", action="rewind")


@app.post("/api/draft/restore", response_model=AskResponse)
def restore_draft(request: DraftRequest) -> AskResponse:
    """Черновик с клиента. Браузер хранит рецепт, а не данные, поэтому
    восстановление идёт тем же путём, что и открытие сохранённого дашборда:
    выборка собирается заново, вид и стек накладываются сверху.
    """
    try:
        analysis = session.restore(request.recipe, _horizon(), saved_id=None)
    except (KeyError, ValidationError) as error:
        raise HTTPException(400, f"черновик не разобрать: {error}") from error
    analysis.dirty = True
    return _ok(analysis, "Вернул черновик с того места, где вы остановились.", action="draft")


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


def _saved_id(dashboard_id: str) -> str:
    """Id из ссылки приходит как есть. Битая или обрезанная ссылка — это «не
    найден», а не падение базы на приведении строки к uuid."""
    try:
        return str(uuid.UUID(dashboard_id))
    except ValueError:
        raise HTTPException(404, "дашборд не найден — ссылка неполная или устарела") from None


@app.get("/api/dashboards/{dashboard_id}/open", response_model=AskResponse)
def open_dashboard(dashboard_id: str) -> AskResponse:
    dashboard_id = _saved_id(dashboard_id)
    try:
        title, state = store.load(dashboard_id)
    except KeyError:
        raise HTTPException(404, "дашборд не найден") from None
    analysis = session.restore(state, _horizon(), dashboard_id)
    analysis.title = title
    return _ok(analysis, f"Открыл «{title}».", action="open")


@app.patch("/api/dashboards/{dashboard_id}", response_model=list[SavedDashboard])
def rename_dashboard(dashboard_id: str, request: RenameRequest) -> list[SavedDashboard]:
    dashboard_id = _saved_id(dashboard_id)
    store.rename(dashboard_id, request.title.strip())
    return store.listing()


@app.post("/api/dashboards/{dashboard_id}/copy", response_model=AskResponse)
def copy_dashboard(dashboard_id: str) -> AskResponse:
    dashboard_id = _saved_id(dashboard_id)
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
    dashboard_id = _saved_id(dashboard_id)
    store.delete(dashboard_id)
    return store.listing()


@app.get("/api/dashboards/{dashboard_id}/versions", response_model=list[SavedVersion])
def dashboard_versions(dashboard_id: str) -> list[SavedVersion]:
    dashboard_id = _saved_id(dashboard_id)
    return store.versions(dashboard_id)


@app.post("/api/dashboards/{dashboard_id}/versions/{version}/open", response_model=AskResponse)
def open_version(dashboard_id: str, version: int) -> AskResponse:
    dashboard_id = _saved_id(dashboard_id)
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


# Собранный веб с того же адреса, что и API: одна ссылка, один пароль, без CORS.
# Монтируется последним — все /api/* уже зарегистрированы и матчатся раньше.
if settings.web_dist:
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=settings.web_dist, html=True), name="web")
