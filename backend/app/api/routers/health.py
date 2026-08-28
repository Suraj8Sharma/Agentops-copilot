"""Health-check router.

Exposes ``GET /health`` — a public, unauthenticated liveness probe used by
Render, CI pipelines, and load balancers to confirm the server is running.
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Response schema for the health-check endpoint."""

    status: str


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness check",
    description=(
        "Returns ``{\"status\": \"ok\"}`` when the server is running. "
        "No authentication required."
    ),
)
def health_check() -> HealthResponse:
    """Liveness probe endpoint.

    Returns:
        HealthResponse: ``{"status": "ok"}``
    """
    return HealthResponse(status="ok")
