"""Notifications router — D24.

Endpoints
---------
GET /notifications
    List the authenticated user's in-app notifications, newest-first.
    Auth: JWT required.
    
POST /notifications/{id}/read
    Mark a single notification as read.
    Auth: JWT required.
    
POST /device-tokens
    Register an FCM device token for this user.
    Auth: JWT required.
    
DELETE /device-tokens/{token_id}
    Remove a device token (logout / uninstall).
    Auth: JWT required.
"""

import logging
from datetime import datetime
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel

from app.core.security import CurrentUser, get_current_user
from app.db.supabase_client import supabase
from app.notifications.banner_model import generate_banner
from app.notifications.fcm import send_push_notification

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notifications"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class NotificationOut(BaseModel):
    id: str
    user_id: str
    type: str
    title: str
    body: str
    banner_text: Optional[str]
    read: bool
    related_task_id: Optional[str]
    created_at: datetime


class NotificationListOut(BaseModel):
    notifications: list[NotificationOut]
    total: int
    limit: int
    offset: int


class DeviceTokenIn(BaseModel):
    fcm_token: str
    device_type: Optional[Literal["ios", "android"]] = None


class DeviceTokenOut(BaseModel):
    id: str
    fcm_token: str
    device_type: Optional[str]
    created_at: datetime


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/notifications",
    summary="List notifications",
    description="Return the authenticated user's in-app notifications, newest-first.",
    response_model=NotificationListOut,
)
def list_notifications(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    limit: int = Query(20, ge=1, le=100, description="Max rows to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    unread_only: bool = Query(False, description="Filter unread notifications only"),
) -> Any:
    try:
        query = (
            supabase.table("notifications")
            .select("*", count="exact")
            .eq("user_id", current_user.id)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
        )
        if unread_only:
            query = query.eq("read", False)

        result = query.execute()
    except Exception as exc:
        logger.error("DB error listing notifications for user_id=%s: %s", current_user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve notifications.",
        ) from exc

    total = result.count if result.count is not None else len(result.data)
    return NotificationListOut(
        notifications=result.data,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/notifications/{id}/read",
    summary="Mark notification read",
    description="Mark a single notification as read.",
)
def mark_notification_read(
    id: str = Path(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    try:
        result = (
            supabase.table("notifications")
            .update({"read": True})
            .eq("id", id)
            .eq("user_id", current_user.id)
            .execute()
        )
    except Exception as exc:
        logger.error("DB error marking notification read for user_id=%s: %s", current_user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark notification as read.",
        ) from exc

    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
        
    return {"id": id, "read": True}


@router.post(
    "/device-tokens",
    summary="Register device token",
    description="Register an FCM device token for this user.",
    response_model=DeviceTokenOut,
)
def register_device_token(
    payload: DeviceTokenIn,
    current_user: CurrentUser = Depends(get_current_user),
) -> Any:
    try:
        # UPSERT to handle re-registration
        data = {
            "user_id": current_user.id,
            "fcm_token": payload.fcm_token,
            "device_type": payload.device_type,
            "last_active": "now()"
        }
        result = (
            supabase.table("sessions_device_tokens")
            .upsert(data, on_conflict="user_id,fcm_token")
            .execute()
        )
    except Exception as exc:
        logger.error("DB error registering device token for user_id=%s: %s", current_user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register device token.",
        ) from exc

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register device token.",
        )

    return result.data[0]


@router.delete(
    "/device-tokens/{token_id}",
    summary="Remove device token",
    description="Remove a device token (logout / uninstall).",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_device_token(
    token_id: str = Path(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    try:
        result = (
            supabase.table("sessions_device_tokens")
            .delete()
            .eq("id", token_id)
            .eq("user_id", current_user.id)
            .execute()
        )
    except Exception as exc:
        logger.error("DB error deleting device token for user_id=%s: %s", current_user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete device token.",
        ) from exc

    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device token not found")


# ---------------------------------------------------------------------------
# Internal Helper
# ---------------------------------------------------------------------------

async def create_notification(
    user_id: str,
    event_type: str,
    title: str,
    body: str,
    related_task_id: str | None = None,
) -> str:
    """
    Inserts a row into the notifications table, generates banner_text via
    banner_model.generate_banner_text(), and fires send_push_notification().
    Returns the new notification id (uuid).
    Best-effort on FCM send — a push failure never blocks the notification insert.
    """
    banner_text = None
    try:
        # We need to construct a payload dict for generate_banner_text based on the spec
        payload_dict = {
            "type": event_type,
            "title": title,
            "body": body,
        }
        if related_task_id:
            payload_dict["task_id"] = related_task_id
            
        banner_text = await generate_banner(payload_dict)
    except Exception as e:
        logger.warning(
            f"Failed to generate banner text for notification (event_type={event_type}): {e}"
        )

    # 2. Insert row into notifications table
    row_data = {
        "user_id": user_id,
        "type": event_type,
        "title": title,
        "body": body,
        "banner_text": banner_text,
    }
    if related_task_id:
        row_data["related_task_id"] = related_task_id
        
    result = supabase.table("notifications").insert(row_data).execute()
    notification_id = result.data[0]["id"]
    
    # 3. After successful insert, call send_push_notification
    # Use best-effort (try-except) so a push error doesn't raise out of create_notification
    try:
        send_push_notification(user_id=user_id, title=title, body=body)
    except Exception as e:
        logger.warning(f"Push notification failed internally: {e}")
        
    return notification_id
