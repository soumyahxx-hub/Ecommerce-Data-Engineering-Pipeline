-- Dimensional model (star schema). All statements idempotent.

-- ---------- dim_date (static calendar 2015-2030) ----------
CREATE TABLE IF NOT EXISTS dw.dim_date (
    date_key     int PRIMARY KEY,           -- yyyymmdd
    full_date    date NOT NULL UNIQUE,
    year         smallint NOT NULL,
    quarter      smallint NOT NULL,
    month        smallint NOT NULL,
    month_name   text NOT NULL,
    day          smallint NOT NULL,
    day_of_week  smallint NOT NULL,         -- 1=Mon .. 7=Sun (ISO)
    day_name     text NOT NULL,
    is_weekend   boolean NOT NULL
);
INSERT INTO dw.dim_date
SELECT to_char(d,'YYYYMMDD')::int, d::date, extract(year FROM d), extract(quarter FROM d), extract(month FROM d),
       trim(to_char(d,'Month')), extract(day FROM d), extract(isodow FROM d), trim(to_char(d,'Day')),
       extract(isodow FROM d) IN (6,7)
FROM generate_series(DATE '2015-01-01', DATE '2030-12-31', INTERVAL '1 day') AS d
ON CONFLICT (date_key) DO NOTHING;

-- ---------- dim_customers (SCD Type 2 on location attributes) ----------
-- Natural key = customer_unique_id (Olist's customer_id is per-order, unique_id identifies the person).
CREATE TABLE IF NOT EXISTS dw.dim_customers (
    customer_sk        bigserial PRIMARY KEY,
    customer_unique_id text NOT NULL,
    zip_code_prefix    text,
    city               text,
    state              text,
    attr_hash          text NOT NULL,
    valid_from         timestamp NOT NULL,
    valid_to           timestamp NOT NULL DEFAULT TIMESTAMP '9999-12-31',
    is_current         boolean NOT NULL DEFAULT true,
    created_run_id     text,
    UNIQUE (customer_unique_id, valid_from)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_dim_customers_current ON dw.dim_customers (customer_unique_id) WHERE is_current;
CREATE INDEX IF NOT EXISTS ix_dim_customers_nk ON dw.dim_customers (customer_unique_id, valid_from, valid_to);

-- ---------- dim_products (SCD Type 2 on category / physical attributes) ----------
CREATE TABLE IF NOT EXISTS dw.dim_products (
    product_sk       bigserial PRIMARY KEY,
    product_id       text NOT NULL,
    category_name_pt text,
    category_name_en text,
    weight_g         numeric,
    length_cm        numeric,
    height_cm        numeric,
    width_cm         numeric,
    photos_qty       int,
    attr_hash        text NOT NULL,
    valid_from       timestamp NOT NULL,
    valid_to         timestamp NOT NULL DEFAULT TIMESTAMP '9999-12-31',
    is_current       boolean NOT NULL DEFAULT true,
    created_run_id   text,
    UNIQUE (product_id, valid_from)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_dim_products_current ON dw.dim_products (product_id) WHERE is_current;
CREATE INDEX IF NOT EXISTS ix_dim_products_nk ON dw.dim_products (product_id, valid_from, valid_to);

-- ---------- dim_sellers (SCD Type 1: overwrite) ----------
CREATE TABLE IF NOT EXISTS dw.dim_sellers (
    seller_sk       bigserial PRIMARY KEY,
    seller_id       text NOT NULL UNIQUE,
    zip_code_prefix text,
    city            text,
    state           text,
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- ---------- dim_payment_methods ----------
CREATE TABLE IF NOT EXISTS dw.dim_payment_methods (
    payment_method_sk bigserial PRIMARY KEY,
    payment_type      text NOT NULL UNIQUE
);

-- ---------- dim_geolocation (one row per zip prefix, SCD1) ----------
CREATE TABLE IF NOT EXISTS dw.dim_geolocation (
    zip_code_prefix text PRIMARY KEY,
    lat   double precision,
    lng   double precision,
    city  text,
    state text
);

-- ---------- reference: FX rates from REST API ----------
CREATE TABLE IF NOT EXISTS dw.ref_fx_rates (
    rate_date      date NOT NULL,
    base_currency  text NOT NULL,
    quote_currency text NOT NULL,
    rate           numeric(12,6) NOT NULL,
    PRIMARY KEY (rate_date, base_currency, quote_currency)
);

-- ---------- 'Unknown' members so facts never lose rows on missing dimension keys ----------
INSERT INTO dw.dim_customers (customer_sk, customer_unique_id, attr_hash, valid_from, is_current)
VALUES (-1, 'UNKNOWN', 'unknown', TIMESTAMP '1900-01-01', true) ON CONFLICT DO NOTHING;
INSERT INTO dw.dim_products (product_sk, product_id, category_name_en, attr_hash, valid_from, is_current)
VALUES (-1, 'UNKNOWN', 'unknown', 'unknown', TIMESTAMP '1900-01-01', true) ON CONFLICT DO NOTHING;
INSERT INTO dw.dim_sellers (seller_sk, seller_id) VALUES (-1, 'UNKNOWN') ON CONFLICT DO NOTHING;
INSERT INTO dw.dim_payment_methods (payment_method_sk, payment_type) VALUES (-1, 'unknown') ON CONFLICT DO NOTHING;

-- ---------- facts ----------
-- Grain: one row per order.
CREATE TABLE IF NOT EXISTS dw.fact_orders (
    order_id                    text PRIMARY KEY,
    customer_sk                 bigint NOT NULL REFERENCES dw.dim_customers (customer_sk),
    order_status                text NOT NULL,
    purchase_ts                 timestamp NOT NULL,
    approved_ts                 timestamp,
    delivered_carrier_ts        timestamp,
    delivered_customer_ts       timestamp,
    estimated_delivery_ts       timestamp,
    purchase_date_key           int NOT NULL REFERENCES dw.dim_date (date_key),
    delivered_date_key          int REFERENCES dw.dim_date (date_key),
    estimated_delivery_date_key int REFERENCES dw.dim_date (date_key),
    item_count                  int NOT NULL DEFAULT 0,
    items_value                 numeric(14,2) NOT NULL DEFAULT 0,
    freight_value               numeric(14,2) NOT NULL DEFAULT 0,
    payment_value               numeric(14,2) NOT NULL DEFAULT 0,
    review_score                numeric(4,2),
    delivery_days               numeric(8,2),
    delivery_delay_days         numeric(8,2),   -- >0 = delivered after the estimate
    is_late                     boolean,
    run_id                      text,
    updated_at                  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_fact_orders_customer ON dw.fact_orders (customer_sk);
CREATE INDEX IF NOT EXISTS ix_fact_orders_date ON dw.fact_orders (purchase_date_key);
CREATE INDEX IF NOT EXISTS ix_fact_orders_status ON dw.fact_orders (order_status);

-- Grain: one row per order line item.
CREATE TABLE IF NOT EXISTS dw.fact_order_items (
    order_id          text NOT NULL REFERENCES dw.fact_orders (order_id),
    order_item_id     int  NOT NULL,
    product_sk        bigint NOT NULL REFERENCES dw.dim_products (product_sk),
    seller_sk         bigint NOT NULL REFERENCES dw.dim_sellers (seller_sk),
    customer_sk       bigint NOT NULL REFERENCES dw.dim_customers (customer_sk),
    purchase_date_key int NOT NULL REFERENCES dw.dim_date (date_key),
    shipping_limit_ts timestamp,
    price             numeric(12,2) NOT NULL,
    freight_value     numeric(12,2) NOT NULL,
    run_id            text,
    updated_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (order_id, order_item_id)
);
CREATE INDEX IF NOT EXISTS ix_foi_product ON dw.fact_order_items (product_sk);
CREATE INDEX IF NOT EXISTS ix_foi_seller ON dw.fact_order_items (seller_sk);
CREATE INDEX IF NOT EXISTS ix_foi_date ON dw.fact_order_items (purchase_date_key);

-- Grain: one row per payment instalment record of an order.
CREATE TABLE IF NOT EXISTS dw.fact_payments (
    order_id             text NOT NULL REFERENCES dw.fact_orders (order_id),
    payment_sequential   int  NOT NULL,
    payment_method_sk    bigint NOT NULL REFERENCES dw.dim_payment_methods (payment_method_sk),
    purchase_date_key    int NOT NULL REFERENCES dw.dim_date (date_key),
    payment_installments int,
    payment_value        numeric(12,2) NOT NULL,
    run_id               text,
    updated_at           timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (order_id, payment_sequential)
);
CREATE INDEX IF NOT EXISTS ix_fp_method ON dw.fact_payments (payment_method_sk);

-- Grain: one row per (review, order). Olist reuses review_id across orders.
CREATE TABLE IF NOT EXISTS dw.fact_reviews (
    review_id         text NOT NULL,
    order_id          text NOT NULL REFERENCES dw.fact_orders (order_id),
    review_score      smallint NOT NULL,
    has_comment       boolean NOT NULL,
    creation_date_key int REFERENCES dw.dim_date (date_key),
    answer_ts         timestamp,
    run_id            text,
    updated_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (review_id, order_id)
);
