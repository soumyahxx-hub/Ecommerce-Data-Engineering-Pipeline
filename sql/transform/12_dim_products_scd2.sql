-- SCD Type 2 for dim_products (category and physical attributes). Effective date = batch time.
CREATE TEMP TABLE _prod_latest ON COMMIT DROP AS
SELECT product_id, category_name_pt, category_name_en, weight_g, length_cm, height_cm, width_cm, photos_qty,
       md5(concat_ws('|', coalesce(category_name_pt,''), coalesce(category_name_en,''), coalesce(weight_g::text,''),
                          coalesce(length_cm::text,''), coalesce(height_cm::text,''), coalesce(width_cm::text,''))) AS attr_hash
FROM stg.products;

UPDATE dw.dim_products d
SET valid_to = current_setting('etl.batch_ts')::timestamp, is_current = false
FROM _prod_latest l
WHERE d.product_id = l.product_id
  AND d.is_current
  AND d.attr_hash <> l.attr_hash
  AND current_setting('etl.batch_ts')::timestamp > d.valid_from;

INSERT INTO dw.dim_products (product_id, category_name_pt, category_name_en, weight_g, length_cm, height_cm, width_cm,
                             photos_qty, attr_hash, valid_from, valid_to, is_current, created_run_id)
SELECT l.product_id, l.category_name_pt, l.category_name_en, l.weight_g, l.length_cm, l.height_cm, l.width_cm,
       l.photos_qty, l.attr_hash,
       CASE WHEN EXISTS (SELECT 1 FROM dw.dim_products p WHERE p.product_id = l.product_id)
            THEN current_setting('etl.batch_ts')::timestamp ELSE TIMESTAMP '1900-01-01' END,
       TIMESTAMP '9999-12-31', true, current_setting('etl.run_id')
FROM _prod_latest l
WHERE NOT EXISTS (SELECT 1 FROM dw.dim_products c WHERE c.product_id = l.product_id AND c.is_current);
