from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from firebase_admin import messaging

from app.api.routers.notifications import create_notification
from app.core.security import get_current_user
from app.main import app
from app.notifications.fcm import send_push_notification

# ---------------------------------------------------------------------------
# Migration & DB Schema Constraints Tests
# (Mocking Supabase calls isn't real DB test, but spec says "run via pytest against
# the test Supabase project". Since we are providing the tests, we assume
# these tests are run in the context where `supabase` client points to a test db.
# For simplicity, we'll write them as integration tests if DB is available,
# or mock them if we just need to verify the interface in unit tests.
# The spec asks to use unittest.mock.patch on supabase.table(...) and firebase_admin.messaging.send
# so we will use mocks for all DB calls as requested in Section 12.)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_supabase():
    with patch("app.api.routers.notifications.supabase") as mock_supa, \
         patch("app.notifications.fcm.supabase") as mock_fcm_supa:
        yield {"router": mock_supa, "fcm": mock_fcm_supa}

@pytest.fixture
def mock_messaging_send():
    with patch("app.notifications.fcm.messaging.send") as mock_send:
        yield mock_send

@pytest.fixture
def mock_generate_banner():
    with patch("app.api.routers.notifications.generate_banner") as mock_gen:
        mock_gen.return_value = "Mocked banner text"
        yield mock_gen

# --- 12.2 FCM helper unit tests ---

def test_send_push_no_tokens_returns_early(mock_supabase, mock_messaging_send):
    mock_supabase["fcm"].table().select().eq().execute.return_value.data = []
    
    send_push_notification("user_123", "Title", "Body")
    
    mock_messaging_send.assert_not_called()

def test_send_push_success_updates_last_active(mock_supabase, mock_messaging_send):
    mock_supabase["fcm"].table().select().eq().execute.return_value.data = [
        {"id": "token_1", "fcm_token": "abc"}
    ]
    
    send_push_notification("user_123", "Title", "Body")
    
    mock_messaging_send.assert_called_once()
    mock_supabase["fcm"].table().update.assert_called_with({"last_active": "now()"})
    mock_supabase["fcm"].table().update().eq.assert_called_with("id", "token_1")

def test_send_push_stale_token_deleted(mock_supabase, mock_messaging_send):
    mock_supabase["fcm"].table().select().eq().execute.return_value.data = [
        {"id": "token_1", "fcm_token": "abc"}
    ]
    mock_messaging_send.side_effect = messaging.UnregisteredError("Token unregistered")
    
    send_push_notification("user_123", "Title", "Body")
    
    mock_supabase["fcm"].table().delete.assert_called()
    mock_supabase["fcm"].table().delete().eq.assert_called_with("id", "token_1")

def test_send_push_network_error_does_not_raise(mock_supabase, mock_messaging_send):
    mock_supabase["fcm"].table().select().eq().execute.return_value.data = [
        {"id": "token_1", "fcm_token": "abc"}
    ]
    # Generic Exception
    mock_messaging_send.side_effect = Exception("Network timeout")
    
    # Should not raise exception
    send_push_notification("user_123", "Title", "Body")
    
    mock_supabase["fcm"].table().update.assert_not_called()
    mock_supabase["fcm"].table().delete.assert_not_called()

def test_send_push_does_not_log_raw_token(mock_supabase, mock_messaging_send, caplog):
    mock_supabase["fcm"].table().select().eq().execute.return_value.data = [
        {"id": "token_1", "fcm_token": "SECRET_TOKEN_VALUE"}
    ]
    mock_messaging_send.side_effect = messaging.UnregisteredError("error")
    
    send_push_notification("user_123", "Title", "Body")
    
    assert "SECRET_TOKEN_VALUE" not in caplog.text


# We will use fastapi.testclient.TestClient to test endpoints
# We need to bypass auth for simple unit testing
class MockUser:
    id = "test-user-id"

app.dependency_overrides[get_current_user] = lambda: MockUser()

client = TestClient(app)

def test_get_notifications_returns_list(mock_supabase):
    mock_data = [
        {
            "id": "notif_1", "user_id": "test-user-id", "type": "task_completed", 
            "title": "T", "body": "B", "banner_text": None, "read": False,
            "related_task_id": None, "created_at": "2026-09-19T00:00:00Z"
        }
    ]
    
    mock_response = MagicMock()
    mock_response.data = mock_data
    mock_response.count = 1
    mock_supabase["router"].table().select().eq().order().range().execute.return_value = (
        mock_response
    )
    
    resp = client.get("/notifications")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["total"] == 1
    assert resp.json()["notifications"][0]["id"] == "notif_1"

