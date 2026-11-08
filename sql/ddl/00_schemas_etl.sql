-- Schemas and audit / metadata tables (idempotent)
CREATE SCHEMA IF NOT EXISTS stg;
CREATE SCHEMA IF NOT EXISTS dw;
CREATE SCHEMA IF NOT EXISTS etl;
CREATE SCHEMA IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS etl.pipeline_runs (
    run_id        text PRIMARY KEY,
    pipeline_name text        NOT NULL DEFAULT 'ecom_olist',
    status        text        NOT NULL CHECK (status IN ('running','success','failed')),
    started_at    timestamptz NOT NULL DEFAULT now(),
    finished_at   timestamptz,
    error_message text
);

CREATE TABLE IF NOT EXISTS etl.step_log (
    id            bigserial PRIMARY KEY,
    run_id        text        NOT NULL,
    step          text        NOT NULL,
    status        text        NOT NULL CHECK (status IN ('running','success','failed')),
    started_at    timestamptz NOT NULL DEFAULT now(),
    finished_at   timestamptz,
    rows_processed bigint,
    error_message text
);
CREATE INDEX IF NOT EXISTS ix_step_log_run ON etl.step_log (run_id);

-- High-water mark for incremental extraction (max order_purchase_timestamp successfully loaded)
CREATE TABLE IF NOT EXISTS etl.watermarks (
    source_name text PRIMARY KEY,
    watermark   timestamp NOT NULL,
    run_id      text,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS etl.dq_results (
    id          bigserial PRIMARY KEY,
    run_id      text    NOT NULL,
    table_name  text    NOT NULL,
    check_name  text    NOT NULL,
    severity    text    NOT NULL,
    passed      boolean NOT NULL,
    failed_rows bigint  NOT NULL,
    total_rows  bigint  NOT NULL,
    detail      text,
    checked_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_dq_run ON etl.dq_results (run_id);
