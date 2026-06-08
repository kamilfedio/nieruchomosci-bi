-- KPI dashboard views for nieruchomosci-bi star schema.
-- Source mapping vs spec:
--   Fact_Oferta_Nieruchomosci → Fact_Change (ceny ofertowe deweloperów)
--   Ogłoszenia Kaggle         → Fact_Listing
--   Benchmark NBP             → Fact_Benchmark_NBP
--   Klimatyzacja              → brak w Dim_Unit_Type (tylko balkon/winda/parking)

-- Helper: ostatnia znana cena lokalu deweloperskiego
CREATE OR REPLACE VIEW vw_dev_latest_unit AS
SELECT DISTINCT ON (fc.download_url, fc.unit_id)
    fc.id,
    fc.fk_time,
    fc.fk_location,
    fc.fk_unit_status,
    fc.unit_id,
    fc.unit_value_pln,
    fc.price_per_m2_pln,
    t.date AS snapshot_date,
    t.year,
    t.quarter,
    t.month
FROM "Fact_Change" fc
JOIN "Dim_Time" t ON fc.fk_time = t.id
WHERE fc.price_per_m2_pln IS NOT NULL
ORDER BY fc.download_url, fc.unit_id, fc.fk_time DESC;


-- KPI 1: Średnia cena ofertowa za m² (miasto × dzielnica × czas)
-- Źródło: ogłoszenia Kaggle (jedyny wymiar z dzielnicą)
CREATE OR REPLACE VIEW vw_kpi_01_avg_offer_price_m2 AS
SELECT
    t.year,
    t.quarter,
    t.month,
    t.date AS snapshot_date,
    g.city,
    g.district,
    AVG(fl.price_per_m2_pln) AS avg_price_m2_pln,
    COUNT(*) AS listing_count
FROM "Fact_Listing" fl
JOIN "Dim_Geo_Location" g ON fl.fk_geo_location = g.id
JOIN "Dim_Time" t ON fl.fk_time = t.id
WHERE fl.price_per_m2_pln IS NOT NULL
GROUP BY t.year, t.quarter, t.month, t.date, g.city, g.district;


-- KPI 2: Odchylenie ceny ofertowej (Kaggle) od ceny transakcyjnej NBP (%)
-- Źródło: Fact_Listing (ogłoszenia Kaggle) vs Fact_Benchmark_NBP
-- Ziarno: miasto × kwartał
CREATE OR REPLACE VIEW vw_kpi_02_offer_vs_nbp_deviation AS
WITH kaggle_offers AS (
    SELECT
        g.city,
        t.year,
        t.quarter,
        AVG(fl.price_per_m2_pln) AS avg_offer_m2_pln,
        COUNT(*)               AS observation_count
    FROM "Fact_Listing" fl
    JOIN "Dim_Geo_Location" g ON fl.fk_geo_location = g.id
    JOIN "Dim_Time" t          ON fl.fk_time = t.id
    WHERE fl.price_per_m2_pln IS NOT NULL
    GROUP BY g.city, t.year, t.quarter
)
SELECT
    k.city,
    k.year,
    k.quarter,
    k.avg_offer_m2_pln,
    nbp.avg_transaction_price_m2_pln AS nbp_transaction_m2_pln,
    nbp.avg_offer_price_m2_pln       AS nbp_offer_m2_pln,
    (
        (k.avg_offer_m2_pln - nbp.avg_transaction_price_m2_pln)
        / NULLIF(nbp.avg_transaction_price_m2_pln, 0)
    ) * 100 AS deviation_from_transaction_pct,
    k.observation_count
FROM kaggle_offers k
JOIN "Dim_Location" loc
    ON LOWER(loc.city_norm) = k.city
JOIN "Fact_Benchmark_NBP" nbp
    ON nbp.fk_location = loc.id
JOIN "Dim_Time" nt
    ON nbp.fk_time = nt.id
    AND nt.year = k.year
    AND nt.quarter = k.quarter
JOIN "Dim_Market_Type" mt
    ON nbp.fk_market_type = mt.id
    AND mt.market_code = 'primary';


-- KPI 3: Wskaźnik dostępności mieszkaniowej (miesięcy pracy na 1 m²)
CREATE OR REPLACE VIEW vw_kpi_03_housing_affordability AS
SELECT
    d.city,
    d.year,
    AVG(fl.price_per_m2_pln) AS avg_price_m2_pln,
    AVG(d.avg_gross_salary) AS avg_gross_salary_pln,
    AVG(fl.price_per_m2_pln) / NULLIF(AVG(d.avg_gross_salary), 0) AS months_salary_per_m2,
    COUNT(*) AS listing_count
