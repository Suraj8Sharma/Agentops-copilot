"""
backend/app/notifications/banner_model.py
==========================================
Owner: Ishani
Status: SPEC + PROMPT DRAFT (D11) — Implementation is D17
Last updated: 2026-09-04

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
D11 SPEC — Notification Banner Model
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PURPOSE
───────
When a notification is created, the system needs a short, human-readable one-liner
to display as the push/in-app banner text. This module owns that LLM call.

Design principle (from Section 3 of the manual):
    "The model is built and evaluated separately from the planner so a bad banner
    line can never change what the agent actually does."

The banner model DESCRIBES. It never decides. Nothing in approval_gate.py, the
planner, or any other agent component reads banner_text to make a behavioral
decision. It is a pure display field. banner_text is nullable — no downstream
code may treat None as an error.

INPUT/OUTPUT CONTRACT
─────────────────────
Input: a dict with the following shape (only fields relevant to the notification
type will be populated; others may be None or omitted):

    {
      "type": str,           # approval_needed | task_completed | digest_ready | oauth_expiring
      "title": str,          # full notification title
      "body": str,           # full notification body
      "tool_name": str,      # e.g. "gmail_send"  (approval_needed, task_completed)
      "input_params": dict,  # tool call parameters (approval_needed)
      "task_id": str,        # UUID of the task (task_completed, approval_needed)
      "provider": str,       # e.g. "google"  (oauth_expiring)
      "expires_at": str,     # ISO-8601 datetime string  (oauth_expiring)
      "digest_period": str,  # "daily" | "weekly"  (digest_ready)
    }

Output: str — a single short banner line.

    banner_text: str   # <= 80 characters, plain English, non-alarming, no markdown

Hard output constraints:
  - Maximum 80 characters (tested: test_banner_model_output_length_under_limit)
  - Minimum 10 characters
  - No markdown (no **bold**, _italic_, bullet points)
  - No invented details (only facts from the input dict)
  - Non-alarming tone (no "WARNING", "CRITICAL", "DANGER", "FAILED")
  - English only

API CONTRACT (Section 3)
────────────────────────
No new REST endpoint. This is an internal backend call invoked when a notification
is created. The client-facing surface is already defined:

    GET  /notifications           JWT  → list in-app notifications (includes banner_text)
    POST /notifications/{id}/read JWT  → mark a notification read

Storage contract — notifications table (Group E):

    Column       Type   Notes
    ─────────────────────────────────────────────────────────────────────
    banner_text  text   Short LLM-written line, advisory only, display field
                        NULLABLE — no downstream code may treat None as an error
    type         text   approval_needed | task_completed | digest_ready | oauth_expiring
    title        text   Full notification title (already written by caller)
    body         text   Full notification body (already written by caller)

LOGGING
───────
Every call emits a row to llm_usage_logs with:
    request_type = "banner"
(already in the enum: planning | routing | risk_explanation | banner | memory_extraction)

LLM ROUTER & BUDGET
───────────────────
Primary: Groq (smallest/fastest model available — banner calls need speed, not depth)
Fallback: Gemini (automatic on 429, via shared LLM router — no banner-specific exception path)
Token budget: input <= 400 tokens, output <= 30 tokens

PER-EVENT-TYPE BEHAVIOR
────────────────────────
approval_needed
  Tone: Calm, informative. The action hasn't happened yet.
  Key fields: tool_name (in human words, not raw identifier), input_params (summarise only)
  Golden: "Your agent wants to send an email — tap to review before it goes."
  Golden: "Agent is ready to create a calendar event — your approval needed."
  Constraint: Must NOT imply the action already ran.

task_completed
  Tone: Positive, brief. Past tense.
  Key fields: tool_name (in human words)
  Golden: "Done — your calendar event was created successfully."
  Golden: "Email sent. Your task is complete."
  Constraint: Must NOT include raw task IDs or UUIDs.

digest_ready
  Tone: Neutral, inviting.
  Key fields: digest_period ("daily" | "weekly")
  Golden: "Your daily digest is ready — see what your agent did today."
  Golden: "Weekly summary ready — tap to review this week's activity."
  Constraint: Must include period if present; must NOT claim counts unless in input.

oauth_expiring
  Tone: Calm, factual. NOT alarming — this is routine re-auth.
  Key fields: provider (write in plain English: "Google", not "google"), expires_at
  Golden: "Your Google connection expires soon — tap to reconnect."
  Golden: "GitHub access token expiring — a quick reconnect keeps things running."
  Constraint: Must NOT use "EXPIRED", "CRITICAL", "DANGER", "BROKEN".

FAILURE HANDLING
────────────────
LLM call times out:      banner_text = None; notification fires anyway with title+body intact
Output > 80 chars:       Truncate at 80 chars with "…" suffix; log a warning
LLM returns empty:       Fall back to BANNER_DEFAULTS[type]
Groq 429:                Auto-fallback to Gemini via shared router (Section 8.4)
Unknown type value:      Log error; banner_text = None; do not raise

DOWNSTREAM DEPENDENCY CHAIN
────────────────────────────
D11 (this spec)
  └─► D17  First working banner_model.py (Ishani)
        └─► D19  In-app banner wiring, banner_widget.dart (Jigyasu)
              └─► D20  Per-event copy rules, trigger_rules.py (Suraj)
                    └─► D21  Eval cases authored (Sanskriti)
                          └─► D29  Quality pass vs. golden banner-text cases

OPEN DECISIONS (resolve before D17)
─────────────────────────────────────
1. [Suraj] Confirm banner_text = None on failure is acceptable (default: yes)
2. [Ishani + Jigyasu] Confirm 80-char limit vs. 100/120
3. [Suraj] Confirm smallest Groq model for banner calls (default: llama-3.1-8b-instant)
4. [Ishani + Sanskriti] Confirm eval golden-case format before D21

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
D11 SYSTEM PROMPT DRAFT — generate_banner_system_prompt()
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

See BANNER_SYSTEM_PROMPT below. Style mirrors the Section 9.3 explanation-LLM
prompt: plain English, no invented details, non-alarming, advisory only.
"""

