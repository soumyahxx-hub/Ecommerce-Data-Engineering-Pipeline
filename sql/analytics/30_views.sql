-- Analytics layer. Revenue = items value of orders that were not cancelled / unavailable.
CREATE OR REPLACE VIEW analytics.v_valid_orders AS
SELECT * FROM dw.fact_orders WHERE order_status NOT IN ('canceled', 'unavailable');

CREATE OR REPLACE VIEW analytics.v_daily_sales AS
SELECT d.full_date, count(*) AS orders, sum(o.items_value) AS revenue, sum(o.freight_value) AS freight,
       round(avg(o.items_value), 2) AS avg_order_value
FROM analytics.v_valid_orders o JOIN dw.dim_date d ON d.date_key = o.purchase_date_key
GROUP BY d.full_date;

CREATE OR REPLACE VIEW analytics.v_monthly_revenue AS
WITH m AS (
    SELECT date_trunc('month', d.full_date)::date AS month, count(*) AS orders, sum(o.items_value) AS revenue,
           count(DISTINCT c.customer_unique_id) AS customers
    FROM analytics.v_valid_orders o
    JOIN dw.dim_date d ON d.date_key = o.purchase_date_key
    JOIN dw.dim_customers c ON c.customer_sk = o.customer_sk
    GROUP BY 1)
SELECT month, orders, revenue, customers,
       round(100.0 * (revenue - lag(revenue) OVER w) / nullif(lag(revenue) OVER w, 0), 2) AS revenue_mom_pct,
       sum(revenue) OVER (ORDER BY month) AS cumulative_revenue
FROM m WINDOW w AS (ORDER BY month);

CREATE OR REPLACE VIEW analytics.v_monthly_revenue_usd AS
SELECT m.month, m.revenue AS revenue_brl, round(avg(fx.rate), 4) AS avg_usd_brl,
       round(m.revenue / nullif(avg(fx.rate), 0), 2) AS revenue_usd_approx
FROM analytics.v_monthly_revenue m
LEFT JOIN dw.ref_fx_rates fx ON date_trunc('month', fx.rate_date)::date = m.month
                            AND fx.base_currency = 'USD' AND fx.quote_currency = 'BRL'
GROUP BY m.month, m.revenue;

CREATE OR REPLACE VIEW analytics.v_category_performance AS
SELECT p.category_name_en AS category, count(*) AS items_sold, sum(i.price) AS revenue,
       round(avg(i.price), 2) AS avg_price,
       rank() OVER (ORDER BY sum(i.price) DESC) AS revenue_rank
FROM dw.fact_order_items i
JOIN dw.dim_products p ON p.product_sk = i.product_sk
JOIN dw.fact_orders o ON o.order_id = i.order_id AND o.order_status NOT IN ('canceled', 'unavailable')
GROUP BY p.category_name_en;

CREATE OR REPLACE VIEW analytics.v_seller_performance AS
SELECT s.seller_id, s.state, count(DISTINCT i.order_id) AS orders, sum(i.price) AS revenue,
       round(avg(o.review_score), 2) AS avg_review_score,
       round(100.0 * avg(CASE WHEN o.is_late THEN 1 ELSE 0 END) FILTER (WHERE o.is_late IS NOT NULL), 2) AS late_delivery_pct
FROM dw.fact_order_items i
JOIN dw.dim_sellers s ON s.seller_sk = i.seller_sk
JOIN analytics.v_valid_orders o ON o.order_id = i.order_id
GROUP BY s.seller_id, s.state;

CREATE OR REPLACE VIEW analytics.v_customer_value AS
SELECT c.customer_unique_id, count(DISTINCT o.order_id) AS orders, sum(o.items_value) AS lifetime_value,
       min(o.purchase_ts) AS first_order_at, max(o.purchase_ts) AS last_order_at,
       count(DISTINCT o.order_id) > 1 AS is_repeat_customer
FROM analytics.v_valid_orders o JOIN dw.dim_customers c ON c.customer_sk = o.customer_sk
WHERE c.customer_unique_id <> 'UNKNOWN'
GROUP BY c.customer_unique_id;

CREATE OR REPLACE VIEW analytics.v_delivery_performance AS
SELECT c.state, date_trunc('month', o.purchase_ts)::date AS month, count(*) AS delivered_orders,
       round(avg(o.delivery_days), 2) AS avg_delivery_days,
       round(100.0 * avg(CASE WHEN o.is_late THEN 1 ELSE 0 END), 2) AS late_pct
FROM dw.fact_orders o JOIN dw.dim_customers c ON c.customer_sk = o.customer_sk
WHERE o.order_status = 'delivered' AND o.delivered_customer_ts IS NOT NULL
GROUP BY c.state, date_trunc('month', o.purchase_ts);

CREATE OR REPLACE VIEW analytics.v_payment_mix AS
SELECT pm.payment_type, count(*) AS payments, sum(p.payment_value) AS total_value,
       round(avg(p.payment_installments), 2) AS avg_installments,
       round(100.0 * sum(p.payment_value) / nullif(sum(sum(p.payment_value)) OVER (), 0), 2) AS pct_of_value
FROM dw.fact_payments p JOIN dw.dim_payment_methods pm USING (payment_method_sk)
GROUP BY pm.payment_type;

CREATE OR REPLACE VIEW analytics.v_kpi_summary AS
SELECT (SELECT count(*) FROM analytics.v_valid_orders)                       AS orders,
       (SELECT coalesce(sum(items_value), 0) FROM analytics.v_valid_orders)  AS revenue,
       (SELECT round(avg(items_value), 2) FROM analytics.v_valid_orders)     AS avg_order_value,
       (SELECT round(avg(review_score), 2) FROM dw.fact_orders)              AS avg_review_score,
       (SELECT round(100.0 * avg(CASE WHEN is_late THEN 1 ELSE 0 END), 2) FROM dw.fact_orders WHERE is_late IS NOT NULL) AS late_delivery_pct,
       (SELECT round(100.0 * avg(CASE WHEN is_repeat_customer THEN 1 ELSE 0 END), 2) FROM analytics.v_customer_value) AS repeat_customer_pct;

CREATE OR REPLACE VIEW analytics.v_pipeline_health AS
SELECT r.run_id, r.status, r.started_at, r.finished_at,
       round(extract(epoch FROM (r.finished_at - r.started_at))::numeric, 1) AS duration_s,
       r.error_message,
       (SELECT count(*) FROM etl.dq_results d WHERE d.run_id = r.run_id AND NOT d.passed) AS dq_failures
FROM etl.pipeline_runs r ORDER BY r.started_at DESC;
