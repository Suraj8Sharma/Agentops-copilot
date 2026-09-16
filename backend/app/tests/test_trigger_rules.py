from datetime import datetime, timedelta

import pytest

from app.notifications.trigger_rules import NotificationEvent, evaluate_trigger


def test_approval_needed_always_fires():
    payload = {
        "tool_name": "gmail_send",
        "task_id": "123e4567-e89b-12d3-a456-426614174000",
        "input_params": {"to": "test@example.com"},
    }
    assert evaluate_trigger(NotificationEvent.APPROVAL_NEEDED, payload) is True


def test_task_completed_always_fires():
    payload = {"task_id": "123e4567-e89b-12d3-a456-426614174000"}
    assert evaluate_trigger(NotificationEvent.TASK_COMPLETED, payload) is True


def test_digest_ready_always_fires():
    payload = {"digest_period": "daily"}
    assert evaluate_trigger(NotificationEvent.DIGEST_READY, payload) is True


def test_oauth_expiring_fires_within_window():
    # 2 days from now (within 3 day window)
    expires_at = (datetime.now() + timedelta(days=2)).isoformat()
    payload = {"provider": "google", "expires_at": expires_at}
    assert evaluate_trigger(NotificationEvent.OAUTH_EXPIRING, payload) is True


def test_oauth_expiring_suppressed_if_future():
    # 5 days from now (outside 3 day window)
    expires_at = (datetime.now() + timedelta(days=5)).isoformat()
    payload = {"provider": "google", "expires_at": expires_at}
    assert evaluate_trigger(NotificationEvent.OAUTH_EXPIRING, payload) is False


def test_oauth_expiring_suppressed_if_past():
    # already expired
    expires_at = (datetime.now() - timedelta(days=1)).isoformat()
    payload = {"provider": "google", "expires_at": expires_at}
    assert evaluate_trigger(NotificationEvent.OAUTH_EXPIRING, payload) is False


def test_invalid_payload_raises_error():
    # Missing input_params
    payload = {"tool_name": "gmail_send", "task_id": "123e4567-e89b-12d3-a456-426614174000"}
    with pytest.raises(ValueError, match="missing required fields: input_params"):
        evaluate_trigger(NotificationEvent.APPROVAL_NEEDED, payload)


def test_digest_ready_invalid_period_raises_error():
    payload = {"digest_period": "monthly"}
    with pytest.raises(ValueError, match="Invalid digest_period: monthly"):
        evaluate_trigger(NotificationEvent.DIGEST_READY, payload)


def test_invalid_event_type_raises_error():
    with pytest.raises(ValueError, match="Invalid event_type"):
        evaluate_trigger("not_an_enum", {})
