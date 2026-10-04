"""Реплика на русском → намерение и его параметры.

Единственное место, где участвует модель. Она не пишет SQL, не выбирает тип
графика и не исполняет формулы — только переводит язык в структуру из
закрытого списка (ADR-0004).

Один вызов на реплику. Модель получает не переписку, а компактное описание
текущей сессии: что построено, какие шаги в стеке, что включено. Поэтому
стоимость запроса не растёт с длиной диалога (ADR-0001).

Форма ответа задана строгой JSON-схемой на стороне OpenAI, а не примером в
промпте. Это принципиально: без схемы модели возвращают поля в своей форме и
ломают разбор, причём слабые модели чаще — и выглядит это так, будто они хуже
понимают аналитику, хотя они просто не угадали форму.
"""

import hashlib
import json
import threading
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from app import vocabulary
from app.config import settings
from app.labels import DIMENSION_LABELS, METRIC_LABELS, STEP_LABELS
from app.schema import (
    CalcStep,
    Clarification,
    Dimension,
    Filter,
    Intent,
    Metric,
    Period,
    PeriodGrain,
    QuerySpec,
    RelativePeriod,
    SortOrder,
    StepKind,
    ViewMode,
)

_client: OpenAI | None = None

CACHE_PATH = Path(__file__).resolve().parent.parent / ".cache" / "planner.json"
_cache: dict[str, dict[str, Any]] = {}
_cache_lock = threading.Lock()
_cache_loaded = False


def _load_cache() -> None:
    """Кеш разобранных реплик. Бюджет на API ограничен, а на отладке и на демо
    одни и те же вопросы задаются десятки раз — платить за них повторно
    незачем. Ключ включает отпечаток промпта и описание сессии: поменялось
    что-то из этого — кеш мимо.

    Загрузка ленивая: привязка к старту сервера оставляла кеш пустым во всех
    остальных точках входа — скриптах, тестах, замерах.
    """
    global _cache_loaded
    if _cache_loaded:
        return
    _cache_loaded = True
    if CACHE_PATH.exists():
        try:
            _cache.update(json.loads(CACHE_PATH.read_text()))
        except (json.JSONDecodeError, OSError):
            pass


def _save_cache() -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(_cache, ensure_ascii=False, indent=1))


def _cache_key(question: str, system: str, context: str) -> str:
    fingerprint = hashlib.sha256(
        f"{settings.openai_model}\n{system}\n{context}\n{question.strip().casefold()}".encode()
    )
    return fingerprint.hexdigest()[:32]


def cache_size() -> int:
    _load_cache()
    return len(_cache)


def _openai() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


CALC_FIELDS = [m.value for m in Metric]


class Interpretation(BaseModel):
    """Плоское зеркало всех намерений: строгий режим OpenAI не любит вложенные
    необязательные объекты, а плоскую структуру модели заполняют надёжнее.
    """

    intent: Intent

    needs_clarification: bool
    clarification_question: str | None
    clarification_reason: str | None

    dimensions: list[Dimension]
    metrics: list[Metric]
    period: RelativePeriod
    filters: list[Filter]
    order_by: Metric | None
    order: SortOrder
    limit: int | None

    calc_kind: StepKind | None
    calc_source: list[Metric]
    calc_expression: str | None
    calc_title: str | None

    set_primary: Dimension | None
    set_period_grain: PeriodGrain | None
    set_metric: Metric | None
    set_mode: ViewMode | None

    panel: int | None
    sort_field: str | None

    target_title: str | None
    new_title: str | None

    def to_spec(self) -> QuerySpec:
        return QuerySpec(
            dimensions=self.dimensions[:3],
            metrics=self.metrics[:6] or [Metric.FACT_AMOUNT],
            period=Period(relative=self.period),
            filters=self.filters,
            order_by=self.order_by,
            order=self.order,
            limit=self.limit,
        )

    def to_step(self) -> CalcStep:
        kind = self.calc_kind or StepKind.ARITHMETIC
        source = [m.value for m in self.calc_source]
        step = CalcStep(
            id=uuid.uuid4().hex[:8],
            title=self.calc_title or "",
            kind=kind,
            field=f"calc_{uuid.uuid4().hex[:6]}",
            source=source,
            expression=self.calc_expression,
        )
        from app.calculations import DEFAULT_SOURCES, STEP_UNITS, normalize_source, step_title

        if not step.source:
            step.source = list(DEFAULT_SOURCES.get(kind, []))
        step.source = normalize_source(kind, step.source)
        step.unit = STEP_UNITS[kind]
        step.title = step.title or step_title(step)
        return step

    def clarification(self) -> Clarification:
        return Clarification(
            question=self.clarification_question or "Уточните, пожалуйста, запрос.",
            reason=self.clarification_reason or "",
        )


