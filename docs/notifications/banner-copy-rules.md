# Notification banner copy rules (D20)

These rules are the executable companion to the D19 payload contract. The
authoritative event `type` selects exactly one rule in
`backend/app/notifications/banner_model.py`; the model may only use the
permitted input fields for that type. Every output is a display-only
`banner_text` value and cannot affect risk rules, approval decisions, or agent
execution.

| Type | Permitted facts | Must convey | Must not | Example |
| --- | --- | --- | --- | --- |
| `approval_needed` | title, body, tool_name, input_params, task_id | Pending action and affected tool/target when supplied | Recommend approve/reject, imply it ran, invent urgency, expose UUIDs | “Your agent wants to send an email — tap to review.” |
| `task_completed` | title, body, tool_name, task_id | What finished, in past tense | Invent a result, expose UUIDs, imply future work | “Done — your calendar event was created successfully.” |
| `digest_ready` | title, body, digest_period | Digest availability and period when supplied | Invent contents/counts or imply an action occurred | “Your daily digest is ready — see your recent activity.” |
| `oauth_expiring` | title, body, provider, expires_at | Provider needing renewal and reconnect action | Say expired/critical/danger/broken/failed, hide provider, invent dates | “Your Google connection needs a quick reconnect.” |

All types share the D19 maximum of 80 characters. Missing fields cause a
shorter factual line or the model fallback; they never justify invented facts.
Empty model output falls back to the notification body/title in the widget
contract. D21 evaluation cases can assert type-specific permitted fields,
approval non-recommendation, OAuth provider visibility, and the shared length
cap directly from `BANNER_COPY_RULES`.

D29 quality pass: banner generation now rejects empty, over-long, alarmist, or
recommendation-heavy output and falls back to deterministic per-type copy
instead of surfacing invalid text. This keeps the banner advisory-only while
preserving a safe user experience even when the LLM route is unavailable.
