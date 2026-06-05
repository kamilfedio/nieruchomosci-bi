"""LLM-based column mapper: source CSV headers → unified TARGET_SCHEMA.

Results are cached in SQLite keyed by an MD5 hash of the sorted column
names. Identical column sets (e.g. the same developer format repeated
across daily snapshots) never call Gemini more than once.
"""

import hashlib
import json
import sqlite3
from pathlib import Path

from google import genai
from google.genai import types
from loguru import logger

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

_DDL_CACHE = """
CREATE TABLE IF NOT EXISTS column_mapping_cache (
    cache_key  TEXT PRIMARY KEY,
    mapping    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
)
"""


def _cache_key(columns: list[str]) -> str:
    normalized = "|".join(sorted(columns))
    return hashlib.md5(normalized.encode()).hexdigest()  # noqa: S324


def _cache_get(db_path: Path, key: str) -> dict[str, str | None] | None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(_DDL_CACHE)
        row = conn.execute(
            "SELECT mapping FROM column_mapping_cache WHERE cache_key = ?", (key,)
        ).fetchone()
    return json.loads(row[0]) if row else None


def _cache_set(db_path: Path, key: str, mapping: dict[str, str | None]) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(_DDL_CACHE)
        conn.execute(
            "INSERT OR REPLACE INTO column_mapping_cache (cache_key, mapping)"
            " VALUES (?, ?)",
            (key, json.dumps(mapping)),
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
    return json.loads(response.text)


def map_columns(
    source_columns: list[str],
    api_key: str,
    db_path: Path | None = None,
) -> dict[str, str | None]:
    """Map source CSV columns to TARGET_SCHEMA via Gemini, with SQLite cache.

    Returns dict[target_col → source_col | None].
    Cache hit: no API call. Cache miss: calls Gemini and stores result.
    """
    key = _cache_key(source_columns)

    if db_path is not None:
        cached = _cache_get(db_path, key)
        if cached is not None:
            logger.debug("Column mapping cache hit ({})", key[:8])
            return cached

    logger.debug("Requesting column mapping for {} source columns", len(source_columns))
    mapping = _call_gemini(source_columns, api_key)
    logger.debug("Column mapping: {}", mapping)

    if db_path is not None:
        _cache_set(db_path, key, mapping)

    return mapping
