"""Прогрев кеша планировщика демо-вопросами.

Запускать после любой правки системного промпта: ключ кеша включает его
отпечаток, поэтому правка обнуляет кеш целиком, и на демо каждый вопрос
будет оплачен заново.

Прогреваются только реплики, которые начинают разговор, — у них пустой
контекст сессии, и ключ предсказуем. Реплики внутри диалога зависят от
состояния и прогреву не поддаются.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db, planner, templates, vocabulary  # noqa: E402

EXTRA = [
    "Покажи выполнение плана по регионам",
    "Какие точки не выполняют план?",
    "Сравни категории по объёму продаж",
    "Сколько сделок было в последнем квартале?",
    "Покажи продажи напитков по регионам",
    "ТОП-5 продуктов по выручке за последний год",
]


def main() -> None:
    db.open_pool()
    vocabulary.load()
    horizon = db.fact_horizon()

    questions = [t.question for t in templates.all() if t.group in ("Дашборды", "Выводы")]
    questions += EXTRA

    before = planner.cache_size()
    started = time.time()
    for question in questions:
        mark = "="
        try:
            size = planner.cache_size()
            planner.interpret(question, horizon)
            mark = "+" if planner.cache_size() > size else "="
        except Exception as error:  # noqa: BLE001
            mark = "!"
            print(f"  {error}")
        print(f"{mark} {question}")

    print(
        f"\nбыло {before}, стало {planner.cache_size()}, "
        f"вопросов {len(questions)}, {time.time() - started:.1f}с"
    )
    db.close_pool()


if __name__ == "__main__":
    main()
