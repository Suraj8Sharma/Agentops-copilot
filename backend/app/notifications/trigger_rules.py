from enum import Enum
from datetime import datetime, timedelta
from typing import Dict, Any, Union

class NotificationEvent(str, Enum):
    APPROVAL_NEEDED = "approval_needed"
    TASK_COMPLETED = "task_completed"
    DIGEST_READY = "digest_ready"
    OAUTH_EXPIRING = "oauth_expiring"

def evaluate_trigger(event_type: NotificationEvent, payload: Dict[str, Any]) -> bool:
    """
    Evaluates whether an event should fire a notification based on its type and payload.
    Validates that the required payload fields for the given event type are present.
    Returns True if the notification should proceed, False otherwise.
    """
    if not isinstance(event_type, NotificationEvent):
        raise ValueError(f"Invalid event_type: {event_type}")

    if event_type == NotificationEvent.APPROVAL_NEEDED:
        required_fields = ["tool_name", "task_id", "input_params"]
        _validate_payload(event_type, payload, required_fields)
        return True

    elif event_type == NotificationEvent.TASK_COMPLETED:
        required_fields = ["task_id"]
        _validate_payload(event_type, payload, required_fields)
        return True

    elif event_type == NotificationEvent.DIGEST_READY:
        required_fields = ["digest_period"]
        _validate_payload(event_type, payload, required_fields)
        if payload["digest_period"] not in ["daily", "weekly"]:
            raise ValueError(f"Invalid digest_period: {payload['digest_period']}")
        return True

    elif event_type == NotificationEvent.OAUTH_EXPIRING:
        required_fields = ["provider", "expires_at"]
        _validate_payload(event_type, payload, required_fields)
        
        # Parse expires_at (expecting ISO-8601 string)
        try:
            # Handle standard ISO format from Python or DB
            expires_at_str = payload["expires_at"]
            if expires_at_str.endswith('Z'):
                expires_at_str = expires_at_str[:-1] + '+00:00'
            expires_at = datetime.fromisoformat(expires_at_str)
        except ValueError as e:
            raise ValueError(f"Invalid expires_at format: {payload['expires_at']}. Expected ISO-8601.") from e
        
        # Make comparison timezone-aware if expires_at is timezone-aware
        now = datetime.now(expires_at.tzinfo) if expires_at.tzinfo else datetime.now()
        
        # Fire if expires_at is within 3 days
        time_until_expiry = expires_at - now
        if timedelta(days=0) <= time_until_expiry <= timedelta(days=3):
            return True
        return False

    return False

def _validate_payload(event_type: NotificationEvent, payload: Dict[str, Any], required_fields: list[str]) -> None:
    missing_fields = [field for field in required_fields if field not in payload]
    if missing_fields:
        raise ValueError(f"Payload for {event_type.value} missing required fields: {', '.join(missing_fields)}")