FROM "Fact_Listing" fl
JOIN "Dim_Demographics" d ON fl.fk_demographics = d.id
WHERE fl.price_per_m2_pln IS NOT NULL
  AND d.avg_gross_salary IS NOT NULL
  AND d.avg_gross_salary > 0
GROUP BY d.city, d.year;


-- KPI 4: Liczba ofert w strefie ryzyka powodziowego (Q10 / Q1 / Q0,2)
CREATE OR REPLACE VIEW vw_kpi_04_flood_risk_listings AS
SELECT
    g.city,
    g.district,
    fr.scenario,
    fr.risk_class,
    COUNT(*) AS listing_count,
    AVG(fl.price_per_m2_pln) AS avg_price_m2_pln
FROM "Fact_Listing" fl
JOIN "Dim_Geo_Location" g ON fl.fk_geo_location = g.id
JOIN "Dim_Flood_Risk" fr ON fl.fk_flood_risk = fr.id
WHERE fr.scenario IN ('Q10%', 'Q1%', 'Q0.2%')
GROUP BY g.city, g.district, fr.scenario, fr.risk_class;


-- KPI 5: Dyskonto / premia powodziowa (%)
CREATE OR REPLACE VIEW vw_kpi_05_flood_price_premium AS
WITH district_prices AS (
    SELECT
        g.city,
        g.district,
        fr.scenario,
        AVG(fl.price_per_m2_pln) AS avg_price_m2_pln
    FROM "Fact_Listing" fl
    JOIN "Dim_Geo_Location" g ON fl.fk_geo_location = g.id
    JOIN "Dim_Flood_Risk" fr ON fl.fk_flood_risk = fr.id
    WHERE fl.price_per_m2_pln IS NOT NULL
    GROUP BY g.city, g.district, fr.scenario
)
SELECT
    risk.city,
    risk.district,
    risk.scenario AS risk_scenario,
    risk.avg_price_m2_pln AS avg_price_risk_m2_pln,
    safe.avg_price_m2_pln AS avg_price_safe_m2_pln,
    risk.avg_price_m2_pln - safe.avg_price_m2_pln AS premium_pln_m2,
    (
        (risk.avg_price_m2_pln - safe.avg_price_m2_pln)
        / NULLIF(safe.avg_price_m2_pln, 0)
    ) * 100 AS flood_premium_pct
FROM district_prices risk
JOIN district_prices safe
    ON risk.city = safe.city
    AND COALESCE(risk.district, '') = COALESCE(safe.district, '')
WHERE risk.scenario IN ('Q10%', 'Q1%', 'Q0.2%')
  AND safe.scenario = 'none';


-- KPI 6: Tempo sprzedaży deweloperskiej (lokale → zarezerwowany/sprzedany per tydzień)
CREATE OR REPLACE VIEW vw_kpi_06_sales_velocity AS
SELECT
    date_trunc('week', t.date)::date AS week_start,
    loc.city_norm AS city,
    COUNT(*) AS units_sold_or_reserved
FROM "Fact_Change" fc
JOIN "Dim_Time" t ON fc.fk_time = t.id
JOIN "Dim_Location" loc ON fc.fk_location = loc.id
JOIN "Dim_Unit_Status" st ON fc.fk_unit_status = st.id
WHERE fc.is_status_changed
  AND st.status_group = 'TRANSACTIONAL'
GROUP BY date_trunc('week', t.date)::date, loc.city_norm;


-- KPI 7: Łączna wartość sprzedanych / zarezerwowanych lokali
CREATE OR REPLACE VIEW vw_kpi_07_sold_reserved_value AS
SELECT
    date_trunc('week', t.date)::date AS week_start,
    loc.city_norm AS city,
    st.status_norm,
    st.status_group,
    COUNT(*) AS unit_count,
    SUM(fc.unit_value_pln) AS total_value_pln
FROM "Fact_Change" fc
JOIN "Dim_Time" t ON fc.fk_time = t.id
JOIN "Dim_Location" loc ON fc.fk_location = loc.id
JOIN "Dim_Unit_Status" st ON fc.fk_unit_status = st.id
WHERE fc.is_status_changed
  AND st.status_group = 'TRANSACTIONAL'
  AND fc.unit_value_pln IS NOT NULL
GROUP BY date_trunc('week', t.date)::date, loc.city_norm, st.status_norm, st.status_group;


-- KPI 8: Liczba i średnia wartość obniżek cen
CREATE OR REPLACE VIEW vw_kpi_08_price_drops AS
SELECT
    t.year,
    t.quarter,
    loc.city_norm AS city,
    COUNT(*) AS drop_count,
    AVG(ABS(fc.change_amount_pln)) AS avg_drop_amount_pln,
    SUM(ABS(fc.change_amount_pln)) AS total_drop_amount_pln
