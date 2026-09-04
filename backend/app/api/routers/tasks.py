"""Tasks router — D11.

Endpoints
---------
POST /tasks
    Submit a new text or voice task.
    Writes a row to ``tasks`` with status ``submitted`` and returns it.
    The LangGraph planner (D13) will pick the task up and advance its status.
    Auth: JWT required.

GET /tasks
    List the authenticated user''s tasks, newest-first.
    Supports optional ``status`` filter and ``limit`` / ``offset`` pagination.
    Auth: JWT required.

GET /tasks/{id}
    Return a single task by ID.
    Returns 404 if the task does not exist or belongs to another user
    (RLS surfaces both cases as "not found" — never leaks task existence).
    Auth: JWT required.

Out of scope (D13+)
-------------------
- LangGraph planner invocation.
- GET /tasks/{id}/plan  (requires task_plans data).
- Approval flow.
"""

import logging
import uuid as _uuid
from datetime import datetime
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator

from app.core.security import CurrentUser, get_current_user
from app.db.supabase_client import supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class TaskCreate(BaseModel):
    """Request body for POST /tasks."""

    input_type: Literal["text", "voice"]
    raw_input: Optional[str] = Field(
        None,
        max_length=5000,
        description="Required when input_type is ''text''.",
    )
    transcription_text: Optional[str] = Field(
        None,
        max_length=5000,
        description="Required when input_type is ''voice''. "
        "Populated by the Flutter STT client before the API call.",
    )

    @model_validator(mode="after")
    def check_input_present(self) -> "TaskCreate":
        """Ensure the correct input field is provided for the given type."""
        if self.input_type == "text" and not self.raw_input:
            raise ValueError("raw_input is required when input_type is ''text''")
        if self.input_type == "voice" and not self.transcription_text:
            raise ValueError("transcription_text is required when input_type is ''voice''")
        return self


class TaskOut(BaseModel):
    """Single task row returned to the client."""

    id: str
    user_id: str
    input_type: str
    raw_input: Optional[str]
    transcription_text: Optional[str]
    status: str
    created_at: datetime
    completed_at: Optional[datetime]


class TaskListOut(BaseModel):
    """Paginated task list."""

    tasks: list[TaskOut]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# POST /tasks
# ---------------------------------------------------------------------------


@router.post(
    "",
    summary="Submit a new task",
    description=(
        "Accept a text or voice task from the authenticated user, persist it "
        "with status ``submitted``, and return the created task object. "
        "The LangGraph planner will pick it up asynchronously (D13)."
    ),
    status_code=status.HTTP_201_CREATED,
    response_model=TaskOut,
)
def create_task(
    body: TaskCreate,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Any:
    """Write a new task row and return it.

    The Supabase singleton uses the service-role key, so it bypasses RLS for
    the INSERT.  ``user_id`` is always taken from the verified JWT — the
    request body never supplies it, preventing cross-user injection.
    """
    payload: dict[str, Any] = {
        "user_id": current_user.id,
        "input_type": body.input_type,
        "raw_input": body.raw_input,
        "transcription_text": body.transcription_text,
        "status": "submitted",
    }

    try:
        result = supabase.table("tasks").insert(payload).execute()
    except Exception as exc:
        logger.error("DB error creating task for user_id=%s: %s", current_user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create task.",
        ) from exc

    if not result.data:
        logger.error("Task insert returned no data for user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Task creation failed — no data returned.",
        )

    logger.info(
        "Task created: task_id=%s user_id=%s input_type=%s",
        result.data[0].get("id"),
        current_user.id,
        body.input_type,
    )
    return result.data[0]


# ---------------------------------------------------------------------------
# GET /tasks
# ---------------------------------------------------------------------------

_VALID_STATUSES = frozenset(
    {
        "submitted",
        "planning",
        "awaiting_approval",
        "executing",
        "completed",
        "failed",
        "cancelled",
    }
)


@router.get(
    "",
    summary="List tasks",
    description=(
        "Return the authenticated user''s tasks, newest-first. "
        "Supports optional ``status`` filter and ``limit``/``offset`` pagination."
    ),
    response_model=TaskListOut,
)
def list_tasks(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    limit: int = Query(20, ge=1, le=100, description="Max rows to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    status: Optional[str] = Query(
        None, description="Filter by task status (e.g. submitted, completed)"
    ),
) -> Any:
    """List tasks for the current user with optional filtering and pagination."""
    if status is not None and status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status filter {status!r}. Valid values: {sorted(_VALID_STATUSES)}",
        )

    try:
        query = (
            supabase.table("tasks")
            .select("*", count="exact")
            .eq("user_id", current_user.id)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
        )
        if status is not None:
            query = query.eq("status", status)

        result = query.execute()
    except Exception as exc:
        logger.error("DB error listing tasks for user_id=%s: %s", current_user.id, exc)
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve tasks.",
        ) from exc

    total = result.count if result.count is not None else len(result.data)
    return TaskListOut(
        tasks=result.data,
        total=total,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# GET /tasks/{id}
# ---------------------------------------------------------------------------


@router.get(
    "/{task_id}",
    summary="Get task detail",
    description=(
        "Return a single task by ID. "
        "Returns 404 if the task does not exist or belongs to another user."
    ),
    response_model=TaskOut,
)
def get_task(
    task_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Any:
    """Fetch a single task row by ID, scoped to the current user."""
    # Validate that the path param looks like a UUID before hitting the DB.
    try:
        _uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found.",
        )

    try:
        result = (
            supabase.table("tasks")
            .select("*")
            .eq("id", task_id)
            .eq("user_id", current_user.id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.error(
            "DB error fetching task_id=%s for user_id=%s: %s",
            task_id,
            current_user.id,
            exc,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve task.",
        ) from exc

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found.",
        )

    return result.data[0]
