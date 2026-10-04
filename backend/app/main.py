from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app import charting, db, planner, sql_builder, vocabulary
from app.config import settings
from app.labels import METRIC_UNITS, dimension_label, metric_label
from app.schema import (
    AskRequest,
    AskResponse,
    Clarification,
    Column,
    Dimension,
    Metric,
    QuerySpec,
    Table,
)


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


def _columns(spec: QuerySpec) -> list[Column]:
    columns = [
        Column(field=d.value, label=dimension_label(d), kind="dimension")
        for d in spec.dimensions
    ]
    columns += [
        Column(field=m.value, label=metric_label(m), kind="metric", unit=METRIC_UNITS[m])
        for m in spec.metrics
    ]
    return columns


def _serialise(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        clean: dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, date):
                clean[key] = value.isoformat()
            elif isinstance(value, Decimal):
                clean[key] = float(value)
            else:
                clean[key] = value
        out.append(clean)
    return out


def _millions(value: float) -> str:
    return f"{value / 1e6:,.0f}".replace(",", "\u00a0") + "\u00a0млн\u00a0₽"


def _percent(value: float) -> str:
    return f"{value:.1f}".replace(".", ",") + "%"


def _summary(spec: QuerySpec, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "По такому запросу данных не нашлось — попробуй расширить период или снять фильтры."

    tail = f"Нашёл {len(rows)} строк."
    if Metric.PLAN_AMOUNT in spec.metrics and Metric.FACT_AMOUNT in spec.metrics:
        plan = sum(float(r.get("plan_amount") or 0) for r in rows)
        fact = sum(float(r.get("fact_amount") or 0) for r in rows)
        done = _percent(fact / plan * 100) if plan else "—"
        return f"{tail} План {_millions(plan)}, факт {_millions(fact)}, выполнение {done}."
    if Metric.FACT_AMOUNT in spec.metrics:
        fact = sum(float(r.get("fact_amount") or 0) for r in rows)
        return f"{tail} Факт {_millions(fact)}."
    return tail


@app.get("/api/health")
def health() -> dict[str, Any]:
    horizon = db.fact_horizon()
    return {
        "status": "ok",
        "fact_horizon": horizon.isoformat(),
        "model": settings.openai_model,
        "openai_configured": settings.has_openai,
        "cached_questions": planner.cache_size(),
    }


@app.post("/api/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    if not settings.has_openai:
        raise HTTPException(503, "OPENAI_API_KEY не задан — понимание запросов недоступно")

    horizon = db.fact_horizon()
    try:
        planned = planner.plan(request.question, horizon)
    except Exception as error:
        raise HTTPException(502, f"не удалось разобрать запрос: {error}") from error

    if isinstance(planned, Clarification):
        return AskResponse(message=planned.question, clarification=planned)

    notes = planner.resolve_filters(planned)
    built = sql_builder.build(planned, horizon)
    notes += built.notes

    try:
        rows = db.select(built.sql, built.params)
    except Exception as error:
        raise HTTPException(502, f"запрос к базе не прошёл: {error}") from error

    table = Table(columns=_columns(planned), rows=_serialise(rows), row_count=len(rows))
    chart = charting.build(planned) if rows else None

    return AskResponse(
        message=_summary(planned, rows),
        spec=planned,
        table=table,
        chart=chart,
        notes=notes,
        sql=built.sql,
    )
