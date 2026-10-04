"""Прогрев кеша планировщика демо-вопросами.

Бюджет на OpenAI ограничен, а демо-сценарий прогоняется много раз. После
прогрева все вопросы ниже отвечают из кеша: ноль запросов к API и мгновенный
отклик. Запускать после изменения системного промпта — ключ кеша включает его
отпечаток, поэтому старые записи становятся недостижимы.

    backend/.venv/bin/python backend/scripts/warm_cache.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db, planner, vocabulary  # noqa: E402
from app.config import settings  # noqa: E402
from app.schema import Clarification  # noqa: E402

QUESTIONS = [
    # Из приложения к кейсу — данные и визуализация
    "Покажи план-факт продаж по регионам за последний квартал",
    "Собери дашборд по продажам: динамика, структура, ТОП точек, выполнение плана",
    "Сравни продажи по торговым точкам за год, выдели отстающих",
    "Покажи структуру продаж по продуктам за последний месяц",
    # Разрезы, которые спросят на защите
    "Покажи план-факт продаж по регионам и торговым точкам за последний год",
    "Динамика продаж по месяцам за последний год",
    "Структура продаж по категориям за последний месяц",
    "Сравни план и факт по типам точек за всё время",
    "ТОП-10 торговых точек по объёму продаж за последний квартал",
    "Покажи выполнение плана по регионам и месяцам за последний год",
    "Сколько сделок прошло по категориям в прошлом месяце",
    "Сколько мы продали напитков в Центральном регионе в этом году",
    "Покажи продажи по городам за последний квартал",
    "Какие категории не выполнили план за последний год",
    "Покажи динамику по кварталам за всё время",
    # Проверка отказа и уточнения
    "Покажи продажи в Мухосранске",
]


def main() -> None:
    db.open_pool()
    vocabulary.load()
    horizon = db.fact_horizon()

    print(f"модель {settings.openai_model}, в кеше было {planner.cache_size()} записей\n")
    asked = 0
    started = time.time()
    for question in QUESTIONS:
        before = planner.cache_size()
        moment = time.time()
        try:
            result = planner.plan(question, horizon)
        except Exception as error:  # noqa: BLE001
            print(f"  ✗ {question[:58]:<58} {str(error)[:50]}")
            continue
        fresh = planner.cache_size() > before
        asked += fresh
        kind = "уточнение" if isinstance(result, Clarification) else "выборка"
        mark = "+" if fresh else "="
        print(f"  {mark} {question[:58]:<58} {kind:<10} {time.time() - moment:.1f}с")

    print(
        f"\nзапросов к API: {asked} из {len(QUESTIONS)}, "
        f"в кеше теперь {planner.cache_size()}, всего {time.time() - started:.0f}с"
    )
    db.close_pool()


if __name__ == "__main__":
    main()
