"""Integration test of DDL + staging load + SQL transforms + SCD2 + idempotency + views against a REAL PostgreSQL.
Uses the psql client with standard PG* env vars (PGHOST, PGUSER, ...). Skipped when unavailable."""
import os
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from ecom_dw import clean, db
from ecom_dw.schemas import SILVER_COLUMNS
from ecom_dw.stage import copy_columns, to_copy_csv
from tests.helpers import raw_batch1, raw_batch2

pytestmark = pytest.mark.integration
SQL = Path(__file__).resolve().parents[1] / "sql"
TESTDB = "ecom_dw_it"


def _psql(args, db_name=TESTDB, input_=None):
    cmd = ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-d", db_name, "-At", "-F", "|"] + args
    p = subprocess.run(cmd, capture_output=True, text=True, input=input_)
    if p.returncode != 0:
        raise RuntimeError(f"psql failed: {p.stderr}\n{p.stdout}")
    return p.stdout.strip()


@pytest.fixture(scope="module")
def pg():
    if not shutil.which("psql"):
        pytest.skip("psql client not installed")
    try:
        _psql(["-c", "select 1"], db_name="postgres")
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"PostgreSQL not reachable via PG* env vars: {e}")
    _psql(["-c", f"DROP DATABASE IF EXISTS {TESTDB}"], db_name="postgres")
    _psql(["-c", f"CREATE DATABASE {TESTDB}"], db_name="postgres")
    for f in db.DDL_FILES + db.VIEW_FILES:
        _psql(["-f", str(SQL / f)])
    yield
    _psql(["-c", f"DROP DATABASE IF EXISTS {TESTDB}"], db_name="postgres")


def silver(raw) -> dict:
    c, _ = clean.run_clean(raw)
    c["fx_rates"] = clean.clean_fx({"base": "USD", "rates": {"2017-01-05": {"BRL": 3.2}, "2017-03-01": {"BRL": 3.1}}})[0]
    return c


def run_batch(frames, run_id, batch_ts):
    """Equivalent of stage.load_staging + db.run_transforms, in one transaction, via psql."""
    parts = ["BEGIN;", f"SELECT set_config('etl.run_id','{run_id}',true), set_config('etl.batch_ts','{batch_ts}',true);"]
    for t, df in frames.items():
        parts.append(f"TRUNCATE stg.{t};")
        if len(df):
            parts.append(f"COPY stg.{t} ({', '.join(copy_columns(t))}) FROM STDIN WITH (FORMAT csv);")
            parts.append(to_copy_csv(df, t, run_id).rstrip("\n"))
            parts.append("\\.")
    for f in db.TRANSFORM_FILES:
        parts.append(f"\\i {SQL / f}")
    parts.append("COMMIT;")
    _psql(["-f", "-"], input_="\n".join(parts) + "\n")


def q(sql):
    return _psql(["-c", sql])


def post_checks(run_id):
    out = _psql(["-f", "-"], input_=f"SELECT set_config('etl.run_id','{run_id}',false) \\g /dev/null\n"
                                    + (SQL / db.POST_CHECK_FILE).read_text())
    return [tuple(r.split("|")) for r in out.splitlines() if "|" in r]


def test_batch1_loads_star_schema(pg):
    run_batch(silver(raw_batch1()), "run1", "2017-01-31 00:00:00")
    assert q("SELECT count(*) FROM dw.fact_orders") == "3"
    assert q("SELECT count(*) FROM dw.fact_order_items") == "4"
    assert q("SELECT count(*) FROM dw.fact_payments") == "4"
    assert q("SELECT count(*) FROM dw.dim_customers WHERE customer_sk <> -1") == "2"
    assert q("SELECT items_value||'|'||freight_value||'|'||payment_value||'|'||item_count FROM dw.fact_orders WHERE order_id='o1'") == "150.50|15.25|165.75|2"
    assert q("SELECT delivery_days||'|'||delivery_delay_days||'|'||is_late FROM dw.fact_orders WHERE order_id='o1'") == "7.00|-7.58|false"
    assert q("SELECT is_late FROM dw.fact_orders WHERE order_id='o3'") == "t"
    # missing dimension keys fall back to the 'unknown' member instead of dropping the row
    assert q("SELECT customer_sk FROM dw.fact_orders WHERE order_id='o3'") == "-1"
    assert q("SELECT product_sk||'|'||seller_sk FROM dw.fact_order_items WHERE order_id='o3'") == "-1|-1"
    assert q("SELECT review_score FROM dw.fact_orders WHERE order_id='o1'") == "4.00"
    assert q("SELECT count(*) FROM dw.dim_geolocation") == "1"
    assert q("SELECT count(*) FROM dw.ref_fx_rates") == "2"


