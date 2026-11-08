# Interview Preparation

> Rule: only quote numbers you measured yourself after running on real data. None are claimed here.

## 15-20 minute walkthrough (script)
1. **Problem (1 min)** – Management needs reliable revenue, delivery and customer metrics from orders/payments/products arriving from CSV exports and an API. I built a batch platform that lands raw data, cleans it, models it as a star schema and serves KPIs.
2. **Architecture (3 min)** – Sources -> Python ingestion -> bronze (raw, immutable, per-run prefix in MinIO/S3) -> silver (typed Parquet + rejects) -> Postgres staging via COPY -> SQL transforms into `dw` star schema -> analytics views; gold Parquet export feeds optional Redshift. Airflow orchestrates; `etl.*` tables audit it.
3. **Incremental + idempotency (3 min)** – Watermark on max purchase timestamp, 7-day lookback to catch late status changes, upserts on grain keys, hash-compare SCD2, atomic transaction, watermark advanced only after post-load checks, never backwards.
4. **Modelling (3 min)** – Grains of 4 facts; customer_unique_id vs per-order customer_id quirk; SCD2 on customers/products with point-in-time join; unknown members; dim_date.
5. **Data quality (2 min)** – Row-level rejects with reasons; table-level checks (PK, FK, reject ratio) that block the load; SQL reconciliation after load; warnings vs errors.
6. **Orchestration/ops (2 min)** – DAG tasks = audited steps; retries with exponential backoff; `all_done` finish task records true status; max_active_runs=1; freshness.
7. **Cloud/Trade-offs (2 min)** – MinIO<->S3 same API; Redshift as serving target from gold (no ON CONFLICT there); costs. Limitations: lookback window, no CDC, full-refresh Redshift.
8. **What I'd do next (1 min)** – CDC/updated_at, MERGE into Redshift, alerting, partitioned gold.

## Component cheat-sheet (what / why / failure / scale / alternative)
- **Bronze in S3**: replay + audit; if lost, re-ingest from source; scales to PBs; alt: data lake table formats (Delta/Iceberg).
- **Silver Parquet**: columnar, typed; failure -> step retry (idempotent keys per run_id); alt: Spark for >memory data.
- **Postgres staging + COPY**: fastest bulk path; truncate+load so re-run safe.
- **SQL transforms in one txn**: all-or-nothing; alt: dbt for lineage/tests (not used to avoid duplicating SQL).
- **Airflow**: dependencies, retries, backfill, UI; alt: Dagster, Prefect, cron.
- **Watermark table**: stores high-water mark; failure before commit -> next run re-reads same window.

## Required discussion topics
- **Duplicate orders**: dedupe in silver (last record wins) + upsert on `order_id`; duplicate rows logged to rejects as `duplicate_key`.
- **Missing customer IDs**: null `customer_id` rejected; unmatched ids map to dim member `-1` and raise a DQ warning.
- **Late-arriving records**: lookback re-read + upsert; SCD2 ignores older-than-current attribute changes; point-in-time join by timestamp.
- **Failed ingestion**: step audited; task retries; partial work isolated (bronze per run_id, warehouse atomic); watermark not advanced.
- **Schema changes**: missing columns fail fast (`SchemaError`); new columns dropped with a logged warning; silver Parquet is the contract.
- **Incremental updates**: window = [watermark − lookback, until); children selected by order_id.

## Questions & short answers
**Python**
- *Why lazy-import psycopg2/boto3?* Unit tests and tooling import modules without needing drivers.
- *How is retry implemented?* Decorator with exponential backoff for S3/HTTP; Airflow adds task-level retries.
- *Why `dtype=str` on read?* Bronze must not coerce (leading-zero zips, bad dates); typing happens in silver.

**SQL**
- *Explain SCD2 here.* Close current row (`valid_to`, `is_current=false`) when `attr_hash` differs and the new effective date is later; insert new version; partial unique index guarantees one current row.
- *How do you make an upsert idempotent?* `ON CONFLICT (grain) DO UPDATE`, deterministic source query.
- *Window functions used?* `LAG` for MoM revenue, `rank()` for categories, `sum() OVER` cumulative revenue.
- *Why `ON COMMIT DROP` temp tables?* Scratch results shared by SCD2 close+insert statements, cleaned automatically.

**ETL/ELT**
- *Why ELT for modelling?* Set-based SQL is faster and auditable in the warehouse; pandas only for row-level cleaning.
- *How do you prove data was loaded correctly?* Post-load reconciliation SQL (staged vs fact counts, sum checks).

**Airflow**
- *Why `max_active_runs=1`?* Watermark logic assumes serial runs.
- *What does `all_done` on finish do?* Runs even when upstream failed to write the final run status.
- *Backfills?* Idempotent steps make reruns safe; `window_days` param simulates historical windows.

**AWS**
- *MinIO vs S3?* Same S3 API, endpoint URL switch. *IAM?* Least-privilege user/role on one bucket. *Redshift COPY?* Needs IAM role + real S3; DISTKEY/SORTKEY choices in `ddl_redshift.sql`. *Cost control?* Local first; pause/delete Redshift.

**Data warehousing**
- *Why surrogate keys?* Needed for SCD2 versions, insulate from source key changes. *Grain?* See SCHEMA.md. *Why not snowflake?* Star is simpler/faster for BI at this scale.

**Failure scenarios**
- Source file missing/changed -> fail fast, nothing written downstream.
- DQ error -> silver not published, results still persisted.
- Warehouse SQL error -> transaction rollback; staging remains for debugging; re-run safe.
- Post-check failure -> watermark not advanced.
- API down -> soft failure; USD view has NULLs.

**Performance**
- COPY not row inserts; indexes on FK/date columns; partial unique index; aggregates pre-computed per order; for Redshift: DISTKEY/SORTKEY; next: partition gold by date, MERGE incremental.
