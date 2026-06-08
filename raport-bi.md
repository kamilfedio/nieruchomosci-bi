# Raport BI — Nieruchomości w Polsce

**Data raportu**: 2026-06-08  
**Autor**: nieruchomosci-bi pipeline  
**Stack**: Apache Airflow 3 · PostgreSQL 16 + PostGIS · Polars · Streamlit · Plotly

---

## 1. Streszczenie projektu

System Business Intelligence do analizy polskiego rynku nieruchomości. Dane z pięciu niezależnych źródeł są integrowane przez pipeline ELT (Extract → Load → Transform) zarządzany przez Apache Airflow, ładowane do hurtowni danych w schemacie gwiazdy (PostgreSQL + PostGIS) i prezentowane w interaktywnym dashboardzie Streamlit.

**Cel biznesowy**: umożliwić porównanie cen ofertowych i transakcyjnych, ocenę dostępności mieszkań względem wynagrodzeń, lokalizację ryzyka powodziowego w zasobach mieszkaniowych oraz monitoring aktywności deweloperskiej.

---

## 2. Źródła danych

| Źródło | Typ | Częstotliwość | Zakres |
|--------|-----|---------------|--------|
| **Kaggle** — `krzysztofjamroz/apartment-prices-in-poland` | CSV snapshoty | @monthly + backfill | ~195 tys. ogłoszeń sprzedaży i najmu (2023–2024) |
| **dane.gov.pl** — rejestr prospektów deweloperskich | CSV/XLSX per deweloper | @weekly (batch 500) | ~526 tys. plików; lokale z ceną, statusem, adresem |
| **NBP BaRN** — Baza Rynku Nieruchomości | Excel kwartalny | kwartalnie | Ceny ofertowe i transakcyjne dla 17 miast (RP/RW) |
| **GUS BDL** — Bank Danych Lokalnych API | JSON REST | 15 marca rocznie | Population, avg_gross_salary, unemployment_rate, migration_balance (10 miast) |
| **Wody Polskie MZP** — Mapy Zagrożenia Powodziowego | WFS GeoJSON | manualnie (~co 6 lat) | Poligony stref Q10%/Q1%/Q0,2% (SRID 4326, PostGIS) |

---

## 3. Tabele wymiarów

### 3.1 `Dim_Time`

| Pole | Typ | Opis |
|------|-----|------|
| `id` (PK) | INT | Klucz surogatowy |
| `date` | DATE | Data (unique) |
| `year`, `quarter`, `month`, `week`, `day` | SMALLINT | Atrybuty temporalne |
| `day_of_week`, `day_name`, `month_name` | – | Etykiety |
| `year_quarter` | VARCHAR(7) | Format `2024Q1` |
| `is_weekend` | BOOL | Flaga weekendu |

**Grain**: jeden wiersz = jeden dzień kalendarzowy  
**SCD**: Type 0 (immutable)

---

### 3.2 `Dim_Location`

| Pole | Typ | Opis |
|------|-----|------|
| `id` (PK) | INT | Klucz surogatowy |
| `city_norm` | VARCHAR | Małe litery ASCII (np. `warszawa`) |

**Grain**: miasto (unikalne `city_norm`)  
**SCD**: Type 0  
**Użycie**: Fact_Change, Fact_Benchmark_NBP (dane deweloperskie i NBP)

---

### 3.3 `Dim_Unit_Status`

| Pole | Typ | Opis |
|------|-----|------|
| `id` (PK) | INT | |
| `status_norm` | VARCHAR(20) | AVAILABLE / RESERVED / SOLD / WITHDRAWN |
| `status_label` | VARCHAR | Etykieta wyświetlana |
| `status_group` | VARCHAR(20) | ACTIVE / TRANSACTIONAL / INACTIVE |
| `is_available`, `is_sold`, `is_reserved` | BOOL | Flagi pomocnicze |

**Grain**: typ statusu  
**SCD**: Type 1

---

### 3.4 `Dim_Investment`

| Pole | Typ | Opis |
|------|-----|------|
| `id` (PK) | INT | |
| `developer_name` | TEXT | Nazwa dewelopera |
| `investment_id`, `investment_name` | – | ID i nazwa inwestycji |
| `regon` | VARCHAR(14) | NIP/REGON |
| `city`, `street` | VARCHAR | Adres |
| `valid_from`, `valid_to` | DATE | Zakres ważności wiersza SCD2 |
| `is_current` | BOOL | Aktualny rekord |

