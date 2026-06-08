"""Airflow task environment bootstrap.

Call setup_task_env() at the top of every @task function instead of the
old sys.path.insert(0, "/opt/airflow") pattern. It does two things:

  1. Ensures /opt/airflow is on sys.path (idempotent).
  2. Injects Airflow Variables into os.environ so that pydantic-settings
     Config() picks them up via the normal env-var resolution order:
       Airflow Variable  >  .env file  >  field default

Variables are only injected when running inside an Airflow worker process
(i.e. when airflow.models is importable). In local / test environments the
import silently falls back to os.environ / .env as usual.
"""

from __future__ import annotations

import os

_AIRFLOW_VAR_NAMES: tuple[str, ...] = (
    "DATABASE_URL",
    "GEMINI_API_KEY",
    "BDL_API_KEY",
    "GOOGLE_MAPS_API_KEY",
    "KAGGLE_API_TOKEN",
    "KAGGLE_DATASET_SLUG",
    "GOV_DATA_BATCH_SIZE",
    "GOV_DATA_SCRAPE_WORKERS",
    "GEOCODE_WORKERS",
    "GEMINI_TIMEOUT_MS",
)


def setup_task_env() -> None:
    """Bootstrap sys.path and inject Airflow Variables into os.environ."""
    import sys

    if "/opt/airflow" not in sys.path:
        sys.path.insert(0, "/opt/airflow")

    try:
        from airflow.models import Variable  # noqa: PLC0415
    except ImportError:
        return  # not inside an Airflow worker — .env / defaults are used instead

    for name in _AIRFLOW_VAR_NAMES:
        if name not in os.environ:
            try:
                val: str | None = Variable.get(name, default_var=None)
                if val:
                    os.environ[name] = val
            except Exception:  # noqa: BLE001, S110
                pass
