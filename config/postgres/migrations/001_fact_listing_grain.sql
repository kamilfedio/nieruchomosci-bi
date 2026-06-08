-- Change Fact_Listing grain from listing_id to (listing_id, fk_time)
-- for historical Kaggle snapshot backfill.
-- Run manually on existing databases; create_all() does not alter constraints.

ALTER TABLE "Fact_Listing" DROP CONSTRAINT IF EXISTS "Fact_Listing_listing_id_key";
ALTER TABLE "Fact_Listing" DROP CONSTRAINT IF EXISTS uq_fact_listing_listing_time;

CREATE UNIQUE INDEX IF NOT EXISTS uq_fact_listing_listing_time
    ON "Fact_Listing" (listing_id, fk_time);
