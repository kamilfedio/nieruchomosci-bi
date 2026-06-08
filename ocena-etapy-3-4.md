# Ocena realizacji Etapów 3 i 4 — nieruchomosci-bi

> Data analizy: 2026-06-08 (zaktualizowano: 2026-06-08)

---

## Etap 3 — Implementacja Modelu

### Zrealizowane w pełni

**Model gwiazdowy (star schema) / konstelacja faktów w PostgreSQL + PostGIS:**

| Tabela | Typ | SCD | Status |
|--------|-----|-----|--------|
| `Dim_Time` | Wymiar czasu | Type 0 | ✅ Pełna hierarchia: rok → kwartał → miesiąc → tydzień → dzień, flaga weekendu, etykiety |
| `Dim_Location` | Wymiar lokalizacji | Type 0 | ✅ |
| `Dim_Investment` | Wymiar inwestycji | **Type 2** | ✅ Z polami `valid_from`, `valid_to`, `is_current` |
| `Dim_Unit_Status` | Wymiar statusu lokalu | Type 1 | ✅ Z grupami ACTIVE/TRANSACTIONAL/INACTIVE i flagami logicznymi |
| `Dim_Geo_Location` | Wymiar geolokalizacji (Kaggle) | Type 1 | ✅ Z zaokrąglonymi współrzędnymi ~111m jako kluczem unikalności |
| `Dim_Unit_Type` | Wymiar atrybutów fizycznych | Type 1 | ✅ Z hashem MD5 jako kluczem surrogatowym |
| `Dim_Market_Type` | Wymiar typu rynku | Type 1 | ✅ Z mappingiem do segmentów NBP |
| `Dim_Demographics` | Wymiar demograficzny | Snapshot roczny | ✅ Z danymi GUS BDL |
| `Dim_Flood_Risk` | Wymiar ryzyka powodziowego | Type 0 | ✅ |
| `Fact_Change` | Tabela faktów zmian cen/statusów deweloperów | — | ✅ |
| `Fact_Listing` | Tabela faktów ogłoszeń Kaggle | — | ✅ |
| `Fact_Benchmark_NBP` | Tabela faktów benchmarku NBP | — | ✅ |

**Dokumentacja modelu:** `raport-bi.md` (511 linii), `erd.md` (449 linii) — pełne metryki per tabela, opis ziarna, SCD, źródeł.

**Architektura w ASCII art** w `raport-bi.md` (sekcja 8) przedstawia przepływ: źródła → raw → staging → processed → hurtownia → dashboard.

### Wymaga poprawy

**Graficzny diagram ERD** — projekt ma opis tekstowy i schemat ASCII, ale brakuje właściwego diagramu graficznego (np. PNG/SVG z relacjami FK). Zadanie mówi o *graficznej reprezentacji bazy danych*.

---

## Etap 4 — Implementacja procesu ETL

### Krok 1 — Ekstrakcja ✅

- **Tryb dostępu**: HTTP REST (Kaggle API, GUS BDL), WFS (Wody Polskie), HTTP pobieranie plików (dane.gov.pl), Excel (NBP BaRN)
- **Wykrywanie błędów**: Status tracking w tabeli `developer_files` (`pending → downloaded → staged → processed / failed`), sentinel pattern w DAG `gov_data_pipeline`
- **Ekstrakcja przyrostowa**: Zaimplementowana — `extract_missing()` w KaggleScraper, pobieranie tylko plików o statusie `pending` z `developer_files`, `catchup=False` w DAGach, batch 500 plików/tygodniowo

### Krok 2 — Transformacja (obszar staging) ✅

- **Obszar staging**: `data/staging/` z plikami Parquet per źródło
- **Oczyszczanie**: `GovDataTransformer` — normalizacja cen (heurystyka cena/m²), statusów, miast; `KaggleTransformer` — typowanie, filtry NULL/zero, normalizacja materiałów, warunków, boolean yes/no
- **Wymiar czasu**: `DimTimeRepository.get_or_create()` — generuje wszystkie atrybuty przy pierwszym wstawieniu
- **Kolumny obliczeniowe**: `price_per_m2_pln`, `change_amount_pln`, `is_price_drop`, `is_price_changed`, `is_status_changed`
- **Deduplication**: `BaseStaging._dedup()` + `INSERT ... ON CONFLICT DO NOTHING`