def test_post_load_checks_have_no_error_failures(pg):
    rows = post_checks("run1")
    assert rows, "post-load checks returned nothing"
    assert [r for r in rows if r[1] == "error" and int(r[2]) > 0] == []
    warns = {r[0]: int(r[2]) for r in rows if r[1] == "warn"}
    assert warns["orders_with_unknown_customer"] == 1 and warns["items_with_unknown_product"] == 1


def test_reload_is_idempotent(pg):
    before = {t: q(f"SELECT count(*) FROM dw.{t}") for t in
              ["fact_orders", "fact_order_items", "fact_payments", "fact_reviews", "dim_customers", "dim_products", "dim_sellers", "dim_payment_methods"]}
    run_batch(silver(raw_batch1()), "run1b", "2017-01-31 00:00:00")
    after = {t: q(f"SELECT count(*) FROM dw.{t}") for t in before}
    assert before == after


def test_batch2_scd2_upserts_and_late_status_change(pg):
    run_batch(silver(raw_batch2()), "run2", "2017-02-20 00:00:00")
    # SCD2 customer: u1 moved -> 2 versions, old closed at the new order's purchase time, exactly one current
    rows = q("SELECT city||'|'||valid_from||'|'||valid_to||'|'||is_current FROM dw.dim_customers WHERE customer_unique_id='u1' ORDER BY valid_from")
    old, new = rows.splitlines()
    assert old == "sao paulo|1900-01-01 00:00:00|2017-03-01 09:00:00|false"
    assert new == "rio de janeiro|2017-03-01 09:00:00|9999-12-31 00:00:00|true"
    # point-in-time: old order keeps old version, new order gets new version
    assert q("SELECT c.city FROM dw.fact_orders o JOIN dw.dim_customers c USING (customer_sk) WHERE order_id='o1'") == "sao paulo"
    assert q("SELECT c.city FROM dw.fact_orders o JOIN dw.dim_customers c USING (customer_sk) WHERE order_id='o4'") == "rio de janeiro"
    # SCD2 product: weight change -> new version; new order maps to it, old order's item keeps the old one
    assert q("SELECT count(*) FROM dw.dim_products WHERE product_id='p1'") == "2"
    assert q("SELECT p.weight_g::int FROM dw.fact_order_items i JOIN dw.dim_products p USING (product_sk) WHERE order_id='o4'") == "300"
    assert q("SELECT p.weight_g::int FROM dw.fact_order_items i JOIN dw.dim_products p USING (product_sk) WHERE order_id='o1' AND order_item_id=1") == "225"
    # late status change on existing order is an upsert, not a duplicate
    assert q("SELECT order_status FROM dw.fact_orders WHERE order_id='o2'") == "delivered"
    assert q("SELECT count(*) FROM dw.fact_orders") == "4"
    assert [r for r in post_checks("run2") if r[1] == "error" and int(r[2]) > 0] == []


def test_scd2_rerun_does_not_create_versions(pg):
    run_batch(silver(raw_batch2()), "run2b", "2017-02-21 00:00:00")
    assert q("SELECT count(*) FROM dw.dim_customers WHERE customer_unique_id='u1'") == "2"
    assert q("SELECT count(*) FROM dw.dim_products WHERE product_id='p1'") == "2"


def test_analytics_views_return_data(pg):
    assert int(q("SELECT orders FROM analytics.v_kpi_summary")) == 4
    assert int(q("SELECT count(*) FROM analytics.v_monthly_revenue")) == 2
    assert q("SELECT count(*) FROM analytics.v_monthly_revenue_usd WHERE avg_usd_brl IS NOT NULL") == "2"
    for v in ["v_daily_sales", "v_category_performance", "v_seller_performance", "v_customer_value",
              "v_delivery_performance", "v_payment_mix", "v_pipeline_health"]:
        q(f"SELECT * FROM analytics.{v}")
    assert q("SELECT is_repeat_customer FROM analytics.v_customer_value WHERE customer_unique_id='u1'") == "t"
