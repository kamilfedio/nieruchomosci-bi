FROM apache/airflow:3.2.2-python3.12

RUN pip install --no-cache-dir \
    "polars==1.41.2" \
    "sqlalchemy==2.0.50" \
    "google-genai==2.8.0" \
    "pydantic==2.13.4" \
    "pydantic-settings==2.14.1" \
    "loguru==0.7.3" \
    "httpx==0.28.1" \
    "fastexcel==0.20.2" \
    "kaggle==2.2.0" \
    "psycopg2-binary==2.9.10" \
    "geoalchemy2==0.17.1"
