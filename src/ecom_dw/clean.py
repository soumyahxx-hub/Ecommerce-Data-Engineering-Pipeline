"""Silver layer: cleaning, standardisation, dedup and reject handling.
Every clean_* returns (clean_df, rejects_df); rejects carry a `_reject_reason` column."""
from __future__ import annotations

import pandas as pd

from .schemas import (BRAZIL_LAT, BRAZIL_LNG, ORDER_STATUSES, PRIMARY_KEYS, RENAMES, SILVER_COLUMNS)


def _s(series: pd.Series) -> pd.Series:
    """Strip strings; empty -> None."""
    out = series.astype("object")
    out = out.where(series.notna(), None)
    return out.map(lambda v: (v.strip() or None) if isinstance(v, str) else v)


def _prep(raw: pd.DataFrame, table: str) -> pd.DataFrame:
    df = raw.copy()
    for c in df.columns:
        df[c] = _s(df[c])
    return df.rename(columns=RENAMES.get(table, {}))


def _reject(df: pd.DataFrame, mask: pd.Series, reason: str, rej: list):
    mask = mask.fillna(True).astype(bool)
    if mask.any():
        bad = df[mask].copy()
        bad["_reject_reason"] = reason
        rej.append(bad)
    return df[~mask]


def _dedupe(df: pd.DataFrame, keys: list[str], rej: list, keep: str = "last"):
    return _reject(df, df.duplicated(keys, keep=keep), "duplicate_key", rej)


def _finish(df: pd.DataFrame, table: str, rej: list):
    clean = df[SILVER_COLUMNS[table]].reset_index(drop=True)
    rejects = pd.concat(rej, ignore_index=True) if rej else pd.DataFrame(columns=["_reject_reason"])
    return clean, rejects


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _int(s: pd.Series) -> pd.Series:
    return _num(s).round().astype("Int64")


def _zip(s: pd.Series) -> pd.Series:
    return s.map(lambda v: str(v).zfill(5) if v is not None and v == v else None)


def clean_orders(raw: pd.DataFrame):
    df, rej = _prep(raw, "orders"), []
    for c in ["purchase_ts", "approved_ts", "delivered_carrier_ts", "delivered_customer_ts", "estimated_delivery_ts"]:
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df["order_status"] = df["order_status"].str.lower()
    df = _reject(df, df["order_id"].isna(), "null_order_id", rej)
    df = _reject(df, df["customer_id"].isna(), "null_customer_id", rej)
    df = _reject(df, df["purchase_ts"].isna(), "invalid_purchase_ts", rej)
    df = _reject(df, ~df["order_status"].isin(ORDER_STATUSES), "invalid_order_status", rej)
    df = _dedupe(df, PRIMARY_KEYS["orders"], rej)
    return _finish(df, "orders", rej)


def clean_order_items(raw: pd.DataFrame):
    df, rej = _prep(raw, "order_items"), []
    df["order_item_id"] = _int(df["order_item_id"])
    df["shipping_limit_ts"] = pd.to_datetime(df["shipping_limit_ts"], errors="coerce")
    df["price"], df["freight_value"] = _num(df["price"]), _num(df["freight_value"])
    df["freight_value"] = df["freight_value"].fillna(0.0)
    df = _reject(df, df["order_id"].isna() | df["order_item_id"].isna(), "null_key", rej)
    df = _reject(df, df["price"].isna() | (df["price"] < 0) | (df["freight_value"] < 0), "invalid_amount", rej)
    df = _dedupe(df, PRIMARY_KEYS["order_items"], rej)
    return _finish(df, "order_items", rej)


def clean_payments(raw: pd.DataFrame):
    df, rej = _prep(raw, "payments"), []
    df["payment_sequential"], df["payment_installments"] = _int(df["payment_sequential"]), _int(df["payment_installments"])
    df["payment_value"] = _num(df["payment_value"])
    df["payment_type"] = df["payment_type"].str.lower().fillna("not_defined")
    df = _reject(df, df["order_id"].isna() | df["payment_sequential"].isna(), "null_key", rej)
    df = _reject(df, df["payment_value"].isna() | (df["payment_value"] < 0), "invalid_amount", rej)
    df = _dedupe(df, PRIMARY_KEYS["payments"], rej)
    return _finish(df, "payments", rej)


def clean_reviews(raw: pd.DataFrame):
    df, rej = _prep(raw, "reviews"), []
    df["review_score"] = _int(df["review_score"])
    df["creation_ts"] = pd.to_datetime(df["creation_ts"], errors="coerce")
    df["answer_ts"] = pd.to_datetime(df["answer_ts"], errors="coerce")
    df = _reject(df, df["review_id"].isna() | df["order_id"].isna(), "null_key", rej)
    df = _reject(df, ~df["review_score"].between(1, 5), "invalid_review_score", rej)
    df = df.sort_values("answer_ts", na_position="first", kind="stable")  # keep latest answer
    df = _dedupe(df, PRIMARY_KEYS["reviews"], rej)
    return _finish(df, "reviews", rej)


