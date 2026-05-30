"""NBP scraper"""

from pathlib import Path

from httpx import Client

from .base import BaseScraper


class NBPScraper(BaseScraper):
    def __init__(
        self,
        link_to_file: str,
        timeout: float = 10.0,
        verify: bool = True,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        self._link_to_file: str = link_to_file

        self._client: Client = Client(
            timeout=timeout,
            verify=verify,
            follow_redirects=False,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "*/*;q=0.8",
                "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )

    @property
    def source_name(self) -> str:
        return "nbp_data"

    def extract(self) -> Path:
        file_path: Path = self._raw_dir / self.source_name / (self.batch_id + ".xlsx")
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with self._client.stream("GET", self._link_to_file) as res:
            res.raise_for_status()

            with open(file_path, "wb") as f:
                for chunk in res.iter_bytes(chunk_size=8192):
                    f.write(chunk)

        return file_path


if __name__ == "__main__":
    link: str = "https://static.nbp.pl/dane/rynek-nieruchomosci/ceny_mieszkan.xlsx"

    nbp: NBPScraper = NBPScraper(link)
    nbp.run()