from __future__ import annotations

import logging

from app.llm.router import route_llm_call
from app.notifications.banner_contract import (
    BANNER_MAX_CHARS,
    NOTIFICATION_TYPES,
    NotificationBannerPayload,
)

_logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

# Safe hardcoded fallbacks — used when LLM returns an unusable response.
# These are NOT LLM-generated; they are a last-resort safety net.
BANNER_DEFAULTS: dict[str, str] = {
    "approval_needed": "Your agent needs your approval.",
    "task_completed": "Your task completed.",
    "digest_ready": "Your digest is ready.",
    "oauth_expiring": "A connected account needs your attention.",
}

# ──────────────────────────────────────────────────────────────────────────────
# D11 DELIVERABLE: System Prompt Draft
# ──────────────────────────────────────────────────────────────────────────────
# This is the first draft of the system prompt. It will be refined in D17
# (implementation) and again in D29 (quality pass vs. golden cases).
#
# Design notes (matching the Section 9.3 explanation-LLM philosophy):
#   - Plain English instructions, no jargon
#   - Explicit "do not invent" constraint
#   - Explicit tone constraint (non-alarming)
#   - Explicit format constraint (no markdown, single line, <= 80 chars)
#   - The model is told it is advisory — it summarises, it does not decide
# ──────────────────────────────────────────────────────────────────────────────

BANNER_SYSTEM_PROMPT = """
You write short notification banner lines for an AI assistant app called AgentOps Copilot.

Your job is to read a notification event and produce ONE short sentence that a user
will see as the banner text on a push or in-app notification.

RULES — follow every one of these, no exceptions:

1. Length: Your response must be 80 characters or fewer. Count carefully.

2. One sentence only. No lists, no bullets, no paragraphs.

3. No markdown. Do not use **bold**, _italic_, or any other formatting.
   Plain text only.

4. Only use facts from the input. Do not invent names, dates, file names,
   email addresses, or any detail that is not in the event data given to you.
   If a detail is not in the input, leave it out entirely.

5. Tone: calm and clear. Do not use the words WARNING, CRITICAL, DANGER,
   FAILED, ERROR, URGENT, or ALERT. These are routine notifications, not
   emergencies. Treat them that way.

6. Match the event type:
   - approval_needed: the action has NOT happened yet. Say what the agent
     wants to do and invite the user to review. Do not say it's done.
   - task_completed: the action is finished. Use past tense. Keep it positive
     and brief.
   - digest_ready: a summary is ready to view. Keep it short and inviting.
   - oauth_expiring: a connection needs to be renewed. Calm, not alarming.
     Name the provider in plain English (Google, not "google").

7. Do not include raw technical identifiers — no UUIDs, no raw tool names
   (like "gmail_send"), no database column values. Translate them into
   human words.

Output only the banner line. Nothing else — no explanation, no prefix, no quotes.
""".strip()


