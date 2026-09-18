"""Shared notification-banner payload contract for D19.

This module is the contract between ``banner_model.py`` and the future mobile
banner widget. The payload mirrors the notifications table exactly; routing is
derived from ``type`` and therefore does not add a client-only database field.
``banner_text`` is advisory display copy and must never be read by the planner
or approval gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar

NOTIFICATION_TYPES = (
    "approval_needed",
    "task_completed",
    "digest_ready",
    "oauth_expiring",
)

BANNER_MAX_CHARS = 80

# Tap destinations are a client routing concern, derived from the persisted
# event type. Keeping this mapping here makes the contract explicit without
# adding an orphan column to the notifications table.
BANNER_DESTINATIONS = {
    "approval_needed": "approval",
    "task_completed": "task",
    "digest_ready": "digest",
    "oauth_expiring": "oauth_connections",
}


@dataclass(frozen=True)
class NotificationBannerPayload:
    """The exact row-shaped payload consumed by the future banner widget."""

    notification_id: str | None
    type: str
    title: str
    body: str
    banner_text: str | None
    related_task_id: str | None
    read: bool
    created_at: str | None

    TABLE_COLUMNS: ClassVar[tuple[str, ...]] = (
        "notification_id",
        "type",
        "title",
        "body",
        "banner_text",
        "related_task_id",
        "read",
        "created_at",
    )

    def __post_init__(self) -> None:
        if self.type not in NOTIFICATION_TYPES:
            raise ValueError(f"Unsupported notification type: {self.type}")
        if len(self.banner_text or "") > BANNER_MAX_CHARS:
            raise ValueError("banner_text exceeds the shared 80-character cap")

    @property
    def destination(self) -> str:
        """Return the tap destination derived from the authoritative type."""
        return BANNER_DESTINATIONS[self.type]

    @property
    def display_text(self) -> str:
        """Fallback copy when model generation is unavailable."""
        return self.banner_text or self.body or self.title or "New notification"

    def to_dict(self) -> dict[str, Any]:
        """Serialize using the notifications-table/API field names."""
        return {
            "notification_id": self.notification_id,
            "type": self.type,
            "title": self.title,
            "body": self.body,
            "banner_text": self.banner_text,
            "related_task_id": self.related_task_id,
            "read": self.read,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "NotificationBannerPayload":
        """Parse an API/database-shaped payload without inferring missing copy."""
        created_at = payload.get("created_at")
        if isinstance(created_at, datetime):
            created_at = created_at.isoformat()
        return cls(
            notification_id=payload.get("notification_id", payload.get("id")),
            type=payload.get("type", ""),
            title=payload.get("title", ""),
            body=payload.get("body", ""),
            banner_text=payload.get("banner_text"),
            related_task_id=payload.get("related_task_id"),
            read=bool(payload.get("read", False)),
            created_at=created_at,
        )


MOCK_BANNER_PAYLOADS: dict[str, NotificationBannerPayload] = {
    "approval_needed": NotificationBannerPayload(
        notification_id=None,
        type="approval_needed",
        title="Approval needed",
        body="Your agent wants to send the weekly update.",
        banner_text="Your agent needs approval to send the weekly update.",
        related_task_id="task-approval-demo",
        read=False,
        created_at="2026-09-14T09:00:00Z",
    ),
    "task_completed": NotificationBannerPayload(
        notification_id=None,
        type="task_completed",
        title="Task completed",
        body="Your calendar event was created.",
        banner_text="Done — your calendar event was created.",
        related_task_id="task-completed-demo",
        read=False,
        created_at="2026-09-14T10:00:00Z",
    ),
    "digest_ready": NotificationBannerPayload(
        notification_id=None,
        type="digest_ready",
        title="Digest ready",
        body="Your daily activity summary is ready to review.",
        banner_text="Your daily digest is ready to review.",
        related_task_id=None,
        read=False,
        created_at="2026-09-14T11:00:00Z",
    ),
    "oauth_expiring": NotificationBannerPayload(
        notification_id=None,
        type="oauth_expiring",
        title="Connection renewal",
        body="Your Google connection needs to be renewed soon.",
        banner_text="Your Google connection needs a quick reconnect.",
        related_task_id=None,
        read=False,
        created_at="2026-09-14T12:00:00Z",
    ),
}
