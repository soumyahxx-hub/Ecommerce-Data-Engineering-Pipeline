# TODO

## Must do on your machine (verification)
- [ ] Download Olist CSVs, run full pipeline, fix anything real data exposes; record real row counts / reject rates / runtime in PROJECT_STATUS.md.
- [ ] Run Airflow DAG once end-to-end; take screenshots (DAG graph, MinIO bucket, analytics query, Metabase/Power BI dashboard) into `docs/screenshots/`.
- [ ] Run `pytest -v` with a local Postgres so integration tests execute; confirm pyarrow test passes.

## Improvements
- [ ] Extract from a source PostgreSQL OLTP database (incremental by `updated_at`) as a third source.
- [ ] Redshift incremental load (MERGE) instead of full refresh.
- [ ] Add a Python-level integration test (psycopg2 + MinIO via testcontainers).
- [ ] Alerts on failure (Airflow email / CloudWatch alarm).
- [ ] Partition gold Parquet by date; add table/column documentation to the views.
