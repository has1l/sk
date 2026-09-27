#!/bin/bash
set -e

# bi_reader — под ним исполняется всё, что построено из запроса пользователя.
# Права только на чтение, транзакции только на чтение, жёсткий таймаут.
# Это граница безопасности (ADR-0004), а не просьба к модели вести себя хорошо.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE ROLE bi_reader LOGIN PASSWORD '${BI_READER_PASSWORD}';
    GRANT CONNECT ON DATABASE "$POSTGRES_DB" TO bi_reader;
    GRANT USAGE ON SCHEMA public TO bi_reader;
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO bi_reader;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO bi_reader;
    ALTER ROLE bi_reader SET statement_timeout = '10s';
    ALTER ROLE bi_reader SET default_transaction_read_only = on;
    REVOKE CREATE ON SCHEMA public FROM bi_reader;
    REVOKE ALL ON SCHEMA app FROM bi_reader;

    -- app — сохранённые дашборды. Читает данные, пишет только в свою схему.
    CREATE ROLE app LOGIN PASSWORD '${APP_PASSWORD}';
    GRANT CONNECT ON DATABASE "$POSTGRES_DB" TO app;
    GRANT USAGE ON SCHEMA public TO app;
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO app;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO app;
    ALTER SCHEMA app OWNER TO app;
EOSQL
