"""Unit tests for resumable scraper downloads."""

from pathlib import Path

import httpx
import pytest

from src.api.scrapers.download import download_to_file


def test_download_to_file_resumes_after_interrupted_stream(tmp_path: Path) -> None:
    payload = b"abcdefghij"
    interrupted = {"done": False}

    def handler(request: httpx.Request) -> httpx.Response:
        range_header = request.headers.get("range")
        if range_header is None:
            return httpx.Response(
                200,
                headers={"Content-Length": str(len(payload))},
                content=payload[:4],
            )

        assert range_header == "bytes=4-"
        interrupted["done"] = True
        return httpx.Response(
            206,
            headers={
                "Content-Range": f"bytes 4-{len(payload) - 1}/{len(payload)}",
                "Content-Length": str(len(payload) - 4),
            },
            content=payload[4:],
        )

    dest = tmp_path / "metadata.csv"
    dest.write_bytes(payload[:4])

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        download_to_file(client, "https://example.com/metadata.csv", dest)

    assert dest.read_bytes() == payload
    assert interrupted["done"] is True


def test_download_to_file_retries_on_incomplete_size(tmp_path: Path, monkeypatch):
    payload = b"12345"
    attempts = {"count": 0}
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(
                200,
                headers={"Content-Length": str(len(payload))},
                content=payload[:2],
            )
        return httpx.Response(
            200,
            headers={"Content-Length": str(len(payload))},
            content=payload,
        )

    monkeypatch.setattr(
        "src.api.scrapers.download.time.sleep",
        lambda seconds: sleeps.append(seconds),
    )

    dest = tmp_path / "metadata.csv"
    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        download_to_file(
            client,
            "https://example.com/metadata.csv",
            dest,
            max_retries=2,
        )

    assert dest.read_bytes() == payload
    assert attempts["count"] == 2
    assert sleeps == [5]


def test_download_to_file_raises_after_exhausted_retries(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("src.api.scrapers.download.time.sleep", lambda _seconds: None)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Length": "10"},
            content=b"short",
        )

    dest = tmp_path / "metadata.csv"
    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        with pytest.raises(Exception, match="Incomplete download"):
            download_to_file(
                client,
                "https://example.com/metadata.csv",
                dest,
                max_retries=1,
            )
