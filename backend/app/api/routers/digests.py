"""Digests router — D23.

Endpoints
---------
GET /digests
    List the authenticated user's digest rows, newest-first.
    Supports optional ``period_type`` filter (``daily`` | ``weekly``) and
    ``limit`` / ``offset`` pagination — same convention as ``GET /tasks``.
    Auth: JWT required.

Out of scope (D24+)
-------------------
- POST /digests/{id}/read  — digests are not a read/unread notification.
- Digest generation trigger via HTTP — the APScheduler job handles that.
"""

import logging
from datetime import datetime
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.core.security import CurrentUser, get_current_user
from app.db.supabase_client import supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/digests", tags=["digests"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class DigestOut(BaseModel):
    """Single digest row returned to the client."""

    id: str
    user_id: str
    period_type: str
    summary_text: str
    tasks_included: Optional[Any]  # jsonb — list of task_id strings
    generated_at: datetime


class DigestListOut(BaseModel):
    """Paginated digest list."""

    digests: list[DigestOut]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# GET /digests
# ---------------------------------------------------------------------------

_VALID_PERIOD_TYPES = frozenset({"daily", "weekly"})


@router.get(
    "",
    summary="List digests",
    description=(
        "Return the authenticated user's digest rows, newest-first. "
        "Supports optional ``period_type`` filter (``daily`` | ``weekly``) "
        "and ``limit``/``offset`` pagination."
    ),
    response_model=DigestListOut,
)
def list_digests(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    limit: int = Query(20, ge=1, le=100, description="Max rows to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    period_type: Optional[Literal["daily", "weekly"]] = Query(
        None, description="Filter by digest period type: daily or weekly"
    ),
) -> Any:
    """List digest rows for the current user with optional filtering and pagination.

    RLS handles user-scoping — only the calling user's rows are ever returned.
    The route does not manually filter by ``user_id``; the Supabase client's
    auth context (service-role key) combined with RLS enforces isolation.
    """
    try:
        query = (
            supabase.table("digests")
            .select("*", count="exact")
            .eq("user_id", current_user.id)
            .order("generated_at", desc=True)
            .range(offset, offset + limit - 1)
        )
        if period_type is not None:
            query = query.eq("period_type", period_type)

        result = query.execute()
    except Exception as exc:
        logger.error("DB error listing digests for user_id=%s: %s", current_user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve digests.",
        ) from exc

    total = result.count if result.count is not None else len(result.data)
    return DigestListOut(
        digests=result.data,
        total=total,
        limit=limit,
        offset=offset,
    )
