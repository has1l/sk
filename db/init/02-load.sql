-- Загрузка CSV. Порядок продиктован внешними ключами.
-- NULL в файлах закодирован как \N, поэтому FORMAT csv + NULL '\N'.

COPY regions    FROM '/seed/regions.csv'    WITH (FORMAT csv, HEADER true, NULL '\N');
COPY products   FROM '/seed/products.csv'   WITH (FORMAT csv, HEADER true, NULL '\N');
COPY clients    FROM '/seed/clients.csv'    WITH (FORMAT csv, HEADER true, NULL '\N');
COPY outlets    FROM '/seed/outlets.csv'    WITH (FORMAT csv, HEADER true, NULL '\N');
COPY contracts  FROM '/seed/contracts.csv'  WITH (FORMAT csv, HEADER true, NULL '\N');
COPY sales      FROM '/seed/sales.csv'      WITH (FORMAT csv, HEADER true, NULL '\N');
COPY sales_plan FROM '/seed/sales_plan.csv' WITH (FORMAT csv, HEADER true, NULL '\N');
COPY discounts  FROM '/seed/discounts.csv'  WITH (FORMAT csv, HEADER true, NULL '\N');
