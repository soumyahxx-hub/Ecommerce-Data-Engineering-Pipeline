-- Staging = latest silver batch (truncate + load each run). Column order == schemas.SILVER_COLUMNS + _run_id.
CREATE TABLE IF NOT EXISTS stg.customers   (customer_id text, customer_unique_id text, zip_code_prefix text, city text, state text, _run_id text);
CREATE TABLE IF NOT EXISTS stg.sellers     (seller_id text, zip_code_prefix text, city text, state text, _run_id text);
CREATE TABLE IF NOT EXISTS stg.geolocation (zip_code_prefix text, lat double precision, lng double precision, city text, state text, _run_id text);
CREATE TABLE IF NOT EXISTS stg.products    (product_id text, category_name_pt text, category_name_en text, name_length int, description_length int,
                                            photos_qty int, weight_g numeric, length_cm numeric, height_cm numeric, width_cm numeric, _run_id text);
CREATE TABLE IF NOT EXISTS stg.orders      (order_id text, customer_id text, order_status text, purchase_ts timestamp, approved_ts timestamp,
                                            delivered_carrier_ts timestamp, delivered_customer_ts timestamp, estimated_delivery_ts timestamp, _run_id text);
CREATE TABLE IF NOT EXISTS stg.order_items (order_id text, order_item_id int, product_id text, seller_id text, shipping_limit_ts timestamp,
                                            price numeric(12,2), freight_value numeric(12,2), _run_id text);
CREATE TABLE IF NOT EXISTS stg.payments    (order_id text, payment_sequential int, payment_type text, payment_installments int, payment_value numeric(12,2), _run_id text);
CREATE TABLE IF NOT EXISTS stg.reviews     (review_id text, order_id text, review_score int, comment_title text, comment_message text,
                                            creation_ts timestamp, answer_ts timestamp, _run_id text);
CREATE TABLE IF NOT EXISTS stg.fx_rates    (rate_date date, base_currency text, quote_currency text, rate numeric(12,6), _run_id text);
