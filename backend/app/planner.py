"""Вопрос на русском → спецификация выборки.

Единственное место, где участвует модель. Она не пишет SQL и не выбирает тип
графика — только переводит язык в структуру из закрытого списка (ADR-0004).

Форма ответа задана строгой JSON-схемой на стороне OpenAI, а не примером в
промпте. Это принципиально: без схемы модели возвращают фильтр в своей форме
и ломают разбор, причём слабые модели чаще — и выглядит это как будто они хуже
понимают аналитику, хотя они просто не угадали форму.

Схема плоская и генерируется из перечислений, чтобы не расходиться с ними.
"""

import hashlib
import json
import threading
from datetime import date
from pathlib import Path
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from app import vocabulary
from app.config import settings
from app.labels import DIMENSION_LABELS, METRIC_LABELS
from app.schema import (
    Clarification,
    Dimension,
    Filter,
    Metric,
    Period,
    QuerySpec,
    RelativePeriod,
    SortOrder,
)

_client: OpenAI | None = None

CACHE_PATH = Path(__file__).resolve().parent.parent / ".cache" / "planner.json"
_cache: dict[str, dict[str, Any]] = {}
_cache_lock = threading.Lock()


_cache_loaded = False


def _load_cache() -> None:
    """Кеш разобранных вопросов. Бюджет на API ограничен, а на отладке и на
    демо одни и те же вопросы задаются десятки раз — платить за них повторно
    незачем. Ключ включает отпечаток промпта: поменялся промпт — кеш мимо.

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


def _cache_key(question: str, system: str) -> str:
    fingerprint = hashlib.sha256(
        f"{settings.openai_model}\n{system}\n{question.strip().casefold()}".encode()
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


class PlannerOutput(BaseModel):
    """Плоское зеркало QuerySpec: строгий режим OpenAI не любит вложенные
    необязательные объекты, а плоскую структуру модели заполняют надёжнее.
    """

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

    def to_spec(self) -> QuerySpec:
        return QuerySpec(
            dimensions=self.dimensions[:3],
            metrics=self.metrics[:5] or [Metric.FACT_AMOUNT],
            period=Period(relative=self.period),
            filters=self.filters,
            order_by=self.order_by,
            order=self.order,
            limit=self.limit,
        )


def _schema() -> dict[str, Any]:
    dimensions = [d.value for d in Dimension]
    metrics = [m.value for m in Metric]
    return {
        "name": "query_plan",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "needs_clarification",
                "clarification_question",
                "clarification_reason",
                "dimensions",
                "metrics",
                "period",
                "filters",
                "order_by",
                "order",
                "limit",
            ],
            "properties": {
                "needs_clarification": {"type": "boolean"},
                "clarification_question": {"type": ["string", "null"]},
                "clarification_reason": {"type": ["string", "null"]},
                "dimensions": {
                    "type": "array",
                    "items": {"type": "string", "enum": dimensions},
                },
                "metrics": {
                    "type": "array",
                    "items": {"type": "string", "enum": metrics},
                },
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
                "order_by": {"type": ["string", "null"], "enum": [*metrics, None]},
                "order": {"type": "string", "enum": ["asc", "desc"]},
                "limit": {"type": ["integer", "null"]},
            },
        },
    }


def _system_prompt(horizon: date) -> str:
    dimensions = "\n".join(f"- {d.value} — {label}" for d, label in DIMENSION_LABELS.items())
    metrics = "\n".join(f"- {m.value} — {label}" for m, label in METRIC_LABELS.items())
    vocab = "\n".join(
        f"{d.value}: {', '.join(values)}" for d, values in vocabulary.for_prompt().items()
    )

    return f"""Ты переводишь вопрос руководителя про продажи в структурированный заказ выборки.

Данные: продажи FMCG-дистрибьютора по торговым точкам, с планом и фактом.
Факт заканчивается {horizon:%m.%Y}. Относительные периоды считаются от этой даты, не от сегодняшней.

РАЗРЕЗЫ (dimensions), не больше 3, первый — главная ось графика:
{dimensions}

МЕТРИКИ (metrics), не больше 5:
{metrics}

ПЕРИОД (period): last_month, last_quarter, last_year, year_to_date, all_time

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
6. needs_clarification=true только если догадка меняет ответ по существу.
   Период не указан — это не повод уточнять, бери all_time.
   Названия нет в списке допустимых значений — вот это повод уточнить.
7. Если уточнение не нужно, clarification_question и clarification_reason оставь null."""


def plan(question: str, horizon: date) -> QuerySpec | Clarification:
    _load_cache()
    system = _system_prompt(horizon)
    key = _cache_key(question, system)

    with _cache_lock:
        hit = _cache.get(key)
    if hit is not None:
        if hit["kind"] == "clarification":
            return Clarification.model_validate(hit["payload"])
        return QuerySpec.model_validate(hit["payload"])

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]

    for attempt in range(2):
        response = _openai().chat.completions.create(
            model=settings.openai_model,
            response_format={"type": "json_schema", "json_schema": _schema()},
            messages=messages,
        )
        raw = response.choices[0].message.content or "{}"
        try:
            output = PlannerOutput.model_validate_json(raw)
        except (json.JSONDecodeError, ValidationError) as error:
            if attempt == 1:
                raise
            messages += [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"Ответ не прошёл проверку: {error}. Исправь."},
            ]
            continue

        if output.needs_clarification and output.clarification_question:
            clarification = Clarification(
                question=output.clarification_question,
                reason=output.clarification_reason or "",
            )
            _remember(key, "clarification", clarification.model_dump())
            return clarification

        spec = output.to_spec()
        _remember(key, "spec", spec.model_dump(mode="json"))
        return spec

    raise RuntimeError("недостижимо")


def _remember(key: str, kind: str, payload: dict[str, Any]) -> None:
    with _cache_lock:
        _cache[key] = {"kind": kind, "payload": payload}
        _save_cache()


def resolve_filters(spec: QuerySpec) -> list[str]:
    """Приводит значения фильтров к тем, что есть в базе. Нераспознанное
    выбрасывает и возвращает примечания — молчаливый пустой график хуже.
    """
    notes: list[str] = []
    kept: list[Filter] = []
    for flt in spec.filters:
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
    spec.filters = kept
    return notes
