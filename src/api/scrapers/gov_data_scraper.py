"""GOV Data scraper"""

from pathlib import Path

from httpx import Client, Timeout

from .base import BaseScraper


class GovDataScraper(BaseScraper):
    def __init__(
        self,
        resource_url: str,
        file_format: str,
        connect_timeout: float = 10.0,
        read_timeout: float = 600.0,
        verify: bool = True,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        self._resource_url: str = resource_url
        self._file_format: str = file_format

        self._client: Client = Client(
            timeout=Timeout(
                connect=connect_timeout, read=read_timeout, write=5.0, pool=5.0
            ),
            verify=verify,
            follow_redirects=True,
        )

    @property
    def source_name(self) -> str:
        return "gov_data"

    def extract(self) -> Path:
        file_path: Path = (
            self._raw_dir / self.source_name / (self.batch_id + "." + self._file_format)
        )
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with self._client.stream("GET", self._resource_url) as res:
            res.raise_for_status()

            with open(file_path, "wb") as f:
                for chunk in res.iter_bytes(chunk_size=8192):
                    f.write(chunk)

        return file_path


if __name__ == "__main__":
    link: str = "https://api.dane.gov.pl/resources/952632,ceny-ofertowe-mieszkan-dewelopera-zd-wrocaw-szarskiego-spoka-z-ograniczona-odpowiedzialnoscia-inwestycja-lesnica-2025-12-21/file"
    format: str = "csv"

    gov: GovDataScraper = GovDataScraper(link, format)
    gov.run()
