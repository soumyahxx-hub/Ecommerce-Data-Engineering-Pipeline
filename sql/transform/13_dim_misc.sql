-- Payment methods (insert-only), geolocation (SCD1), FX reference rates (upsert)
INSERT INTO dw.dim_payment_methods (payment_type)
SELECT DISTINCT payment_type FROM stg.payments WHERE payment_type IS NOT NULL
ON CONFLICT (payment_type) DO NOTHING;

INSERT INTO dw.dim_geolocation (zip_code_prefix, lat, lng, city, state)
SELECT zip_code_prefix, lat, lng, city, state FROM stg.geolocation
ON CONFLICT (zip_code_prefix) DO UPDATE
SET lat = EXCLUDED.lat, lng = EXCLUDED.lng, city = EXCLUDED.city, state = EXCLUDED.state
WHERE (dw.dim_geolocation.lat, dw.dim_geolocation.lng, dw.dim_geolocation.city, dw.dim_geolocation.state)
      IS DISTINCT FROM (EXCLUDED.lat, EXCLUDED.lng, EXCLUDED.city, EXCLUDED.state);

INSERT INTO dw.ref_fx_rates (rate_date, base_currency, quote_currency, rate)
SELECT rate_date, base_currency, quote_currency, rate FROM stg.fx_rates
ON CONFLICT (rate_date, base_currency, quote_currency) DO UPDATE SET rate = EXCLUDED.rate;
