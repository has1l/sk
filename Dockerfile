# Публичный прототип одним контейнером: FastAPI отдаёт и API, и собранный веб.
# База — отдельный сервис (Railway Postgres), ключ и пароли — переменные окружения.

FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY backend/pyproject.toml ./
COPY backend/app ./app
COPY backend/scripts ./scripts
RUN pip install --no-cache-dir .
COPY --from=web /web/dist /app/web
ENV WEB_DIST=/app/web
RUN useradd --create-home klodik && chown -R klodik /app
USER klodik
# --proxy-headers: за прокси Railway лимит реплик должен видеть адрес человека,
# а не прокси — иначе все посетители делят одну минутную квоту.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
