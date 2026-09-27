-- Схема тестового датасета кейса. Структура повторяет CSV один в один,
-- типы ужесточены: даты датами, деньги numeric, ИНН текстом (ведущие нули).

CREATE TABLE regions (
    region_id       int  PRIMARY KEY,
    region_name     text NOT NULL,
    regional_center text NOT NULL
);

CREATE TABLE products (
    product_id        int  PRIMARY KEY,
    product_name      text NOT NULL,
    category          text NOT NULL,
    unit_price        numeric(12,2) NOT NULL,
    unit              text NOT NULL,
    launch_date       date NOT NULL,
    discontinued_date date
);

CREATE TABLE clients (
    client_id       int  PRIMARY KEY,
    client_name     text NOT NULL,
    inn             text NOT NULL,
    segment         text NOT NULL,
    region_id       int  NOT NULL REFERENCES regions,
    registered_date date NOT NULL,
    is_key_client   boolean NOT NULL
);

CREATE TABLE outlets (
    outlet_id   int  PRIMARY KEY,
    outlet_name text NOT NULL,
    region_id   int  NOT NULL REFERENCES regions,
    city        text NOT NULL,
    outlet_type text NOT NULL,
    address     text NOT NULL,
    opened_date date NOT NULL,
    closed_date date
);

CREATE TABLE contracts (
    contract_id        int  PRIMARY KEY,
    contract_number    text NOT NULL,
    client_id          int  NOT NULL REFERENCES clients,
    start_date         date NOT NULL,
    end_date           date NOT NULL,
    status             text NOT NULL,
    payment_terms_days int  NOT NULL,
    base_discount_pct  numeric(5,2) NOT NULL
);

CREATE TABLE sales (
    sale_id     int  PRIMARY KEY,
    sale_date   date NOT NULL,
    contract_id int  NOT NULL REFERENCES contracts,
    client_id   int  NOT NULL REFERENCES clients,
    outlet_id   int  NOT NULL REFERENCES outlets,
    product_id  int  NOT NULL REFERENCES products,
    quantity    int  NOT NULL,
    amount      numeric(14,2) NOT NULL
);

-- Плана по клиентам и договорам не существует: зерно только месяц × точка × продукт.
CREATE TABLE sales_plan (
    plan_id     int  PRIMARY KEY,
    plan_month  date NOT NULL,
    outlet_id   int  NOT NULL REFERENCES outlets,
    product_id  int  NOT NULL REFERENCES products,
    plan_amount numeric(14,2) NOT NULL,
    plan_qty    int  NOT NULL
);

CREATE TABLE discounts (
    discount_id     int  PRIMARY KEY,
    sale_id         int  NOT NULL REFERENCES sales,
    client_id       int  NOT NULL REFERENCES clients,
    discount_date   date NOT NULL,
    discount_amount numeric(14,2) NOT NULL,
    discount_pct    numeric(5,2) NOT NULL,
    reason          text NOT NULL
);

CREATE SCHEMA app;  -- сохранённые дашборды; таблицы появятся в срезе 5
