"""Object storage abstraction: S3Store (RustFS or AWS S3) and LocalStore (folder; tests / no-Docker mode).
Layout (one bucket, layer prefixes): bronze/ silver/ rejects/ gold/ meta/"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd

from .config import Settings
from .utils import retry


class LocalStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def put_bytes(self, key: str, data: bytes) -> None:
        p = self.root / key
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get_bytes(self, key: str) -> bytes:
        return (self.root / key).read_bytes()

    def exists(self, key: str) -> bool:
        return (self.root / key).exists()


class S3Store:
    def __init__(self, bucket: str, endpoint_url: str | None, region: str):
        import boto3  # lazy: unit tests do not need boto3
        from botocore.config import Config

        self.bucket = bucket
        client_kwargs = {"endpoint_url": endpoint_url, "region_name": region}
        if endpoint_url:
            # RustFS's local endpoint uses path-style, SigV4 S3 requests.
            client_kwargs["config"] = Config(signature_version="s3v4", s3={"addressing_style": "path"})
        self.client = boto3.client("s3", **client_kwargs)  # creds from env/role

    @retry(attempts=3, base_delay=1.0)
    def put_bytes(self, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)

    @retry(attempts=3, base_delay=1.0)
    def get_bytes(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False


def get_store(s: Settings):
    if s.storage_backend == "local":
        return LocalStore(s.local_store_dir)
    return S3Store(s.s3_bucket, s.s3_endpoint_url, s.aws_region)


# ---- key helpers -------------------------------------------------------------------------------
def bronze_key(table: str, run_id: str) -> str:
    return f"bronze/olist/{table}/run_id={run_id}/{table}.csv"


def bronze_fx_key(run_id: str) -> str:
    return f"bronze/api/fx_rates/run_id={run_id}/fx_rates.json"


def silver_key(table: str, run_id: str) -> str:
    return f"silver/{table}/run_id={run_id}/{table}.parquet"


def rejects_key(table: str, run_id: str) -> str:
    return f"rejects/{table}/run_id={run_id}/rejects.csv"


def gold_key(table: str, run_id: str) -> str:
    return f"gold/{table}/run_id={run_id}/{table}.parquet"


def manifest_key(run_id: str) -> str:
    return f"meta/manifests/run_id={run_id}/manifest.json"


# ---- (de)serialisation -------------------------------------------------------------------------
def put_csv(store, key: str, df: pd.DataFrame) -> None:
    store.put_bytes(key, df.to_csv(index=False).encode("utf-8"))


def get_csv(store, key: str) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(store.get_bytes(key)), dtype=str, keep_default_na=False, na_values=[""])


def put_parquet(store, key: str, df: pd.DataFrame) -> None:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False, engine="pyarrow")
    store.put_bytes(key, buf.getvalue())


def get_parquet(store, key: str) -> pd.DataFrame:
    return pd.read_parquet(io.BytesIO(store.get_bytes(key)), engine="pyarrow")


def put_json(store, key: str, obj) -> None:
    store.put_bytes(key, json.dumps(obj, default=str, indent=2).encode("utf-8"))


def get_json(store, key: str):
    return json.loads(store.get_bytes(key).decode("utf-8"))
