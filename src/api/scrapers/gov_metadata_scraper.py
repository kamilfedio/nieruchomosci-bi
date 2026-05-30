"""GOV Meatada scraper"""

from pathlib import Path

from httpx import Client, Timeout

from .base import BaseScraper


class GovMetadaScraper(BaseScraper):
    def __init__(
        self,
        link_to_file: str,
        category: str,
        connect_timeout: float = 10.0,
        read_timeout: float = 600.0,
        verify: bool = True,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        self._category: str = category
        self._link_to_file: str = link_to_file

        self._client: Client = Client(
            timeout=Timeout(connect=connect_timeout, read=read_timeout, write=5.0, pool=5.0),
            verify=verify,
            follow_redirects=False,
        )

    @property
    def source_name(self) -> str:
        return "gov_metadata"

    def extract(self) -> Path:
        file_path: Path = self._raw_dir / self.source_name / (self.batch_id + ".csv")
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with self._client.stream(
            "GET", self._link_to_file, params={"lang": "en"}
        ) as res:
            res.raise_for_status()

            with open(file_path, "wb") as f:
                for chunk in res.iter_bytes(chunk_size=8192):
                    f.write(chunk)

        return file_path


if __name__ == "__main__":
    link: str = "https://api.dane.gov.pl/1.4/datasets/resources/metadata.csv"

    gov: GovMetadaScraper = GovMetadaScraper(link, "Developers")
    gov.run()
