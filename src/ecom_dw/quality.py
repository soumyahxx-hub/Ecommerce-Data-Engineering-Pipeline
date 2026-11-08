"""Silver-layer data quality checks. Severity 'error' blocks the load; 'warn' is recorded only."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from .schemas import PRIMARY_KEYS


class DataQualityError(Exception):
    pass


@dataclass
class CheckResult:
    check: str
    table: str
    severity: str  # error | warn
    passed: bool
    failed_rows: int
    total_rows: int
    detail: str = ""

    def as_dict(self):
        return asdict(self)


def _res(check, table, severity, failed, total, detail=""):
    return CheckResult(check, table, severity, failed == 0, int(failed), int(total), detail)


def run_checks(clean: dict[str, pd.DataFrame], reject_counts: dict[str, int], max_reject_pct: float = 5.0):
    out: list[CheckResult] = []
    orders = clean["orders"]
    out.append(_res("orders_not_empty", "orders", "error", 0 if len(orders) else 1, len(orders)))

    for t, keys in PRIMARY_KEYS.items():
        df = clean.get(t)
        if df is None or t == "fx_rates":
            continue
        out.append(_res("pk_not_null", t, "error", df[keys].isna().any(axis=1).sum(), len(df)))
        out.append(_res("pk_unique", t, "error", df.duplicated(keys).sum(), len(df)))

    for t, n_rej in reject_counts.items():
        total = n_rej + len(clean.get(t, []))
        pct = 100.0 * n_rej / total if total else 0.0
        out.append(CheckResult("reject_ratio", t, "error", pct <= max_reject_pct, int(n_rej), int(total),
                               f"{pct:.2f}% rejected (limit {max_reject_pct}%)"))

    oids = set(orders["order_id"])
    for t in ("order_items", "payments", "reviews"):
        out.append(_res("fk_order_exists", t, "error", (~clean[t]["order_id"].isin(oids)).sum(), len(clean[t])))
    # Missing dimension members map to the 'unknown' member (-1) in the warehouse -> warn only.
    out.append(_res("fk_customer_exists", "orders", "warn", (~orders["customer_id"].isin(set(clean["customers"]["customer_id"]))).sum(), len(orders)))
    it = clean["order_items"]
    out.append(_res("fk_product_exists", "order_items", "warn", (~it["product_id"].isin(set(clean["products"]["product_id"]))).sum(), len(it)))
    out.append(_res("fk_seller_exists", "order_items", "warn", (~it["seller_id"].isin(set(clean["sellers"]["seller_id"]))).sum(), len(it)))

    d, p = orders["delivered_customer_ts"], orders["purchase_ts"]
    out.append(_res("delivered_not_before_purchase", "orders", "warn", (d < p).sum(), len(orders)))
    out.append(_res("orders_without_items", "orders", "warn", (~orders["order_id"].isin(set(it["order_id"]))).sum(), len(orders)))
    return out


def raise_on_errors(results: list[CheckResult]):
    bad = [r for r in results if r.severity == "error" and not r.passed]
    if bad:
        raise DataQualityError("; ".join(f"{r.table}.{r.check} failed_rows={r.failed_rows} {r.detail}" for r in bad))
