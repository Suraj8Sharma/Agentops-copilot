"""Stub /tasks router — protected, returns placeholder task list.

A real implementation arrives in a later day once the agent pipeline is
wired up.  Today this stub exists solely so that:
  1. The JWT middleware can be exercised end-to-end via ``GET /tasks``.
  2. The acceptance check in the D5 spec passes (401 without token, 200
     with a valid token).
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.core.security import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get(
    "",
    summary="List tasks (stub)",
    description=(
        "Returns a placeholder empty task list for the authenticated user. "
        "Requires a valid ``Authorization: Bearer <token>`` header."
    ),
)
def list_tasks(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Any:
    """Stub task list — returns empty list for the current user.

    Returns:
        dict with ``user_id`` and empty ``tasks`` list.
    """
    logger.info("Tasks requested by user_id=%s", current_user.id)
    return {"user_id": current_user.id, "tasks": []}