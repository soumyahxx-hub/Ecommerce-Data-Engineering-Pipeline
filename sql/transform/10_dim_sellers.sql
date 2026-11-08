-- SCD Type 1: overwrite changed attributes, never duplicate.
INSERT INTO dw.dim_sellers (seller_id, zip_code_prefix, city, state)
SELECT seller_id, zip_code_prefix, city, state FROM stg.sellers
ON CONFLICT (seller_id) DO UPDATE
SET zip_code_prefix = EXCLUDED.zip_code_prefix, city = EXCLUDED.city, state = EXCLUDED.state, updated_at = now()
WHERE (dw.dim_sellers.zip_code_prefix, dw.dim_sellers.city, dw.dim_sellers.state)
      IS DISTINCT FROM (EXCLUDED.zip_code_prefix, EXCLUDED.city, EXCLUDED.state);
