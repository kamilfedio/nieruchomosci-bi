"""LLM-based column mapper: source CSV headers → unified TARGET_SCHEMA.

Results are cached in PostgreSQL keyed by an MD5 hash of the sorted column
names. Identical column sets (e.g. the same developer format repeated
across daily snapshots) never call Gemini more than once.
"""

import hashlib
import json

from google import genai
from google.genai import types
from loguru import logger
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .schema import TARGET_COLUMNS

_MODEL = "gemini-2.5-flash"

_SYSTEM = """\
Jesteś ekspertem od polskich danych rynku nieruchomości.
Otrzymasz listę kolumn z pliku CSV dewelopera i schemat docelowy.
Twoim zadaniem jest dopasowanie kolumn źródłowych do docelowych.
Zwróć TYLKO obiekt JSON — bez komentarzy, bez markdown.
"""

_PROMPT_TMPL = """\
Kolumny źródłowe (CSV dewelopera):
{source_columns}

Kolumny docelowe do wypełnienia:
{target_columns}

Opis kolumn docelowych (nazwy w angielskim snake_case):
- unit_id: unikalny identyfikator lokalu/mieszkania nadany przez dewelopera
- investment_id: nazwa lub identyfikator inwestycji/przedsięwzięcia
- developer_name: pełna nazwa dewelopera
- city: miejscowość lokalizacji inwestycji (nie siedziba dewelopera)
- street: ulica lokalizacji inwestycji
- total_price_gross: całkowita cena brutto lokalu w PLN
- usable_area_m2: powierzchnia użytkowa w m²
- unit_status: status lokalu (dostępny, zarezerwowany, sprzedany itp.)
- updated_at: data ostatniej aktualizacji ceny lub statusu

Zasady:
1. Dla każdej kolumny docelowej podaj DOKŁADNĄ nazwę kolumny źródłowej
   (przepisz ją tak jak jest).
2. Jeśli żadna kolumna źródłowa nie odpowiada kolumnie docelowej, użyj null.
3. Nie wymyślaj kolumn — tylko te które są na liście źródłowej.
4. Jeśli jest kilka kandydatów, wybierz najlepiej pasującą.

Zwróć JSON w formacie:
{{"unit_id": "<nazwa_kolumny lub null>", "investment_id": "...", ...}}
"""

_RESPONSE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        col: types.Schema(type=types.Type.STRING, nullable=True)
        for col in TARGET_COLUMNS
    },
    required=TARGET_COLUMNS,
)


def _cache_key(columns: list[str]) -> str:
    normalized = "|".join(sorted(columns))
    return hashlib.md5(normalized.encode()).hexdigest()  # noqa: S324


def _ensure_cache_table(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS column_mapping_cache (
                    cache_key  TEXT PRIMARY KEY,
                    mapping    JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )


def _cache_get(engine: Engine, key: str) -> dict[str, str | None] | None:
    _ensure_cache_table(engine)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT mapping FROM column_mapping_cache WHERE cache_key = :key"),
            {"key": key},
        ).fetchone()
    return dict(row[0]) if row else None


def _cache_set(engine: Engine, key: str, mapping: dict[str, str | None]) -> None:
    _ensure_cache_table(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO column_mapping_cache (cache_key, mapping)
                VALUES (:key, CAST(:mapping AS JSONB))
                ON CONFLICT (cache_key) DO UPDATE SET mapping = EXCLUDED.mapping
                """
            ),
            {"key": key, "mapping": json.dumps(mapping)},
        )


def _call_gemini(source_columns: list[str], api_key: str) -> dict[str, str | None]:
    client = genai.Client(api_key=api_key)
    prompt = _PROMPT_TMPL.format(
        source_columns=json.dumps(source_columns, ensure_ascii=False, indent=2),
        target_columns=json.dumps(TARGET_COLUMNS, ensure_ascii=False),
    )
    response = client.models.generate_content(
        model=_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM,
            response_mime_type="application/json",
            response_schema=_RESPONSE_SCHEMA,
            temperature=0.0,
        ),
    )
    if not response.text:
        msg = "Empty response from Gemini column mapping"
        raise ValueError(msg)
    return json.loads(response.text)


_PROCESS_CACHE: dict[str, dict[str, str | None]] = {}


def map_columns(
    source_columns: list[str],
    api_key: str,
    database_url: str | None = None,
) -> dict[str, str | None]:
    """Map source CSV columns to TARGET_SCHEMA via Gemini.

    Cache hierarchy (fastest first):
      1. In-process dict  — zero-cost within same transform task
      2. PostgreSQL table — survives across DAG runs
      3. Gemini API call  — stores result in both caches
    """
    key = _cache_key(source_columns)

    if key in _PROCESS_CACHE:
        logger.debug("Column mapping process-cache hit ({})", key[:8])
        return _PROCESS_CACHE[key]

    engine: Engine | None = None
    if database_url is not None:
        engine = create_engine(database_url, pool_pre_ping=True)
        cached = _cache_get(engine, key)
        if cached is not None:
            logger.debug("Column mapping DB-cache hit ({})", key[:8])
            _PROCESS_CACHE[key] = cached
            return cached

    logger.debug("Requesting column mapping for {} source columns", len(source_columns))
    mapping = _call_gemini(source_columns, api_key)
    logger.debug("Column mapping: {}", mapping)

    _PROCESS_CACHE[key] = mapping
    if engine is not None:
        _cache_set(engine, key, mapping)

    return mapping
