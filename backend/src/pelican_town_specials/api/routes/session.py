from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Request, Response
from pydantic import Field

from pelican_town_specials.api.security import SecurityState, require_session
from pelican_town_specials.domain.common import StrictModel

router = APIRouter()


class LaunchBootstrapRequest(StrictModel):
    launch_token: str = Field(alias="launchToken", min_length=1)


def _security_state(request: Request) -> SecurityState:
    return cast(SecurityState, request.app.state.security)


@router.post("/session/bootstrap", status_code=204)
def bootstrap_session(
    payload: LaunchBootstrapRequest,
    request: Request,
) -> Response:
    security = _security_state(request)
    security.require_allowed_host(request.headers.get("host"))
    credentials = security.bootstrap(payload.launch_token)
    response = Response(status_code=204)
    response.set_cookie(
        key="PTS_SESSION",
        value=credentials.session_id,
        httponly=True,
        samesite="strict",
        path="/",
    )
    response.headers["X-PTS-CSRF"] = credentials.csrf_token
    return response


@router.get("/session/status", status_code=200)
def session_status(request: Request) -> Response:
    """Recover the CSRF token for an existing session after a page reload.

    The CSRF token is intentionally held only in browser memory; a reload
    clears it while the HttpOnly session cookie persists. This endpoint
    re-issues the token to the session holder so mutations do not spuriously
    fail with PTS_AUTH_CSRF_INVALID and force a re-launch.
    """
    credentials = require_session(request)
    response = Response(status_code=200)
    response.headers["X-PTS-CSRF"] = credentials.csrf_token
    return response
