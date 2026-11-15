"""Справочники значений разрезов.

Нужны в двух местах. Первое — промпт: модель должна видеть, что регион
называется «Северо-Западный», а не «Северо-Запад». Второе — сверка: модель
всё равно возвращает «напитки» вместо «Напитки», и такой фильтр молча дал бы
пустой график. Поэтому любое значение перед попаданием в SQL сверяется здесь.

Точек 300 — в промпт они не влезают, поэтому ищутся по базе подстрокой.
"""

from app.db import select
import re

from app.schema import Dimension

COLUMNS: dict[Dimension, str] = {
    Dimension.REGION: "region_name",
    Dimension.OUTLET_TYPE: "outlet_type",
    Dimension.CATEGORY: "category",
    Dimension.CITY: "city",
    Dimension.PRODUCT: "product_name",
    Dimension.OUTLET: "outlet_name",
    Dimension.CLIENT: "client_name",
    Dimension.CLIENT_SEGMENT: "client_segment",
    Dimension.DISCOUNT_REASON: "discount_reason",
}

MAX_IN_PROMPT = 100

_values: dict[Dimension, list[str]] = {}


def load() -> None:
    _values.clear()
    for dimension, column in COLUMNS.items():
        source = "client_fact_flat" if dimension.is_fact_only else "plan_fact_flat"
        rows = select(
            f"SELECT DISTINCT {column} AS v FROM {source} ORDER BY v"  # noqa: S608
        )
        _values[dimension] = [r["v"] for r in rows]


def for_prompt() -> dict[Dimension, list[str]]:
    return {d: v for d, v in _values.items() if len(v) <= MAX_IN_PROMPT}


# Названия точек в базе выглядят как «Гипермаркет «Лидер», Краснодар,
# ул. Набережная, 53». Пользователь говорит «гипермаркет Лидер», и целиком
# такая строка не найдётся никогда — поэтому ищем по словам.
MAX_MATCHES = 30
MIN_TOKEN = 3

# Слова, которыми человек называет сущность, а не её имя: «точка Меридиан»,
# «торговую точку Атлас». В названиях они не встречаются и, если требовать
# совпадения всех слов, обнуляют поиск. «Магазин» сюда не входит намеренно —
# он часть реальных названий («Магазин у дома «Лидер»»).
FILLER = {
    "точка", "точку", "точке", "точки", "торговая", "торговую", "торговой", "сеть", "сети",
    "клиент", "клиента", "клиенту", "клиентом", "компания", "компании",
}


def match(dimension: Dimension, value: str) -> list[str]:
    """Все значения базы, которые человек мог иметь в виду.

    Возвращается список, а не одно значение: «Лидер» — это торговая сеть из
    21 точки, и отфильтровать по ней осмысленно. Раньше такой запрос молча
    отбрасывался, потому что совпадение было не единственным.
    """
    known = _values.get(dimension)
    if not known:
        return []
    if value in known:
        return [value]

    folded = value.casefold().strip()
    exact = [c for c in known if c.casefold() == folded]
    if exact:
        return exact

    tokens = [
        t
        for t in re.split(r"\W+", folded, flags=re.UNICODE)
        if len(t) >= MIN_TOKEN and t not in FILLER
    ]
    if not tokens:
        return []
    hits = [c for c in known if all(_token_in(token, c.casefold()) for token in tokens)]
    return hits if len(hits) <= MAX_MATCHES else []


def _token_in(token: str, candidate: str) -> bool:
    """Слово целиком, иначе — без двух последних букв.

    В базе «Москва», человек говорит «в Москве». Полноценная морфология
    русского здесь не нужна: обрубок «москв» ловит все падежи, а требование
    совпасть всем словам сразу не даёт обрубкам нахватать лишнего.
    """
    if token in candidate:
        return True
    return len(token) >= MIN_TOKEN + 2 and token[:-2] in candidate


def resolve(dimension: Dimension, value: str) -> str | None:
    found = match(dimension, value)
    return found[0] if len(found) == 1 else None
