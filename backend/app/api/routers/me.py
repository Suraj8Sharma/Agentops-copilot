"""Protected /me router — returns the authenticated user s own profile.

This is the first protected route in the API and the canonical smoke-test
for the JWT middleware:  a valid token returns 200 + profile data;
any missing/invalid/expired token returns 401 before this handler runs.
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.core.security import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me", tags=["me"])


@router.get(
    "",
    summary="Get current user profile",
    description=(
        "Returns the authenticated user s id and email from the validated "
        "JWT.  Requires a valid ``Authorization: Bearer <token>`` header."
    ),
)
def get_me(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Any:
    """Return the current user s basic profile from the JWT payload.

    Returns:
        dict with ``user_id``, ``email``, and ``role``.
    """
    logger.info("Profile requested by user_id=%s", current_user.id)
    return {
        "user_id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
    }