**Grain**: (deweloper, inwestycja, wersja adresu)  
**SCD**: Type 2 — śledzi zmiany adresu inwestycji

---

### 3.5 `Dim_Geo_Location`

| Pole | Typ | Opis |
|------|-----|------|
| `id` (PK) | INT | |
| `city` | VARCHAR | Miasto (Kaggle) |
| `district` | VARCHAR | Dzielnica |
| `latitude`, `longitude` | FLOAT | Dokładne współrzędne |
| `lat_r`, `lon_r` | FLOAT | Zaokrąglone do 3dp (~111 m) — klucz unikalności |

**Grain**: (city, lat_r, lon_r) — jeden wiersz ≈ blok 111 m  
**SCD**: Type 1  
**Uwaga**: `lat_r`/`lon_r` zawsze wypełnione; `latitude`/`longitude` opcjonalne

---

### 3.6 `Dim_Unit_Type`

| Pole | Typ | Opis |
|------|-----|------|
| `id` (PK) | INT | |
| `type_hash` | VARCHAR(32) | MD5 atrybutów fizycznych |
| `market_type` | VARCHAR(20) | primary / secondary |
| `rooms` | SMALLINT | Liczba pokoi |
| `floor`, `floor_count` | SMALLINT | Piętro / liczba pięter |
| `build_year` | SMALLINT | Rok budowy |
| `building_material` | VARCHAR(20) | Materiał (cegła, beton, itp.) |
| `condition` | VARCHAR(20) | Stan wykończenia |
| `has_balcony`, `has_elevator`, `has_parking`, `has_storage`, `has_security` | BOOL | Udogodnienia |
| `ownership_form` | VARCHAR(30) | Forma własności |

**Grain**: unikalny zestaw atrybutów fizycznych  
**SCD**: Type 1

---

### 3.7 `Dim_Market_Type`

| Pole | Typ | Opis |
|------|-----|------|
| `id` (PK) | INT | |
| `market_code` | VARCHAR(20) | primary / secondary / unknown |
| `market_label` | VARCHAR(50) | Etykieta |
| `segment_nbp` | VARCHAR(5) | RP (rynek pierwotny) / RW (wtórny) — klucz do NBP BaRN |

**Grain**: typ rynku  
**SCD**: Type 1

---

### 3.8 `Dim_Flood_Risk`

| Pole | Typ | Opis |
|------|-----|------|
| `id` (PK) | INT 0–3 | |
| `scenario` | VARCHAR(10) | none / Q10% / Q1% / Q0.2% |
| `risk_class` | VARCHAR(10) | Klasa ryzyka |
| `numeric_risk_class` | INT | 0=brak, 1=niskie, 2=wysokie, 3=ekstremalne |
| `depth_m` | FLOAT | Średnia głębokość powodzi (m) z MZP |

**Grain**: scenariusz ryzyka (4 wiersze stałe)  
**SCD**: Type 0  
**Mapowanie**: Q10% = raz na 10 lat; Q1% = raz na 100 lat; Q0.2% = 1:500 lat

---

### 3.9 `Dim_Demographics`

| Pole | Typ | Opis |
|------|-----|------|
| `id` (PK) | INT | |
| `teryt` | VARCHAR(12) | Kod TERYT jednostki GUS |
| `year` | SMALLINT | Rok danych |
| `city` | VARCHAR | Miasto |
| `population` | INT | Liczba ludności |
| `avg_gross_salary` | FLOAT | Śr. wynagrodzenie brutto (PLN/mies.) |
| `unemployment_rate` | FLOAT | Stopa bezrobocia (%) |
| `migration_balance` | INT | Saldo migracji |
| `working_age_population` | INT | Ludność w wieku produkcyjnym |

**Grain**: (teryt, year)  
**SCD**: Upsert (najnowszy rok zastępuje poprzedni per city)

---

## 4. Tabele faktów

### 4.1 `Fact_Change`

**Źródło**: dane.gov.pl — pliki CSV deweloperów  
**Grain**: `(download_url, unit_id, fk_time)` — jedna zmiana ceny lub statusu lokalu per snapshot

