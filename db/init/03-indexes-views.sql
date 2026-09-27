-- Индексы под запросы дашборда: почти всё группируется по месяцу и режется
-- по региону, точке, продукту, категории.

CREATE INDEX sales_date_idx          ON sales (sale_date);
CREATE INDEX sales_outlet_prod_idx   ON sales (outlet_id, product_id, sale_date);
CREATE INDEX sales_client_idx        ON sales (client_id);
CREATE INDEX sales_contract_idx      ON sales (contract_id);

CREATE UNIQUE INDEX plan_grain_idx   ON sales_plan (plan_month, outlet_id, product_id);
CREATE INDEX plan_outlet_idx         ON sales_plan (outlet_id);
CREATE INDEX plan_product_idx        ON sales_plan (product_id);

CREATE UNIQUE INDEX discounts_sale_idx ON discounts (sale_id);
CREATE INDEX discounts_client_idx      ON discounts (client_id);
CREATE INDEX discounts_date_idx        ON discounts (discount_date);
CREATE INDEX discounts_reason_idx      ON discounts (reason);

CREATE INDEX outlets_region_idx      ON outlets (region_id);
CREATE INDEX clients_region_idx      ON clients (region_id);
CREATE INDEX clients_segment_idx     ON clients (segment);
CREATE INDEX products_category_idx   ON products (category);


-- Факт, поднятый до зерна плана. Без этого шага джойн с планом размножает
-- plan_amount по числу продаж: на один (месяц, точка, продукт) приходится
-- до 4 строк продаж — разные договоры и клиенты.
CREATE MATERIALIZED VIEW sales_monthly AS
SELECT date_trunc('month', sale_date)::date AS month,
       outlet_id,
       product_id,
       sum(amount)              AS fact_amount,
       sum(quantity)            AS fact_qty,
       count(*)                 AS sales_count,
       count(DISTINCT client_id) AS client_count
FROM sales
GROUP BY 1, 2, 3;

CREATE UNIQUE INDEX sales_monthly_grain_idx ON sales_monthly (month, outlet_id, product_id);


-- План и факт вместе. Только FULL OUTER JOIN: 11 711 ключей имеют план на
-- 445 млн ₽ без единой продажи, 610 — продажи без плана. INNER JOIN выбросил
-- бы 11% плана и поднял выполнение с 82,7% до ~92,7%.
CREATE VIEW plan_fact_monthly AS
SELECT COALESCE(p.plan_month, f.month)      AS month,
       COALESCE(p.outlet_id,  f.outlet_id)  AS outlet_id,
       COALESCE(p.product_id, f.product_id) AS product_id,
       COALESCE(p.plan_amount, 0)  AS plan_amount,
       COALESCE(p.plan_qty,    0)  AS plan_qty,
       COALESCE(f.fact_amount, 0)  AS fact_amount,
       COALESCE(f.fact_qty,    0)  AS fact_qty,
       COALESCE(f.sales_count, 0)  AS sales_count,
       COALESCE(f.client_count, 0) AS client_count
FROM sales_plan p
FULL OUTER JOIN sales_monthly f
  ON  p.plan_month = f.month
  AND p.outlet_id  = f.outlet_id
  AND p.product_id = f.product_id;


-- Базовая плоская таблица проекта. Сборщик SQL группирует её с фильтрами —
-- и обе ловушки джойна закрыты конструкцией, а не дисциплиной.
CREATE VIEW plan_fact_flat AS
SELECT pf.month,
       pf.outlet_id, o.outlet_name, o.city, o.outlet_type,
       o.region_id,  r.region_name,
       pf.product_id, p.product_name, p.category,
       pf.plan_amount, pf.plan_qty,
       pf.fact_amount, pf.fact_qty,
       pf.sales_count, pf.client_count
FROM plan_fact_monthly pf
JOIN outlets  o ON o.outlet_id  = pf.outlet_id
JOIN regions  r ON r.region_id  = o.region_id
JOIN products p ON p.product_id = pf.product_id;


-- Горизонт факта: до какого месяца данные реально есть. Нужен, чтобы
-- не сравнивать полный год плана с девятью месяцами продаж.
CREATE VIEW fact_horizon AS
SELECT max(sale_date) AS last_sale_date,
       date_trunc('month', max(sale_date))::date AS last_full_month
FROM sales;
