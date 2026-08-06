"""SSRF regression tests for provider image URL download (Task 19 Step 2).

Covers T19-SECURITY-001: the SafeImageDownloader must reject loopback,
RFC1918 private, and link-local targets (including redirect hops) before any
request is made. These tests verify existing Task 11 controls.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
import respx

from pelican_town_specials.providers.safe_download import (
    DownloadError,
    SafeImageDownloader,
)

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


def _resolver(*addresses: str) -> Callable[[str], list[str]]:
    def resolve(host: str) -> list[str]:
        del host
        return list(addresses)

    return resolve


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("ip",),
    [
        ("127.0.0.1",),
        ("10.0.0.1",),
        ("192.168.1.1",),
        ("172.16.0.1",),
        ("172.31.255.255",),
        ("169.254.169.254",),
        ("::1",),
    ],
)
async def test_download_rejects_private_loopback_linklocal(ip: str) -> None:
    downloader = SafeImageDownloader(
        http_client=httpx.AsyncClient(), resolve_dns=_resolver(ip)
    )

    with pytest.raises(DownloadError, match="non-public"):
        await downloader.download("https://example.com/img.png")


@pytest.mark.asyncio
async def test_download_rejects_any_private_resolution() -> None:
    downloader = SafeImageDownloader(
        http_client=httpx.AsyncClient(),
        resolve_dns=_resolver("1.2.3.4", "10.0.0.1"),
    )

    with pytest.raises(DownloadError, match="non-public"):
        await downloader.download("https://example.com/img.png")


@pytest.mark.asyncio
@respx.mock
async def test_redirect_to_private_target_is_rejected() -> None:
    def redirect_resolver(host: str) -> list[str]:
        return ["10.0.0.1"] if host == "10.0.0.1" else ["1.2.3.4"]

    respx.get("https://cdn.example.com/a.png").mock(
        return_value=httpx.Response(
            302, headers={"location": "https://10.0.0.1/evil.png"}
        )
    )
    downloader = SafeImageDownloader(
        http_client=httpx.AsyncClient(), resolve_dns=redirect_resolver
    )

    with pytest.raises(DownloadError, match="non-public"):
        await downloader.download("https://cdn.example.com/a.png")


@pytest.mark.asyncio
async def test_download_rejects_userinfo_and_http() -> None:
    downloader = SafeImageDownloader(
        http_client=httpx.AsyncClient(), resolve_dns=_resolver("1.2.3.4")
    )

    with pytest.raises(DownloadError, match="userinfo"):
        await downloader.download("https://user:pass@cdn.example.com/a.png")
    with pytest.raises(DownloadError, match="https"):
        await downloader.download("http://cdn.example.com/a.png")