| Pole | Typ | Opis |
|------|-----|------|
| `id` (PK) | INT | |
| `fk_time` | FK → Dim_Time | Data snapshota |
| `fk_investment` | FK → Dim_Investment | Inwestycja dewelopera (SCD2) |
| `fk_unit_status` | FK → Dim_Unit_Status | Status lokalu |
| `fk_location` | FK → Dim_Location | Miasto |
| `fk_flood_risk` | FK → Dim_Flood_Risk | Strefa ryzyka (opcjonalne) |
| `unit_id` | VARCHAR | ID lokalu w pliku dewelopera |
| `download_url` | VARCHAR | URL źródłowego pliku |
| `is_first_snapshot` | BOOL | Pierwszy snapshot dla lokalu |
| `is_price_changed` | BOOL | Cena różni się od poprzedniego snapshota |
| `is_status_changed` | BOOL | Status różni się od poprzedniego snapshota |
| `is_price_drop` | BOOL | Cena spadła vs poprzedni snapshot |
| `unit_value_pln` | FLOAT | Cena całkowita (PLN) |
| `prev_price` | FLOAT | Cena w poprzednim snapshocie |
| `prev_status` | VARCHAR | Status w poprzednim snapshocie |
| `change_amount_pln` | FLOAT | Kwota zmiany (ujemna = obniżka) |
| `price_per_m2_pln` | FLOAT | Cena / m² |

---

### 4.2 `Fact_Benchmark_NBP`

**Źródło**: NBP BaRN — Excel kwartalny  
**Grain**: `(fk_time, fk_location, fk_market_type)` — kwartał × miasto × typ rynku

| Pole | Typ | Opis |
|------|-----|------|
| `fk_time` | FK → Dim_Time | Pierwsza data kwartału |
| `fk_location` | FK → Dim_Location | Miasto |
| `fk_market_type` | FK → Dim_Market_Type | RP (primary) / RW (secondary) |
| `avg_offer_price_m2_pln` | FLOAT | Śr. cena ofertowa NBP (PLN/m²) |
| `avg_transaction_price_m2_pln` | FLOAT | Śr. cena transakcyjna NBP (PLN/m²) |
| `hedonic_index` | FLOAT | Indeks hedoniczny NBP |

---

### 4.3 `Fact_Listing`

**Źródło**: Kaggle — dataset ogłoszeń mieszkaniowych  
**Grain**: `(listing_id, fk_time)` — jeden listing w jednym snapshocie

| Pole | Typ | Opis |
|------|-----|------|
| `fk_time` | FK → Dim_Time | Data snapshota |
| `fk_geo_location` | FK → Dim_Geo_Location | Lokalizacja (city + lat/lon) |
| `fk_unit_type` | FK → Dim_Unit_Type | Atrybuty fizyczne |
| `fk_market_type` | FK → Dim_Market_Type | primary / secondary |
| `fk_flood_risk` | FK → Dim_Flood_Risk | Strefa ryzyka MZP (ST_Covers) |
| `fk_demographics` | FK → Dim_Demographics | Dane demograficzne (city × year) |
| `listing_id` | VARCHAR | ID ogłoszenia |
| `total_price_pln` | FLOAT | Cena całkowita (PLN) |
| `area_m2` | FLOAT | Powierzchnia (m²) |
| `price_per_m2_pln` | FLOAT | Cena / m² |
| `listing_count` | SMALLINT | Zawsze 1 (do agregacji) |

---

### 4.4 Tabela operacyjna `developer_files`

Katalog plików do pobrania z dane.gov.pl. Status: `pending → downloaded → staged → processed / failed`.

---

## 5. Pipeline'y ELT

```
Raw (pliki)  →  Staging (Parquet)  →  Processed (Parquet)  →  DB (star schema)
```

### Harmonogram pipeline'ów

