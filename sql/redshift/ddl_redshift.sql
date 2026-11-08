-- Redshift serving schema (gold snapshot). Redshift does not enforce PK/FK; they are declared as planner hints.
CREATE SCHEMA IF NOT EXISTS rs_dw;

CREATE TABLE IF NOT EXISTS rs_dw.dim_date (date_key int, full_date date, year smallint, quarter smallint, month smallint,
    month_name varchar(20), day smallint, day_of_week smallint, day_name varchar(20), is_weekend boolean, PRIMARY KEY (date_key)) DISTSTYLE ALL;
CREATE TABLE IF NOT EXISTS rs_dw.dim_customers (customer_sk bigint, customer_unique_id varchar(64), zip_code_prefix varchar(10), city varchar(128),
    state varchar(8), attr_hash varchar(64), valid_from timestamp, valid_to timestamp, is_current boolean, created_run_id varchar(256), PRIMARY KEY (customer_sk)) DISTKEY (customer_sk);
CREATE TABLE IF NOT EXISTS rs_dw.dim_products (product_sk bigint, product_id varchar(64), category_name_pt varchar(128), category_name_en varchar(128),
    weight_g numeric(12,2), length_cm numeric(12,2), height_cm numeric(12,2), width_cm numeric(12,2), photos_qty int, attr_hash varchar(64),
    valid_from timestamp, valid_to timestamp, is_current boolean, created_run_id varchar(256), PRIMARY KEY (product_sk)) DISTSTYLE ALL;
CREATE TABLE IF NOT EXISTS rs_dw.dim_sellers (seller_sk bigint, seller_id varchar(64), zip_code_prefix varchar(10), city varchar(128), state varchar(8),
    updated_at timestamptz, PRIMARY KEY (seller_sk)) DISTSTYLE ALL;
CREATE TABLE IF NOT EXISTS rs_dw.dim_payment_methods (payment_method_sk bigint, payment_type varchar(32), PRIMARY KEY (payment_method_sk)) DISTSTYLE ALL;

CREATE TABLE IF NOT EXISTS rs_dw.fact_orders (order_id varchar(64), customer_sk bigint, order_status varchar(32), purchase_ts timestamp, approved_ts timestamp,
    delivered_carrier_ts timestamp, delivered_customer_ts timestamp, estimated_delivery_ts timestamp, purchase_date_key int, delivered_date_key int,
    estimated_delivery_date_key int, item_count int, items_value numeric(14,2), freight_value numeric(14,2), payment_value numeric(14,2),
    review_score numeric(4,2), delivery_days numeric(8,2), delivery_delay_days numeric(8,2), is_late boolean, run_id varchar(256), updated_at timestamptz,
    PRIMARY KEY (order_id)) DISTKEY (customer_sk) SORTKEY (purchase_date_key);
CREATE TABLE IF NOT EXISTS rs_dw.fact_order_items (order_id varchar(64), order_item_id int, product_sk bigint, seller_sk bigint, customer_sk bigint,
    purchase_date_key int, shipping_limit_ts timestamp, price numeric(12,2), freight_value numeric(12,2), run_id varchar(256), updated_at timestamptz,
    PRIMARY KEY (order_id, order_item_id)) DISTKEY (customer_sk) SORTKEY (purchase_date_key);
CREATE TABLE IF NOT EXISTS rs_dw.fact_payments (order_id varchar(64), payment_sequential int, payment_method_sk bigint, purchase_date_key int,
    payment_installments int, payment_value numeric(12,2), run_id varchar(256), updated_at timestamptz, PRIMARY KEY (order_id, payment_sequential))
    DISTKEY (order_id) SORTKEY (purchase_date_key);
CREATE TABLE IF NOT EXISTS rs_dw.fact_reviews (review_id varchar(64), order_id varchar(64), review_score smallint, has_comment boolean,
    creation_date_key int, answer_ts timestamp, run_id varchar(256), updated_at timestamptz, PRIMARY KEY (review_id, order_id)) DISTKEY (order_id);
