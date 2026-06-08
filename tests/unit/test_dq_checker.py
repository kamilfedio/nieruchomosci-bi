"""Unit tests for DQChecker and DQRule."""

from unittest.mock import MagicMock, patch

import polars as pl
import pytest
from src.api.quality.checker import DQChecker
from src.api.quality.rules import DQRule, gus_bdl_rules, kaggle_rules

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def simple_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "id": ["a", "b", "c", None],
            "price": [100.0, 0.0, 200.0, 150.0],
            "square_meters": [50.0, 30.0, 0.0, 40.0],
        }
    )


@pytest.fixture
def checker_error_only() -> DQChecker:
    rules = [
        DQRule(
            name="id_not_null",
            description="id must not be null",
            severity="ERROR",
            predicate=pl.col("id").is_not_null(),
        ),
        DQRule(
            name="price_positive",
            description="price must be > 0",
            severity="ERROR",
            predicate=pl.col("price") > 0,
        ),
    ]
    return DQChecker(source="test", batch_id="batch_001", rules=rules)


@pytest.fixture
def checker_with_warning() -> DQChecker:
    rules = [
        DQRule(
            name="id_not_null",
            description="id must not be null",
            severity="ERROR",
            predicate=pl.col("id").is_not_null(),
        ),
        DQRule(
            name="area_positive",
            description="area must be > 0",
            severity="WARNING",
            predicate=pl.col("square_meters") > 0,
        ),
    ]
    return DQChecker(source="test", batch_id="batch_001", rules=rules)


# ── Tests: check() ────────────────────────────────────────────────────────────


def test_check_all_pass() -> None:
    df = pl.DataFrame({"price": [10.0, 20.0], "square_meters": [5.0, 10.0]})
    rule = DQRule("p", "price > 0", "ERROR", pl.col("price") > 0)
    checker = DQChecker("src", "b", [rule])

    passed, rejected = checker.check(df.lazy())

    assert passed.collect().shape[0] == 2
    assert rejected.is_empty()


def test_check_rejects_nulls(
    checker_error_only: DQChecker, simple_df: pl.DataFrame
) -> None:
    passed, rejected = checker_error_only.check(simple_df.lazy())

    passed_df = passed.collect()
    # Row with null id or price=0 → rejected; row c passes both ERROR rules
    assert all(r is not None for r in passed_df["id"].to_list())
    assert all(p > 0 for p in passed_df["price"].to_list())

    # rejected has annotation columns
    assert "dq_rule_name" in rejected.columns
    assert "dq_severity" in rejected.columns
    assert "dq_source" in rejected.columns
    assert set(rejected["dq_severity"].to_list()) == {"ERROR"}


def test_check_multiple_rules_both_fail(simple_df: pl.DataFrame) -> None:
    """A row that breaks two rules should appear in rejected twice."""
    rules = [
        DQRule("id_not_null", "id must not be null", "ERROR", pl.col("id").is_not_null()),
        DQRule("price_positive", "price > 0", "ERROR", pl.col("price") > 0),
    ]
    checker = DQChecker("src", "b", rules)
    _, rejected = checker.check(simple_df.lazy())

    # Row with null id appears once (for id_not_null rule)
    # Row with price=0 appears once (for price_positive rule)
    rule_names = rejected["dq_rule_name"].to_list()
    assert "id_not_null" in rule_names
    assert "price_positive" in rule_names


def test_warning_does_not_drop_row(
    checker_with_warning: DQChecker, simple_df: pl.DataFrame
) -> None:
    """WARNING rule: row with area=0 stays in passed but appears in rejected."""
    passed, rejected = checker_with_warning.check(simple_df.lazy())

    passed_df = passed.collect()
    # Only ERROR rule drops rows (id_not_null drops row with id=None)
    # WARNING rule (area>0) does NOT drop — row c (area=0) stays in passed
    area_zero_in_passed = passed_df.filter(pl.col("square_meters") == 0)
    assert len(area_zero_in_passed) == 1

    # But it does appear in rejected with WARNING severity
    warnings = rejected.filter(pl.col("dq_severity") == "WARNING")
    assert len(warnings) >= 1


def test_rejected_has_dq_annotations(simple_df: pl.DataFrame) -> None:
    rules = [DQRule("p", "price > 0", "ERROR", pl.col("price") > 0)]
    checker = DQChecker("my_source", "my_batch", rules)
    _, rejected = checker.check(simple_df.lazy())

    assert rejected["dq_source"].to_list() == ["my_source"]
    assert rejected["dq_batch_id"].to_list() == ["my_batch"]
    assert rejected["dq_rule_name"].to_list() == ["p"]


def test_no_rules_returns_all_passed() -> None:
    df = pl.DataFrame({"x": [1, 2, 3]})
    checker = DQChecker("src", "b", rules=[])
    passed, rejected = checker.check(df.lazy())

    assert passed.collect().shape[0] == 3
    assert rejected.is_empty()


# ── Tests: save_rejected() ────────────────────────────────────────────────────


def test_save_rejected_empty_returns_zero() -> None:
    checker = DQChecker("src", "b", [])
    empty = pl.DataFrame(
        schema={
            "dq_source": pl.String,
            "dq_batch_id": pl.String,
            "dq_rule_name": pl.String,
            "dq_rule_description": pl.String,
            "dq_severity": pl.String,
        }
    )
    assert checker.save_rejected(empty, "postgresql://x") == 0


def test_save_rejected_calls_db(simple_df: pl.DataFrame) -> None:
    rules = [DQRule("p", "price > 0", "ERROR", pl.col("price") > 0)]
    checker = DQChecker("src", "b", rules)
    _, rejected = checker.check(simple_df.lazy())

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)

    # Imports are local inside save_rejected, so patch the source modules
    with (
        patch("src.api.db.connection.build_engine"),
        patch("src.api.db.connection.get_session", return_value=mock_session),
    ):
        count = checker.save_rejected(rejected, "postgresql://test")

    assert count == len(rejected)
    mock_session.add_all.assert_called_once()
    inserted = mock_session.add_all.call_args[0][0]
    assert len(inserted) == count
    # Verify each record has expected attributes
    for rec in inserted:
        assert rec.source == "src"
        assert rec.batch_id == "b"
        assert rec.rule_name == "p"
        assert rec.severity == "ERROR"


# ── Tests: rule sets ──────────────────────────────────────────────────────────


def test_kaggle_rules_reject_null_id() -> None:
    df = pl.DataFrame(
        {
            "id": [None, "x"],
            "price": [100.0, 100.0],
            "square_meters": [10.0, 10.0],
            "build_year": [None, None],
        }
    )
    checker = DQChecker("kaggle", "b", kaggle_rules())
    passed, rejected = checker.check(df.lazy())

    assert passed.collect().shape[0] == 1
    assert "id_not_null" in rejected["dq_rule_name"].to_list()


def test_gus_bdl_rules_warn_on_zero_population() -> None:
    df = pl.DataFrame(
        {
            "city": ["warszawa", "krakow"],
            "year": [2023, 2023],
            "population": [0, 1_000_000],
            "avg_gross_salary": [5000.0, 6000.0],
        }
    )
    checker = DQChecker("gus_bdl", "b", gus_bdl_rules())
    passed, rejected = checker.check(df.lazy())

    # WARNING rule — both rows stay in passed
    assert passed.collect().shape[0] == 2
    # But zero-population row appears in rejected as WARNING
    assert "population_positive" in rejected["dq_rule_name"].to_list()
    assert all(s == "WARNING" for s in rejected["dq_severity"].to_list())
