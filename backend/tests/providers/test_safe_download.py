"""SSRF-safe temporary image URL download tests."""

from __future__ import annotations

import httpx
import pytest
import respx

from pelican_town_specials.providers.safe_download import (
    DownloadError,
    SafeImageDownloader,
)

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


def _public_resolver(host: str) -> list[str]:
    del host
    return ["1.2.3.4"]


def _private_resolver(host: str) -> list[str]:
    del host
    return ["127.0.0.1"]


def _empty_resolver(host: str) -> list[str]:
    del host
    return []


@pytest.mark.asyncio
async def test_download_rejects_non_https() -> None:
    downloader = SafeImageDownloader(
        http_client=httpx.AsyncClient(), resolve_dns=_public_resolver
    )
    with pytest.raises(DownloadError, match="https"):
        await downloader.download("http://example.com/img.png")


@pytest.mark.asyncio
async def test_download_rejects_private_ip_before_request() -> None:
    downloader = SafeImageDownloader(
        http_client=httpx.AsyncClient(), resolve_dns=_private_resolver
    )
    with pytest.raises(DownloadError, match="non-public"):
        await downloader.download("https://example.com/img.png")


@pytest.mark.asyncio
async def test_download_fails_closed_on_empty_dns() -> None:
    downloader = SafeImageDownloader(
        http_client=httpx.AsyncClient(), resolve_dns=_empty_resolver
    )
    with pytest.raises(DownloadError, match="does not resolve"):
        await downloader.download("https://example.com/img.png")


@pytest.mark.asyncio
@respx.mock
async def test_download_accepts_public_https_png() -> None:
    route = respx.get("https://cdn.example.com/img.png").mock(
        return_value=httpx.Response(
            200, content=_PNG, headers={"content-type": "image/png"}
        )
    )
    downloader = SafeImageDownloader(
        http_client=httpx.AsyncClient(), resolve_dns=_public_resolver
    )

    result = await downloader.download("https://cdn.example.com/img.png")

    assert route.called
    assert result.data == _PNG
    assert result.media_type.value == "image/png"


@pytest.mark.asyncio
@respx.mock
async def test_download_enforces_size_limit() -> None:
    respx.get("https://cdn.example.com/big.png").mock(
        return_value=httpx.Response(
            200, content=_PNG * 4, headers={"content-type": "image/png"}
        )
    )
    downloader = SafeImageDownloader(
        http_client=httpx.AsyncClient(),
        resolve_dns=_public_resolver,
        max_bytes=10,
    )

    with pytest.raises(DownloadError, match="size"):
        await downloader.download("https://cdn.example.com/big.png")