# ──────────────────────────────────────────────────────────────────────────────
# D11 DELIVERABLE: User Prompt Template Draft
# ──────────────────────────────────────────────────────────────────────────────
# Constructs the user-turn message sent alongside the system prompt.
# Implementation (D17) will call this to build the per-request message.
# ──────────────────────────────────────────────────────────────────────────────


def build_banner_user_prompt(event: dict) -> str:
    """
    Construct the user-turn message for a banner generation call.

    Args:
        event: Notification event dict (see module docstring for shape).

    Returns:
        A formatted string to send as the user message to the LLM.

    NOTE (D11): This is a prompt DRAFT. The exact field rendering may be refined
    in D17 based on real LLM behaviour in testing.
    """
    notification_type = event.get("type", "unknown")
    title = event.get("title", "")
    body = event.get("body", "")

    # Build a minimal, type-specific context block.
    # Only include fields relevant to the type — never dump the full dict.
    context_lines = [
        f"Notification type: {notification_type}",
        f"Title: {title}",
        f"Body: {body}",
    ]

    if notification_type == "approval_needed":
        tool_name = event.get("tool_name", "")
        if tool_name:
            context_lines.append(f"Tool requested: {tool_name}")

    elif notification_type == "task_completed":
        tool_name = event.get("tool_name", "")
        if tool_name:
            context_lines.append(f"Tool that completed: {tool_name}")

    elif notification_type == "digest_ready":
        period = event.get("digest_period", "")
        if period:
            context_lines.append(f"Digest period: {period}")

    elif notification_type == "oauth_expiring":
        provider = event.get("provider", "")
        expires_at = event.get("expires_at", "")
        if provider:
            context_lines.append(f"Provider: {provider}")
        if expires_at:
            context_lines.append(f"Expires at: {expires_at}")

    context = "\n".join(context_lines)

    return (
        f"Write a short banner line (max 80 characters) for this notification:\n\n"
        f"{context}\n\n"
        f"Banner line:"
    )


# ──────────────────────────────────────────────────────────────────────────────
# D11 STUB: generate_banner() — implementation is D17
# ──────────────────────────────────────────────────────────────────────────────


async def generate_banner(event: dict) -> str | None:
    """
    Generate a short banner line for a notification event.

    Args:
        event: Notification event dict. See module docstring for full shape.

    Returns:
        A short banner string (<= 80 chars), or None if generation fails.
    """
    event_type = event.get("type")
    if event_type not in NOTIFICATION_TYPES:
        _logger.error(f"Unknown notification event type: {event_type}")
        return None

    user_prompt = build_banner_user_prompt(event)

    full_prompt = f"System: {BANNER_SYSTEM_PROMPT}\n\nUser: {user_prompt}"

    try:
        response = await route_llm_call(prompt=full_prompt, request_type="banner")

        if not response or not response.text:
            return BANNER_DEFAULTS.get(event_type)

        banner_text = response.text.strip()

        if len(banner_text) > BANNER_MAX_CHARS:
            _logger.warning(f"Banner exceeded {BANNER_MAX_CHARS} chars, truncating.")
            banner_text = banner_text[: BANNER_MAX_CHARS - 3] + "..."

        return banner_text
    except Exception as e:
        _logger.error(f"Failed to generate banner: {e}", exc_info=True)
        return None


def build_banner_payload(
    event: dict,
    banner_text: str | None,
    *,
    notification_id: str | None = None,
    related_task_id: str | None = None,
    read: bool = False,
    created_at: str | None = None,
) -> NotificationBannerPayload:
    """Assemble the row-shaped payload shared with the mobile banner widget.

    Trigger rules own ``type``, ``title``, ``body`` and task linkage. This
    helper only places the model's advisory ``banner_text`` into that contract.
    It never produces approval or risk decisions.
    """
    return NotificationBannerPayload(
        notification_id=notification_id,
        type=event["type"],
        title=event.get("title", ""),
        body=event.get("body", ""),
        banner_text=banner_text,
        related_task_id=related_task_id or event.get("task_id"),
        read=read,
        created_at=created_at,
    )
