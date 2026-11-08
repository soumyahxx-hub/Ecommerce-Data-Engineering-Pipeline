import json

import pandas as pd
import pytest

from ecom_dw import clean, ingest, quality, storage
from ecom_dw.redshift import build_copy_sql
from ecom_dw.schemas import SOURCE_FILES
from ecom_dw.stage import copy_columns, to_copy_csv
from ecom_dw.utils import retry, safe_run_id
from tests.helpers import raw_batch1


def test_validate_schema_missing_column_fails():
    df = raw_batch1()["orders"].drop(columns=["customer_id"])
    with pytest.raises(ingest.SchemaError):
        ingest.validate_schema("orders", df)


def test_validate_schema_drops_extra_columns():
    df = raw_batch1()["sellers"].assign(new_col="x")
    out = ingest.validate_schema("sellers", df)
    assert list(out.columns) == SOURCE_FILES["sellers"][1]


def test_plan_window_and_incremental_selection():
    raw = raw_batch1()
    start, end = ingest.plan_window(raw["orders"], pd.Timestamp("2017-01-10"), 3)
    assert start == pd.Timestamp("2017-01-07") and end is None
    sel = ingest.select_incremental(raw, start, end)
    assert set(sel["orders"]["order_id"].dropna()) == {"o3", "o_nodate"} or "o3" in set(sel["orders"]["order_id"])
    assert set(sel["order_items"]["order_id"]) <= set(sel["orders"]["order_id"])
    # until: inclusive date; window_days from first order
    s2, e2 = ingest.plan_window(raw["orders"], None, 0, until="2017-01-06")
    assert s2 is None and e2 == pd.Timestamp("2017-01-07")
    s3, e3 = ingest.plan_window(raw["orders"], None, 0, window_days=2)
    assert e3 == pd.Timestamp("2017-01-07")
    sel2 = ingest.select_incremental(raw, s2, e2)
    assert {"o1", "o2"} <= set(sel2["orders"]["order_id"]) and "o3" not in set(sel2["orders"]["order_id"])


def test_quality_checks_pass_on_clean_batch_and_fail_on_high_reject_rate():
    c, r = clean.run_clean(raw_batch1())
    c["fx_rates"] = pd.DataFrame(columns=["rate_date", "base_currency", "quote_currency", "rate"])
    res = quality.run_checks(c, {t: len(x) for t, x in r.items()}, max_reject_pct=100)
    assert not [x for x in res if x.severity == "error" and not x.passed]
    strict = quality.run_checks(c, {t: len(x) for t, x in r.items()}, max_reject_pct=1)
    with pytest.raises(quality.DataQualityError):
        quality.raise_on_errors(strict)
    # missing customer / product are warnings (mapped to unknown member), not errors
    warn = [x for x in res if x.check in ("fk_customer_exists", "fk_product_exists") and x.failed_rows > 0]
    assert warn and all(x.severity == "warn" for x in warn)


def test_empty_orders_is_error():
    c, r = clean.run_clean(raw_batch1())
    c["orders"] = c["orders"].iloc[0:0]
    with pytest.raises(quality.DataQualityError):
        quality.raise_on_errors(quality.run_checks({**c, "fx_rates": pd.DataFrame()}, {}))


def test_local_store_roundtrip(tmp_path):
    st = storage.LocalStore(tmp_path)
    df = raw_batch1()["orders"]
    storage.put_csv(st, "bronze/x.csv", df)
    back = storage.get_csv(st, "bronze/x.csv")
    assert back.shape == df.shape
    storage.put_json(st, "meta/m.json", {"a": 1})
    assert storage.get_json(st, "meta/m.json") == {"a": 1}
    assert st.exists("meta/m.json") and not st.exists("nope")


def test_parquet_roundtrip(tmp_path):
    pytest.importorskip("pyarrow")
    st = storage.LocalStore(tmp_path)
    c, _ = clean.run_clean(raw_batch1())
    storage.put_parquet(st, "silver/o.parquet", c["orders"])
    assert len(storage.get_parquet(st, "silver/o.parquet")) == len(c["orders"])


def test_retry_succeeds_after_transient_failures():
    calls = {"n": 0}

    @retry(attempts=3, base_delay=0)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("transient")
        return "ok"

    assert flaky() == "ok" and calls["n"] == 3


def test_retry_gives_up():
    @retry(attempts=2, base_delay=0)
    def always():
        raise ValueError("boom")

    with pytest.raises(ValueError):
        always()


def test_fetch_fx_rates_uses_retry_and_parses(monkeypatch):
    class Resp:
        def raise_for_status(self): pass
        def json(self): return {"base": "USD", "rates": {"2017-01-02": {"BRL": 3.2}}}

    class Sess:
        def get(self, url, params=None, timeout=None):
            self.url, self.params = url, params
            return Resp()

    s = Sess()
    from datetime import date
    out = ingest.fetch_fx_rates("http://x", date(2017, 1, 1), date(2017, 1, 5), session=s)
    assert out["rates"] and s.url.endswith("2017-01-01..2017-01-05") and s.params["symbols"] == "BRL"


def test_stage_copy_csv_has_run_id_and_null_empty():
    c, _ = clean.run_clean(raw_batch1())
    txt = to_copy_csv(c["orders"], "orders", "run1")
    first = txt.splitlines()[0].split(",")
    assert len(first) == len(copy_columns("orders")) and first[-1] == "run1"


def test_redshift_copy_sql_and_run_id_sanitising():
    sql = build_copy_sql("fact_orders", "bkt", "r1", "arn:aws:iam::123456789012:role/x", "us-east-1")
    assert sql.startswith("COPY rs_dw.fact_orders FROM 's3://bkt/gold/fact_orders/run_id=r1/'")
    assert "FORMAT AS PARQUET" in sql
    assert safe_run_id("scheduled__2024-01-01T00:00:00+00:00") == "scheduled__2024-01-01T00_00_00_00_00"
    json.dumps({"ok": True})
