"""Поиск сохранённых дашбордов: сценарий кейса «забыл название, помню про
что было». Человек говорит не той формой слова, что в запросе."""

from app.store import matches


def test_search_finds_another_word_form():
    assert matches("скидки", "Какие скидки делались клиенту и почему")
    assert matches("скидки", "Динамика скидок по месяцам")
    assert matches("про скидки", "Структура по скидкам")


def test_search_needs_every_meaningful_word():
    assert not matches("скидки Центральный", "Динамика скидок по месяцам")
    assert matches("скидки центральный", "Скидки в Центральном регионе")


def test_search_ignores_the_words_that_name_the_search_itself():
    assert matches("дашборд про скидки", "Скидки по клиентам")


def test_search_does_not_match_unrelated():
    assert not matches("скидки", "План-факт по регионам за последний квартал")
