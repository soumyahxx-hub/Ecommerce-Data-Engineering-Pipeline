-- fact_orders: upsert keyed on order_id (idempotent; re-processing a late/updated order overwrites it).
INSERT INTO dw.fact_orders (
    order_id, customer_sk, order_status, purchase_ts, approved_ts, delivered_carrier_ts, delivered_customer_ts,
    estimated_delivery_ts, purchase_date_key, delivered_date_key, estimated_delivery_date_key,
    item_count, items_value, freight_value, payment_value, review_score,
    delivery_days, delivery_delay_days, is_late, run_id)
SELECT o.order_id,
       coalesce(dc.customer_sk, -1),
       o.order_status, o.purchase_ts, o.approved_ts, o.delivered_carrier_ts, o.delivered_customer_ts, o.estimated_delivery_ts,
       to_char(o.purchase_ts, 'YYYYMMDD')::int,
       to_char(o.delivered_customer_ts, 'YYYYMMDD')::int,
       to_char(o.estimated_delivery_ts, 'YYYYMMDD')::int,
       coalesce(i.item_count, 0), coalesce(i.items_value, 0), coalesce(i.freight_value, 0),
       coalesce(p.payment_value, 0), r.review_score,
       round((extract(epoch FROM (o.delivered_customer_ts - o.purchase_ts)) / 86400.0)::numeric, 2),
       round((extract(epoch FROM (o.delivered_customer_ts - o.estimated_delivery_ts)) / 86400.0)::numeric, 2),
       CASE WHEN o.delivered_customer_ts IS NULL OR o.estimated_delivery_ts IS NULL THEN NULL
            ELSE o.delivered_customer_ts > o.estimated_delivery_ts END,
       current_setting('etl.run_id')
FROM stg.orders o
LEFT JOIN stg.customers sc ON sc.customer_id = o.customer_id
LEFT JOIN dw.dim_customers dc ON dc.customer_unique_id = sc.customer_unique_id
                              AND o.purchase_ts >= dc.valid_from AND o.purchase_ts < dc.valid_to
LEFT JOIN (SELECT order_id, count(*) AS item_count, sum(price) AS items_value, sum(freight_value) AS freight_value
           FROM stg.order_items GROUP BY order_id) i ON i.order_id = o.order_id
LEFT JOIN (SELECT order_id, sum(payment_value) AS payment_value FROM stg.payments GROUP BY order_id) p ON p.order_id = o.order_id
LEFT JOIN (SELECT order_id, round(avg(review_score)::numeric, 2) AS review_score FROM stg.reviews GROUP BY order_id) r ON r.order_id = o.order_id
ON CONFLICT (order_id) DO UPDATE SET
    customer_sk = EXCLUDED.customer_sk, order_status = EXCLUDED.order_status, purchase_ts = EXCLUDED.purchase_ts,
    approved_ts = EXCLUDED.approved_ts, delivered_carrier_ts = EXCLUDED.delivered_carrier_ts,
    delivered_customer_ts = EXCLUDED.delivered_customer_ts, estimated_delivery_ts = EXCLUDED.estimated_delivery_ts,
    purchase_date_key = EXCLUDED.purchase_date_key, delivered_date_key = EXCLUDED.delivered_date_key,
    estimated_delivery_date_key = EXCLUDED.estimated_delivery_date_key, item_count = EXCLUDED.item_count,
    items_value = EXCLUDED.items_value, freight_value = EXCLUDED.freight_value, payment_value = EXCLUDED.payment_value,
    review_score = EXCLUDED.review_score, delivery_days = EXCLUDED.delivery_days,
    delivery_delay_days = EXCLUDED.delivery_delay_days, is_late = EXCLUDED.is_late,
    run_id = EXCLUDED.run_id, updated_at = now();
