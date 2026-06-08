-- Migration 003 — apply all model changes from the current dev session.
-- Safe to run on an existing populated database (all statements are idempotent).
-- Run manually: psql -d nieruchomosci -f config/postgres/migrations/003_session_schema_updates.sql

-- ── Dim_Time ──────────────────────────────────────────────────────────────────
ALTER TABLE "Dim_Time"
    ADD COLUMN IF NOT EXISTS week        SMALLINT,
    ADD COLUMN IF NOT EXISTS day_name    VARCHAR(10),
    ADD COLUMN IF NOT EXISTS month_name  VARCHAR(10),
    ADD COLUMN IF NOT EXISTS year_quarter VARCHAR(7),
    ADD COLUMN IF NOT EXISTS is_weekend  BOOLEAN;

-- Back-fill existing rows so NOT NULL constraints can be added later if needed.
UPDATE "Dim_Time" SET
    week          = EXTRACT(WEEK FROM date)::SMALLINT,
    day_name      = TO_CHAR(date, 'Day'),
    month_name    = TO_CHAR(date, 'Month'),
    year_quarter  = EXTRACT(YEAR FROM date)::TEXT || 'Q' || EXTRACT(QUARTER FROM date)::TEXT,
    is_weekend    = EXTRACT(DOW FROM date) IN (0, 6)
WHERE week IS NULL;

-- ── Dim_Unit_Status ───────────────────────────────────────────────────────────
ALTER TABLE "Dim_Unit_Status"
    ADD COLUMN IF NOT EXISTS status_group  VARCHAR(20) DEFAULT 'INACTIVE',
    ADD COLUMN IF NOT EXISTS is_available  BOOLEAN     DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS is_sold       BOOLEAN     DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS is_reserved   BOOLEAN     DEFAULT FALSE;

UPDATE "Dim_Unit_Status" SET
    status_group = CASE status_norm
        WHEN 'AVAILABLE' THEN 'ACTIVE'
        WHEN 'RESERVED'  THEN 'TRANSACTIONAL'
        WHEN 'SOLD'      THEN 'TRANSACTIONAL'
        ELSE 'INACTIVE'
    END,
    is_available = (status_norm = 'AVAILABLE'),
    is_sold      = (status_norm = 'SOLD'),
    is_reserved  = (status_norm = 'RESERVED')
WHERE status_group IS NULL OR status_group = 'INACTIVE';

-- ── Dim_Investment ────────────────────────────────────────────────────────────
ALTER TABLE "Dim_Investment"
    ADD COLUMN IF NOT EXISTS investment_name TEXT;

-- ── Dim_Unit_Type ─────────────────────────────────────────────────────────────
ALTER TABLE "Dim_Unit_Type"
    ADD COLUMN IF NOT EXISTS has_security   BOOLEAN,
    ADD COLUMN IF NOT EXISTS ownership_form VARCHAR(30);

-- ── Dim_Market_Type ───────────────────────────────────────────────────────────
ALTER TABLE "Dim_Market_Type"
    ADD COLUMN IF NOT EXISTS segment_nbp VARCHAR(5);

UPDATE "Dim_Market_Type" SET
    segment_nbp = CASE market_code
        WHEN 'primary'   THEN 'RP'
        WHEN 'secondary' THEN 'RW'
        ELSE NULL
    END
WHERE segment_nbp IS NULL;

-- ── Dim_Flood_Risk ────────────────────────────────────────────────────────────
ALTER TABLE "Dim_Flood_Risk"
    ADD COLUMN IF NOT EXISTS numeric_risk_class INTEGER,
    ADD COLUMN IF NOT EXISTS depth_m            FLOAT;

UPDATE "Dim_Flood_Risk" SET numeric_risk_class = id WHERE numeric_risk_class IS NULL;

-- Back-fill depth_m from flood_zones aggregates (runs only if zones are loaded).
UPDATE "Dim_Flood_Risk" dfr
SET depth_m = sub.avg_depth
FROM (
    SELECT fk_flood_risk, AVG(depth_m) AS avg_depth
    FROM flood_zones
    WHERE depth_m IS NOT NULL
    GROUP BY fk_flood_risk
) sub
WHERE dfr.id = sub.fk_flood_risk AND dfr.depth_m IS NULL;

-- ── Fact_Change — new columns ─────────────────────────────────────────────────
ALTER TABLE "Fact_Change"
    ADD COLUMN IF NOT EXISTS prev_status   VARCHAR(20),
    ADD COLUMN IF NOT EXISTS fk_flood_risk INTEGER REFERENCES "Dim_Flood_Risk"(id);

-- ── geocoding_cache — new table ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS geocoding_cache (
    cache_key   VARCHAR(32)  PRIMARY KEY,
    address     TEXT         NOT NULL,
    latitude    FLOAT,
    longitude   FLOAT,
    geocoded_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ── KPI views — recreate after schema changes ─────────────────────────────────
-- (vw_kpi_02 now uses Fact_Listing instead of Fact_Change;
--  vw_kpi_06/07 use status_group instead of status_norm IN (...);
--  vw_kpi_10 adds security amenity)
-- Run the full kpi_views.sql separately or trigger init_db() to apply.