def test_get_notifications_unread_filter(mock_supabase):
    mock_response = MagicMock()
    mock_response.data = []
    mock_response.count = 0
    
    mock_query = mock_supabase["router"].table().select().eq().order().range()
    mock_query.eq.return_value.execute.return_value = mock_response
    
    resp = client.get("/notifications?unread_only=true")
    assert resp.status_code == status.HTTP_200_OK
    
    # Verify .eq("read", False) was called
    mock_query.eq.assert_called_with("read", False)

def test_mark_notification_read(mock_supabase):
    mock_supabase["router"].table().update().eq().eq().execute.return_value.data = [
        {"id": "notif_1"}
    ]
    
    resp = client.post("/notifications/notif_1/read")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json() == {"id": "notif_1", "read": True}

def test_mark_notification_wrong_owner_returns_404(mock_supabase):
    mock_supabase["router"].table().update().eq().eq().execute.return_value.data = []
    
    resp = client.post("/notifications/notif_1/read")
    assert resp.status_code == status.HTTP_404_NOT_FOUND

def test_register_device_token(mock_supabase):
    mock_supabase["router"].table().upsert().execute.return_value.data = [
        {
            "id": "token_1", "fcm_token": "abc", "device_type": "ios", 
            "created_at": "2026-09-19T00:00:00Z"
        }
    ]
    
    resp = client.post("/device-tokens", json={"fcm_token": "abc", "device_type": "ios"})
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["id"] == "token_1"

def test_register_device_token_duplicate_upserts(mock_supabase):
    # Tested by same logic - the DB handles UPSERT. We just verify the API calls the DB with UPSERT.
    mock_supabase["router"].table().upsert().execute.return_value.data = [
        {
            "id": "token_1", "fcm_token": "abc", "device_type": "ios", 
            "created_at": "2026-09-19T00:00:00Z"
        }
    ]
    client.post("/device-tokens", json={"fcm_token": "abc", "device_type": "ios"})
    mock_supabase["router"].table().upsert.assert_called()
    kwargs = mock_supabase["router"].table().upsert.call_args[1]
    assert kwargs.get("on_conflict") == "user_id,fcm_token"

def test_delete_device_token(mock_supabase):
    mock_supabase["router"].table().delete().eq().eq().execute.return_value.data = [
        {"id": "token_1"}
    ]
    
    resp = client.delete("/device-tokens/token_1")
    assert resp.status_code == status.HTTP_204_NO_CONTENT

def test_delete_device_token_wrong_owner_returns_404(mock_supabase):
    mock_supabase["router"].table().delete().eq().eq().execute.return_value.data = []
    
    resp = client.delete("/device-tokens/token_1")
    assert resp.status_code == status.HTTP_404_NOT_FOUND


# --- 12.4 create_notification() unit tests ---

@patch("app.api.routers.notifications.send_push_notification")
@pytest.mark.asyncio
async def test_create_notification_inserts_row(mock_send_push, mock_supabase, mock_generate_banner):
    mock_supabase["router"].table().insert().execute.return_value.data = [{"id": "notif_uuid"}]
    
    notif_id = await create_notification("user_123", "task_completed", "Title", "Body")
    
    assert notif_id == "notif_uuid"
    mock_supabase["router"].table().insert.assert_called()
    
    # Assert banner model is called
    mock_generate_banner.assert_called_once()
    
    # Assert push was sent
    mock_send_push.assert_called_with(user_id="user_123", title="Title", body="Body")

@patch("app.api.routers.notifications.send_push_notification")
@pytest.mark.asyncio
async def test_create_notification_banner_failure_inserts_anyway(
    mock_send_push, mock_supabase, mock_generate_banner
):
    mock_generate_banner.side_effect = Exception("Banner failed")
    mock_supabase["router"].table().insert().execute.return_value.data = [{"id": "notif_uuid"}]
    
    notif_id = await create_notification("user_123", "task_completed", "Title", "Body")
    
    assert notif_id == "notif_uuid"
    # Verify we still inserted with banner_text=None
    call_args = mock_supabase["router"].table().insert.call_args[0][0]
    assert call_args["banner_text"] is None

@patch("app.api.routers.notifications.send_push_notification")
@pytest.mark.asyncio
async def test_create_notification_push_failure_does_not_raise(
    mock_send_push, mock_supabase, mock_generate_banner
):
    mock_send_push.side_effect = Exception("FCM failure")
    mock_supabase["router"].table().insert().execute.return_value.data = [{"id": "notif_uuid"}]
    
    # Should not raise
    notif_id = await create_notification("user_123", "task_completed", "Title", "Body")
    assert notif_id == "notif_uuid"
