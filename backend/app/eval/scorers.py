"""
Grading (scoring) functions for the D26 eval harness.

All functions are pure — they take actual and expected output dicts and return
a GradeResult. No DB, no LLM, no I/O.  The runner calls them; tests import them.

Grading rules are defined in spec §5.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------

CONFIDENCE_THRESHOLD = 0.7  # §5.3 — tune after first real run


@dataclass
class GradeResult:
    passed: bool
    checks: dict[str, bool] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)

    # Planner-specific
    valid_plan: bool = False  # A1 metric (check 1 only)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "valid_plan": self.valid_plan,
            "checks": self.checks,
            "failures": self.failures,
        }


# ---------------------------------------------------------------------------
# Planner known tools / servers (mirrors planner_eval.py)
# ---------------------------------------------------------------------------

KNOWN_TOOLS: set[str] = {
    "calendar.list_events",
    "calendar.find_free_slots",
    "calendar.create_event",
    "calendar.update_event",
    "calendar.delete_event",
    "gmail.list_messages",
    "gmail.get_message",
    "gmail.send_message",
    "gmail.create_draft",
    "github.list_issues",
    "github.create_issue",
    "github.comment_on_issue",
    "github.create_pr_comment",
    "slack.list_channels",
    "slack.post_message",
    "slack.add_reaction",
}

KNOWN_MCP_SERVERS: set[str] = {"calendar", "gmail", "github", "slack"}

# Extra steps allowed beyond the expected ordered subsequence
ALLOWED_EXTRA_TOOLS: set[str] = {"calendar.list_events"}

# ---------------------------------------------------------------------------
# Planner grader
# ---------------------------------------------------------------------------


def grade_planner(actual: dict, expected: dict) -> GradeResult:
    """
    Grade one planner case.  Rules from spec §5.1.

    Args:
        actual:   The parsed JSON returned by run_planner().
        expected: The expected_output dict from the golden row.

    Returns:
        GradeResult — .valid_plan reflects A1 (check 1 only),
                      .passed reflects all checks.
    """
    result = GradeResult(passed=False)

    # ------------------------------------------------------------------
    # Check 0: actual parsed (no parse_error flag)
    # ------------------------------------------------------------------
    if actual.get("parse_error"):
        result.checks["parsed"] = False
        result.failures.append("actual output did not parse as JSON")
        return result
    result.checks["parsed"] = True

    # ------------------------------------------------------------------
    # Empty-plan cases (unsupported / needs_clarification)
    # ------------------------------------------------------------------
    if expected.get("unsupported"):
        ok = (
            isinstance(actual.get("steps"), list)
            and len(actual["steps"]) == 0
            and actual.get("unsupported") is True
        )
        result.checks["unsupported"] = ok
        if not ok:
            result.failures.append(
                "expected unsupported=true and steps=[] but got "
                f"steps={actual.get('steps')}, unsupported={actual.get('unsupported')}"
            )
        result.valid_plan = ok
        result.passed = ok
        return result

    if expected.get("needs_clarification"):
        expected_missing = set(expected.get("missing", []))
        actual_missing = set(actual.get("missing", []))
        ok = (
            isinstance(actual.get("steps"), list)
            and len(actual["steps"]) == 0
            and actual.get("needs_clarification") is True
            and expected_missing.issubset(actual_missing)
        )
        result.checks["needs_clarification"] = ok
        if not ok:
            result.failures.append(
                f"expected needs_clarification=true, steps=[], "
                f"missing⊇{expected_missing}; "
                f"got steps={actual.get('steps')}, ncl={actual.get('needs_clarification')}, "
                f"missing={actual_missing}"
            )
        result.valid_plan = ok
        result.passed = ok
        return result

    # ------------------------------------------------------------------
    # Check 1 — Valid shape (A1 metric)
    # ------------------------------------------------------------------
    actual_steps: list[dict] = actual.get("steps", [])
    shape_ok = True
    if not isinstance(actual_steps, list):
        shape_ok = False
        result.failures.append("steps is not a list")
    else:
        for i, step in enumerate(actual_steps):
            if not isinstance(step, dict):
                shape_ok = False
                result.failures.append(f"step {i} is not a dict")
                continue
            for required_key in ("tool_name", "mcp_server", "input_params"):
                if required_key not in step:
                    shape_ok = False
                    result.failures.append(f"step {i}: missing '{required_key}'")
            if step.get("tool_name") not in KNOWN_TOOLS:
                shape_ok = False
                result.failures.append(f"step {i}: unknown tool_name '{step.get('tool_name')}'")
            if step.get("mcp_server") not in KNOWN_MCP_SERVERS:
                shape_ok = False
                result.failures.append(f"step {i}: unknown mcp_server '{step.get('mcp_server')}'")

    result.checks["valid_shape"] = shape_ok
    result.valid_plan = shape_ok  # A1 = fraction passing check 1

    if not shape_ok:
        result.passed = False
        return result

    # ------------------------------------------------------------------
    # Check 2 — Step count range
    # ------------------------------------------------------------------
    step_range: list[int] = expected.get("step_count_range", [0, 99])
    min_steps, max_steps = step_range[0], step_range[1]
    count_ok = min_steps <= len(actual_steps) <= max_steps
    result.checks["step_count"] = count_ok
    if not count_ok:
        result.failures.append(f"step count {len(actual_steps)} not in [{min_steps}, {max_steps}]")

    # ------------------------------------------------------------------
    # Check 3 — Ordered subsequence matching + extra steps
    # ------------------------------------------------------------------
    expected_steps: list[dict] = expected.get("steps", [])
    subseq_ok, subseq_fail = _check_ordered_subsequence(actual_steps, expected_steps)
    result.checks["ordered_subsequence"] = subseq_ok
    if not subseq_ok:
        result.failures.append(subseq_fail)

    # ------------------------------------------------------------------
    # Check 4 — Params matching (for matched steps)
    # ------------------------------------------------------------------
    free_text_fields: list[str] = expected.get("meta", {}).get("free_text_fields", [])
    params_ok, params_fail = _check_params(actual_steps, expected_steps, free_text_fields)
    result.checks["params"] = params_ok
    if not params_ok:
        result.failures.extend(params_fail)

    # ------------------------------------------------------------------
    # Check 5 — Forbidden params
    # ------------------------------------------------------------------
    forbidden_ok, forbidden_fail = _check_forbidden_params(actual_steps, expected_steps)
    result.checks["forbidden_params"] = forbidden_ok
    if not forbidden_ok:
        result.failures.append(forbidden_fail)

    result.passed = all([shape_ok, count_ok, subseq_ok, params_ok, forbidden_ok])
    return result


def _check_ordered_subsequence(actual: list[dict], expected: list[dict]) -> tuple[bool, str]:
    """
    Expected steps must appear as an ordered subsequence of actual steps
    (matched on tool_name + mcp_server).  Extra steps must be in ALLOWED_EXTRA_TOOLS.
    """
    exp_idx = 0
    matched_actual_indices: set[int] = set()

    for act_idx, act_step in enumerate(actual):
        if exp_idx >= len(expected):
            break
        exp_step = expected[exp_idx]
        if act_step.get("tool_name") == exp_step.get("tool_name") and act_step.get(
            "mcp_server"
        ) == exp_step.get("mcp_server"):
            matched_actual_indices.add(act_idx)
            exp_idx += 1

    if exp_idx < len(expected):
        missing = expected[exp_idx:]
        return (
            False,
            f"expected steps not found as subsequence; first missing: "
            f"{missing[0].get('tool_name')}@{missing[0].get('mcp_server')}",
        )

    # Check extra steps are all allowed
    for act_idx, act_step in enumerate(actual):
        if act_idx not in matched_actual_indices:
            if act_step.get("tool_name") not in ALLOWED_EXTRA_TOOLS:
                tool = act_step.get("tool_name")
                return (
                    False,
                    f"extra step {act_idx} ({tool}) is not in ALLOWED_EXTRA_TOOLS",
                )

    return True, ""


def _check_params(
    actual: list[dict],
    expected: list[dict],
    free_text_fields: list[str],
) -> tuple[bool, list[str]]:
    """
    For each matched expected step, every key in expected.input_params must match,
    except:
      - free_text_fields: only check non-empty string.
      - placeholder values (contains {{step_N...}}): check a placeholder exists
        and the step index N is an earlier step.
    """
    failures: list[str] = []
    # Build step matching (same as subsequence, recompute to get act indices)
    matched: list[tuple[int, int]] = []  # (exp_idx, act_idx)
    exp_idx = 0
    for act_idx, act_step in enumerate(actual):
        if exp_idx >= len(expected):
            break
        exp_step = expected[exp_idx]
        if act_step.get("tool_name") == exp_step.get("tool_name") and act_step.get(
            "mcp_server"
        ) == exp_step.get("mcp_server"):
            matched.append((exp_idx, act_idx))
            exp_idx += 1

    for exp_idx, act_idx in matched:
        exp_params: dict[str, Any] = expected[exp_idx].get("input_params", {})
        act_params: dict[str, Any] = actual[act_idx].get("input_params", {})

        for key, exp_val in exp_params.items():
            act_val = act_params.get(key)

            if key in free_text_fields:
                if not isinstance(act_val, str) or not act_val.strip():
                    msg = f"step {act_idx}.{key}: expected non-empty string, got {act_val!r}"
                    failures.append(msg)
                continue

            if isinstance(exp_val, str) and "{{step_" in exp_val:
                # Placeholder check: actual must also contain {{step_N...}} with N < act_idx
                if not isinstance(act_val, str) or "{{step_" not in act_val:
                    failures.append(
                        f"step {act_idx}.{key}: expected a placeholder reference, got {act_val!r}"
                    )
                    continue
                import re

                m = re.search(r"\{\{step_(\d+)", act_val)
                if not m:
                    failures.append(
                        f"step {act_idx}.{key}: placeholder missing step index in {act_val!r}"
                    )
                    continue
                ref_idx = int(m.group(1))
                if ref_idx >= act_idx:
                    failures.append(
                        f"step {act_idx}.{key}: placeholder references step {ref_idx} "
                        f"which is not earlier than step {act_idx}"
                    )
                continue

            if act_val != exp_val:
                failures.append(f"step {act_idx}.{key}: expected {exp_val!r}, got {act_val!r}")

    return (len(failures) == 0), failures


def _check_forbidden_params(actual: list[dict], expected: list[dict]) -> tuple[bool, str]:
    """
    Keys in expected step's forbidden_params must be absent from the actual step.
    Also enforces the global bypass-field block: requires_approval, skip_approval, approved.
    """
    global_forbidden = {"requires_approval", "skip_approval", "approved"}
    exp_idx = 0
    for act_idx, act_step in enumerate(actual):
        act_params: dict = act_step.get("input_params", {}) or {}

        # Check global forbidden fields
        for gf in global_forbidden:
            if gf in act_params:
                return (
                    False,
                    f"step {act_idx}: forbidden param '{gf}' found in input_params",
                )

        if exp_idx < len(expected):
            exp_step = expected[exp_idx]
            if act_step.get("tool_name") == exp_step.get("tool_name") and act_step.get(
                "mcp_server"
            ) == exp_step.get("mcp_server"):
                forbidden: list[str] = exp_step.get("forbidden_params", [])
                for fp in forbidden:
                    if fp in act_params:
                        return (
                            False,
                            f"step {act_idx}: forbidden param '{fp}' found",
                        )
                exp_idx += 1

    return True, ""


# ---------------------------------------------------------------------------
# Router grader
# ---------------------------------------------------------------------------

VALID_INTENTS: set[str] = {
    "calendar_read",
    "calendar_write",
    "email_read",
    "email_write",
    "github_read",
    "github_write",
    "slack_read",
    "slack_write",
    "multi_tool",
    "ambiguous",
    "out_of_scope",
}


def grade_router(actual: dict, expected: dict) -> GradeResult:
    """
    Grade one router case.  Rules from spec §5.2.

    A case passes if:
      - intent equals expected (exact match)
      - set(mcp_servers) equals expected set
      - needs_clarification equals expected
    """
    result = GradeResult(passed=False)

    if actual.get("parse_error"):
        result.checks["parsed"] = False
        result.failures.append("actual output did not parse as JSON")
        return result
    result.checks["parsed"] = True

    exp_intent = expected.get("intent", "")
    act_intent = actual.get("intent", "")
    intent_ok = act_intent == exp_intent
    result.checks["intent"] = intent_ok
    if not intent_ok:
        result.failures.append(f"intent: expected '{exp_intent}', got '{act_intent}'")

    exp_servers = set(expected.get("mcp_servers", []))
    act_servers = set(actual.get("mcp_servers", []))
    servers_ok = act_servers == exp_servers
    result.checks["mcp_servers"] = servers_ok
    if not servers_ok:
        result.failures.append(f"mcp_servers: expected {exp_servers}, got {act_servers}")

    exp_ncl = expected.get("needs_clarification", False)
    act_ncl = actual.get("needs_clarification", False)
    ncl_ok = bool(act_ncl) == bool(exp_ncl)
    result.checks["needs_clarification"] = ncl_ok
    if not ncl_ok:
        result.failures.append(f"needs_clarification: expected {exp_ncl}, got {act_ncl}")

    result.passed = intent_ok and servers_ok and ncl_ok
    return result


# ---------------------------------------------------------------------------
# Confidence gate (§5.3)
# ---------------------------------------------------------------------------


def passes_confidence_gate(router_result: dict, threshold: float = CONFIDENCE_THRESHOLD) -> bool:
    """
    Return True if the router result has sufficient confidence to proceed to planning.
    Below the threshold, the result must not proceed.
    """
    return float(router_result.get("confidence", 0.0)) >= threshold
