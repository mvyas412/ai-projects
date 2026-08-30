from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from backend.app.core.config import Settings
from backend.app.schemas.health import LivenessResponse, ReadinessResponse
from backend.app.services.readiness import ReadinessService, get_readiness_service

router = APIRouter(prefix="/health", tags=["health"])


@router.get(
    "/live",
    response_model=LivenessResponse,
    summary="Process liveness",
)
def liveness(request: Request) -> LivenessResponse:
    settings: Settings = request.app.state.settings
    return LivenessResponse(service=settings.app_name, version=settings.app_version)


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
    summary="Dependency readiness",
)
def readiness(
    service: Annotated[ReadinessService, Depends(get_readiness_service)],
) -> ReadinessResponse | JSONResponse:
    report = service.check()
    if report.status == "ready":
        return report

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=report.model_dump(mode="json"),
    )
