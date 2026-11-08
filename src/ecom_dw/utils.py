"""Small shared helpers: retry with exponential backoff, run-id sanitising."""
from __future__ import annotations

import functools
import re
import time
from typing import Callable, Iterable

from .logging_utils import get_logger, log_event

_log = get_logger("ecom_dw.utils")


def retry(attempts: int = 3, base_delay: float = 1.0, exceptions: Iterable[type] = (Exception,)):
    """Retry a function with exponential backoff (base_delay * 2**n)."""
    exc = tuple(exceptions)

    def deco(fn: Callable):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            for n in range(attempts):
                try:
                    return fn(*a, **kw)
                except exc as err:
                    if n == attempts - 1:
                        raise
                    delay = base_delay * (2**n)
                    log_event(_log, "retrying", function=fn.__name__, attempt=n + 1, delay_s=delay, error=str(err))
                    time.sleep(delay)

        return wrapper

    return deco


def safe_run_id(run_id: str) -> str:
    """Airflow run ids contain ':' '+' etc.; make them safe for S3 keys and SQL text."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", run_id)
