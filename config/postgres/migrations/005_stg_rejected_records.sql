-- Migration 005: Data-quality rejection log
-- Apply with: psql -U airflow -d nieruchomosci -f config/postgres/migrations/005_stg_rejected_records.sql

CREATE TABLE IF NOT EXISTS stg_rejected_records (
    id               BIGSERIAL PRIMARY KEY,
    source           TEXT NOT NULL,
    batch_id         TEXT,
    rule_name        TEXT NOT NULL,
    rule_description TEXT,
    severity         TEXT NOT NULL CHECK (severity IN ('ERROR', 'WARNING')),
    rejected_at      TIMESTAMPTZ DEFAULT now(),
    row_data         JSONB
);

CREATE INDEX IF NOT EXISTS idx_stg_rej_source_batch
    ON stg_rejected_records (source, batch_id);

GRANT SELECT ON stg_rejected_records TO analyst_ro;
GRANT SELECT, INSERT ON stg_rejected_records TO admin_rw;
GRANT USAGE, SELECT ON SEQUENCE stg_rejected_records_id_seq TO admin_rw;
