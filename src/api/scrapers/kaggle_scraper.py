"""Kaggle scraper"""

import zipfile
from datetime import datetime
from pathlib import Path

from kaggle import KaggleApi
from loguru import logger

from .base import BaseScraper


class KaggleScraper(BaseScraper):
    def __init__(
        self,
        dataset: str,
        tmp_dir: Path = Path("data/tmp"),
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        self._tmp_dir: Path = tmp_dir

        self._api: KaggleApi = KaggleApi()
        self._api.authenticate()
        self._dataset: str = dataset

    @property
    def source_name(self) -> str:
        return "kaggle_data"

    def _extract_newest_file(self) -> str:
        logger.debug("Fetching file list for dataset '{}'", self._dataset)
        files = self._api.dataset_list_files(self._dataset).files
        valid_files = [f for f in files if f is not None] if files else []
        if not valid_files:
            raise ValueError()

        latest_file = max(valid_files, key=lambda f: f.creation_date or datetime.min)  # type: ignore

        if latest_file.name is None:
            raise ValueError()
        logger.debug("Newest file: '{}'", latest_file.name)
        return latest_file.name

    @staticmethod
    def _delete_file(path: Path) -> None:
        logger.info("Deleting file {}", path)
        path.unlink()

    @staticmethod
    def _unzip(
        path: Path,
        extract_path_dir: Path,
        extract_file: str,
        output_name: str | None = None,
    ) -> Path:
        logger.info("Extracting zip, {}", path)
        with zipfile.ZipFile(path) as zf:
            extracted = Path(zf.extract(extract_file, extract_path_dir))

        if output_name and extracted.name != output_name:
            file_ext = extract_file.split(".")[-1]
            renamed = extracted.with_name(output_name + "." + file_ext)
            logger.info("Renaming file to {}", renamed)

            extracted.rename(renamed)
            return renamed

        return extracted

    def extract(self) -> Path:
        file = self._extract_newest_file()

        logger.info("Downloading '{}' from dataset '{}'", file, self._dataset)
        self._api.dataset_download_file(self._dataset, file, path=self._tmp_dir)

        zip_name: Path = self._tmp_dir / (file + ".zip")
        logger.debug(
            "Extracting '{}' to '{}'", zip_name, self._raw_dir / self.source_name
        )
        unzipped_path: Path = self._unzip(
            zip_name,
            self._raw_dir / self.source_name,
            file,
            output_name=self.batch_id,
        )

        logger.debug("Removing temporary zip '{}'", zip_name)
        self._delete_file(zip_name)

        return unzipped_path


if __name__ == "__main__":
    dataset = "krzysztofjamroz/apartment-prices-in-poland"
    kaggle: KaggleScraper = KaggleScraper(dataset)
    kaggle.run()
