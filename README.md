# E-Commerce Data Pipeline & Data Warehouse (Olist)

Batch data-engineering project: CSV + REST API -> bronze/silver/gold in S3-compatible storage -> PostgreSQL star schema (SCD2, upserts) -> analytics views, orchestrated by Airflow, with data-quality checks, audit trail, tests and CI. Optional AWS S3 / Redshift path.

```
Olist CSVs + FX API -> Python ingest -> Bronze (RustFS/S3) -> Silver Parquet (+rejects) -> stg.* -> dw.* star schema -> analytics.* -> Metabase/Power BI
                                                                             Airflow DAG orchestrates; etl.* tables audit every step
                                                                             dw -> Gold Parquet -> (optional) Redshift
```

**Stack:** Python 3.11, pandas, PostgreSQL 16, RustFS/S3, Parquet, Airflow 2.10, Docker Compose, pytest, GitHub Actions, optional Redshift.

**Highlights**
- Incremental load with watermark + lookback (late updates), idempotent upserts, atomic warehouse transaction
- SCD Type 2 customers/products with point-in-time fact joins; unknown-member handling
- Reject quarantine, schema-drift handling, silver + post-load DQ checks persisted to `etl.dq_results`
- Retries with backoff (Python + Airflow), execution history, freshness check, JSON logs

**Start here:** [SETUP_GUIDE.md](SETUP_GUIDE.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [SCHEMA.md](SCHEMA.md) · [DATA_DICTIONARY.md](DATA_DICTIONARY.md) · [INTERVIEW_PREPARATION.md](INTERVIEW_PREPARATION.md) · [PROJECT_STATUS.md](PROJECT_STATUS.md) (what is and is not verified) · [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)

```
src/ecom_dw/   pipeline modules      dags/   Airflow DAG       sql/   ddl, transform, quality, analytics, redshift
tests/         pytest (unit+integration)    docker/ + docker-compose.yml    scripts/ PowerShell helpers    data/raw/olist/ (put CSVs here)
```

Dataset: Olist Brazilian E-Commerce Public Dataset (Kaggle) — download separately; not included.
