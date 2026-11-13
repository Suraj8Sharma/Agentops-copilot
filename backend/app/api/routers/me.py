"""Protected /me router — returns the authenticated user's own profile.

This is the first protected route in the API and the canonical smoke-test
for the JWT middleware: a valid token returns 200 + profile data;
any missing/invalid/expired token returns 401 before this handler runs.
"""

import logging
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel

from app.core.security import CurrentUser, get_current_user
from app.db.supabase_client import supabase_admin
from app.memory.preferences import delete_preference, get_all_preferences, upsert_preference

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me", tags=["me"])


class PreferenceUpdateRequest(BaseModel):
    """Request body used when a user edits a stored preference."""

    value: Any
    confidence: float = 0.8
    source: Literal["extracted_from_memory", "user_stated_in_settings"] = "user_stated_in_settings"


class DeleteAccountRequest(BaseModel):
    """Confirmation payload for account deletion."""

    confirm: bool = False


@router.get(
    "",
    summary="Get current user profile",
    description=(
        "Returns the authenticated user's id and email from the validated "
        "JWT. Requires a valid ``Authorization: Bearer <token>`` header."
    ),
)
def get_me(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Any:
    """Return the current user's basic profile from the JWT payload."""
    logger.info("Profile requested by user_id=%s", current_user.id)
    return {
        "user_id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
    }


@router.get(
    "/preferences",
    summary="Get memory preferences",
    description="Return the authenticated user's stored preferences as a key-value map.",
)
async def get_preferences(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    """Return all stored preference key/value pairs for this user."""
    preferences = await get_all_preferences(current_user.id)
    logger.info("Preferences fetched for user_id=%s count=%s", current_user.id, len(preferences))
    return preferences


@router.put(
    "/preferences/{preference_key}",
    summary="Upsert a memory preference",
    description="Create or update a stored preference for the authenticated user.",
)
async def upsert_preference_for_user(
    preference_key: str,
    payload: PreferenceUpdateRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    """Create or update a user preference."""
    await upsert_preference(
        user_id=current_user.id,
        preference_key=preference_key,
        preference_value=payload.value,
        confidence=payload.confidence,
        source=payload.source,
    )
    return {
        "preference_key": preference_key,
        "value": payload.value,
        "confidence": payload.confidence,
        "source": payload.source,
    }


@router.delete(
    "/preferences/{preference_key}",
    summary="Delete a memory preference",
    description="Delete a single stored preference for the authenticated user.",
)
async def delete_preference_for_user(
    preference_key: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, str]:
    """Delete a user preference by key."""
    await delete_preference(current_user.id, preference_key)
    return {"preference_key": preference_key, "status": "deleted"}


@router.delete(
    "/account",
    summary="Delete the current user account",
    description="Delete the current user account and all owned rows after explicit confirmation.",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_account(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    confirm: bool = Query(False, description="Must be true to permanently delete the account"),
) -> Response:
    """Delete the current account after confirmation."""
    if not confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account deletion requires confirm=true.",
        )

    try:
        supabase_admin.auth.admin.delete_user(current_user.id)
    except Exception as exc:  # pragma: no cover - depends on external provider
        logger.exception("Account deletion failed for user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete account.",
        ) from exc

    logger.warning("Account deleted for user_id=%s", current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
