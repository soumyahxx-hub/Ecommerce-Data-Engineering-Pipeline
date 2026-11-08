# Data Dictionary

Source columns follow the published Olist Kaggle dataset as I know it (including the original misspelling `lenght`). **I could not inspect the real files in the build environment**; the pipeline validates the headers at run time and fails with `SchemaError` if they differ. Timestamps are naive (Brazil local time, no timezone conversion).

## Source files -> silver
| Source file | Key columns (source) | Silver table / rules |
|---|---|---|
| olist_orders_dataset.csv | order_id, customer_id, order_status, order_purchase_timestamp, order_approved_at, order_delivered_carrier_date, order_delivered_customer_date, order_estimated_delivery_date | `orders`; status in {created, approved, invoiced, processing, shipped, delivered, unavailable, canceled}; reject null keys / bad purchase date / bad status; duplicates: last record wins |
| olist_order_items_dataset.csv | order_id, order_item_id, product_id, seller_id, shipping_limit_date, price, freight_value | `order_items`; reject price<0/null, null keys, orphan orders; freight null -> 0 |
| olist_order_payments_dataset.csv | order_id, payment_sequential, payment_type, payment_installments, payment_value | `payments`; reject value<0/null; null type -> `not_defined` |
| olist_order_reviews_dataset.csv | review_id, order_id, review_score, review_comment_title/message, review_creation_date, review_answer_timestamp | `reviews`; score 1-5 else reject; (review_id, order_id) dedup keeps latest answer |
| olist_customers_dataset.csv | customer_id, customer_unique_id, customer_zip_code_prefix, customer_city, customer_state | `customers`; zip left-padded to 5; city lower, state upper |
| olist_sellers_dataset.csv | seller_id, seller_zip_code_prefix, seller_city, seller_state | `sellers`; same rules |
| olist_products_dataset.csv | product_id, product_category_name, product_name_lenght, product_description_lenght, product_photos_qty, product_weight_g, product_length_cm, product_height_cm, product_width_cm | `products`; typo columns renamed to `name_length`, `description_length`; negatives -> NULL; English category via translation, fallback to Portuguese name then `unknown` |
| product_category_name_translation.csv | product_category_name, product_category_name_english | merged into `products.category_name_en` |
| olist_geolocation_dataset.csv | geolocation_zip_code_prefix, geolocation_lat, geolocation_lng, geolocation_city, geolocation_state | `geolocation`; points outside Brazil bbox rejected; aggregated to 1 row / prefix (mean lat/lng, modal city/state) |
| FX REST API (Frankfurter) | rates{date:{BRL}} | `fx_rates` (USD->BRL daily) |

## Derived measures (fact_orders)
| Column | Definition |
|---|---|
| items_value | sum(price) of the order's items (excl. freight) |
| freight_value | sum(freight_value) |
| payment_value | sum(payment_value) over all payment records |
| review_score | avg(score) of the order's reviews |
| delivery_days | delivered_customer_ts − purchase_ts in days |
| delivery_delay_days | delivered − estimated; >0 means late |
| is_late | delivered > estimated (NULL if not delivered) |

Revenue in analytics views = `items_value` of orders not `canceled`/`unavailable`.

## Audit tables (`etl`)
`pipeline_runs(run_id,status,started_at,finished_at,error_message)`, `step_log(run_id,step,status,rows_processed,error_message)`, `watermarks(source_name,watermark)`, `dq_results(run_id,table_name,check_name,severity,passed,failed_rows,total_rows,detail)`.