FROM "Fact_Change" fc
JOIN "Dim_Time" t ON fc.fk_time = t.id
JOIN "Dim_Location" loc ON fc.fk_location = loc.id
WHERE fc.is_price_drop
  AND fc.change_amount_pln IS NOT NULL
GROUP BY t.year, t.quarter, loc.city_norm;


-- KPI 9: Udział rynku pierwotnego w ofertach (%)
CREATE OR REPLACE VIEW vw_kpi_09_primary_market_share AS
SELECT
    g.city,
    t.year,
    t.quarter,
    t.month,
    COUNT(*) FILTER (WHERE mt.market_code = 'primary') AS primary_listing_count,
    COUNT(*) AS total_listing_count,
    (
        COUNT(*) FILTER (WHERE mt.market_code = 'primary')::numeric
        / NULLIF(COUNT(*), 0)
    ) * 100 AS primary_market_share_pct
FROM "Fact_Listing" fl
JOIN "Dim_Geo_Location" g ON fl.fk_geo_location = g.id
JOIN "Dim_Time" t ON fl.fk_time = t.id
JOIN "Dim_Market_Type" mt ON fl.fk_market_type = mt.id
GROUP BY g.city, t.year, t.quarter, t.month;


-- KPI 10: Premia za udogodnienia (balkon / winda / parking / ochrona; ziarno: miasto × pokoje)
CREATE OR REPLACE VIEW vw_kpi_10_amenity_premium AS
WITH listing_attrs AS (
    SELECT
        g.city,
        ut.rooms,
        ut.has_balcony,
        ut.has_elevator,
        ut.has_parking,
        ut.has_security,
        fl.price_per_m2_pln
    FROM "Fact_Listing" fl
    JOIN "Dim_Geo_Location" g ON fl.fk_geo_location = g.id
    JOIN "Dim_Unit_Type" ut ON fl.fk_unit_type = ut.id
    WHERE fl.price_per_m2_pln IS NOT NULL
),
amenity_rows AS (
    SELECT city, rooms, 'balcony' AS amenity, has_balcony AS has_amenity, price_per_m2_pln
    FROM listing_attrs
    WHERE has_balcony IS NOT NULL
    UNION ALL
    SELECT city, rooms, 'elevator', has_elevator, price_per_m2_pln
    FROM listing_attrs
    WHERE has_elevator IS NOT NULL
    UNION ALL
    SELECT city, rooms, 'parking', has_parking, price_per_m2_pln
    FROM listing_attrs
    WHERE has_parking IS NOT NULL
    UNION ALL
    SELECT city, rooms, 'security', has_security, price_per_m2_pln
    FROM listing_attrs
    WHERE has_security IS NOT NULL
)
SELECT
    city,
    rooms,
    amenity,
    AVG(price_per_m2_pln) FILTER (WHERE has_amenity) AS avg_price_with_amenity_m2,
    AVG(price_per_m2_pln) FILTER (WHERE NOT has_amenity) AS avg_price_without_amenity_m2,
    AVG(price_per_m2_pln) FILTER (WHERE has_amenity)
        - AVG(price_per_m2_pln) FILTER (WHERE NOT has_amenity) AS premium_pln_m2,
    COUNT(*) FILTER (WHERE has_amenity) AS with_amenity_count,
    COUNT(*) FILTER (WHERE NOT has_amenity) AS without_amenity_count
FROM amenity_rows
GROUP BY city, rooms, amenity;


-- Helper: denormalized listings for dashboard filters (market, rooms, flood)
CREATE OR REPLACE VIEW vw_dashboard_listing_detail AS
SELECT
    fl.listing_id,
    g.city,
    g.district,
    t.year,
    t.quarter,
    t.month,
    t.date AS snapshot_date,
    mt.market_code,
    ut.rooms,
    fr.scenario AS flood_scenario,
    fl.price_per_m2_pln,
    fl.total_price_pln,
    fl.area_m2,
    d.avg_gross_salary,
    d.year AS demographics_year,
    COALESCE(g.latitude, g.lat_r)   AS lat,
    COALESCE(g.longitude, g.lon_r)  AS lon
FROM "Fact_Listing" fl
JOIN "Dim_Geo_Location" g ON fl.fk_geo_location = g.id
JOIN "Dim_Time" t ON fl.fk_time = t.id
JOIN "Dim_Market_Type" mt ON fl.fk_market_type = mt.id
JOIN "Dim_Unit_Type" ut ON fl.fk_unit_type = ut.id
JOIN "Dim_Flood_Risk" fr ON fl.fk_flood_risk = fr.id
LEFT JOIN "Dim_Demographics" d ON fl.fk_demographics = d.id;
