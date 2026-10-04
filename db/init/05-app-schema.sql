-- Сохранённые дашборды. Единственное место, куда приложение пишет: роль app
-- владеет только этой схемой, к данным она ходит на чтение, как bi_reader.
--
-- В state лежит рецепт, а не данные: заказ выборки, стек вычислений, состояние
-- фильтров и переключателей, конфиг графиков. Открытие дашборда пересобирает
-- таблицу из базы заново (ADR-0001).

CREATE TABLE app.dashboards (
    dashboard_id uuid PRIMARY KEY,
    title        text NOT NULL,
    question     text NOT NULL,
    state        jsonb NOT NULL,
    version      int  NOT NULL DEFAULT 1,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX dashboards_updated_idx ON app.dashboards (updated_at DESC);
CREATE INDEX dashboards_title_idx   ON app.dashboards (lower(title));

-- История версий: каждое сохранение поверх существующего дашборда сначала
-- откладывает предыдущее состояние сюда, поэтому откат ничего не теряет.
CREATE TABLE app.dashboard_versions (
    version_id   bigserial PRIMARY KEY,
    dashboard_id uuid NOT NULL REFERENCES app.dashboards ON DELETE CASCADE,
    version      int  NOT NULL,
    title        text NOT NULL,
    state        jsonb NOT NULL,
    note         text NOT NULL DEFAULT '',
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (dashboard_id, version)
);

CREATE INDEX dashboard_versions_dash_idx ON app.dashboard_versions (dashboard_id, version DESC);

ALTER TABLE app.dashboards         OWNER TO app;
ALTER TABLE app.dashboard_versions OWNER TO app;
ALTER SEQUENCE app.dashboard_versions_version_id_seq OWNER TO app;
