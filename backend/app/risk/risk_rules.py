"""In-process lookup module for the risk_rules safety table.

The risk_rules table is seeded by a migration and never written to by the
running application or by any LLM.  This module:

1. Loads all rows once at first call (module-level cache, process-lifetime).
2. Exposes ``lookup(action_type, mcp_server) -> RiskRule | None``.
3. Returns ``None`` when no matching row exists - **the caller must treat
   None as (risk_tier="high", requires_approval=True)**.  The module never
   silently defaults to permissive.

Usage::

    from app.risk.risk_rules import lookup, RiskRule

    rule: RiskRule | None = lookup("gmail.send_message", "gmail")
    if rule is None:
        # Fail-closed: no matching row -> treat as high / requires approval.
        ...

Supabase access uses the service-role client (bypasses RLS) because
risk_rules is a global config table with no per-user rows.  The SELECT RLS
policy for the authenticated role exists as defence-in-depth for the Supabase
dashboard / PostgREST path; it is NOT the access path used here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.db.supabase_client import supabase

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RiskRule:
    """Immutable record representing one row in the risk_rules table.

    ``frozen=True`` makes instances hashable and prevents accidental mutation
    anywhere in the codebase.
    """

    action_type: str
    mcp_server: str
    risk_tier: str  # "low" | "medium" | "high"
    requires_approval: bool
    rationale: str


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_cache: dict[tuple[str, str], RiskRule] | None = None


def _load_rules() -> dict[tuple[str, str], RiskRule]:
    """Fetch all rows from risk_rules via the service-role Supabase client.

    Raises:
        RuntimeError: If the Supabase query fails, so the caller gets a loud
                      error rather than a silent empty cache that would make
                      every lookup return None (and thus trigger fail-closed
                      for ALL actions - equally bad as failing open).
    """
    try:
        result = supabase.table("risk_rules").select("*").execute()
    except Exception as exc:
        raise RuntimeError("risk_rules: failed to load cache from Supabase") from exc

    rows: list[dict] = result.data or []
    logger.info("risk_rules cache loaded: %d rules", len(rows))

    return {
        (row["action_type"], row["mcp_server"]): RiskRule(
            action_type=row["action_type"],
            mcp_server=row["mcp_server"],
            risk_tier=row["risk_tier"],
            requires_approval=bool(row["requires_approval"]),
            rationale=row.get("rationale") or "",
        )
        for row in rows
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def lookup(action_type: str, mcp_server: str) -> RiskRule | None:
    """Return the matching RiskRule, or None if no row exists.

    CONTRACT:
        ``None`` MUST be treated as ``(risk_tier="high", requires_approval=True)``
        by the caller.  This function never defaults - it returns ``None``
        honestly and the approval gate (D17) enforces the default-deny rule.

    The result is served from an in-memory cache populated at first call.
    The cache lives for the lifetime of the process - risk_rules only changes
    via migrations (i.e. deploys), so process-lifetime caching is correct.

    Args:
        action_type: The specific tool action, e.g. ``"gmail.send_message"``.
        mcp_server:  The MCP server name, e.g. ``"gmail"``.

    Returns:
        A frozen :class:`RiskRule` dataclass, or ``None`` on a cache miss.
    """
    global _cache
    if _cache is None:
        _cache = _load_rules()
    return _cache.get((action_type, mcp_server))


def invalidate_cache() -> None:
    """Force re-load of the rules cache on the next ``lookup()`` call.

    FOR TEST USE ONLY.  Never call this from production code - the CI lint
    gate (grep for ``invalidate_cache`` outside test files) will catch it.
    """
    global _cache
    _cache = None
