import logging

import firebase_admin
from firebase_admin import credentials, messaging

from app.core.config import settings
from app.db.supabase_client import supabase

logger = logging.getLogger(__name__)

import os

# Module-Level Initialisation (once at import)
if settings.FIREBASE_SERVICE_ACCOUNT_PATH and os.path.exists(settings.FIREBASE_SERVICE_ACCOUNT_PATH):
    try:
        cred = credentials.Certificate(settings.FIREBASE_SERVICE_ACCOUNT_PATH)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        logger.warning("Failed to initialize Firebase Admin SDK: %s", e)
elif settings.FIREBASE_SERVICE_ACCOUNT_PATH:
    logger.warning(
        "FIREBASE_SERVICE_ACCOUNT_PATH file not found: %s",
        settings.FIREBASE_SERVICE_ACCOUNT_PATH,
    )

def send_push_notification(
    user_id: str,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> None:
    """
    Send a push notification to all registered devices for user_id via FCM HTTP v1.
    Best-effort: never raises. Logs warnings on partial or total failure.
    Stale/invalid tokens are silently removed from sessions_device_tokens.
    """
    try:
        # 1. Query sessions_device_tokens for all rows where user_id = user_id.
        result = (
            supabase.table("sessions_device_tokens")
            .select("id, fcm_token")
            .eq("user_id", user_id)
            .execute()
        )
        tokens = result.data
        
        # 2. If no tokens exist, log at DEBUG level and return immediately.
        if not tokens:
            logger.debug(f"No device tokens found for user_id={user_id}")
            return
            
        success_count = 0
        failure_count = 0
        
        # 3. For each token, build and send via the SDK:
        for token_row in tokens:
            fcm_token = token_row["fcm_token"]
            token_id = token_row["id"]
            try:
                message = messaging.Message(
                    notification=messaging.Notification(title=title, body=body),
                    data=data or {},
                    token=fcm_token,
                )
                messaging.send(message)
                
                # 4. On success: update last_active on that token's row in sessions_device_tokens.
                (
                    supabase.table("sessions_device_tokens")
                    .update({"last_active": "now()"})
                    .eq("id", token_id)
                    .execute()
                )
                success_count += 1
                
            except messaging.UnregisteredError:
                # 5. On messaging.UnregisteredError: delete the stale token row
                supabase.table("sessions_device_tokens").delete().eq("id", token_id).execute()
                logger.warning(f"Deleted stale device token for user_id={user_id}")
                failure_count += 1
                
            except Exception as e:
                # 6. On any other Exception: log at WARNING, do not delete the token,
                # do not re-raise.
                logger.warning(f"Failed to send push notification to user_id={user_id}: {e}")
                failure_count += 1
                
        # 7. After iterating all tokens, log a summary at INFO level
        logger.info(
            f"Push notification summary for user_id={user_id}: total={len(tokens)}, "
            f"success={success_count}, failure={failure_count}"
        )
        
    except Exception as e:
        logger.warning(f"Failed to process push notifications for user_id={user_id}: {e}")
