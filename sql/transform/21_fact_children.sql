-- fact_order_items, fact_payments, fact_reviews (all upserts keyed on their grain)
INSERT INTO dw.fact_order_items (order_id, order_item_id, product_sk, seller_sk, customer_sk, purchase_date_key,
                                 shipping_limit_ts, price, freight_value, run_id)
SELECT i.order_id, i.order_item_id,
       coalesce(dp.product_sk, -1), coalesce(ds.seller_sk, -1), fo.customer_sk, fo.purchase_date_key,
       i.shipping_limit_ts, i.price, i.freight_value, current_setting('etl.run_id')
FROM stg.order_items i
JOIN dw.fact_orders fo ON fo.order_id = i.order_id
LEFT JOIN dw.dim_products dp ON dp.product_id = i.product_id
                            AND fo.purchase_ts >= dp.valid_from AND fo.purchase_ts < dp.valid_to
LEFT JOIN dw.dim_sellers ds ON ds.seller_id = i.seller_id
ON CONFLICT (order_id, order_item_id) DO UPDATE SET
    product_sk = EXCLUDED.product_sk, seller_sk = EXCLUDED.seller_sk, customer_sk = EXCLUDED.customer_sk,
    purchase_date_key = EXCLUDED.purchase_date_key, shipping_limit_ts = EXCLUDED.shipping_limit_ts,
    price = EXCLUDED.price, freight_value = EXCLUDED.freight_value, run_id = EXCLUDED.run_id, updated_at = now();

INSERT INTO dw.fact_payments (order_id, payment_sequential, payment_method_sk, purchase_date_key,
                              payment_installments, payment_value, run_id)
SELECT p.order_id, p.payment_sequential, coalesce(pm.payment_method_sk, -1), fo.purchase_date_key,
       p.payment_installments, p.payment_value, current_setting('etl.run_id')
FROM stg.payments p
JOIN dw.fact_orders fo ON fo.order_id = p.order_id
LEFT JOIN dw.dim_payment_methods pm ON pm.payment_type = p.payment_type
ON CONFLICT (order_id, payment_sequential) DO UPDATE SET
    payment_method_sk = EXCLUDED.payment_method_sk, purchase_date_key = EXCLUDED.purchase_date_key,
    payment_installments = EXCLUDED.payment_installments, payment_value = EXCLUDED.payment_value,
    run_id = EXCLUDED.run_id, updated_at = now();

INSERT INTO dw.fact_reviews (review_id, order_id, review_score, has_comment, creation_date_key, answer_ts, run_id)
SELECT r.review_id, r.order_id, r.review_score,
       (r.comment_title IS NOT NULL OR r.comment_message IS NOT NULL),
       to_char(r.creation_ts, 'YYYYMMDD')::int, r.answer_ts, current_setting('etl.run_id')
FROM stg.reviews r
JOIN dw.fact_orders fo ON fo.order_id = r.order_id
ON CONFLICT (review_id, order_id) DO UPDATE SET
    review_score = EXCLUDED.review_score, has_comment = EXCLUDED.has_comment,
    creation_date_key = EXCLUDED.creation_date_key, answer_ts = EXCLUDED.answer_ts,
    run_id = EXCLUDED.run_id, updated_at = now();
