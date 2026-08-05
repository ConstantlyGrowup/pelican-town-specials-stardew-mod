"""Export endpoints: validate, synchronous compile, download and open folder."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import StreamingResponse

from pelican_town_specials.api.dependencies import export_service
from pelican_town_specials.domain.export import ExportRecordView, ExportSpec
from pelican_town_specials.domain.validation import ValidationReport

router = APIRouter()


@router.post(
    "/exports/validate",
    response_model=ValidationReport,
    response_model_by_alias=True,
)
def validate_export_request(request: Request, spec: ExportSpec) -> ValidationReport:
    return export_service(request).validate(spec)


@router.post(
    "/exports",
    status_code=201,
    response_model=ExportRecordView,
    response_model_by_alias=True,
)
def create_export(
    request: Request,
    spec: ExportSpec,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key"),
    ] = None,
) -> ExportRecordView:
    record = export_service(request).create_export(
        spec,
        idempotency_key=idempotency_key or "",
    )
    return ExportRecordView.from_record(record)


@router.get(
    "/exports/{export_id}",
    response_model=ExportRecordView,
    response_model_by_alias=True,
)
def get_export(export_id: UUID, request: Request) -> ExportRecordView:
    return export_service(request).get_export(export_id)


@router.get("/exports/{export_id}/download")
def download_export(export_id: UUID, request: Request) -> StreamingResponse:
    service = export_service(request)
    record = service.get_export(export_id)
    handle = service.download_export(export_id)
    filename = f"[CP] Pelican Town Specials - {record.spec.pack_slug}.zip"
    return StreamingResponse(
        iter(lambda: handle.read(64 * 1024), b""),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/exports/{export_id}/open-folder", status_code=204)
def open_export_folder(export_id: UUID, request: Request) -> Response:
    export_service(request).open_export_folder(export_id)
    return Response(status_code=204)