| Pipeline | Schedule | Źródło | Output DB |
|----------|----------|--------|-----------|
| `gov_metadata_pipeline` | @weekly | dane.gov.pl metadata CSV | `developer_files` |
| `gov_data_pipeline` | @weekly (batch 500) | pliki deweloperów CSV/XLSX | `Fact_Change`, `Dim_Investment` |
| `kaggle_pipeline` | @monthly | Kaggle ZIP snapshot | `Fact_Listing`, `Dim_Geo_Location`, `Dim_Unit_Type` |
| `kaggle_backfill_pipeline` | manual | Kaggle (historyczne snapshoty) | `Fact_Listing` |
| `nbp_pipeline` | kwartalnie (1 dzień kwartału) | NBP BaRN Excel | `Fact_Benchmark_NBP` |
| `mzp_pipeline` | manual | Wody Polskie WFS | `flood_zones`, `Dim_Flood_Risk` |
| `gus_bdl_pipeline` | 15 marca rocznie | GUS BDL REST API | `Dim_Demographics` |

### Wzorce techniczne

- **Template Method**: `BaseScraper` → `BaseStaging` → `BaseTransformer` → `BaseLoader`
- **Polars lazy evaluation**: `scan_parquet` + streaming engine (`sink_parquet`)
- **Sentinel pattern**: `gov_data_pipeline.stage_batch()` zwraca `{"failed": "1"}` zamiast wyjątku
- **PostgreSQL upsert**: `INSERT ... ON CONFLICT DO UPDATE / DO NOTHING`
- **Geocoding**: Google Maps API z trójpoziomowym cache (process dict → PostgreSQL → API)

---

## 5a. Bezpieczeństwo — role i uprawnienia

### Role PostgreSQL

| Rola | Uprawnienia | Użytkownik |
|------|-------------|-----------|
| `analyst_ro` | `SELECT` na wszystkich tabelach i widokach (obecnych i przyszłych) | Dashboard Streamlit — zapytania analityczne |
| `admin_rw` | `SELECT, INSERT, UPDATE, DELETE` na tabelach + `USAGE, SELECT` na sekwencjach | Pipelines Airflow — ładowanie danych, DDL |

Role tworzone przy inicjalizacji kontenera PostgreSQL (`config/postgres/init-nieruchomosci.sh`) oraz przez migrację `config/postgres/migrations/004_roles_and_permissions.sql` dla istniejących baz.

### Uwierzytelnianie dashboardu

Dashboard Streamlit wymaga logowania SHA-256 przed udostępnieniem jakichkolwiek danych:

| Użytkownik | Rola | Widoczność |
|-----------|------|-----------|
| `admin` | admin | Pełny dashboard + sekcje „Statystyki tabel wymiarów" i „Status ETL" |
| `analyst` | analyst | Pełny dashboard (bez sekcji administracyjnych) |

Hasze haseł konfigurowane przez zmienne środowiskowe `ADMIN_PASSWORD_HASH` i `ANALYST_PASSWORD_HASH` (SHA-256 hex). Dashboard zawsze łączy się z bazą przez konto `analyst_ro` — operacje DDL (inicjalizacja schematu) używają oddzielnego konta admin przez `DATABASE_URL`.

---

## 5b. Kontrola jakości danych

### Architektura DQ

Warstwa kontroli jakości zaimplementowana w `src/api/quality/` bez zewnętrznych frameworków (tylko Polars + SQLAlchemy):

```
Transformer (po _cast_types)
    └─ DQChecker.check(lf) → (passed_lf, rejected_df)
         ├─ ERROR rules → odrzucony wiersz usunięty z pipeline
         └─ WARNING rules → odrzucony wiersz zostaje w pipeline
              └─ DQChecker.save_rejected() → stg_rejected_records (PostgreSQL)

DAG: load() → validate() → DQChecker.source_summary() → loguru warning (jeśli ERROR > 0)
```

### Tabela błędów `stg_rejected_records`

| Pole | Opis |
|------|------|
| `source` | Nazwa źródła (`kaggle`, `gov_data`, `nbp_data`, `gus_bdl`) |
| `batch_id` | Identyfikator uruchomienia transformera |
| `rule_name` | Nazwa reguły (np. `price_positive`) |
| `rule_description` | Opis warunku |
| `severity` | `ERROR` (wiersz odrzucony) lub `WARNING` (wiersz zachowany) |
| `rejected_at` | Timestamp zapisu |
| `row_data` | JSONB — pełna zawartość odrzuconego wiersza |

### Punkty kontrolne per źródło

#### Kaggle (`Fact_Listing`)

