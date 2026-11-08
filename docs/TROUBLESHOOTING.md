# Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `FileNotFoundError: Missing source file ... olist_*.csv` | Dataset not in `data\raw\olist\` (see SETUP_GUIDE §3). |
| `SchemaError: <table>: missing columns [...]` | Source file layout changed. Compare to `src/ecom_dw/schemas.py`. Extra columns are only warned about; missing ones stop the run by design. |
| `psycopg2.OperationalError: connection refused` | `docker compose up -d postgres`; check `POSTGRES_HOST/PORT` in `.env`. Inside containers the host is `postgres`, from Windows it is `localhost`. |
| `relation "stg.orders" does not exist` | Run `python -m ecom_dw.pipeline init-db`. |
| `botocore ... EndpointConnectionError` / `NoSuchBucket` | RustFS not up or `rustfs-init` did not finish successfully: `docker compose logs rustfs-init`. Or use `STORAGE_BACKEND=local`. |
| `ModuleNotFoundError: ecom_dw` | `pip install -e .` or `$env:PYTHONPATH="src"`. |
| `ImportError: pyarrow` | `pip install pyarrow` (Parquet engine). |
| `DataQualityError: ... reject_ratio` | More than `DQ_MAX_REJECT_PCT` of a table was rejected. Inspect `rejects/<table>/run_id=.../rejects.csv` in the bucket and `etl.dq_results`. |
| Run failed at `post_load_checks` | Nothing advanced the watermark (it commits after checks). Fix cause, re-run: loads are idempotent. |
| Airflow DAG import error | `docker compose logs airflow`; the DAG imports `ecom_dw` from `/opt/airflow/src` (PYTHONPATH set in compose). |
| FX API step logs `fx_api_unavailable_continuing` | Public API unreachable; pipeline continues, `analytics.v_monthly_revenue_usd` will have NULL rates. |
| Port 5432/9000/8080 already in use | Stop the other service or change the host port mapping in `docker-compose.yml`. |
| Integration tests skipped | `psql` missing or PG* env vars not set (see SETUP_GUIDE §8). |
