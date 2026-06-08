"""Unit tests for KaggleScraper — mocked Kaggle API, no network."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

from src.api.scrapers.kaggle_scraper import KaggleScraper


def _file(name: str, creation_date: datetime | None = None) -> MagicMock:
    f = MagicMock()
    f.name = name
    f.creation_date = creation_date or datetime(2024, 6, 6, 8, 45, 39)
    return f


def _scraper(tmp_path: Path) -> KaggleScraper:
    with patch.object(KaggleScraper, "__init__", lambda self, *a, **kw: None):
        scraper = KaggleScraper("owner/dataset")
    scraper._raw_dir = tmp_path / "raw"
    scraper._tmp_dir = tmp_path / "tmp"
    scraper._tmp_dir.mkdir(parents=True, exist_ok=True)
    scraper._dataset = "owner/dataset"
    scraper._api = MagicMock()
    scraper.batch_id = "20260101_120000"
    return scraper


def test_filter_sale_files_excludes_rent():
    files = [
        _file("apartments_pl_2024_01.csv"),
        _file("apartments_pl_2024_02_rent.csv"),
    ]
    result = KaggleScraper._filter_sale_files(files)
    assert len(result) == 1
    assert result[0].name == "apartments_pl_2024_01.csv"


def test_filter_sale_files_falls_back_when_only_rent():
    files = [_file("apartments_pl_2024_02_rent.csv")]
    result = KaggleScraper._filter_sale_files(files)
    assert len(result) == 1


def test_output_name_from_kaggle_filename():
    f = _file("apartments_pl_2023_08.csv")
    assert KaggleScraper._output_name(f) == "20230801_000000"


def test_output_name_fallback_to_stem():
    f = _file("custom_snapshot.csv")
    assert KaggleScraper._output_name(f) == "custom_snapshot"


def test_extract_downloads_newest_sale_file(tmp_path):
    scraper = _scraper(tmp_path)
    newest = _file("apartments_pl_2024_03.csv")
    older = _file("apartments_pl_2024_01.csv")
    rent = _file("apartments_pl_2024_04_rent.csv")
    scraper._list_dataset_files = MagicMock(return_value=[older, newest, rent])  # type: ignore[method-assign]

    csv_name = "apartments_pl_2024_03.csv"
    zip_path = scraper._tmp_dir / f"{csv_name}.zip"
    with ZipFile(zip_path, "w") as zf:
        zf.writestr(csv_name, "id,price\n1,100")

    scraper._api.dataset_download_file = MagicMock()

    result = scraper.extract()

    scraper._api.dataset_download_file.assert_called_once_with(
        "owner/dataset", csv_name, path=scraper._tmp_dir
    )
    assert result.name == "20240301_000000.csv"
    assert result.exists()


def test_extract_missing_downloads_all_when_same_creation_date(tmp_path):
    scraper = _scraper(tmp_path)
    same_date = datetime(2024, 6, 6, 8, 45, 39)
    files = [
        _file("apartments_pl_2023_08.csv", same_date),
        _file("apartments_pl_2023_09.csv", same_date),
        _file("apartments_pl_2023_10.csv", same_date),
    ]
    scraper._list_dataset_files = MagicMock(return_value=files)  # type: ignore[method-assign]

    def fake_download(dataset: str, file_name: str, path: Path) -> None:
        zip_path = path / f"{file_name}.zip"
        with ZipFile(zip_path, "w") as zf:
            zf.writestr(file_name, "id,price\n1,100")

    scraper._api.dataset_download_file = MagicMock(side_effect=fake_download)

    result = scraper.extract_missing()

    assert len(result) == 3
    assert scraper._api.dataset_download_file.call_count == 3
    names = {p.name for p in result}
    assert names == {
        "20230801_000000.csv",
        "20230901_000000.csv",
        "20231001_000000.csv",
    }


def test_extract_missing_returns_existing_and_downloads_missing(tmp_path):
    scraper = _scraper(tmp_path)
    raw_dir = scraper._raw_dir / scraper.source_name
    raw_dir.mkdir(parents=True)
    (raw_dir / "20230801_000000.csv").write_text("already here")

    files = [
        _file("apartments_pl_2023_08.csv"),
        _file("apartments_pl_2023_09.csv"),
    ]
    scraper._list_dataset_files = MagicMock(return_value=files)  # type: ignore[method-assign]

    csv_name = "apartments_pl_2023_09.csv"
    zip_path = scraper._tmp_dir / f"{csv_name}.zip"
    with ZipFile(zip_path, "w") as zf:
        zf.writestr(csv_name, "id,price\n2,200")

    scraper._api.dataset_download_file = MagicMock()

    result = scraper.extract_missing()

    assert len(result) == 2
    assert result[0].name == "20230801_000000.csv"
    assert result[1].name == "20230901_000000.csv"
    scraper._api.dataset_download_file.assert_called_once()