| Reguła | Warunek | Severity | Akcja |
|--------|---------|----------|-------|
| `price_positive` | `price IS NOT NULL AND price > 0` | ERROR | Wiersz odrzucony |
| `area_positive` | `square_meters IS NOT NULL AND square_meters > 0` | ERROR | Wiersz odrzucony |
| `id_not_null` | `id IS NOT NULL` | ERROR | Wiersz odrzucony |
| `build_year_range` | `build_year IS NULL OR build_year IN [1900, 2026]` | WARNING | Wiersz zachowany, zalogowany |

#### Gov data (`Fact_Change`)

| Reguła | Warunek | Severity | Akcja |
|--------|---------|----------|-------|
| `unit_id_not_null` | `unit_id IS NOT NULL` | ERROR | Wiersz odrzucony |
| `price_positive` | `total_price_gross IS NOT NULL AND total_price_gross > 0` | ERROR | Wiersz odrzucony |
| `snapshot_date_not_null` | `snapshot_date IS NOT NULL` | ERROR | Wiersz odrzucony |

#### NBP (`Fact_Benchmark_NBP`)

| Reguła | Warunek | Severity | Akcja |
|--------|---------|----------|-------|
| `year_not_null` | `year IS NOT NULL` | ERROR | Wiersz odrzucony |
| `quarter_not_null` | `quarter IS NOT NULL` | ERROR | Wiersz odrzucony |
| `offer_price_positive` | `avg_offer_price_m2_pln IS NULL OR avg_offer_price_m2_pln > 0` | WARNING | Wiersz zachowany, zalogowany |
| `transaction_price_positive` | `avg_transaction_price_m2_pln IS NULL OR avg_transaction_price_m2_pln > 0` | WARNING | Wiersz zachowany, zalogowany |

#### GUS BDL (`Dim_Demographics`)

| Reguła | Warunek | Severity | Akcja |
|--------|---------|----------|-------|
| `city_not_null` | `city IS NOT NULL` | ERROR | Wiersz odrzucony |
| `year_not_null` | `year IS NOT NULL` | ERROR | Wiersz odrzucony |
| `population_positive` | `population IS NULL OR population > 0` | WARNING | Wiersz zachowany, zalogowany |
| `salary_positive` | `avg_gross_salary IS NULL OR avg_gross_salary > 0` | WARNING | Wiersz zachowany, zalogowany |

### Automatyczna weryfikacja po załadowaniu

Każdy DAG zawiera finalny task `validate()` wywoływany po `load()`:

```python
@task
def validate(processed_path: str) -> dict:
    return DQChecker.source_summary(source, Config().database_url)
    # Zwraca: {"total_rejected": N, "by_rule": {...}, "by_severity": {...}}
    # Loguje WARNING w loguru jeśli ERROR > 0
```

Zapytanie do `stg_rejected_records` za ostatnie 48 h dla danego źródła. Wynik widoczny w logach Airflow i zwracany przez XCom.

### Testy DQ

10 testów jednostkowych w `tests/unit/test_dq_checker.py`:
- Wszystkie reguły OK → rejected pusty
- Reguła ERROR → wiersz usunięty z passed
- Reguła WARNING → wiersz pozostaje w passed, trafia do rejected
- Wiele reguł — wiersz łamiący dwie reguły pojawia się dwukrotnie w rejected
- Adnotacje DQ (source, batch_id, rule_name, severity) na odrzuconych wierszach
- `save_rejected` → mock SQLAlchemy, weryfikacja `add_all`
- Zestawy reguł per źródło (kaggle, gus_bdl)

---

## 6. KPI i metryki

### KPI 1 — Średnia cena ofertowa / m²

**Widok SQL**: `vw_kpi_01_avg_offer_price_m2`  
**Formuła**:
```sql
AVG(fl.price_per_m2_pln)
FROM Fact_Listing fl
JOIN Dim_Geo_Location g ON fl.fk_geo_location = g.id
JOIN Dim_Time t ON fl.fk_time = t.id
GROUP BY t.year, t.quarter, t.month, t.date, g.city, g.district
```
**Interpretacja**: Średnia cena oferowana przez sprzedających na rynku Kaggle, per miasto, dzielnica i okres.  
**Zakres danych**: ~195 tys. ogłoszeń, 10 miast, 2023–2024.

---

### KPI 2 — Odchylenie ceny ofertowej od transakcyjnej NBP (%)

