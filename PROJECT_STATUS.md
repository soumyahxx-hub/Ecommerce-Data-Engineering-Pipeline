# Project Status

Last updated: 2026-11-08

## Implemented
Config/logging/retry · CSV + REST ingestion with schema validation · incremental window + lookback + watermark · bronze/silver/gold in MinIO/S3 (or local folder) ·
pandas cleaning with reject quarantine · DQ checks (silver + post-load SQL) · Postgres staging via COPY · star schema (4 facts, 5 dims + geolocation + FX ref) ·
SCD2 (customers, products), SCD1 (sellers) · upsert/idempotent facts · audit tables, freshness check · Airflow DAG (retries, backoff, params, all_done finish task) ·
Docker Compose (Postgres, MinIO, Airflow, optional Metabase) · analytics views · GitHub Actions CI · optional Redshift load (gold Parquet -> COPY) · docs.

## Verified in the build environment (Linux, Python 3.13, PostgreSQL 16.15)
Command: `PGHOST=/tmp PGPORT=5433 PGUSER=postgres pytest -v`
Result: **25 passed, 1 skipped** (skipped: Parquet round-trip, `pyarrow` not installed in the build sandbox).
- Unit tests: cleaning rules, schema validation, window planning, DQ checks, storage (local), retry, REST call (mocked), COPY CSV formatting, Redshift COPY SQL builder.
- Integration (real PostgreSQL via psql): DDL, staging COPY, all transform SQL, point-in-time SCD2, unknown members, idempotent reload, late status change upsert, post-load checks, all analytics views.
- `py_compile` of every module and the DAG file; module imports.

## NOT verified (could not be run in the build environment)
- Anything using psycopg2 (`db.py`, `audit.py`, `stage.load_staging`, `gold.py`, `pipeline.py` end-to-end): psycopg2 was not installable offline. SQL it runs IS verified via psql; the Python glue is not.
- Parquet writing/reading (pyarrow) and boto3/MinIO/S3 access.
- Docker Compose stack, Airflow DAG execution (DAG only syntax-checked), Metabase, Power BI.
- Real Olist data: never inspected. Column names come from the published dataset; no row counts, DQ rates, or performance numbers exist yet.
- FX API endpoint and response shape (code assumes Frankfurter v1 format; soft-fails if it differs).
- AWS S3 / Redshift: nothing deployed.
- No execution screenshots exist.

## First thing to do on your machine
Run the SETUP_GUIDE steps; if `python -m ecom_dw.pipeline run` errors, send the exact error output.