def _nullable_enum(values: list[str]) -> dict[str, Any]:
    return {"type": ["string", "null"], "enum": [*values, None]}


def _schema() -> dict[str, Any]:
    dimensions = [d.value for d in Dimension]
    metrics = [m.value for m in Metric]
    properties: dict[str, Any] = {
        "intent": {"type": "string", "enum": [i.value for i in Intent]},
        "needs_clarification": {"type": "boolean"},
        "clarification_question": {"type": ["string", "null"]},
        "clarification_reason": {"type": ["string", "null"]},
        "dimensions": {"type": "array", "items": {"type": "string", "enum": dimensions}},
        "metrics": {"type": "array", "items": {"type": "string", "enum": metrics}},
        "period": {"type": "string", "enum": [p.value for p in RelativePeriod]},
        "filters": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["dimension", "values"],
                "properties": {
                    "dimension": {"type": "string", "enum": dimensions},
                    "values": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "order_by": _nullable_enum(metrics),
        "order": {"type": "string", "enum": [o.value for o in SortOrder]},
        "limit": {"type": ["integer", "null"]},
        "calc_kind": _nullable_enum([k.value for k in StepKind]),
        "calc_source": {"type": "array", "items": {"type": "string", "enum": metrics}},
        "calc_expression": {"type": ["string", "null"]},
        "calc_title": {"type": ["string", "null"]},
        "set_primary": _nullable_enum(dimensions),
        "set_period_grain": _nullable_enum([g.value for g in PeriodGrain]),
        "set_metric": _nullable_enum(metrics),
        "set_mode": _nullable_enum([m.value for m in ViewMode]),
        "panel": {"type": ["integer", "null"]},
        "sort_field": {"type": ["string", "null"]},
        "target_title": {"type": ["string", "null"]},
        "new_title": {"type": ["string", "null"]},
    }
    return {
        "name": "chat_intent",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": list(properties),
            "properties": properties,
        },
    }


