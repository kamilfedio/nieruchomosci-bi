"""LLM-based column mapper: source CSV headers → unified TARGET_SCHEMA."""

import json

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


def map_columns(
    source_columns: list[str],
    api_key: str,
) -> dict[str, str | None]:
    """Ask Gemini to map source CSV columns to TARGET_SCHEMA.

    Returns dict[target_col → source_col | None].
    """
    client = genai.Client(api_key=api_key)

    prompt = _PROMPT_TMPL.format(
        source_columns=json.dumps(source_columns, ensure_ascii=False, indent=2),
        target_columns=json.dumps(TARGET_COLUMNS, ensure_ascii=False),
    )

    logger.debug("Requesting column mapping for {} source columns", len(source_columns))

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

    mapping: dict[str, str | None] = json.loads(response.text)
    logger.debug("Column mapping: {}", mapping)
    return mapping
