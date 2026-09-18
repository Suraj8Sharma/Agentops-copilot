"""Digest generation job — D23.

Generates daily and weekly digest rows for users who completed tasks within
the relevant time window.

Design decisions (see spec §4):
- Queries ``tasks`` directly (status='completed', completed_at in window) and
  groups by user_id in Python.  Does NOT iterate ``profiles`` — "active user"
  is implicitly anyone who completed a task in the window.
- Skips users with zero completed tasks in the window (no empty-digest rows).
- Builds a deterministic template summary — no LLM call (free-tier constraint,
  Section 2.3; LLM hook deferred to TODO(post-D23)).
- No ``execution_logs`` write — digest_job is not an agent-loop step (D23 §5).
  To add observability later: add 'digest_job' to the agent_name CHECK
  constraint in a new migration before wiring it here.

Scheduler:
- APScheduler BackgroundScheduler (in-process, thread-based).
- Daily job: fires at 08:00 UTC every day.
- Weekly job: fires at 08:00 UTC every Monday.

# TODO(pre-demo-hardening): revisit before D33/D39 — a sleeping free-tier
# Render instance will silently miss scheduled firings. Consider replacing
# with an external cron trigger hitting POST /internal/digests/run.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from itertools import groupby

from apscheduler.schedulers.background import BackgroundScheduler

from app.db.supabase_client import supabase

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TRUNCATE_CHARS = 40  # max chars per task snippet in the summary


def _truncate(text: str | None, limit: int = _TRUNCATE_CHARS) -> str:
    if not text:
        return "(no input)"
    return text[:limit] + "…" if len(text) > limit else text


def _build_summary(tasks: list[dict]) -> str:
    """Build a deterministic template summary string.

    Format: "{n} tasks completed: task1 snippet, task2 snippet, ..."
    No LLM call — keeps the job free of rate-limit exposure and fully testable.

    # TODO(post-D23): swap this for a call through app.llm.router if a
    # natural-language summary is wanted later.
    """
    n = len(tasks)
    snippets = ", ".join(_truncate(t.get("raw_input")) for t in tasks)
    return f"{n} task{'s' if n != 1 else ''} completed: {snippets}"


# ---------------------------------------------------------------------------
# Core job logic (pure function — easy to unit-test)
# ---------------------------------------------------------------------------


def run_digest_job(period_type: str, window_start: datetime, window_end: datetime) -> int:
    """Generate digest rows for all users who completed tasks in the window.

    Args:
        period_type: ``'daily'`` or ``'weekly'``.
        window_start: Start of the period window (inclusive), timezone-aware.
        window_end: End of the period window (inclusive), timezone-aware.

    Returns:
        Number of digest rows written.
    """
    logger.info(
        "digest_job starting: period_type=%s window=[%s, %s]",
        period_type,
        window_start.isoformat(),
        window_end.isoformat(),
    )

    # Step 1 — Query all completed tasks inside the window.
    try:
        result = (
            supabase.table("tasks")
            .select("id, user_id, raw_input")
            .eq("status", "completed")
            .gte("completed_at", window_start.isoformat())
            .lte("completed_at", window_end.isoformat())
            .execute()
        )
    except Exception as exc:
        logger.error("digest_job DB query failed: %s", exc)
        return 0

    rows = result.data or []
    if not rows:
        logger.info("digest_job: no completed tasks in window — nothing to write")
        return 0

    # Step 2 — Group by user_id in Python.
    sorted_rows = sorted(rows, key=lambda r: r["user_id"])
    by_user: dict[str, list[dict]] = {
        uid: list(tasks)
        for uid, tasks in groupby(sorted_rows, key=lambda r: r["user_id"])
    }

    # Step 3 — Insert one digest row per user with completed tasks.
    written = 0
    for user_id, tasks in by_user.items():
        summary_text = _build_summary(tasks)
        tasks_included = [t["id"] for t in tasks]

        try:
            supabase.table("digests").insert(
                {
                    "user_id": user_id,
                    "period_type": period_type,
                    "summary_text": summary_text,
                    "tasks_included": json.dumps(tasks_included),
                    "generated_at": datetime.now(tz=timezone.utc).isoformat(),
                }
            ).execute()
            written += 1
            logger.info(
                "digest_job: wrote %s digest for user_id=%s tasks=%d",
                period_type,
                user_id,
                len(tasks),
            )
        except Exception as exc:
            logger.error(
                "digest_job: failed to insert digest for user_id=%s: %s", user_id, exc
            )

    logger.info("digest_job done: period_type=%s rows_written=%d", period_type, written)
    return written


# ---------------------------------------------------------------------------
# Scheduled job callbacks
# ---------------------------------------------------------------------------


def _daily_job() -> None:
    """APScheduler callback — runs once per day."""
    now = datetime.now(tz=timezone.utc)
    window_end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    window_start = window_end - timedelta(days=1)
    run_digest_job("daily", window_start, window_end)


def _weekly_job() -> None:
    """APScheduler callback — runs once per week (Monday)."""
    now = datetime.now(tz=timezone.utc)
    # Start of today (Monday 00:00 UTC) → back 7 days
    window_end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    window_start = window_end - timedelta(weeks=1)
    run_digest_job("weekly", window_start, window_end)


# ---------------------------------------------------------------------------
# Scheduler lifecycle
# ---------------------------------------------------------------------------


def start_scheduler() -> BackgroundScheduler:
    """Create, configure, and start the APScheduler instance.

    Call this once at application startup (inside the FastAPI lifespan hook).
    Returns the running scheduler so the caller can shut it down gracefully.

    Schedule:
    - Daily digest:  08:00 UTC every day.
    - Weekly digest: 08:00 UTC every Monday (day_of_week=0).
    """
    scheduler = BackgroundScheduler(timezone="UTC")

    scheduler.add_job(
        _daily_job,
        trigger="cron",
        hour=8,
        minute=0,
        id="digest_daily",
        name="Daily digest generation",
        replace_existing=True,
    )

    scheduler.add_job(
        _weekly_job,
        trigger="cron",
        day_of_week=0,  # Monday
        hour=8,
        minute=0,
        id="digest_weekly",
        name="Weekly digest generation",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "digest_job scheduler started — daily@08:00 UTC, weekly@Mon 08:00 UTC"
    )
    return scheduler


def stop_scheduler(scheduler: BackgroundScheduler) -> None:
    """Gracefully shut down the scheduler on application shutdown."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("digest_job scheduler stopped")
