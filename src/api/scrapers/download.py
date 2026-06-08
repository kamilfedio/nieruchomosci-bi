"""Resumable HTTP download helpers for large scraper files."""

import time
from pathlib import Path

import httpx
from loguru import logger

_CHUNK_SIZE = 65_536
_RETRY_DELAYS = (5, 15, 60, 120, 300)


class IncompleteDownloadError(Exception):
    """Raised when the downloaded file size does not match the declared total."""


def _expected_total_bytes(response: httpx.Response, resume_from: int) -> int | None:
    content_range = response.headers.get("content-range")
    if content_range:
        total_part = content_range.rsplit("/", maxsplit=1)[-1]
        if total_part != "*":
            return int(total_part)

    content_length = response.headers.get("content-length")
    if content_length is None:
        return None
    length = int(content_length)
    return resume_from + length if resume_from > 0 else length


def download_to_file(
    client: httpx.Client,
    url: str,
    dest: Path,
    *,
    params: dict[str, str] | None = None,
    max_retries: int = 5,
    chunk_size: int = _CHUNK_SIZE,
) -> None:
    """Download URL to dest, resuming from partial data on transient failures."""
    dest.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(max_retries):
        resume_from = dest.stat().st_size if dest.exists() else 0
        headers: dict[str, str] = {}
        if resume_from > 0:
            headers["Range"] = f"bytes={resume_from}-"
            logger.info(
                "Resuming download from byte {} (attempt {}/{})",
                resume_from,
                attempt + 1,
                max_retries,
            )
        else:
            logger.info(
                "Starting download (attempt {}/{})",
                attempt + 1,
                max_retries,
            )

        try:
            with client.stream(
                "GET", url, params=params, headers=headers
            ) as response:
                if resume_from > 0 and response.status_code == 416:
                    if resume_from > 0:
                        logger.info(
                            "Range not satisfiable at byte {} — treating as complete",
                            resume_from,
                        )
                        return
                    dest.unlink(missing_ok=True)
                    continue

                if resume_from > 0 and response.status_code == 200:
                    logger.warning(
                        "Server ignored Range header — restarting download from scratch"
                    )
                    dest.unlink(missing_ok=True)
                    resume_from = 0

                response.raise_for_status()

                mode = "ab" if resume_from > 0 and response.status_code == 206 else "wb"
                if mode == "wb" and dest.exists():
                    dest.unlink(missing_ok=True)

                with open(dest, mode) as file:
                    for chunk in response.iter_bytes(chunk_size=chunk_size):
                        file.write(chunk)

                expected_total = _expected_total_bytes(response, resume_from)
                actual_size = dest.stat().st_size
                if expected_total is not None and actual_size != expected_total:
                    msg = (
                        f"Incomplete download: got {actual_size} bytes, "
                        f"expected {expected_total}"
                    )
                    raise IncompleteDownloadError(msg)

                return
        except (
            httpx.NetworkError,
            httpx.TimeoutException,
            IncompleteDownloadError,
        ) as exc:
            if attempt == max_retries - 1:
                raise
            delay = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
            logger.warning(
                "Download interrupted ({}), retrying in {}s",
                exc,
                delay,
            )
            time.sleep(delay)
