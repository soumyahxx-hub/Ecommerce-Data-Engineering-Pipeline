"""Pipeline steps (called by Airflow tasks and by the CLI).

Flow: ingest(bronze) -> silver(clean+DQ) -> stage(COPY) -> warehouse(SQL, 1 txn) -> post_checks
      -> commit_watermark -> gold(parquet) -> [redshift] ; every step is audited in etl.step_log.
Steps communicate only through object storage + the run manifest, so each can run in a separate process/task."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

import pandas as pd

from . import audit, clean, db, ingest, quality, stage, storage
from .config import get_settings
from .logging_utils import get_logger, log_event
from .schemas import SILVER_COLUMNS, SOURCE_FILES
from .utils import safe_run_id

log = get_logger("ecom_dw.pipeline")
FX_SOURCE = "fx"


def _clean_opt(v):
    return None if v in (None, "", "None", "null") else v


# ------------------------------------------------------------------------------------------------
def step_init_db() -> None:
    db.init_db(get_settings())


def step_start_run(run_id: str) -> None:
    audit.start_run(get_settings(), run_id)


@audit.audited("ingest_bronze")
def step_ingest(run_id: str, until=None, window_days=None, data_dir=None) -> dict:
    s, store = get_settings(), storage.get_store(get_settings())
    until, window_days = _clean_opt(until), _clean_opt(window_days)
    raw = {n: ingest.validate_schema(n, ingest.read_source(data_dir or s.raw_data_dir, n)) for n in SOURCE_FILES}
    wm = audit.get_watermark(s)
    start, end = ingest.plan_window(raw["orders"], wm, s.lookback_days, until,
                                    int(window_days) if window_days else None)
    sel = ingest.select_incremental(raw, start, end)
    manifest = {"run_id": run_id, "watermark_before": wm, "window_start": start, "window_end": end,
                "max_purchase_ts": ingest.max_purchase_ts(sel["orders"]), "rows": {}, "fx_key": None}
    for name, df in sel.items():
        storage.put_csv(store, storage.bronze_key(name, run_id), df)
        manifest["rows"][name] = len(df)

    if len(sel["orders"]):  # REST API source (soft dependency: failure is logged, pipeline continues)
        ts = pd.to_datetime(sel["orders"]["order_purchase_timestamp"], errors="coerce").dropna()
        if len(ts):
            try:
                fx = ingest.fetch_fx_rates(s.fx_api_url, ts.min().date(), ts.max().date(), s.http_retries)
                storage.put_json(store, storage.bronze_fx_key(run_id), fx)
                manifest["fx_key"] = storage.bronze_fx_key(run_id)
            except Exception as err:  # noqa: BLE001
                log_event(log, "fx_api_unavailable_continuing", error=str(err))
    storage.put_json(store, storage.manifest_key(run_id), manifest)
    log_event(log, "bronze_written", run_id=run_id, rows=manifest["rows"])
    return {"rows": manifest["rows"]["orders"]}


def _manifest(store, run_id):
    return storage.get_json(store, storage.manifest_key(run_id))


@audit.audited("silver_clean_validate")
def step_silver(run_id: str) -> dict:
    s, store = get_settings(), storage.get_store(get_settings())
    m = _manifest(store, run_id)
    if m["rows"]["orders"] == 0:
        log_event(log, "no_new_orders_skipping", run_id=run_id)
        return {"rows": 0}
    raw = {n: storage.get_csv(store, storage.bronze_key(n, run_id)) for n in m["rows"]}
    cleaned, rejects = clean.run_clean(raw)
    fx_clean = clean.clean_fx(storage.get_json(store, m["fx_key"]))[0] if m.get("fx_key") else \
        pd.DataFrame(columns=SILVER_COLUMNS["fx_rates"])
    cleaned["fx_rates"] = fx_clean

    results = quality.run_checks(cleaned, {t: len(r) for t, r in rejects.items()}, s.dq_max_reject_pct)
    audit.record_dq(s, run_id, results)               # persisted even if we are about to fail
    for t, r in rejects.items():
        if len(r):
            storage.put_csv(store, storage.rejects_key(t, run_id), r)
    storage.put_json(store, f"meta/dq/run_id={run_id}/dq.json", [r.as_dict() for r in results])
    quality.raise_on_errors(results)
    for t, df in cleaned.items():
        storage.put_parquet(store, storage.silver_key(t, run_id), df)
    return {"rows": len(cleaned["orders"])}


@audit.audited("load_staging")
def step_stage(run_id: str) -> dict:
    s, store = get_settings(), storage.get_store(get_settings())
    if _manifest(store, run_id)["rows"]["orders"] == 0:
        return {"rows": 0}
    frames = {t: storage.get_parquet(store, storage.silver_key(t, run_id)) for t in SILVER_COLUMNS}
    with db.connect(s) as conn:
        counts = stage.load_staging(conn, run_id, frames)
    return {"rows": counts["orders"]}


@audit.audited("transform_warehouse")
def step_warehouse(run_id: str) -> dict:
    s, store = get_settings(), storage.get_store(get_settings())
    m = _manifest(store, run_id)
    if m["rows"]["orders"] == 0:
        return {"rows": 0}
    db.run_transforms(s, run_id, datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" "))
    return {"rows": m["rows"]["orders"]}


@audit.audited("post_load_checks")
def step_post_checks(run_id: str) -> dict:
    s, store = get_settings(), storage.get_store(get_settings())
    if _manifest(store, run_id)["rows"]["orders"] == 0:
        return {"rows": 0}
    rows = db.run_post_checks(s, run_id)
    results = [quality.CheckResult(n, "warehouse", sev, c == 0, c, 0) for n, sev, c in rows]
    audit.record_dq(s, run_id, results)
    quality.raise_on_errors(results)
    return {"rows": len(rows)}


@audit.audited("commit_watermark")
def step_commit_watermark(run_id: str) -> dict:
    """Advance the high-water mark ONLY after the batch is loaded and verified."""
    s, store = get_settings(), storage.get_store(get_settings())
    m = _manifest(store, run_id)
    if m.get("max_purchase_ts"):
        audit.set_watermark(s, pd.Timestamp(m["max_purchase_ts"]).to_pydatetime(), run_id)
    return {"rows": 0}


@audit.audited("export_gold")
def step_gold(run_id: str) -> dict:
    from .gold import export_gold

    counts = export_gold(get_settings(), run_id)
    return {"rows": sum(counts.values())}


@audit.audited("load_redshift")
def step_redshift(run_id: str) -> dict:
    from .redshift import load_redshift

    load_redshift(get_settings(), run_id)
    return {"rows": 0}


def step_finish_run(run_id: str, status: str = "success", error: str | None = None) -> None:
    audit.finish_run(get_settings(), run_id, status, error)


def run_all(run_id: str | None = None, until=None, window_days=None, data_dir=None) -> str:
    run_id = safe_run_id(run_id or datetime.now(timezone.utc).strftime("manual_%Y%m%dT%H%M%S"))
    s = get_settings()
    step_init_db()
    step_start_run(run_id)
    try:
        step_ingest(run_id, until, window_days, data_dir)
        step_silver(run_id)
        step_stage(run_id)
        step_warehouse(run_id)
        step_post_checks(run_id)
        step_commit_watermark(run_id)
        step_gold(run_id)
        if s.enable_redshift:
            step_redshift(run_id)
    except Exception as err:  # noqa: BLE001
        step_finish_run(run_id, "failed", str(err))
        raise
    step_finish_run(run_id, "success")
    log_event(log, "pipeline_succeeded", run_id=run_id)
    return run_id


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="ecom_dw.pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db")
    r = sub.add_parser("run", help="run the full pipeline")
    r.add_argument("--run-id")
    r.add_argument("--until", help="YYYY-MM-DD, inclusive upper bound on purchase date (simulate daily batches)")
    r.add_argument("--window-days", type=int, help="process N days after the watermark (or after first order)")
    r.add_argument("--data-dir")
    sub.add_parser("freshness")
    a = p.parse_args(argv)
    if a.cmd == "init-db":
        step_init_db()
        print("Database initialised.")
    elif a.cmd == "run":
        print("run_id:", run_all(a.run_id, a.until, a.window_days, a.data_dir))
    elif a.cmd == "freshness":
        ok, age = audit.check_freshness(get_settings())
        print({"fresh": ok, "hours_since_last_success": age})
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
