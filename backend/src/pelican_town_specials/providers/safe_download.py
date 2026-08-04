"""SSRF-safe download of temporary provider image URLs."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urljoin, urlparse

import httpx

from .contracts import GeneratedImage, ImageMediaType

MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
MAX_REDIRECTS = 3
_REDIRECT_STATUS = frozenset({301, 302, 303, 307, 308})

DNSResolver = Callable[[str], list[str]]


class DownloadError(Exception):
    pass


def _is_globally_routable(ip_text: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_text)
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def _resolve_default(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return []
    addresses: set[str] = set()
    for info in infos:
        sockaddr = info[4]
        if isinstance(sockaddr, tuple) and sockaddr and isinstance(sockaddr[0], str):
            addresses.add(sockaddr[0])
    return sorted(addresses)


def detect_media_type(data: bytes) -> ImageMediaType | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ImageMediaType.PNG
    if data.startswith(b"\xff\xd8\xff"):
        return ImageMediaType.JPEG
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ImageMediaType.WEBP
    return None


class SafeImageDownloader:
    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        resolve_dns: DNSResolver = _resolve_default,
        max_bytes: int = MAX_DOWNLOAD_BYTES,
        max_redirects: int = MAX_REDIRECTS,
    ) -> None:
        self._client = http_client
        self._resolve_dns = resolve_dns
        self._max_bytes = max_bytes
        self._max_redirects = max_redirects

    async def download(self, url: str) -> GeneratedImage:
        current = url
        redirects = 0
        while True:
            self._validate_public_url(current)
            response = self._client.stream("GET", current, follow_redirects=False)
            async with response as resp:
                if resp.status_code in _REDIRECT_STATUS:
                    redirects += 1
                    if redirects > self._max_redirects:
                        raise DownloadError("too many redirects")
                    location = resp.headers.get("location")
                    if not location:
                        raise DownloadError("redirect missing location")
                    current = urljoin(current, location)
                    continue
                if resp.status_code != 200:
                    raise DownloadError("image download failed")
                content_length = resp.headers.get("content-length")
                if content_length:
                    try:
                        if int(content_length) > self._max_bytes:
                            raise DownloadError("image exceeds size limit")
                    except ValueError:
                        raise DownloadError("invalid content-length") from None
                data = bytearray()
                async for chunk in resp.aiter_bytes():
                    if len(data) + len(chunk) > self._max_bytes:
                        raise DownloadError("image exceeds size limit")
                    data.extend(chunk)

            media_type = detect_media_type(bytes(data))
            if media_type is None:
                raise DownloadError("image has unknown media type")
            declared = resp.headers.get("content-type", "").split(";")[0].strip().lower()
            if declared and declared != media_type.value:
                raise DownloadError("image content type does not match content")
            return GeneratedImage(data=bytes(data), media_type=media_type)

    def _validate_public_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise DownloadError("only https URLs are allowed")
        if parsed.username is not None or parsed.password is not None:
            raise DownloadError("URL userinfo is not allowed")
        host = parsed.hostname
        if not host:
            raise DownloadError("URL has no host")
        addresses = self._resolve_dns(host)
        if not addresses:
            raise DownloadError("URL does not resolve to a public address")
        for ip_text in addresses:
            if not _is_globally_routable(ip_text):
                raise DownloadError("URL resolves to a non-public address")