def _system_prompt(horizon: date) -> str:
    dimensions = "\n".join(f"- {d.value} — {label}" for d, label in DIMENSION_LABELS.items())
    metrics = "\n".join(f"- {m.value} — {label}" for m, label in METRIC_LABELS.items())
    steps = "\n".join(f"- {k.value} — {label}" for k, label in STEP_LABELS.items())
    vocab = "\n".join(
        f"{d.value}: {', '.join(values)}" for d, values in vocabulary.for_prompt().items()
    )

    return f"""Ты разбираешь реплику руководителя в чате аналитики продаж и превращаешь её в структурированную команду.

Данные: продажи FMCG-дистрибьютора по торговым точкам, с планом и фактом.
Факт заканчивается {horizon:%m.%Y}. Относительные периоды считаются от этой даты, не от сегодняшней.

НАМЕРЕНИЯ (intent) — выбери ровно одно:
- new_query — новый аналитический вопрос, не связанный с текущим дашбордом.
- refine — нужны ДРУГИЕ данные из базы: другой диапазон дат («а за 2025 год»),
  другие метрики («добавь количество сделок»), другой набор разрезов.
- filter — «покажи только Центральный регион», «убери фильтры». Меняет фильтры, не выборку.
- toggle — меняется ПРЕДСТАВЛЕНИЕ уже построенного, данные те же:
  «по кварталам» / «по годам» / «по месяцам» → set_period_grain;
  «переключи на точки» / «разбей по категориям» → set_primary;
  «метрику на скидки» → set_metric; «покажи в процентах» / «в динамике» → set_mode.
  Смена зерна времени — это ВСЕГДА toggle, а не refine: из базы ничего нового не нужно.
- calculate — добавить колонку вычисления.
- undo — «отмени», «верни как было», «убери последнее вычисление».
- show_table — «покажи таблицу», «покажи данные».
- chart — перестроить график: «отсортируй третий график по проценту выполнения».
- explain — «что здесь главное», «объясни», «дай выводы».
- save — «сохрани дашборд», «сохрани как "Продажи Q3"».
- list_saved — «покажи мои дашборды».
- open_saved — «открой дашборд "Продажи Q3"».
- rename — «переименуй дашборд».
- copy — «сделай копию».
- delete — «удали дашборд "Старый отчёт"».

РАЗРЕЗЫ (dimensions), не больше 3, первый — главная ось:
{dimensions}

МЕТРИКИ (metrics), не больше 6:
{metrics}

ПЕРИОД (period): last_month, last_quarter, last_year, year_to_date, all_time

ТИПЫ ВЫЧИСЛЕНИЙ (calc_kind):
{steps}

ДОПУСТИМЫЕ ЗНАЧЕНИЯ ФИЛЬТРОВ (торговых точек в списке нет — для них пиши как сказал пользователь):
{vocab}

ПРАВИЛА:
1. Выбирай МИНИМАЛЬНЫЙ достаточный набор метрик.
   «План-факт», «выполнение плана», «сравни план и факт» — ровно plan_amount и fact_amount.
   «Структура», «динамика», «сколько продали», «объём» — только fact_amount.
   «Сколько сделок» — только sales_count. Не добавляй метрики на всякий случай.
2. Для вопросов про динамику первым разрезом ставь month, quarter или year.
3. Разрез и фильтр — разные вещи. «Напитки в Центральном регионе» — это два фильтра
   и пустые dimensions, а не разрезы по категории и региону.
4. Вопрос про одно число без разбивки — пустой dimensions.
5. «ТОП-N» — задай order_by по главной метрике, order=desc и limit=N.
6. Для calculate: «процент выполнения плана» — completion; «отклонение» — deviation;
   «доля» — share; «динамика к прошлому месяцу» — growth; «накопительный итог» — cumulative;
   «место в рейтинге» — rank. Если формула не сводится к этим типам, бери arithmetic и
   напиши calc_expression через имена метрик латиницей, например
   (fact_amount - plan_amount) / plan_amount * 100
   Разрез по периоду для growth и cumulative добавит код сам — не делай из этого refine.
7. Для toggle заполняй только те set_* поля, которые пользователь действительно поменял.
8. Для chart укажи panel (1 — план-факт по периодам, 2 — структура, 3 — ТОП, 4 — динамика
   выполнения) и sort_field, если просят сортировку.
9. needs_clarification=true только если догадка меняет ответ по существу.
   Период не указан — это не повод уточнять, бери all_time.
   Названия нет в списке допустимых значений — вот это повод уточнить.
10. Если уточнение не нужно, clarification_question и clarification_reason оставь null.
    Незаполненные поля других намерений оставляй null или пустым массивом."""


def interpret(question: str, horizon: date, context: str = "") -> Interpretation:
    _load_cache()
    system = _system_prompt(horizon)
    key = _cache_key(question, system, context)

    with _cache_lock:
        hit = _cache.get(key)
    if hit is not None:
        return Interpretation.model_validate(hit["payload"])

    user = question if not context else f"Текущее состояние:\n{context}\n\nРеплика: {question}"
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    for attempt in range(2):
        response = _openai().chat.completions.create(
            model=settings.openai_model,
            response_format={"type": "json_schema", "json_schema": _schema()},
            messages=messages,
        )
        raw = response.choices[0].message.content or "{}"
        try:
            output = Interpretation.model_validate_json(raw)
        except (json.JSONDecodeError, ValidationError) as error:
            if attempt == 1:
                raise
            messages += [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"Ответ не прошёл проверку: {error}. Исправь."},
            ]
            continue

        _remember(key, output.model_dump(mode="json"))
        return output

    raise RuntimeError("недостижимо")


def _remember(key: str, payload: dict[str, Any]) -> None:
    with _cache_lock:
        _cache[key] = {"payload": payload}
        _save_cache()


def resolve_filters(filters: list[Filter]) -> tuple[list[Filter], list[str]]:
    """Приводит значения фильтров к тем, что есть в базе. Нераспознанное
    выбрасывает и возвращает примечания — молчаливый пустой график хуже.
    """
    notes: list[str] = []
    kept: list[Filter] = []
    for flt in filters:
        resolved: list[str] = []
        unknown: list[str] = []
        for value in flt.values:
            match = vocabulary.resolve(flt.dimension, value)
            (resolved if match else unknown).append(match or value)
        if unknown:
            label = DIMENSION_LABELS[flt.dimension]
            notes.append(f"Не нашёл в данных: {label} — {', '.join(unknown)}. Фильтр не применён.")
        if resolved:
            flt.values = resolved
            kept.append(flt)
    return kept, notes