**Widok SQL**: `vw_kpi_02_offer_vs_nbp_deviation`  
**Formuła**:
```sql
(AVG(Kaggle.price_per_m2) - NBP.avg_transaction_price_m2) 
/ NBP.avg_transaction_price_m2 * 100
```
**Interpretacja**: O ile procent ceny ofertowe (Kaggle) są wyższe od faktycznie zawieranych transakcji (NBP BaRN). Wartość dodatnia = rynek „nadwycenia" nieruchomości względem transakcji.  
**Uwaga**: Porównanie dotyczy miast, które mają dane zarówno w Kaggle, jak i NBP BaRN w tym samym kwartale.

---

### KPI 3 — Wskaźnik dostępności mieszkaniowej (miesiące pracy / m²)

**Widok SQL**: `vw_kpi_03_housing_affordability`  
**Formuła**:
```sql
AVG(fl.price_per_m2_pln) / AVG(d.avg_gross_salary)
```
**Interpretacja**: Ile miesięcy pracy (wynagrodzenie brutto, GUS BDL) potrzeba na zakup 1 m². Niższa wartość = lepszy rynek.  
**Benchmark**: wartość ≤ 1,2 = dobra dostępność; 1,2–1,6 = umiarkowana; > 1,6 = zła.

---

### KPI 4 — Liczba ofert w strefie ryzyka powodziowego

**Widok SQL**: `vw_kpi_04_flood_risk_listings`  
**Formuła**: `COUNT(*)` listingów z `fk_flood_risk` wskazującym na scenariusz Q10%/Q1%/Q0,2%.  
**Interpretacja**: Odsetek zasobu mieszkaniowego na rynku eksponowanego na ryzyko powodziowe.

---

### KPI 5 — Dyskonto / premia powodziowa (%)

**Widok SQL**: `vw_kpi_05_flood_price_premium`  
**Formuła**:
```sql
(avg_price_in_flood_zone - avg_price_safe_zone) / avg_price_safe_zone * 100
```
Kontrolowane per miasto i dzielnica (self-join na CTE `district_prices`).  
**Interpretacja**: Wartość ujemna (dyskonto) = oferty w strefach zalewowych tańsze niż bezpieczne lokalizacje. Wartość dodatnia (premia) = paradoks wyżej wycenianych stref (np. nadrzecze premium).

---

### KPI 6 — Tempo sprzedaży deweloperskiej (lokale/tydzień)

**Widok SQL**: `vw_kpi_06_sales_velocity`  
**Formuła**: `COUNT(*)` zdarzeń `is_status_changed = TRUE AND status_group = 'TRANSACTIONAL'` per tydzień.  
**Interpretacja**: Jak szybko deweloperzy finalizują transakcje. Rośnie → rynek rozgrzany; spada → schłodzenie popytu.

---

### KPI 7 — Łączna wartość sprzedanych / zarezerwowanych lokali

**Widok SQL**: `vw_kpi_07_sold_reserved_value`  
**Formuła**: `SUM(fc.unit_value_pln)` per tydzień i miasto, filtr `status_group = 'TRANSACTIONAL'`.  
**Interpretacja**: Wolumen transakcji deweloperskich (PLN) — wskaźnik aktywności rynkowej.

---

### KPI 8 — Liczba i średnia wartość obniżek cen

**Widok SQL**: `vw_kpi_08_price_drops`  
**Formuła**:
```sql
COUNT(*) AS drop_count,
AVG(ABS(fc.change_amount_pln)) AS avg_drop_amount_pln
WHERE fc.is_price_drop = TRUE
```
**Interpretacja**: Presja cenowa na deweloperów. Rosnąca liczba obniżek sygnalizuje nadpodaż lub schłodzenie popytu.

---

### KPI 9 — Udział rynku pierwotnego w ogłoszeniach (%)

**Widok SQL**: `vw_kpi_09_primary_market_share`  
**Formuła**:
```sql
COUNT(*) FILTER (WHERE market_code = 'primary')::numeric / COUNT(*) * 100
```
**Interpretacja**: W miastach z dominującym rynkiem pierwotnym (nowe budownictwo) deweloperzy aktywnie konkurują o kupujących.

---

### KPI 10 — Premia cenowa za udogodnienia

