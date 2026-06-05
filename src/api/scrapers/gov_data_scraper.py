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

    def _validate(self, path: Path) -> None:
        """Raise ValueError if the downloaded file is corrupt or an error page."""
        fmt = self._file_format.lower()
        header = path.read_bytes()[:8]

        if fmt == "xlsx":
            # zipfile.is_zipfile checks the full ZIP structure, not just magic bytes
            import zipfile

            if not zipfile.is_zipfile(path):
                path.unlink(missing_ok=True)
                raise ValueError(f"Invalid xlsx (corrupt ZIP): {path}")

        elif fmt == "xls":
            if not header.startswith(b"\xd0\xcf\x11\xe0"):
                path.unlink(missing_ok=True)
                raise ValueError(f"Invalid xls (bad OLE2 header): {path}")

        else:
            # CSV: reject HTML error pages
            if header.lstrip().startswith(b"<"):
                path.unlink(missing_ok=True)
                raise ValueError(f"Server returned HTML instead of CSV: {path}")

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

        self._validate(file_path)
        return file_path


if __name__ == "__main__":
    link: str = "https://api.dane.gov.pl/resources/952632,ceny-ofertowe-mieszkan-dewelopera-zd-wrocaw-szarskiego-spoka-z-ograniczona-odpowiedzialnoscia-inwestycja-lesnica-2025-12-21/file"
    format: str = "csv"

    gov: GovDataScraper = GovDataScraper(link, format)
    gov.run()
