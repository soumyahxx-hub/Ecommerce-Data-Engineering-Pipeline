"""PostgreSQL helpers (psycopg2). Transactions: commit on success, rollback on any exception."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from .config import Settings

DDL_FILES = ["ddl/00_schemas_etl.sql", "ddl/10_staging.sql", "ddl/20_warehouse.sql"]
TRANSFORM_FILES = ["transform/10_dim_sellers.sql", "transform/11_dim_customers_scd2.sql",
                   "transform/12_dim_products_scd2.sql", "transform/13_dim_misc.sql",
                   "transform/20_fact_orders.sql", "transform/21_fact_children.sql"]
VIEW_FILES = ["analytics/30_views.sql"]
POST_CHECK_FILE = "quality/post_load_checks.sql"


@contextmanager
def connect(s: Settings):
    import psycopg2  # lazy import

    conn = psycopg2.connect(host=s.pg_host, port=s.pg_port, dbname=s.pg_db, user=s.pg_user,
                            password=s.pg_password, connect_timeout=10)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def run_sql_file(cur, sql_dir: Path, rel: str) -> None:
    cur.execute((Path(sql_dir) / rel).read_text(encoding="utf-8"))


def init_db(s: Settings) -> None:
    """Create schemas, audit tables, staging, warehouse tables, unknown members, dim_date and views (idempotent)."""
    with connect(s) as conn, conn.cursor() as cur:
        for f in DDL_FILES + VIEW_FILES:
            run_sql_file(cur, s.sql_dir, f)


def run_transforms(s: Settings, run_id: str, batch_ts: str) -> None:
    """All warehouse SQL in ONE transaction: either the whole batch lands or nothing does."""
    with connect(s) as conn, conn.cursor() as cur:
        cur.execute("SELECT set_config('etl.run_id', %s, true), set_config('etl.batch_ts', %s, true)",
                    (run_id, batch_ts))
        for f in TRANSFORM_FILES:
            run_sql_file(cur, s.sql_dir, f)


def run_post_checks(s: Settings, run_id: str) -> list[tuple[str, str, int]]:
    with connect(s) as conn, conn.cursor() as cur:
        cur.execute("SELECT set_config('etl.run_id', %s, false)", (run_id,))
        cur.execute((Path(s.sql_dir) / POST_CHECK_FILE).read_text(encoding="utf-8"))
        return [(r[0], r[1], int(r[2])) for r in cur.fetchall()]
