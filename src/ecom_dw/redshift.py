"""OPTIONAL cloud serving layer: gold parquet in S3 -> Amazon Redshift via COPY.
Gold = full snapshot of each warehouse table exported by gold.export_gold(). Redshift load is
TRUNCATE + COPY in one transaction per table set (simple and idempotent; see ARCHITECTURE.md for
incremental alternatives). Requires real AWS S3, a Redshift cluster/serverless workgroup and an IAM role."""
from __future__ import annotations

from pathlib import Path

from .config import Settings
from .gold import GOLD_TABLES
from .storage import gold_key


def build_copy_sql(table: str, bucket: str, run_id: str, iam_role_arn: str, region: str) -> str:
    """Pure function (unit-tested). Redshift COPY of a Parquet prefix."""
    prefix = gold_key(table, run_id).rsplit("/", 1)[0]
    return (f"COPY rs_dw.{table} FROM 's3://{bucket}/{prefix}/' IAM_ROLE '{iam_role_arn}' "
            f"FORMAT AS PARQUET")


def connect_redshift(s: Settings):
    import psycopg2

    missing = [k for k in ("redshift_host", "redshift_db", "redshift_user", "redshift_password", "redshift_iam_role_arn")
               if not getattr(s, k)]
    if missing:
        raise RuntimeError(f"Redshift settings missing: {missing}")
    return psycopg2.connect(host=s.redshift_host, port=s.redshift_port, dbname=s.redshift_db,
                            user=s.redshift_user, password=s.redshift_password, connect_timeout=15)


def load_redshift(s: Settings, run_id: str) -> None:
    if s.s3_endpoint_url:
        raise RuntimeError("Redshift COPY needs real AWS S3: unset S3_ENDPOINT_URL (local RustFS is not reachable by Redshift).")
    ddl = (Path(s.sql_dir) / "redshift" / "ddl_redshift.sql").read_text(encoding="utf-8")
    conn = connect_redshift(s)
    try:
        with conn.cursor() as cur:
            cur.execute(ddl)
            for t in GOLD_TABLES:
                cur.execute(f"TRUNCATE rs_dw.{t}")  # note: TRUNCATE commits implicitly in Redshift
                cur.execute(build_copy_sql(t, s.s3_bucket, run_id, s.redshift_iam_role_arn, s.aws_region))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
