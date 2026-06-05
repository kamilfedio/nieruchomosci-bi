"""Loader: gov_metadata processed parquet → SQLite developer_files"""

from pathlib import Path

import polars as pl
from src.api.config import Config
from src.api.db.connection import build_engine, get_session, init_db
from src.api.db.models import DeveloperFile
from src.api.db.repositories.developer_files import DeveloperFileRepository

from .base import BaseLoader

# 8 bound params per row; keep total well below SQLite's 32766-variable limit
_BATCH_SIZE = 4_000


class GovMetadataLoader(BaseLoader):
    def __init__(
        self,
        source_path: Path,
        config: Config | None = None,
    ) -> None:
        super().__init__(source_path)
        self._config = config or Config()

    def _read_filtered(self) -> pl.DataFrame:
        lf = pl.scan_parquet(self._source_path).select(
            [
                "download_url",
                "developer_name",
                "title",
                "regon",
                "file_format",
                "institution_city",
                "data_date",
                "dataset_url",
            ]
        )
        if self._config.cities:
            lf = lf.filter(pl.col("institution_city").is_in(self._config.cities))
        return lf.collect()

    @staticmethod
    def _to_records(df: pl.DataFrame) -> list[DeveloperFile]:
        return [
            DeveloperFile(
                download_url=row["download_url"] or "",
                developer_name=row["developer_name"],
                title=row["title"],
                regon=str(row["regon"]) if row["regon"] is not None else None,
                file_format=row["file_format"],
                institution_city=row["institution_city"],
                data_date=(
                    str(row["data_date"]) if row["data_date"] is not None else None
                ),
                dataset_url=row["dataset_url"],
            )
            for row in df.iter_rows(named=True)
        ]

    def load(self) -> int:
        engine = build_engine(self._config.db_path)
        init_db(engine)

        df = self._read_filtered()
        records = self._to_records(df)

        total_inserted = 0
        with get_session(engine) as session:
            repo = DeveloperFileRepository(session)
            for i in range(0, len(records), _BATCH_SIZE):
                batch = records[i : i + _BATCH_SIZE]
                total_inserted += repo.insert_or_ignore_batch(batch)

        return total_inserted


if __name__ == "__main__":
    file = Path("data/processed/gov_metadata/20260601_104757.parquet")
    loader = GovMetadataLoader(source_path=file)
    loader.run()
