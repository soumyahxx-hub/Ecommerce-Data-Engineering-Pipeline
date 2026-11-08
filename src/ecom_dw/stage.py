"""Load silver DataFrames into PostgreSQL staging via COPY (fast bulk path)."""
from __future__ import annotations

import io

import pandas as pd

from .schemas import SILVER_COLUMNS


def copy_columns(table: str) -> list[str]:
    return SILVER_COLUMNS[table] + ["_run_id"]


def to_copy_csv(df: pd.DataFrame, table: str, run_id: str) -> str:
    """CSV text for COPY ... CSV (no header). Unquoted empty field == NULL."""
    out = df[SILVER_COLUMNS[table]].copy()
    out["_run_id"] = run_id
    return out.to_csv(index=False, header=False)


def load_staging(conn, run_id: str, frames: dict[str, pd.DataFrame]) -> dict[str, int]:
    """TRUNCATE + COPY every staging table inside the caller's transaction (all-or-nothing)."""
    counts = {}
    with conn.cursor() as cur:
        for table, df in frames.items():
            cur.execute(f"TRUNCATE stg.{table}")
            if len(df):
                cols = ", ".join(copy_columns(table))
                cur.copy_expert(f"COPY stg.{table} ({cols}) FROM STDIN WITH (FORMAT csv)",
                                io.StringIO(to_copy_csv(df, table, run_id)))
            counts[table] = len(df)
    return counts
