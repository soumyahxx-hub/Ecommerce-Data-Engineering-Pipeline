"""Airflow DAG: Olist e-commerce pipeline. Each task is one audited pipeline step; steps hand data over via
object storage + manifest, so tasks are retry-safe and independently re-runnable."""
from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.models.param import Param
from airflow.operators.python import PythonOperator, ShortCircuitOperator
from airflow.utils.trigger_rule import TriggerRule

from ecom_dw import pipeline
from ecom_dw.config import get_settings
from ecom_dw.utils import safe_run_id

RUN = "{{ run_id }}"


def _rid(run_id: str) -> str:
    return safe_run_id(run_id)


def _start(run_id, **_):
    pipeline.step_init_db()
    pipeline.step_start_run(_rid(run_id))


def _ingest(run_id, until, window_days, **_):
    pipeline.step_ingest(_rid(run_id), until or None, window_days or None)


def _finish(run_id, dag_run, **_):
    """Runs even when upstream failed (trigger_rule=all_done) and records the real outcome."""
    failed = [ti for ti in dag_run.get_task_instances() if ti.task_id != "finish_run" and ti.state == "failed"]
    status = "failed" if failed else "success"
    pipeline.step_finish_run(_rid(run_id), status, f"failed tasks: {[t.task_id for t in failed]}" if failed else None)


default_args = {
    "owner": "data-eng",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=15),
    "execution_timeout": timedelta(hours=1),
}

with DAG(
    dag_id="ecom_olist_pipeline",
    description="Olist e-commerce: bronze -> silver -> staging -> star-schema warehouse -> gold",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,              # historical data is simulated with window params / backfills (see SETUP_GUIDE)
    max_active_runs=1,          # watermark logic assumes serial runs
    default_args=default_args,
    params={"until": Param("", type="string", description="YYYY-MM-DD inclusive upper bound (blank = all new data)"),
            "window_days": Param(0, type="integer", description="Process N days after watermark (0 = unbounded)")},
    tags=["ecommerce", "olist"],
) as dag:
    start = PythonOperator(task_id="init_and_start_run", python_callable=_start, op_kwargs={"run_id": RUN})
    ingest = PythonOperator(task_id="ingest_bronze", python_callable=_ingest,
                            op_kwargs={"run_id": RUN, "until": "{{ params.until }}", "window_days": "{{ params.window_days }}"})
    silver = PythonOperator(task_id="silver_clean_validate", python_callable=lambda run_id, **_: pipeline.step_silver(_rid(run_id)),
                            op_kwargs={"run_id": RUN})
    stage = PythonOperator(task_id="load_staging", python_callable=lambda run_id, **_: pipeline.step_stage(_rid(run_id)),
                           op_kwargs={"run_id": RUN})
    warehouse = PythonOperator(task_id="transform_warehouse", python_callable=lambda run_id, **_: pipeline.step_warehouse(_rid(run_id)),
                               op_kwargs={"run_id": RUN})
    checks = PythonOperator(task_id="post_load_checks", python_callable=lambda run_id, **_: pipeline.step_post_checks(_rid(run_id)),
                            op_kwargs={"run_id": RUN})
    watermark = PythonOperator(task_id="commit_watermark", python_callable=lambda run_id, **_: pipeline.step_commit_watermark(_rid(run_id)),
                               op_kwargs={"run_id": RUN})
    gold = PythonOperator(task_id="export_gold", python_callable=lambda run_id, **_: pipeline.step_gold(_rid(run_id)),
                          op_kwargs={"run_id": RUN})
    redshift_on = ShortCircuitOperator(task_id="redshift_enabled", python_callable=lambda **_: get_settings().enable_redshift)
    redshift = PythonOperator(task_id="load_redshift", python_callable=lambda run_id, **_: pipeline.step_redshift(_rid(run_id)),
                              op_kwargs={"run_id": RUN})
    finish = PythonOperator(task_id="finish_run", python_callable=_finish, op_kwargs={"run_id": RUN},
                            trigger_rule=TriggerRule.ALL_DONE, retries=0)

    start >> ingest >> silver >> stage >> warehouse >> checks >> watermark >> gold >> redshift_on >> redshift
    [gold, redshift] >> finish
