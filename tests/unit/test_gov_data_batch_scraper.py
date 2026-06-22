"""Unit tests for GovDataBatchScraper."""

from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

from src.api.config import Config
from src.api.scrapers.gov_data_batch import (
    GovDataBatchScraper,
    _output_stem_from_url,
    _PendingRecord,
)


def _config(tmp_path: Path) -> Config:
    return Config(
        database_url="postgresql+psycopg2://airflow:airflow@localhost:5432/nieruchomosci_test",
        gemini_api_key="",
        bdl_api_key="",
        gov_data_batch_size=2,
        cities=["Warszawa"],
    )


def test_reuse_existing_raw_when_file_on_disk(tmp_path):
    raw = tmp_path / "file.csv"
    raw.write_text("a,b\n1,2\n")
    record = _PendingRecord(
        download_url="http://example.com/a",
        file_format="csv",
        status="downloaded",
        raw_path=str(raw),
    )
    item = GovDataBatchScraper._reuse_existing_raw(record)
    assert item is not None
    assert item.path == str(raw)
    assert item.download_url == record.download_url


def test_reuse_existing_raw_missing_file_returns_none():
    record = _PendingRecord(
        download_url="http://example.com/a",
        file_format="csv",
        status="downloaded",
        raw_path="/nonexistent/file.csv",
    )
    assert GovDataBatchScraper._reuse_existing_raw(record) is None


@patch("src.api.scrapers.gov_data_batch.GovDataScraper")
@patch("src.api.scrapers.gov_data_batch.get_session")
@patch("src.api.scrapers.gov_data_batch.init_db")
@patch("src.api.scrapers.gov_data_batch.build_engine")
def test_scrape_batch_downloads_and_updates_status(
    mock_build_engine,
    mock_init_db,
    mock_get_session,
    mock_scraper_cls,
    tmp_path,
):
    config = _config(tmp_path)
    scraper = GovDataBatchScraper(config)

    pending_rows = [
        MagicMock(
            download_url="http://example.com/1",
            file_format="csv",
            status="pending",
            raw_path="",
            regon="111",
            developer_name="Dev A",
        ),
        MagicMock(
            download_url="http://example.com/2",
            file_format="",
            status="pending",
            raw_path="",
            regon=None,
            developer_name=None,
        ),
    ]

    mock_session = MagicMock()
    mock_get_session.return_value.__enter__.return_value = mock_session
    mock_repo = MagicMock()
    mock_repo.get_pending_by_cities.return_value = pending_rows

    downloaded = tmp_path / "downloaded.csv"
    mock_scraper_cls.return_value.run.return_value = downloaded

    with patch(
        "src.api.scrapers.gov_data_batch.DeveloperFileRepository",
        return_value=mock_repo,
    ):
        items = scraper.scrape_batch()

    assert len(items) == 1
    assert items[0].path == str(downloaded)
    assert items[0].download_url == "http://example.com/1"
    mock_repo.update_status.assert_called_with("http://example.com/1", "downloaded")
    mock_repo.update_raw_path.assert_called_with(
        "http://example.com/1", str(downloaded)
    )
    mock_scraper_cls.assert_called_once_with(
        resource_url="http://example.com/1",
        file_format="csv",
        output_stem=_output_stem_from_url("http://example.com/1"),
        client=ANY,
    )
    mock_repo.get_pending_by_cities.assert_called_once_with(["Warszawa"], limit=2)


def test_output_stem_is_stable_and_unique_per_url():
    a = _output_stem_from_url("http://example.com/a")
    b = _output_stem_from_url("http://example.com/b")
    assert a == _output_stem_from_url("http://example.com/a")
    assert a != b
    assert a.startswith("gov_")


@patch("src.api.scrapers.gov_data_batch.GovDataScraper")
@patch("src.api.scrapers.gov_data_batch.get_session")
@patch("src.api.scrapers.gov_data_batch.init_db")
@patch("src.api.scrapers.gov_data_batch.build_engine")
def test_scrape_batch_downloads_in_parallel(
    mock_build_engine,
    mock_init_db,
    mock_get_session,
    mock_scraper_cls,
    tmp_path,
):
    config = Config(
        database_url="postgresql+psycopg2://airflow:airflow@localhost:5432/nieruchomosci_test",
        gemini_api_key="",
        bdl_api_key="",
        gov_data_batch_size=10,
        gov_data_scrape_workers=4,
        cities=["Warszawa"],
    )
    scraper = GovDataBatchScraper(config)

    pending_rows = [
        MagicMock(
            download_url=f"http://example.com/{i}",
            file_format="csv",
            status="pending",
            raw_path="",
            regon="111",
            developer_name="Dev",
        )
        for i in range(4)
    ]

    mock_session = MagicMock()
    mock_get_session.return_value.__enter__.return_value = mock_session
    mock_repo = MagicMock()
    mock_repo.get_pending_by_cities.return_value = pending_rows

    def _run_side_effect():
        return tmp_path / "file.csv"

    mock_scraper_cls.return_value.run.side_effect = _run_side_effect

    with patch(
        "src.api.scrapers.gov_data_batch.DeveloperFileRepository",
        return_value=mock_repo,
    ):
        items = scraper.scrape_batch()

    assert len(items) == 4
    assert mock_scraper_cls.call_count == 4


@patch("src.api.scrapers.gov_data_batch.get_session")
@patch("src.api.scrapers.gov_data_batch.init_db")
@patch("src.api.scrapers.gov_data_batch.build_engine")
def test_scrape_batch_empty_queue(
    mock_build_engine,
    mock_init_db,
    mock_get_session,
    tmp_path,
):
    config = _config(tmp_path)
    scraper = GovDataBatchScraper(config)

    mock_session = MagicMock()
    mock_get_session.return_value.__enter__.return_value = mock_session
    mock_repo = MagicMock()
    mock_repo.get_pending_by_cities.return_value = []

    with patch(
        "src.api.scrapers.gov_data_batch.DeveloperFileRepository",
        return_value=mock_repo,
    ):
        items = scraper.scrape_batch()

    assert items == []


@patch("src.api.scrapers.gov_data_batch.GovDataScraper")
@patch("src.api.scrapers.gov_data_batch.get_session")
@patch("src.api.scrapers.gov_data_batch.init_db")
@patch("src.api.scrapers.gov_data_batch.build_engine")
def test_scrape_batch_marks_failed_on_download_error(
    mock_build_engine,
    mock_init_db,
    mock_get_session,
    mock_scraper_cls,
    tmp_path,
):
    config = _config(tmp_path)
    scraper = GovDataBatchScraper(config)

    pending_rows = [
        MagicMock(
            download_url="http://example.com/bad",
            file_format="csv",
            status="pending",
            raw_path="",
            regon=None,
            developer_name=None,
        ),
    ]

    mock_session = MagicMock()
    mock_get_session.return_value.__enter__.return_value = mock_session
    mock_repo = MagicMock()
    mock_repo.get_pending_by_cities.return_value = pending_rows
    mock_scraper_cls.return_value.run.side_effect = RuntimeError("network")

    with patch(
        "src.api.scrapers.gov_data_batch.DeveloperFileRepository",
        return_value=mock_repo,
    ):
        items = scraper.scrape_batch()

    assert items == []
    mock_repo.update_status.assert_called_with("http://example.com/bad", "failed")
