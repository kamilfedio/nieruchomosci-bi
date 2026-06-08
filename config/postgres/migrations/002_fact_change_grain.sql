-- Change Fact_Change grain from (download_url, unit_id) to
-- (download_url, unit_id, fk_time) for per-snapshot change history.
-- Run manually on existing databases; create_all() does not alter constraints.

ALTER TABLE "Fact_Change" DROP CONSTRAINT IF EXISTS "Fact_Change_download_url_unit_id_key";
ALTER TABLE "Fact_Change" DROP CONSTRAINT IF EXISTS uq_fact_change_url_unit_time;

CREATE UNIQUE INDEX IF NOT EXISTS uq_fact_change_url_unit_time
    ON "Fact_Change" (download_url, unit_id, fk_time);
