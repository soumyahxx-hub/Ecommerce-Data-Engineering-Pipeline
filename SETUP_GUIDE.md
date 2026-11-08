# Setup Guide (Windows 11, PowerShell)

Prerequisites: Python 3.11+, Docker Desktop (WSL2 backend), Git, VS Code.

## 1. Python environment
```powershell
cd ecom-dw
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
pip install -e .
```

## 2. Environment variables
```powershell
Copy-Item .env.example .env
notepad .env      # replace every change_me_* value; choose a unique RustFS access key/secret; AIRFLOW_FERNET_KEY: see below
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # paste into AIRFLOW_FERNET_KEY (optional for local)
```
`.env` is git-ignored. Never commit it.

For the local RustFS stack, keep `STORAGE_BACKEND=s3` and `S3_ENDPOINT_URL=http://localhost:9000`. RustFS uses `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` as its root credentials. Use a unique uppercase alphanumeric access key without `/` and a unique secret.

## 3. Dataset (manual)
Download "Brazilian E-Commerce Public Dataset by Olist" from Kaggle (olistbr/brazilian-ecommerce), extract the 9 CSVs into `data\raw\olist\`
(or run `.\scripts\download_dataset.ps1` after configuring the Kaggle CLI).
```powershell
Get-ChildItem data\raw\olist -Filter *.csv     # expect 9 files, names listed in data\raw\olist\README.md
```

## 4. Start infrastructure
```powershell
docker compose config -q
docker compose pull rustfs rustfs-init
docker compose up -d postgres rustfs rustfs-init
docker compose ps
docker compose logs rustfs-init
```
- RustFS console: http://localhost:9001 (login = `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` from `.env`). `rustfs-init` should exit with code 0 after creating (or confirming) the `ecom-lake` bucket.
- Postgres: `localhost:5432`, db `ecom_dw`.
- These commands do not delete Docker volumes. The former MinIO volume is intentionally left untouched; it is not mounted by RustFS because the two products have different on-disk formats.

## 5. Initialise databases and run the pipeline (CLI)
```powershell
$env:PYTHONPATH = "src"
python -m ecom_dw.pipeline init-db                      # schemas, audit tables, star schema, dim_date, views
python -m ecom_dw.pipeline run                          # full load of everything after the watermark
```
Simulate incremental daily/monthly batches (Olist is a static 2016-18 dataset):
```powershell
python -m ecom_dw.pipeline run --until 2017-03-31       # batch 1
python -m ecom_dw.pipeline run --window-days 30         # next 30 days after the watermark (7-day lookback re-reads overlap)
python -m ecom_dw.pipeline run --window-days 30         # ...repeat; re-running the same window is idempotent
python -m ecom_dw.pipeline freshness                    # exit code 1 if last successful run is older than FRESHNESS_MAX_HOURS
```
No Docker/RustFS? Set `STORAGE_BACKEND=local` in `.env` (writes to `data\local_lake`) — you still need Postgres.

## 6. Airflow
```powershell
docker compose up -d --build airflow
```
Open http://localhost:8080 (user/password from `.env`: AIRFLOW_ADMIN_USER / AIRFLOW_ADMIN_PASSWORD). Un-pause `ecom_olist_pipeline`, then **Trigger DAG w/ config**
(optional params `until`, `window_days`). Logs: `airflow-logs\`. Backfill: `docker compose exec airflow airflow dags backfill ecom_olist_pipeline -s 2024-01-01 -e 2024-01-03`
(each run continues from the watermark; use `window_days` for historical simulation).

## 7. Inspect the warehouse / analytics
```powershell
docker compose exec postgres psql -U ecom -d ecom_dw -c "SELECT * FROM analytics.v_kpi_summary;"
docker compose exec postgres psql -U ecom -d ecom_dw -c "SELECT * FROM analytics.v_monthly_revenue ORDER BY month;"
docker compose exec postgres psql -U ecom -d ecom_dw -c "SELECT * FROM analytics.v_pipeline_health LIMIT 5;"
```
Dashboards:
- **Metabase** (optional): `docker compose --profile bi up -d`, open http://localhost:3000, add a PostgreSQL database (host `postgres`, db `ecom_dw`, user/password from `.env`), build charts on the `analytics.*` views.
- **Power BI Desktop**: Get Data -> PostgreSQL database -> `localhost:5432`, `ecom_dw` -> select the `analytics` views (Import mode).

## 8. Tests
```powershell
pytest -m "not integration"        # unit tests, no services needed
```
Integration tests need the `psql` client and a reachable Postgres via `PG*` variables (CI does this automatically). On Windows without psql, rely on GitHub Actions, or install the PostgreSQL client tools and run:
```powershell
$env:PGHOST="localhost"; $env:PGPORT="5432"; $env:PGUSER="ecom"; $env:PGPASSWORD="<your password>"
pytest -v        # creates and drops its own database ecom_dw_it (user needs CREATEDB; the compose superuser has it)
```

## 9. GitHub
```powershell
git init; git add .; git commit -m "Initial commit"; git branch -M main
git remote add origin https://github.com/<you>/ecom-dw.git; git push -u origin main
```
GitHub Actions (`.github/workflows/ci.yml`) then runs all tests against a Postgres service.

## 10. OPTIONAL AWS (costs money — read first)
1. **AWS S3 instead of local RustFS** (pennies for this data size): create a bucket, an IAM user with `s3:GetObject/PutObject/ListBucket` on it only; put its keys in `.env`, clear `S3_ENDPOINT_URL`, set `S3_BUCKET`.
2. **Redshift**: Serverless/cluster is chargeable. Create it, an IAM role attached to Redshift with read access to the bucket, then set `REDSHIFT_*` + `ENABLE_REDSHIFT=true`. Redshift COPY reads gold Parquet from real S3 only (not local RustFS). Delete the workgroup/cluster when finished. Cheaper alternative: skip Redshift and keep Postgres (RDS free tier or local) as the warehouse.
3. Never put keys in code, `.env.example` or Git.

See `docs/TROUBLESHOOTING.md` for common errors.
