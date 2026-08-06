"""Read-only diagnostics endpoint.

Returns an in-memory, redacted diagnostic ZIP. The endpoint is intentionally
hidden from the exported OpenAPI contract (``include_in_schema=False``) so the
frontend client is never generated for it (R19-1); it is a backend-only
diagnostic surface.
"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import Response

from pelican_town_specials.observability.diagnostics import DiagnosticsBuilder

router = APIRouter()


@router.get("/diagnostics", include_in_schema=False)
def get_diagnostics(request: Request) -> Response:
    builder = cast(DiagnosticsBuilder, request.app.state.diagnostics_builder)
    request_id = request.headers.get("x-request-id", "")
    bundle = builder.build(request_id=request_id)
    return Response(
        content=bundle,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="pts-diagnostics.zip"'
        },
    )
