FROM apache/airflow:3.2.2-python3.12

RUN pip install --no-cache-dir \
    polars \
    loguru \
    httpx \
    fastexcel \
    kaggle \
    pydantic \
    pydantic-settings