### Krok 3 — Ładowanie i modelowanie ✅ / ⚠️ częściowo

**Zrealizowane:**
- Ładowanie przez `BaseLoader` → konkretne loadery per źródło (5 loaderów)
- Mechanizmy analityczne: 12 widoków SQL KPI + helper view — odpowiednik miar w ROLAP
- Ciągłość aktualizacji: upsert/`ON CONFLICT DO NOTHING`, `@monthly`/`@weekly`/quarterly schedules, backfill pipeline dla danych historycznych

**Brak — zupełnie nieobecne:**
- **Role użytkowników i uprawnienia** — brak `GRANT`, `REVOKE`, PostgreSQL roles. Zadanie wymaga implementacji ról (np. `analyst_ro`, `admin_rw`)
- **DAX** — nie dotyczy (używany w Power BI, tu ROLAP/SQL; widoki KPI są funkcjonalnym odpowiednikiem)

### Krok 4 — Kontrola jakości ⚠️ częściowo

**Zrealizowane:**
- Testy jednostkowe: 8 plików (`test_kaggle_transformer.py`, `test_gov_data_transformer.py`, `test_nbp_transformer.py` itd.) — testują konkretne reguły walidacji
- Testy integracyjne: 6 plików (`test_kpi_views.py`, `test_kaggle_loader.py` itd.) — weryfikują KPI i ładowanie do DB
- Filtry w transformerach: warunki NULL, zakresy liczbowe, wymagane kolumny

**Uzupełnione (2026-06-08):**
- **Zdefiniowane „punkty kontrolne" per tabela** — `src/api/quality/rules.py` definiuje formalne reguły `DQRule` (name, description, severity, predicate) per źródło (kaggle, gov_data, nbp, gus_bdl); udokumentowane w `raport-bi.md` sekcja 5b
- **Tabela błędów** — odrzucone wiersze trafiają do `stg_rejected_records` (JSONB `row_data` + metadata: source, batch_id, rule_name, severity); `DQChecker.save_rejected()` wywoływany przez każdy transformer
- **Automatyczny raport jakości** — task `validate()` po `load()` w każdym DAGu wywołuje `DQChecker.source_summary()` i loguje ostrzeżenie jeśli ERROR > 0

---

## Podsumowanie luk

| Wymaganie | Status | Szczegół |
|-----------|--------|---------|
| Model gwiazdowy + implementacja | ✅ Pełne | 3 fakty, 9+ wymiarów, SCD1/2 |
| Hierarchia czasu | ✅ Pełne | rok→kwartał→miesiąc→tydzień→dzień |
| Diagram bazy danych (graficzny) | ⚠️ Częściowe | Tylko ASCII art; brak grafiki PNG/SVG |
| Ekstrakcja przyrostowa | ✅ Pełne | Status tracker + extract_missing() |
| Staging / oczyszczanie | ✅ Pełne | BaseStaging, transformery, Polars |
| Wymiary + kolumny obliczeniowe | ✅ Pełne | |
| Miary / agregaty (odpowiednik DAX) | ✅ Pełne | 12 widoków KPI SQL |
| **Role / bezpieczeństwo** | ✅ Pełne | `analyst_ro` + `admin_rw`; migracja 004; autentykacja SHA-256 w dashboardzie |
| **Tabela błędów / odrzuceń** | ✅ Pełne | `stg_rejected_records` + `DQChecker.save_rejected()` w każdym transformerze |
| Automatyczna kontrola jakości | ✅ Pełne | `@task validate()` po `load()` w każdym DAGu; 10 testów jednostkowych |
| Raport z opisem etapów 1–4 | ✅ Pełne | `raport-bi.md` (sekcje 5a, 5b uzupełnione) |
| Ciągłość aktualizacji (iteracyjny napływ) | ✅ Pełne | Harmonogramy + ON CONFLICT + backfill |

**Pozostałe punkty do rozważenia:**
1. **Graficzny ERD** — ASCII art w `raport-bi.md`; można uzupełnić o PNG/SVG z narzędzia (np. DBeaver, dbdiagram.io)