def _clean_party(raw: pd.DataFrame, table: str, key: str, extra_required: list[str] | None = None):
    df, rej = _prep(raw, table), []
    df["zip_code_prefix"] = _zip(df["zip_code_prefix"])
    df["city"] = df["city"].str.lower()
    df["state"] = df["state"].str.upper()
    df = _reject(df, df[key].isna(), f"null_{key}", rej)
    for c in extra_required or []:
        df = _reject(df, df[c].isna(), f"null_{c}", rej)
    df = _dedupe(df, PRIMARY_KEYS[table], rej)
    return _finish(df, table, rej)


def clean_customers(raw):
    return _clean_party(raw, "customers", "customer_id", ["customer_unique_id"])


def clean_sellers(raw):
    return _clean_party(raw, "sellers", "seller_id")


def clean_products(raw: pd.DataFrame, translation: pd.DataFrame):
    df, rej = _prep(raw, "products"), []
    for c in ["name_length", "description_length", "photos_qty"]:
        df[c] = _int(df[c])
    for c in ["weight_g", "length_cm", "height_cm", "width_cm"]:
        df[c] = _num(df[c])
    for c in ["name_length", "description_length", "photos_qty", "weight_g", "length_cm", "height_cm", "width_cm"]:
        df[c] = df[c].where(~(df[c] < 0), pd.NA)  # impossible negatives -> NULL
    df["category_name_pt"] = df["category_name_pt"].str.lower()
    tr = _prep(translation, "category_translation").drop_duplicates("product_category_name")
    mapping = dict(zip(tr["product_category_name"].str.lower(), tr["product_category_name_english"]))
    df["category_name_en"] = df["category_name_pt"].map(mapping)
    df["category_name_en"] = df["category_name_en"].fillna(df["category_name_pt"]).fillna("unknown")
    df = _reject(df, df["product_id"].isna(), "null_product_id", rej)
    df = _dedupe(df, PRIMARY_KEYS["products"], rej)
    return _finish(df, "products", rej)


def _mode(s: pd.Series):
    m = s.dropna().mode()
    return m.iloc[0] if len(m) else None


def clean_geolocation(raw: pd.DataFrame):
    """Raw file has many points per zip prefix -> aggregate to one row per prefix (mean lat/lng, modal city)."""
    df, rej = _prep(raw, "geolocation"), []
    df["zip_code_prefix"] = _zip(df["zip_code_prefix"])
    df["lat"], df["lng"] = _num(df["lat"]), _num(df["lng"])
    df["city"], df["state"] = df["city"].str.lower(), df["state"].str.upper()
    df = _reject(df, df["zip_code_prefix"].isna(), "null_zip", rej)
    bad = ~(df["lat"].between(*BRAZIL_LAT) & df["lng"].between(*BRAZIL_LNG))
    df = _reject(df, bad, "coordinates_outside_brazil", rej)
    agg = (df.groupby("zip_code_prefix")
             .agg(lat=("lat", "mean"), lng=("lng", "mean"), city=("city", _mode), state=("state", _mode))
             .reset_index())
    return _finish(agg, "geolocation", rej)


def clean_fx(raw_json: dict, base: str = "USD", quote: str = "BRL"):
    rows = []
    for d, rates in (raw_json.get("rates") or {}).items():
        if quote in rates:
            rows.append({"rate_date": pd.to_datetime(d).date(), "base_currency": raw_json.get("base", base),
                         "quote_currency": quote, "rate": float(rates[quote])})
    df = pd.DataFrame(rows, columns=SILVER_COLUMNS["fx_rates"])
    return df, pd.DataFrame(columns=["_reject_reason"])


def enforce_referential_integrity(clean: dict, rejects: dict):
    """Child rows whose order is not a valid silver order are quarantined (cannot be attributed)."""
    valid = set(clean["orders"]["order_id"])
    for t in ("order_items", "payments", "reviews"):
        df = clean[t]
        orphan = ~df["order_id"].isin(valid)
        if orphan.any():
            bad = df[orphan].copy()
            bad["_reject_reason"] = "orphan_order_id"
            rejects[t] = pd.concat([rejects[t], bad], ignore_index=True)
            clean[t] = df[~orphan].reset_index(drop=True)
    return clean, rejects


def run_clean(raw: dict[str, pd.DataFrame]):
    """raw: bronze frames keyed by logical name -> (clean, rejects) dicts."""
    clean, rejects = {}, {}
    steps = {
        "orders": lambda: clean_orders(raw["orders"]),
        "order_items": lambda: clean_order_items(raw["order_items"]),
        "payments": lambda: clean_payments(raw["payments"]),
        "reviews": lambda: clean_reviews(raw["reviews"]),
        "customers": lambda: clean_customers(raw["customers"]),
        "sellers": lambda: clean_sellers(raw["sellers"]),
        "products": lambda: clean_products(raw["products"], raw["category_translation"]),
        "geolocation": lambda: clean_geolocation(raw["geolocation"]),
    }
    for name, fn in steps.items():
        clean[name], rejects[name] = fn()
    return enforce_referential_integrity(clean, rejects)
