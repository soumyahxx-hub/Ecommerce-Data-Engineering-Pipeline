-- SCD Type 2 for dim_customers. Natural key = customer_unique_id.
-- Current attributes = those on the customer's most recent order in the batch; the version's
-- effective date (eff_ts) is that order's purchase time, so facts can join point-in-time.
CREATE TEMP TABLE _cust_latest ON COMMIT DROP AS
SELECT customer_unique_id, zip_code_prefix, city, state, eff_ts,
       md5(concat_ws('|', coalesce(zip_code_prefix,''), coalesce(city,''), coalesce(state,''))) AS attr_hash
FROM (
    SELECT c.customer_unique_id, c.zip_code_prefix, c.city, c.state,
           coalesce(o.purchase_ts, current_setting('etl.batch_ts')::timestamp) AS eff_ts,
           row_number() OVER (PARTITION BY c.customer_unique_id
                              ORDER BY o.purchase_ts DESC NULLS LAST, c.customer_id DESC) AS rn
    FROM stg.customers c
    LEFT JOIN stg.orders o ON o.customer_id = c.customer_id
) x
WHERE rn = 1;

-- 1) close current version when attributes changed (ignore late-arriving older data: eff_ts must be newer)
UPDATE dw.dim_customers d
SET valid_to = l.eff_ts, is_current = false
FROM _cust_latest l
WHERE d.customer_unique_id = l.customer_unique_id
  AND d.is_current
  AND d.attr_hash <> l.attr_hash
  AND l.eff_ts > d.valid_from;

-- 2) insert brand-new customers (valid since 1900 so any historical order matches) and new versions
INSERT INTO dw.dim_customers (customer_unique_id, zip_code_prefix, city, state, attr_hash, valid_from, valid_to, is_current, created_run_id)
SELECT l.customer_unique_id, l.zip_code_prefix, l.city, l.state, l.attr_hash,
       CASE WHEN EXISTS (SELECT 1 FROM dw.dim_customers p WHERE p.customer_unique_id = l.customer_unique_id)
            THEN l.eff_ts ELSE TIMESTAMP '1900-01-01' END,
       TIMESTAMP '9999-12-31', true, current_setting('etl.run_id')
FROM _cust_latest l
WHERE NOT EXISTS (SELECT 1 FROM dw.dim_customers c WHERE c.customer_unique_id = l.customer_unique_id AND c.is_current);
