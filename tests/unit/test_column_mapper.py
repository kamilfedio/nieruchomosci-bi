"""Unit tests for column_mapper — no Gemini calls."""

from unittest.mock import patch

from src.api.staging.column_mapper import (
    _MIN_SOURCE_COLUMNS,
    map_columns,
)
from src.api.staging.schema import TARGET_COLUMNS


def test_map_columns_skips_gemini_when_too_few_columns():
    with patch("src.api.staging.column_mapper._call_gemini") as mock_gemini:
        mapping = map_columns(["only_one_col"], api_key="test-key")

    mock_gemini.assert_not_called()
    assert set(mapping.keys()) == set(TARGET_COLUMNS)
    assert all(v is None for v in mapping.values())


def test_map_columns_calls_gemini_when_enough_columns():
    expected = dict.fromkeys(TARGET_COLUMNS)
    expected["unit_id"] = "nr_lokalu"

    with patch(
        "src.api.staging.column_mapper._call_gemini",
        return_value=expected,
    ) as mock_gemini:
        cols = [f"col_{i}" for i in range(_MIN_SOURCE_COLUMNS)]
        mapping = map_columns(cols, api_key="test-key")

    mock_gemini.assert_called_once()
    assert mapping["unit_id"] == "nr_lokalu"
