"""Шаблоны частых запросов.

Взяты из раздела «Примеры запросов для демо» кейса — это ровно то, что
заказчик будет пробовать на защите. Статический список: подбирать шаблоны
моделью значило бы платить за подсказки.
"""

from app.schema import QueryTemplate

TEMPLATES: list[QueryTemplate] = [
    QueryTemplate(group="Дашборды", question="Собери дашборд по продажам: план-факт по регионам за последний год"),
    QueryTemplate(group="Дашборды", question="Покажи план-факт продаж по регионам за последний квартал"),
    QueryTemplate(group="Дашборды", question="Динамика продаж по месяцам за последний год"),
    QueryTemplate(group="Дашборды", question="Структура продаж по категориям за последний месяц"),
    QueryTemplate(group="Дашборды", question="ТОП-10 торговых точек по объёму продаж"),
    QueryTemplate(group="Дашборды", question="Сравни выполнение плана по типам точек"),
    QueryTemplate(group="Вычисления", question="Добавь колонку с процентом выполнения плана"),
    QueryTemplate(group="Вычисления", question="Посчитай отклонение факта от плана"),
    QueryTemplate(group="Вычисления", question="Добавь долю каждого региона в общем объёме"),
    QueryTemplate(group="Вычисления", question="Добавь динамику к прошлому месяцу"),
    QueryTemplate(group="Вычисления", question="Посчитай накопительный итог продаж"),
    QueryTemplate(group="Вычисления", question="Отмени последнее вычисление"),
    QueryTemplate(group="Интерактив", question="Покажи только Центральный регион"),
    QueryTemplate(group="Интерактив", question="Переключи разрез на торговые точки"),
    QueryTemplate(group="Интерактив", question="Покажи по кварталам"),
    QueryTemplate(group="Интерактив", question="Отсортируй третий график по проценту выполнения"),
    QueryTemplate(group="Интерактив", question="Покажи таблицу с данными"),
    QueryTemplate(group="Сохранение", question="Сохрани дашборд"),
    QueryTemplate(group="Сохранение", question='Сохрани как "Продажи Q3"'),
    QueryTemplate(group="Сохранение", question="Покажи мои дашборды"),
    QueryTemplate(group="Сохранение", question="Сделай копию дашборда"),
    QueryTemplate(group="Выводы", question="Что здесь главное?"),
    QueryTemplate(group="Выводы", question="Какие регионы отстают от плана?"),
]


def all() -> list[QueryTemplate]:
    return TEMPLATES
