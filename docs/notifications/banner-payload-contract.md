# Notification banner payload contract (D19)

This is the shared contract between `backend/app/notifications/banner_model.py`
and the future `mobile/lib/features/notifications/banner_widget.dart`. It is
also the shape Suraj can persist directly in the D24 `notifications` table.

```json
{
  "notification_id": "uuid | null",
  "type": "approval_needed | task_completed | digest_ready | oauth_expiring",
  "title": "short notification title",
  "body": "full notification text",
  "banner_text": "short advisory copy | null",
  "related_task_id": "uuid | null",
  "read": false,
  "created_at": "timestamptz | null"
}
```

The field mapping is direct: `notification_id` → `id`, and every other field
uses the same name as the planned table column. `banner_text` is capped at 80
characters and is display-only; it must never influence risk, approval, or
execution decisions. If it is null or empty, the widget renders `body`, then
`title`, then a neutral generic notification label.

Tap routing is derived from the authoritative `type`: `approval_needed` opens
the approval surface, `task_completed` opens the related task, `digest_ready`
opens the digest, and `oauth_expiring` opens OAuth Connections. The first two
types carry `related_task_id`; the latter two intentionally carry null. Unknown
types use a safe generic banner and do not crash the notification surface.

Worked payloads for all four types are available as
`MOCK_BANNER_PAYLOADS` in `backend/app/notifications/banner_contract.py`.
