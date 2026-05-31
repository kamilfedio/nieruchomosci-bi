"""NBP staging"""

import warnings
from pathlib import Path

import polars as pl
from loguru import logger

from .base import BaseStaging

_CITIES_17 = [
    "Białystok",
    "Bydgoszcz",
    "Gdańsk",
    "Gdynia",
    "Katowice",
    "Kielce",
    "Kraków",
    "Lublin",
    "Łódź",
    "Olsztyn",
    "Opole",
    "Poznań",
    "Rzeszów",
    "Szczecin",
    "Warszawa",
    "Wrocław",
    "Zielona Góra",
]

_CITIES_16 = [
    "Białystok",
    "Bydgoszcz",
    "Trójmiasto",
    "Katowice",
    "Kielce",
    "Kraków",
    "Lublin",
    "Łódź",
    "Olsztyn",
    "Opole",
    "Poznań",
    "Rzeszów",
    "Szczecin",
    "Warszawa",
    "Wrocław",
    "Zielona Góra",
]

_AGGREGATES = ["7_cities", "10_cities", "6_cities_excl_warszawa", "9_cities"]

_DATA_START = 7
_DATA_END = 86


def _parse_quarters(lf: pl.LazyFrame) -> pl.LazyFrame:
    roman = pl.col("quarter").str.split(" ").list.get(0)
    quarter_int = (
        pl.when(roman == "I")
        .then(1)
        .when(roman == "II")
        .then(2)
        .when(roman == "III")
        .then(3)
        .when(roman == "IV")
        .then(4)
        .otherwise(None)
        .cast(pl.Int8)
    )
    year = pl.col("quarter").str.split(" ").list.get(1).cast(pl.Int16)
    return (
        lf.with_columns(quarter_int.alias("_q"), year.alias("year"))
        .drop("quarter")
        .rename({"_q": "quarter"})
    )


def _slice_and_melt(
    df: pl.DataFrame,
    quarter_col: int,
    entities: list[str],
    value_col: str,
) -> pl.DataFrame:
    q = f"column_{quarter_col + 1}"
    cols = [f"column_{quarter_col + 2 + i}" for i in range(len(entities))]

    rename = {q: "quarter"}
    rename.update(dict(zip(cols, entities, strict=True)))

    _aggregate_entities = set(_AGGREGATES + ["harmonized_index"])

    return (
        df[_DATA_START:_DATA_END]
        .select([q] + cols)
        .rename(rename)
        .filter(pl.col("quarter").is_not_null())
        .unpivot(
            index=["quarter"], on=entities, variable_name="city", value_name=value_col
        )
        .with_columns(
            pl.col(value_col).cast(pl.Float64, strict=False),
            pl.col("city").is_in(list(_aggregate_entities)).alias("is_aggregate"),
        )
    )


def _extract_prices(
    df: pl.DataFrame,
    quarter_col: int,
    cities: list[str],
    price_type: str,
    market: str,
) -> pl.DataFrame:
    return _slice_and_melt(
        df, quarter_col, cities + _AGGREGATES, "price_per_sqm"
    ).with_columns(
        pl.lit(price_type).alias("price_type"),
        pl.lit(market).alias("market"),
    )


def _extract_hedonic_qoq(df: pl.DataFrame) -> pl.DataFrame:
    # quarter at 0-based col 46, 16 cities + 4 aggregates + harmonized index
    return _slice_and_melt(
        df, 46, _CITIES_16 + _AGGREGATES + ["harmonized_index"], "hedonic_qoq"
    )


def _extract_hedonic_yoy(df: pl.DataFrame) -> pl.DataFrame:
    # no own quarter column — shares row alignment with qoq (use col 46 for quarter)
    # city data starts at 0-based col 69 (polars column_70)
    entities = _CITIES_16 + _AGGREGATES
    q = "column_47"  # same quarter source as qoq
    cols = [f"column_{70 + i}" for i in range(len(entities))]

    rename = {q: "quarter"}
    rename.update(dict(zip(cols, entities, strict=True)))

    _agg_set = set(_AGGREGATES + ["harmonized_index"])

    return (
        df[_DATA_START:_DATA_END]
        .select([q] + cols)
        .rename(rename)
        .filter(pl.col("quarter").is_not_null())
        .unpivot(
            index=["quarter"],
            on=entities,
            variable_name="city",
            value_name="hedonic_yoy",
        )
        .with_columns(
            pl.col("hedonic_yoy").cast(pl.Float64, strict=False),
            pl.col("city").is_in(list(_agg_set)).alias("is_aggregate"),
        )
    )


def _read_sheets(path: Path) -> tuple[pl.DataFrame, pl.DataFrame]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        primary = pl.read_excel(path, sheet_name="Rynek pierwotny", has_header=False)
        secondary = pl.read_excel(path, sheet_name="Rynek wtórny", has_header=False)
    return primary, secondary


class NBPStaging(BaseStaging):
    @property
    def source_name(self) -> str:
        return "nbp_data"

    def read(self) -> pl.LazyFrame:
        primary, secondary = _read_sheets(self._source_path)
        return pl.concat(
            [
                _extract_prices(primary, 0, _CITIES_17, "offer", "primary"),
                _extract_prices(primary, 23, _CITIES_17, "transaction", "primary"),
                _extract_prices(secondary, 0, _CITIES_17, "offer", "secondary"),
                _extract_prices(secondary, 23, _CITIES_17, "transaction", "secondary"),
            ]
        ).lazy()

    def _read_hedonic(self) -> pl.LazyFrame:
        _, secondary = _read_sheets(self._source_path)
        qoq = _extract_hedonic_qoq(secondary)
        yoy = _extract_hedonic_yoy(secondary)
        return qoq.join(
            yoy.select(["quarter", "city", "hedonic_yoy"]),
            on=["quarter", "city"],
            how="left",
        ).lazy()

    def _rename_columns(self, df: pl.LazyFrame) -> pl.LazyFrame:
        return df

    def stage(self, df: pl.LazyFrame) -> pl.LazyFrame:
        return _parse_quarters(df)

    def save(self, df: pl.DataFrame) -> Path:
        path = (
            self._staging_dir
            / self.source_name
            / (self._source_path.stem + "_prices.parquet")
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(path)
        return path

    def _save_hedonic(self, df: pl.DataFrame) -> Path:
        path = (
            self._staging_dir
            / self.source_name
            / (self._source_path.stem + "_hedonic.parquet")
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(path)
        return path

    def run(self) -> Path:
        logger.info("Starting NBP staging of '{}'", self._source_path)

        lf = self.read()
        lf = self.stage(lf)
        lf = self._add_technical_columns(lf)
        lf = self._dedup(lf)
        df_prices = lf.collect()
        prices_path = self.save(df_prices)
        logger.info("Prices staged: {} rows → '{}'", len(df_prices), prices_path)

        lf_h = self._read_hedonic()
        lf_h = _parse_quarters(lf_h)
        lf_h = self._add_technical_columns(lf_h)
        lf_h = self._dedup(lf_h)
        df_hedonic = lf_h.collect()
        hedonic_path = self._save_hedonic(df_hedonic)
        logger.info(
            "Hedonic indices staged: {} rows → '{}'", len(df_hedonic), hedonic_path
        )

        return prices_path


if __name__ == "__main__":
    file = Path("data/raw/nbp_data/20260530_155402.xlsx")
    staging = NBPStaging(source_path=file)
    staging.run()
