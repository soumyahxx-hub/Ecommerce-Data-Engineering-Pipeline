"""Environment-driven configuration. No secrets in code."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # optional in containers where env is injected
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

ROOT = Path(os.environ.get("PROJECT_ROOT") or Path(__file__).resolve().parents[2])


def _path(value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else ROOT / p


@dataclass(frozen=True)
class Settings:
    pg_host: str
    pg_port: int
    pg_db: str
    pg_user: str
    pg_password: str
    storage_backend: str
    s3_endpoint_url: str | None
    s3_bucket: str
    aws_region: str
    local_store_dir: Path
    raw_data_dir: Path
    sql_dir: Path
    lookback_days: int
    dq_max_reject_pct: float
    freshness_max_hours: float
    fx_api_url: str
    http_retries: int
    enable_redshift: bool
    redshift_host: str | None
    redshift_port: int
    redshift_db: str | None
    redshift_user: str | None
    redshift_password: str | None
    redshift_iam_role_arn: str | None


def get_settings() -> Settings:
    e = os.environ.get
    return Settings(
        pg_host=e("POSTGRES_HOST", "localhost"),
        pg_port=int(e("POSTGRES_PORT", "5432")),
        pg_db=e("POSTGRES_DB", "ecom_dw"),
        pg_user=e("POSTGRES_USER", "s0umya404"),
        pg_password=e("POSTGRES_PASSWORD", ""),
        storage_backend=e("STORAGE_BACKEND", "s3").lower(),
        s3_endpoint_url=e("S3_ENDPOINT_URL") or None,
        s3_bucket=e("S3_BUCKET", "ecom-lake"),
        aws_region=e("AWS_DEFAULT_REGION", "us-east-1"),
        local_store_dir=_path(e("LOCAL_STORE_DIR", "data/local_lake")),
        raw_data_dir=_path(e("RAW_DATA_DIR", "data/raw/olist")),
        sql_dir=_path(e("SQL_DIR", "sql")),
        lookback_days=int(e("LOOKBACK_DAYS", "7")),
        dq_max_reject_pct=float(e("DQ_MAX_REJECT_PCT", "5")),
        freshness_max_hours=float(e("FRESHNESS_MAX_HOURS", "26")),
        fx_api_url=e("FX_API_URL", "https://api.frankfurter.dev/v1").rstrip("/"),
        http_retries=int(e("HTTP_RETRIES", "3")),
        enable_redshift=e("ENABLE_REDSHIFT", "false").lower() == "true",
        redshift_host=e("REDSHIFT_HOST") or None,
        redshift_port=int(e("REDSHIFT_PORT", "5439")),
        redshift_db=e("REDSHIFT_DB") or None,
        redshift_user=e("REDSHIFT_USER") or None,
        redshift_password=e("REDSHIFT_PASSWORD") or None,
        redshift_iam_role_arn=e("REDSHIFT_IAM_ROLE_ARN") or None,
    )
