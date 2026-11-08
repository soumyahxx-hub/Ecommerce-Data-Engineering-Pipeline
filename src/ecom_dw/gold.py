"""Gold layer: export curated warehouse tables to Parquet in object storage (BI / Redshift ready)."""
from __future__ import annotations

import pandas as pd

from .config import Settings
from .db import connect
from .storage import get_store, gold_key, put_parquet

GOLD_TABLES = ["dim_date", "dim_customers", "dim_products", "dim_sellers", "dim_payment_methods",
               "fact_orders", "fact_order_items", "fact_payments", "fact_reviews"]


def export_gold(s: Settings, run_id: str) -> dict[str, int]:
    store, counts = get_store(s), {}
    with connect(s) as conn, conn.cursor() as cur:
        for t in GOLD_TABLES:
            cur.execute(f"SELECT * FROM dw.{t}")
            cols = [d[0] for d in cur.description]
            df = pd.DataFrame(cur.fetchall(), columns=cols)
            put_parquet(store, gold_key(t, run_id), df)
            counts[t] = len(df)
    return counts
