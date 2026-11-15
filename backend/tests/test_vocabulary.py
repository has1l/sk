"""Подбор значения фильтра по словам человека.

Названия точек в базе выглядят как «Гипермаркет «Лидер», Краснодар,
ул. Набережная, 53». Человек говорит «гипермаркет Лидер». Целиком такая
строка не совпадёт никогда — отсюда поиск по словам, и отсюда же риск
нахватать лишнего, за которым и следят эти тесты.
"""

import pytest

from app import vocabulary
from app.schema import Dimension

OUTLETS = [
    "Гипермаркет «Лидер», Краснодар, ул. Набережная, 53",
    "Магазин у дома «Лидер», Казань, ул. Набережная, 29",
    "Магазин у дома «Лидер», Москва, пр-т Мира, 113",
    "Гипермаркет «Атлас», Москва, ул. Ленина, 32",
    "Гипермаркет «Меридиан», Чебоксары, ул. Заводская, 84",
]


@pytest.fixture(autouse=True)
def vocabulary_loaded():
    saved = dict(vocabulary._values)
    vocabulary._values[Dimension.OUTLET] = list(OUTLETS)
    vocabulary._values[Dimension.CATEGORY] = ["Напитки", "Молочная продукция"]
    yield
    vocabulary._values.clear()
    vocabulary._values.update(saved)


def test_type_plus_name_narrows_to_one_outlet():
    """«гипермаркет Лидер» — это одна точка, а не весь тип точек.

    Главный случай: совпадать должны все слова сразу, иначе «Лидер» утащит
    за собой магазины у дома, которых человек не просил.
    """
    found = vocabulary.match(Dimension.OUTLET, "гипермаркет Лидер")
    assert found == ["Гипермаркет «Лидер», Краснодар, ул. Набережная, 53"]


def test_bare_chain_name_keeps_every_outlet_of_the_chain():
    """«Лидер» без уточнений — вся сеть. Это осмысленный фильтр, а не ошибка."""
    found = vocabulary.match(Dimension.OUTLET, "Лидер")
    assert len(found) == 3


def test_russian_case_endings_do_not_break_the_search():
    """В базе «Москва», человек говорит «в Москве»."""
    found = vocabulary.match(Dimension.OUTLET, "Атлас в Москве")
    assert found == ["Гипермаркет «Атлас», Москва, ул. Ленина, 32"]


def test_words_naming_the_entity_are_ignored():
    """«точка Меридиан» — слова «точка» в названии нет, и требовать его нельзя."""
    found = vocabulary.match(Dimension.OUTLET, "торговую точку Меридиан")
    assert found == ["Гипермаркет «Меридиан», Чебоксары, ул. Заводская, 84"]


def test_unknown_value_matches_nothing():
    assert vocabulary.match(Dimension.OUTLET, "Пятёрочка") == []


def test_too_many_matches_is_treated_as_no_match():
    """Слово, под которое подходит пол-базы, фильтром быть не может.

    Иначе «магазин» отфильтровал бы 200 точек, и пользователь увидел бы
    осмысленный с виду, но случайный срез.
    """
    vocabulary._values[Dimension.OUTLET] = [f"Магазин {i}" for i in range(vocabulary.MAX_MATCHES + 1)]
    assert vocabulary.match(Dimension.OUTLET, "Магазин") == []


def test_short_form_finds_the_full_category():
    assert vocabulary.match(Dimension.CATEGORY, "молочка") == ["Молочная продукция"]


def test_exact_value_wins_over_word_search():
    """Точное совпадение не должно тащить за собой однокоренные."""
    assert vocabulary.match(Dimension.CATEGORY, "Напитки") == ["Напитки"]