**Widok SQL**: `vw_kpi_10_amenity_premium`  
**Formuła**:
```sql
AVG(price_per_m2) FILTER (WHERE has_amenity = TRUE)
- AVG(price_per_m2) FILTER (WHERE has_amenity = FALSE)
```
Per miasto × liczba pokoi, per udogodnienie (balkon, winda, parking, ochrona).  
**Interpretacja**: O ile PLN/m² droższe są mieszkania z danym udogodnieniem vs bez niego, kontrolowane per segment.

---

## 7. Metryki dashboardu

### Definicje metryk obliczanych w dashboardzie

| Metryka | Obliczenie | Źródło |
|---------|-----------|--------|
| **Śr. cena ofertowa / m²** | `mean(price_per_m2_pln)` z filtrowanego widoku | `vw_dashboard_listing_detail` |
| **Delta ceny QoQ** | `(current - prev) / \|prev\| × 100%` | porównanie z poprzednim kwartałem |
| **Odchylenie od NBP** | `mean(deviation_from_transaction_pct)` | `vw_kpi_02_offer_vs_nbp_deviation` |
| **Delta odchylenia (pp)** | różnica percentage points vs Q-1 | kalkulacja w `compute_kpi_metrics()` |
| **Dostępność (mies./m²)** | `mean(price_per_m2 / avg_gross_salary)` per listing | `vw_dashboard_listing_detail` + `Dim_Demographics` |
| **Oferty w strefie ryzyka** | `COUNT` listingów z `flood_scenario IN (Q10%, Q1%, Q0.2%)` | `vw_dashboard_listing_detail` |
| **Tempo sprzedaży** | `SUM(units_sold_or_reserved)` w oknie kwartałowym | `vw_kpi_06_sales_velocity` |
| **Obniżki cen** | `SUM(drop_count)` w oknie kwartałowym | `vw_kpi_08_price_drops` |

### Metryki dodatkowe (wykresy pogłębione)

| Metryka | Obliczenie |
|---------|-----------|
| **Wzrost cen r/r** | `(avg_price_year_n - avg_price_year_n-1) / avg_price_year_n-1 × 100%` per miasto |
| **Rozkład cen per pokoje** | Box plot (Q1, Q2, Q3, IQR) `price_per_m2_pln` grupowany po `rooms` |
| **Zależność salary→cena** | Scatter: `(avg_gross_salary, avg_price_m2)` per miasto — widoczność „premii miejskiej" |
| **Cena vs powierzchnia** | `mean(price_per_m2)` w przedziałach 15–200 m² (bins 9 pasm) |
| **Cena per materiał** | `mean(price_per_m2)` grupowana po `building_material` |
| **Ranking deweloperów** | `SUM(unit_value_pln)` TOP 15 per deweloper z `Fact_Change` |

---

## 8. Architektura systemu

### Warstwy

```
┌──────────────────────────────────────────────────────────────────┐
│                        ŹRÓDŁA DANYCH                            │
│  Kaggle API · dane.gov.pl · NBP · GUS BDL API · Wody Polskie WFS │
└───────────────────┬──────────────────────────────────────────────┘
                    │ HTTP / API / FTP
┌───────────────────▼──────────────────────────────────────────────┐
│                      WARSTWA RAW                                 │
│              data/raw/{source}/  (pliki as-is)                   │
│         CSV · XLSX · ZIP · GeoJSON · JSON                        │
└───────────────────┬──────────────────────────────────────────────┘
                    │ BaseStaging (Polars lazy + streaming)
┌───────────────────▼──────────────────────────────────────────────┐
│                    WARSTWA STAGING                               │
│           data/staging/{source}/  (Parquet)                      │
│  normalizacja kolumn · typy · dedup · audit cols (batch_id)      │
└───────────────────┬──────────────────────────────────────────────┘
                    │ BaseTransformer (Polars lazy)
┌───────────────────▼──────────────────────────────────────────────┐
│                   WARSTWA PROCESSED                              │
│          data/processed/{source}/  (Parquet)                     │
│  filtrowanie miast · business logic · miary pochodne             │
└───────────────────┬──────────────────────────────────────────────┘
                    │ BaseLoader (SQLAlchemy + ON CONFLICT)
┌───────────────────▼──────────────────────────────────────────────┐
│              HURTOWNIA DANYCH (PostgreSQL 16 + PostGIS)          │
│                                                                  │
│  WYMIARY                      FAKTY                              │
│  Dim_Time          ◄──────── Fact_Listing                        │
│  Dim_Geo_Location  ◄──────── Fact_Change                         │
│  Dim_Unit_Type     ◄──────── Fact_Benchmark_NBP                  │
│  Dim_Market_Type                                                 │
│  Dim_Flood_Risk   (+ flood_zones PostGIS)                        │
│  Dim_Location                                                    │
│  Dim_Investment                                                  │
│  Dim_Unit_Status                                                 │
│  Dim_Demographics                                                │
└───────────────────┬──────────────────────────────────────────────┘
                    │ SQLAlchemy + 11 widoków KPI
┌───────────────────▼──────────────────────────────────────────────┐
│              DASHBOARD (Streamlit + Plotly)                      │
│  Mapa (Scattermapbox + PostGIS WKT) · KPI bar · Trendy           │
│  Panel deweloperski · Dostępność · Analiza pogłębiona            │
└──────────────────────────────────────────────────────────────────┘
```

