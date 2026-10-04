# Puzzle RPA — чат-бот с интерактивной визуализацией данных

Пользователь пишет аналитический вопрос на русском — получает в чате живой дашборд: KPI-карточки, фильтры с поиском, переключатели разрезов и связанные графики. Дашборд дорабатывается диалогом, сохраняется и восстанавливается.

Хакатон-кейс компании Puzzle RPA (ООО «ПУСК»). Требования — [`docs/CASE.md`](docs/CASE.md).

## Быстрый старт

```bash
cp .env.example .env     # при необходимости вписать OPENAI_API_KEY
# положить CSV датасета в db/seed/ — см. db/seed/README.md
docker compose up -d     # Postgres на порту 5433
```

Данных в репозитории нет: это датасет заказчика, его нужно скачать отдельно и положить в `db/seed/` **до первого запуска**. Первый запуск создаёт схему, загружает 331 тысячу строк, строит вьюхи и заводит роли. Готовность:

```bash
docker compose ps        # ожидаем healthy
docker exec -e PGPASSWORD=bi_reader puzzle-db \
  psql -U bi_reader -d puzzle -c "SELECT count(*) FROM plan_fact_flat;"
```

Пересоздать базу с нуля: `docker compose down -v && docker compose up -d`.

### Приложение

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/uvicorn app.main:app --port 8000          # API
.venv/bin/python scripts/warm_cache.py              # прогрев кеша демо-вопросами

cd ../web && npm install && npm run dev             # http://localhost:5173
```

В `.env` нужен `OPENAI_API_KEY`. Тесты бэкенда — `backend/.venv/bin/pytest`.

## Структура

| Путь | Что |
|---|---|
| `CLAUDE.md` | Проект, стек, порядок сборки, правила работы |
| `docs/CASE.md` | Требования кейса — источник истины |
| `docs/DATA.md` | Датасет: схема, объёмы, три ловушки |
| `docs/ARCHITECTURE.md`, `docs/adr/` | Схема и решения с обоснованиями |
| `db/` | Схема, загрузка, вьюхи, роли, исходные CSV |
| `backend/` | API, разбор запросов, сборщик SQL, графики |
| `web/` | Веб-клиент: чат, график, таблица |
| `Zura/` | iOS-клиент (в работе) |

## Данные

Продажи FMCG-дистрибьютора за 2023–2026: 8 регионов, 300 торговых точек, 42 продукта, 180 клиентов, 179 тысяч продаж, 122 тысячи строк плана. План 4 082 млн ₽, факт 3 377 млн ₽.
