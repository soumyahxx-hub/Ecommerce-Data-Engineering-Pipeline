"""Pipeline execution history, step logs, watermarks, DQ result persistence, freshness check.
Each call uses its own connection/transaction so audit rows survive a failed pipeline transaction."""
from __future__ import annotations

import functools
import time

import pandas as pd

from .config import Settings, get_settings
from .db import connect
from .logging_utils import get_logger, log_event

log = get_logger("ecom_dw.audit")
SOURCE = "olist_orders"


def start_run(s: Settings, run_id: str) -> None:
    with connect(s) as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO etl.pipeline_runs (run_id, status) VALUES (%s, 'running')
                       ON CONFLICT (run_id) DO UPDATE SET status='running', started_at=now(), finished_at=NULL, error_message=NULL""",
                    (run_id,))


def finish_run(s: Settings, run_id: str, status: str, error: str | None = None) -> None:
    with connect(s) as conn, conn.cursor() as cur:
        cur.execute("UPDATE etl.pipeline_runs SET status=%s, finished_at=now(), error_message=%s WHERE run_id=%s",
                    (status, (error or None) and error[:2000], run_id))


def get_watermark(s: Settings, source: str = SOURCE):
    with connect(s) as conn, conn.cursor() as cur:
        cur.execute("SELECT watermark FROM etl.watermarks WHERE source_name=%s", (source,))
        row = cur.fetchone()
    return pd.Timestamp(row[0]) if row else None


def set_watermark(s: Settings, ts, run_id: str, source: str = SOURCE) -> None:
    """Never moves backwards (GREATEST) so a replayed old window cannot rewind the high-water mark."""
    with connect(s) as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO etl.watermarks (source_name, watermark, run_id) VALUES (%s, %s, %s)
                       ON CONFLICT (source_name) DO UPDATE
                       SET watermark = GREATEST(etl.watermarks.watermark, EXCLUDED.watermark),
                           run_id = EXCLUDED.run_id, updated_at = now()""", (source, ts, run_id))


def record_dq(s: Settings, run_id: str, results) -> None:
    with connect(s) as conn, conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO etl.dq_results (run_id, table_name, check_name, severity, passed, failed_rows, total_rows, detail)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            [
                (
                    run_id,
                    r.table,
                    r.check,
                    r.severity,
                    bool(r.passed),
                    int(r.failed_rows),
                    int(r.total_rows),
                    r.detail,
                )
                for r in results
            ],
        )


def audited(step_name: str):
    """Decorator: logs a step to etl.step_log (running -> success/failed) and re-raises failures.
    The wrapped function takes run_id as its first argument and may return a dict with 'rows'."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(run_id: str, *a, **kw):
            s = get_settings()
            with connect(s) as conn, conn.cursor() as cur:
                cur.execute("INSERT INTO etl.step_log (run_id, step, status) VALUES (%s,%s,'running') RETURNING id",
                            (run_id, step_name))
                sid = cur.fetchone()[0]
            t0 = time.time()
            try:
                result = fn(run_id, *a, **kw)
            except Exception as err:
                with connect(s) as conn, conn.cursor() as cur:
                    cur.execute("UPDATE etl.step_log SET status='failed', finished_at=now(), error_message=%s WHERE id=%s",
                                (str(err)[:2000], sid))
                log_event(log, "step_failed", run_id=run_id, step=step_name, error=str(err))
                raise
            rows = result.get("rows") if isinstance(result, dict) else None
            with connect(s) as conn, conn.cursor() as cur:
                cur.execute("UPDATE etl.step_log SET status='success', finished_at=now(), rows_processed=%s WHERE id=%s",
                            (rows, sid))
            log_event(log, "step_succeeded", run_id=run_id, step=step_name, seconds=round(time.time() - t0, 2), rows=rows)
            return result
        return wrapper
    return deco


def check_freshness(s: Settings):
    """Data freshness = age of the last SUCCESSFUL pipeline run (Olist itself is a static 2016-18 dataset)."""
    with connect(s) as conn, conn.cursor() as cur:
        cur.execute("""SELECT extract(epoch FROM (now() - max(finished_at))) / 3600.0
                       FROM etl.pipeline_runs WHERE status='success'""")
        age = cur.fetchone()[0]
    ok = age is not None and age <= s.freshness_max_hours
    return ok, (None if age is None else round(float(age), 2))
