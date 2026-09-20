"""Activity log router — GET /me/activity.

Returns execution_logs rows that belong to the authenticated user,
joined via task ownership (tasks.user_id = current_user.id).

The service-role client is used for the query so RLS is bypassed on the
server side — ownership is enforced explicitly in the WHERE clause, which
is equivalent to the RLS policy defined in the migration.

Endpoint
--------
GET /me/activity
    Returns up to `limit` execution_logs rows, newest-first.
    Supports optional `event_type` filter.
    Auth: JWT required.
"""

import logging
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.core.security import CurrentUser, get_current_user
from app.db.supabase_client import supabase_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me", tags=["activity"])

# Valid event_type values — matches the DB check constraint.
_VALID_EVENT_TYPES = frozenset(
    {
        "plan_created",
        "risk_tagged",
        "approval_requested",
        "approval_decided",
        "tool_called",
        "tool_result",
        "step_started",
        "step_completed",
        "step_failed",
        "step_awaiting_approval",
        "error",
    }
)


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------


class ActivityLogItem(BaseModel):
    """A single execution_logs row returned to the client."""

    id: int
    task_id: str
    step_id: Optional[str] = None
    agent_name: str
    event_type: str
    payload: dict
    latency_ms: Optional[int] = None
    model_used: Optional[str] = None
    tokens_used: Optional[int] = None
    cost_estimate: Optional[float] = None
    created_at: str


class ActivityLogResponse(BaseModel):
    """Paginated activity log response."""

    items: list[ActivityLogItem]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# GET /me/activity
# ---------------------------------------------------------------------------


@router.get(
    "/activity",
    response_model=ActivityLogResponse,
    status_code=status.HTTP_200_OK,
    summary="Get activity log",
    description=(
        "Return execution_logs rows for tasks owned by the authenticated user, "
        "newest-first. Supports optional ``event_type`` filter and "
        "``limit``/``offset`` pagination."
    ),
)
def get_activity(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    limit: int = Query(50, ge=1, le=200, description="Max rows to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    event_type: Optional[str] = Query(
        None,
        description=(
            "Filter by event_type "
            "(plan_created, tool_called, approval_decided, etc.)"
        ),
    ),
) -> Any:
    """Return execution_logs scoped to the current user's tasks."""

    if event_type is not None and event_type not in _VALID_EVENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid event_type {event_type!r}. "
                f"Valid values: {sorted(_VALID_EVENT_TYPES)}"
            ),
        )

    try:
        # Fetch all task IDs that belong to this user.
        task_result = (
            supabase_admin.table("tasks")
            .select("id")
            .eq("user_id", current_user.id)
            .execute()
        )
        user_task_ids = [row["id"] for row in (task_result.data or [])]

        if not user_task_ids:
            return ActivityLogResponse(items=[], total=0, limit=limit, offset=offset)

        # Query execution_logs for those task IDs.
        query = (
            supabase_admin.table("execution_logs")
            .select("*", count="exact")
            .in_("task_id", user_task_ids)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
        )
        if event_type is not None:
            query = query.eq("event_type", event_type)

        result = query.execute()

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "DB error fetching activity log for user_id=%s: %s",
            current_user.id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve activity log.",
        ) from exc

    total = result.count if result.count is not None else len(result.data or [])
    items = [ActivityLogItem(**row) for row in (result.data or [])]

    logger.info(
        "Activity log fetched: user_id=%s items=%d total=%d",
        current_user.id,
        len(items),
        total,
    )
    return ActivityLogResponse(items=items, total=total, limit=limit, offset=offset)
