import pytest

from app.notifications.banner_contract import (
    BANNER_DESTINATIONS,
    BANNER_MAX_CHARS,
    MOCK_BANNER_PAYLOADS,
    NOTIFICATION_TYPES,
    NotificationBannerPayload,
)
from app.notifications.banner_model import build_banner_payload


def test_contract_covers_all_notification_types_and_table_fields():
    assert set(MOCK_BANNER_PAYLOADS) == set(NOTIFICATION_TYPES)
    assert set(NotificationBannerPayload.TABLE_COLUMNS) == {
        "notification_id",
        "type",
        "title",
        "body",
        "banner_text",
        "related_task_id",
        "read",
        "created_at",
    }


def test_examples_define_task_and_non_task_tap_routes():
    assert MOCK_BANNER_PAYLOADS["approval_needed"].destination == "approval"
    assert MOCK_BANNER_PAYLOADS["task_completed"].destination == "task"
    assert MOCK_BANNER_PAYLOADS["digest_ready"].destination == "digest"
    assert MOCK_BANNER_PAYLOADS["oauth_expiring"].destination == "oauth_connections"
    assert all(
        payload.destination == BANNER_DESTINATIONS[payload.type]
        for payload in MOCK_BANNER_PAYLOADS.values()
    )


def test_banner_fallback_uses_body_without_suppressing_notification():
    payload = NotificationBannerPayload(
        notification_id=None,
        type="digest_ready",
        title="Digest ready",
        body="Your summary is ready.",
        banner_text=None,
        related_task_id=None,
        read=False,
        created_at=None,
    )
    assert payload.display_text == "Your summary is ready."


def test_producer_helper_preserves_advisory_copy_and_task_link():
    payload = build_banner_payload(
        {
            "type": "approval_needed",
            "title": "Approval needed",
            "body": "Review this action.",
            "task_id": "task-123",
        },
        "Review this action before it runs.",
    )
    assert payload.to_dict()["banner_text"] == "Review this action before it runs."
    assert payload.related_task_id == "task-123"
    assert payload.destination == "approval"


def test_contract_rejects_copy_over_shared_length_cap():
    with pytest.raises(ValueError, match="80-character cap"):
        NotificationBannerPayload(
            notification_id=None,
            type="task_completed",
            title="Done",
            body="Done",
            banner_text="x" * (BANNER_MAX_CHARS + 1),
            related_task_id=None,
            read=False,
            created_at=None,
        )