### Widoki KPI

| Widok | Opis |
|-------|------|
| `vw_kpi_01_avg_offer_price_m2` | Śr. cena/m² Kaggle per miasto/dzielnica/kwartał |
| `vw_kpi_02_offer_vs_nbp_deviation` | Odchylenie cen Kaggle vs NBP transakcyjne |
| `vw_kpi_03_housing_affordability` | Dostępność: miesiące pracy per m² |
| `vw_kpi_04_flood_risk_listings` | Liczba listingów w strefach MZP |
| `vw_kpi_05_flood_price_premium` | Dyskonto/premia powodziowa % |
| `vw_kpi_06_sales_velocity` | Tempo transakcji deweloperskich / tydzień |
| `vw_kpi_07_sold_reserved_value` | Wartość sprzedanych/zarezerwowanych lokali |
| `vw_kpi_08_price_drops` | Liczba i kwoty obniżek cen deweloperów |
| `vw_kpi_09_primary_market_share` | Udział rynku pierwotnego % |
| `vw_kpi_10_amenity_premium` | Premia za balkon/windę/parking/ochronę |
| `vw_dashboard_listing_detail` | Denormalizowany widok dla filtrowania w dashboardzie |
| `vw_dev_latest_unit` | Ostatnia cena lokalu deweloperskiego (DISTINCT ON) |

### Stack technologiczny

| Warstwa | Technologia |
|---------|-------------|
| Orkiestracja | Apache Airflow 3 (Docker Compose) |
| Transformacje | Polars (lazy + streaming engine) |
| ORM / SQL | SQLAlchemy 2 + psycopg2 |
| Baza danych | PostgreSQL 16 + PostGIS 3 |
| Dashboard | Streamlit 1.x + Plotly 5 |
| Package manager | uv |
| Linter / typy | ruff + basedpyright (standard mode) |
| Geocoding | Google Maps Geocoding API (3-poziomowy cache) |
| Python | 3.12 |

---

## 9. Uwagi i ograniczenia

1. **Kaggle**: dane ofertowe — nie transakcyjne. Mogą zawierać ogłoszenia nieaktualne lub zawyżone. Snapshot @monthly daje ~195k wierszy per miesiąc.
2. **NBP BaRN**: dane kwartalne dla 17 miast. Nie zawsze pokrywają się z miastami w Kaggle (brak wspólnych kwartałów → `vw_kpi_02` może być puste).
3. **dane.gov.pl**: ~526k plików, część deweloperów publikuje niekompletne/niestandardowe CSV. Transformer pomija pliki z < 3 kolumnami lub bez mapowania.
4. **GUS BDL**: wynagrodzenia roczne — dane mogą być z roku poprzedniego (opóźnienie GUS). Indeks dostępności używa `fallback: year-1`.
5. **MZP**: poligony Wody Polskie pokrywają wybrane obszary Polski — nie wszystkie miasta z datasetu mają przypisany `fk_flood_risk ≠ none`.
6. **Geocoding**: wymaga klucza `GOOGLE_MAPS_API_KEY` w `.env`. Bez niego punkty deweloperskie na mapie nie będą widoczne.
