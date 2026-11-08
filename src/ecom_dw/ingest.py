"""Extraction: CSV sources, schema validation, incremental window selection, REST API (FX rates)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from .logging_utils import get_logger, log_event
from .schemas import SOURCE_FILES
from .utils import retry

log = get_logger("ecom_dw.ingest")


class SchemaError(Exception):
    pass


def read_source(data_dir: Path, name: str) -> pd.DataFrame:
    """Read a raw CSV as strings (no type coercion in bronze)."""
    filename, _ = SOURCE_FILES[name]
    path = Path(data_dir) / filename
    if not path.exists():
        raise FileNotFoundError(f"Missing source file: {path}. See SETUP_GUIDE.md (dataset setup).")
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])


def validate_schema(name: str, df: pd.DataFrame) -> pd.DataFrame:
    """Missing expected columns -> SchemaError. Unexpected extra columns -> warned and dropped (schema drift)."""
    expected = SOURCE_FILES[name][1]
    missing = [c for c in expected if c not in df.columns]
    if missing:
        raise SchemaError(f"{name}: missing columns {missing}")
    extra = [c for c in df.columns if c not in expected]
    if extra:
        log_event(log, "schema_drift_extra_columns_dropped", table=name, columns=extra)
    return df[expected].copy()


def plan_window(orders: pd.DataFrame, watermark: pd.Timestamp | None, lookback_days: int,
                until: str | date | None = None, window_days: int | None = None):
    """Return [start, end) bounds on order_purchase_timestamp (None = unbounded).

    start = watermark - lookback (re-reads recent orders so late status changes / late arrivals are caught;
            loads are upserts so the overlap is harmless).
    end   = day after `until` (inclusive date), or base + window_days (simulates daily batches / backfills).
    """
    ts = pd.to_datetime(orders["order_purchase_timestamp"], errors="coerce")
    start = pd.Timestamp(watermark) - timedelta(days=lookback_days) if watermark is not None else None
    end = None
    if until:
        end = pd.Timestamp(until).normalize() + timedelta(days=1)
    elif window_days:
        base = start if start is not None else ts.min().normalize()
        end = base + timedelta(days=int(window_days))
    return start, end


def select_incremental(frames: dict[str, pd.DataFrame], start, end) -> dict[str, pd.DataFrame]:
    """Filter orders to the window, then keep only the children / dimensions those orders reference.
    Unparseable purchase timestamps are kept so they surface as rejects in silver instead of vanishing."""
    orders = frames["orders"]
    ts = pd.to_datetime(orders["order_purchase_timestamp"], errors="coerce")
    keep = ts.isna()
    ok = ts.notna()
    if start is not None:
        ok &= ts >= start
    if end is not None:
        ok &= ts < end
    orders = orders[keep | ok]
    ids = set(orders["order_id"].dropna())
    items = frames["order_items"]
    items = items[items["order_id"].isin(ids)]
    out = {
        "orders": orders,
        "order_items": items,
        "payments": frames["payments"][frames["payments"]["order_id"].isin(ids)],
        "reviews": frames["reviews"][frames["reviews"]["order_id"].isin(ids)],
        "customers": frames["customers"][frames["customers"]["customer_id"].isin(set(orders["customer_id"].dropna()))],
        "products": frames["products"][frames["products"]["product_id"].isin(set(items["product_id"].dropna()))],
        "sellers": frames["sellers"][frames["sellers"]["seller_id"].isin(set(items["seller_id"].dropna()))],
        "geolocation": frames["geolocation"],            # reference snapshot
        "category_translation": frames["category_translation"],  # reference snapshot
    }
    return out


def max_purchase_ts(orders: pd.DataFrame):
    ts = pd.to_datetime(orders["order_purchase_timestamp"], errors="coerce")
    return None if ts.dropna().empty else ts.max()


def fetch_fx_rates(base_url: str, start: date, end: date, retries: int = 3,
                   base: str = "USD", quote: str = "BRL", session=None) -> dict:
    """REST ingestion example: daily USD->BRL rates (Frankfurter public API, no key needed)."""
    import requests

    sess = session or requests.Session()

    @retry(attempts=retries, base_delay=1.0, exceptions=(requests.RequestException,))
    def _get():
        resp = sess.get(f"{base_url}/{start.isoformat()}..{end.isoformat()}",
                        params={"base": base, "symbols": quote}, timeout=30)
        resp.raise_for_status()
        return resp.json()

    return _get()
