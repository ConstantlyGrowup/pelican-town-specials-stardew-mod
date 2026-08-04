"""Shared safe upload normalization: EXIF, modes, re-encode, metadata clearing.

This is the single deterministic decode boundary for original uploads. It is
the converged implementation of the Task 9 upload rules; the HTTP-facing
AssetService delegates here and keeps only declared-MIME validation.
"""

from __future__ import annotations

import io
import warnings
from typing import Literal

from PIL import Image, ImageOps

from pelican_town_specials.domain.assets import MediaType
from pelican_town_specials.domain.errors import AppError

MAX_ASSET_BYTES = 20 * 1024 * 1024
MAX_IMAGE_SIDE = 8192
MAX_IMAGE_PIXELS = 40_000_000

_SOURCE_FORMATS = frozenset({"PNG", "JPEG", "WEBP"})


class NormalizedImage:
    __slots__ = ("data", "height", "media_type", "mode", "source_format", "width")

    def __init__(
        self,
        *,
        data: bytes,
        media_type: MediaType,
        source_format: Literal["PNG", "JPEG", "WEBP"],
        width: int,
        height: int,
        mode: Literal["RGB", "RGBA"],
    ) -> None:
        self.data = data
        self.media_type = media_type
        self.source_format = source_format
        self.width = width
        self.height = height
        self.mode = mode


def normalize_upload(data: bytes) -> NormalizedImage:
    if not data:
        raise _limit_error()
    if len(data) > MAX_ASSET_BYTES:
        raise _limit_error()

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                source_format = source.format
                if source_format not in _SOURCE_FORMATS:
                    raise _invalid_error()
                width, height = source.size
                if (
                    width > MAX_IMAGE_SIDE
                    or height > MAX_IMAGE_SIDE
                    or width * height > MAX_IMAGE_PIXELS
                ):
                    raise _limit_error()
                transposed = ImageOps.exif_transpose(source)
                transposed.load()
    except Image.DecompressionBombError:
        raise _limit_error() from None
    except Image.DecompressionBombWarning:
        raise _limit_error() from None
    except AppError:
        raise
    except (OSError, ValueError, SyntaxError, TypeError, RuntimeError):
        raise _invalid_error() from None

    if source_format == "JPEG":
        normalized_media = MediaType.JPEG
        mode: Literal["RGB", "RGBA"] = "RGB"
        rgb = transposed.convert("RGB")
        rgb.info.clear()
        output = io.BytesIO()
        rgb.save(output, format="JPEG", quality=90, optimize=False)
    else:
        normalized_media = MediaType.PNG
        mode = "RGBA"
        rgba = transposed.convert("RGBA")
        rgba.info.clear()
        output = io.BytesIO()
        rgba.save(output, format="PNG", compress_level=6, optimize=False)

    return NormalizedImage(
        data=output.getvalue(),
        media_type=normalized_media,
        source_format=source_format,  # type: ignore[arg-type]
        width=transposed.width,
        height=transposed.height,
        mode=mode,
    )


def _limit_error() -> AppError:
    return AppError(
        code="PTS_INPUT_IMAGE_LIMIT_EXCEEDED",
        message="图片文件超过大小或像素/边长上限。",
        http_status=422,
        details={},
        retryable=False,
    )


def _invalid_error() -> AppError:
    return AppError(
        code="PTS_INPUT_IMAGE_INVALID",
        message="图片格式不受支持或内容损坏。",
        http_status=422,
        details={},
        retryable=False,
    )
