from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    app: Literal["PelicanTownSpecials"] = "PelicanTownSpecials"
    api_version: Literal["v1"] = Field(default="v1", serialization_alias="apiVersion")


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    return HealthResponse()
