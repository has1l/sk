"""Сохранённые дашборды. Единственный модуль, который пишет в базу.

Хранится рецепт, а не данные: заказ выборки, стек вычислений, состояние
фильтров и переключателей, конфиг панелей (ADR-0001). Поэтому строка в базе
весит килобайты, а открытие пересобирает таблицу на актуальных данных.

Перед каждой перезаписью предыдущее состояние уезжает в dashboard_versions —
отсюда история версий и откат.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from app import db
from app.schema import SavedDashboard, SavedVersion


def save_new(title: str, question: str, state: dict[str, Any]) -> str:
    dashboard_id = str(uuid.uuid4())
    db.app_query(
        """
        INSERT INTO app.dashboards (dashboard_id, title, question, state, version)
        VALUES (%s, %s, %s, %s, 1)
        """,
        [dashboard_id, title, question, json.dumps(state, ensure_ascii=False)],
    )
    return dashboard_id


def update(dashboard_id: str, title: str, question: str, state: dict[str, Any]) -> int:
    """Перезапись с откладыванием предыдущей версии в историю."""
    rows = db.app_query(
        "SELECT title, state, version FROM app.dashboards WHERE dashboard_id = %s",
        [dashboard_id],
    )
    if not rows:
        raise KeyError(dashboard_id)
    previous = rows[0]

    db.app_query(
        """
        INSERT INTO app.dashboard_versions (dashboard_id, version, title, state, note)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (dashboard_id, version) DO NOTHING
        """,
        [
            dashboard_id,
            previous["version"],
            previous["title"],
            json.dumps(previous["state"], ensure_ascii=False),
            "состояние до перезаписи",
        ],
    )
    version = previous["version"] + 1
    db.app_query(
        """
        UPDATE app.dashboards
           SET title = %s, question = %s, state = %s, version = %s, updated_at = now()
         WHERE dashboard_id = %s
        """,
        [title, question, json.dumps(state, ensure_ascii=False), version, dashboard_id],
    )
    return version


def rename(dashboard_id: str, title: str) -> None:
    db.app_query(
        "UPDATE app.dashboards SET title = %s, updated_at = now() WHERE dashboard_id = %s",
        [title, dashboard_id],
    )


def copy(dashboard_id: str, title: str | None = None) -> str:
    rows = db.app_query(
        "SELECT title, question, state FROM app.dashboards WHERE dashboard_id = %s",
        [dashboard_id],
    )
    if not rows:
        raise KeyError(dashboard_id)
    source = rows[0]
    state = dict(source["state"])
    new_title = title or f"{source['title']} — копия"
    state["title"] = new_title
    return save_new(new_title, source["question"], state)


def delete(dashboard_id: str) -> None:
    db.app_query("DELETE FROM app.dashboards WHERE dashboard_id = %s", [dashboard_id])


def listing(query: str | None = None, sort: str = "updated") -> list[SavedDashboard]:
    """Список дашбордов. Поиск идёт и по названию, и по тексту запроса —
    кейс прямо описывает сценарий «забыл название, помню про что было»."""
    order = {
        "updated": "updated_at DESC",
        "created": "created_at DESC",
        "title": "lower(title) ASC",
    }.get(sort, "updated_at DESC")

    sql = """
        SELECT dashboard_id, title, question, version, created_at, updated_at
        FROM app.dashboards
    """
    sql += f" ORDER BY {order} LIMIT 200"

    items = [
        SavedDashboard(
            id=str(row["dashboard_id"]),
            title=row["title"],
            question=row["question"],
            version=row["version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in db.app_query(sql, [])
    ]
    if not query:
        return items
    return [item for item in items if matches(query, f"{item.title} {item.question}")]


# Слова, которыми человек называет сам поиск, а не его предмет: «найди
# дашборд про скидки». Требование совпасть всем словам иначе обнулило бы его.
_SEARCH_FILLER = {
    "про", "дашборд", "дашборда", "дашборды", "дашбордов", "отчёт", "отчет",
    "мой", "мои", "мою", "где", "был", "была", "было", "который", "которые",
}


def matches(query: str, text: str) -> bool:
    """Все слова запроса есть в тексте — целиком или без двух последних
    букв: «про скидки» находит «какие скидки делались» и «по скидкам».
    ILIKE по всей фразе здесь не годится — «скидки» не найдёт «скидок».
    """
    haystack = text.casefold()
    words = [
        w for w in re.split(r"\W+", query.casefold(), flags=re.UNICODE)
        if len(w) >= 3 and w not in _SEARCH_FILLER
    ]
    if not words:
        return True
    return all(w in haystack or (len(w) >= 5 and w[:-2] in haystack) for w in words)


def load(dashboard_id: str) -> tuple[str, dict[str, Any]]:
    rows = db.app_query(
        "SELECT title, state FROM app.dashboards WHERE dashboard_id = %s",
        [dashboard_id],
    )
    if not rows:
        raise KeyError(dashboard_id)
    return rows[0]["title"], dict(rows[0]["state"])


def find_by_title(title: str) -> SavedDashboard | None:
    """Открытие по названию: пользователь говорит «открой "Продажи Q3"»,
    а не идентификатор.
    """
    matches = listing(query=title)
    if not matches:
        return None
    exact = [m for m in matches if m.title.casefold() == title.casefold()]
    return exact[0] if exact else matches[0]


def versions(dashboard_id: str) -> list[SavedVersion]:
    rows = db.app_query(
        """
        SELECT version, title, note, created_at
        FROM app.dashboard_versions
        WHERE dashboard_id = %s
        ORDER BY version DESC
        """,
        [dashboard_id],
    )
    return [
        SavedVersion(
            version=row["version"],
            title=row["title"],
            note=row["note"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def load_version(dashboard_id: str, version: int) -> tuple[str, dict[str, Any]]:
    rows = db.app_query(
        "SELECT title, state FROM app.dashboard_versions WHERE dashboard_id = %s AND version = %s",
        [dashboard_id, version],
    )
    if not rows:
        raise KeyError(f"{dashboard_id}#{version}")
    return rows[0]["title"], dict(rows[0]["state"])
