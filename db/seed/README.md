# Исходные данные

Здесь должны лежать восемь CSV тестового датасета кейса. **В репозиторий они не входят** — это данные заказчика, выданные участникам, и публиковать их мы не стали.

Скачать: https://nc.puzzle-rpa.ru/s/gZaaDqjx2rcyfP4 — распаковать так, чтобы рядом с этим файлом оказались:

```
clients.csv  contracts.csv  discounts.csv  outlets.csv
products.csv  regions.csv  sales.csv  sales_plan.csv
```

Файлы нужны **до первого** `docker compose up`: база загружает их при инициализации. Если их нет, контейнер упадёт на `COPY ... could not open file "/seed/regions.csv"`.

Данные уже залиты в базу? Эти файлы больше не нужны — повторная инициализация происходит только после `docker compose down -v`.
