"""Original-image upload and registered-asset read endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import StreamingResponse

from pelican_town_specials.api.dependencies import asset_service
from pelican_town_specials.application.assets import MAX_ASSET_BYTES, AssetView

router = APIRouter()


@router.post(
    "/assets/images",
    status_code=201,
    response_model=AssetView,
    response_model_by_alias=True,
)
def upload_image(
    request: Request,
    file: Annotated[UploadFile, File(description="Original dish photo")],
) -> AssetView:
    data = file.file.read(MAX_ASSET_BYTES + 1)
    return asset_service(request).upload_image(
        content_type=file.content_type or "",
        data=data,
    )


@router.get("/assets/{asset_id}")
def get_image(asset_id: UUID, request: Request) -> StreamingResponse:
    payload = asset_service(request).get_image(asset_id)
    return StreamingResponse(
        payload.iter_bytes(),
        media_type=payload.media_type.value,
    )
