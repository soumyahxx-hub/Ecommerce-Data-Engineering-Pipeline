-- Post-load reconciliation. Returns (check_name, severity, failed_count). Any 'error' row with failed_count > 0 fails the run.
-- Uses current_setting('etl.run_id'); staging holds the batch just loaded.
SELECT 'orders_staged_but_missing_in_fact' AS check_name, 'error' AS severity, count(*)::bigint AS failed_count
FROM stg.orders o LEFT JOIN dw.fact_orders f USING (order_id) WHERE f.order_id IS NULL
UNION ALL
SELECT 'items_staged_but_missing_in_fact', 'error', count(*)
FROM stg.order_items i LEFT JOIN dw.fact_order_items f USING (order_id, order_item_id) WHERE f.order_id IS NULL
UNION ALL
SELECT 'payments_staged_but_missing_in_fact', 'error', count(*)
FROM stg.payments p LEFT JOIN dw.fact_payments f USING (order_id, payment_sequential) WHERE f.order_id IS NULL
UNION ALL
SELECT 'order_items_value_mismatch', 'error', count(*)
FROM dw.fact_orders o
JOIN (SELECT order_id, sum(price) v, count(*) n FROM dw.fact_order_items GROUP BY order_id) i USING (order_id)
WHERE o.run_id = current_setting('etl.run_id') AND (o.items_value <> i.v OR o.item_count <> i.n)
UNION ALL
SELECT 'payment_value_mismatch', 'error', count(*)
FROM dw.fact_orders o
JOIN (SELECT order_id, sum(payment_value) v FROM dw.fact_payments GROUP BY order_id) p USING (order_id)
WHERE o.run_id = current_setting('etl.run_id') AND o.payment_value <> p.v
UNION ALL
SELECT 'orders_with_unknown_customer', 'warn', count(*) FROM dw.fact_orders
WHERE run_id = current_setting('etl.run_id') AND customer_sk = -1
UNION ALL
SELECT 'items_with_unknown_product', 'warn', count(*) FROM dw.fact_order_items
WHERE run_id = current_setting('etl.run_id') AND product_sk = -1
UNION ALL
SELECT 'items_with_unknown_seller', 'warn', count(*) FROM dw.fact_order_items
WHERE run_id = current_setting('etl.run_id') AND seller_sk = -1
UNION ALL
SELECT 'scd2_multiple_current_customers', 'error', count(*) FROM (
    SELECT customer_unique_id FROM dw.dim_customers WHERE is_current GROUP BY 1 HAVING count(*) > 1) x
UNION ALL
SELECT 'scd2_multiple_current_products', 'error', count(*) FROM (
    SELECT product_id FROM dw.dim_products WHERE is_current GROUP BY 1 HAVING count(*) > 1) x;
