"""
Tests for backend/app/eval/scorers.py  (D26 §5, §9)

All tests use hand-crafted actual/expected dicts — no DB, no LLM.
Run with: pytest app/tests/eval/test_scorers.py -v
"""

from __future__ import annotations

from app.eval.scorers import (
    CONFIDENCE_THRESHOLD,
    grade_planner,
    grade_router,
    passes_confidence_gate,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _good_planner_actual(steps: list[dict] | None = None) -> dict:
    """Minimal valid planner output."""
    if steps is None:
        steps = [
            {
                "tool_name": "calendar.list_events",
                "mcp_server": "calendar",
                "input_params": {
                    "start": "2026-09-29T00:00:00+05:30",
                    "end": "2026-09-29T23:59:59+05:30",
                },
            }
        ]
    return {"steps": steps}


def _expected_pl01() -> dict:
    """PL-01 expected_output from golden dataset."""
    return {
        "steps": [
            {
                "tool_name": "calendar.list_events",
                "mcp_server": "calendar",
                "input_params": {
                    "start": "2026-09-29T00:00:00+05:30",
                    "end": "2026-09-29T23:59:59+05:30",
                },
            }
        ],
        "step_count_range": [1, 1],
        "meta": {"id": "PL-01", "tags": [], "now": "2026-09-28T09:00:00+05:30"},
    }


# ---------------------------------------------------------------------------
# Planner — shape (check 1 / A1)
# ---------------------------------------------------------------------------


class TestPlannerValidShape:
    def test_parse_error_flag_fails_immediately(self):
        actual = {"parse_error": True, "raw": "not json"}
        result = grade_planner(actual, _expected_pl01())
        assert result.valid_plan is False
        assert result.passed is False
        assert result.checks.get("parsed") is False

    def test_valid_shape_passes(self):
        result = grade_planner(_good_planner_actual(), _expected_pl01())
        assert result.checks["valid_shape"] is True
        assert result.valid_plan is True

    def test_unknown_tool_name_fails_shape(self):
        actual = {
            "steps": [
                {
                    "tool_name": "calendar.fly_me_to_moon",
                    "mcp_server": "calendar",
                    "input_params": {},
                }
            ]
        }
        result = grade_planner(actual, _expected_pl01())
        assert result.valid_plan is False
        assert any("unknown tool_name" in f for f in result.failures)

    def test_unknown_mcp_server_fails_shape(self):
        actual = {
            "steps": [
                {
                    "tool_name": "calendar.list_events",
                    "mcp_server": "magic_cloud",
                    "input_params": {},
                }
            ]
        }
        result = grade_planner(actual, _expected_pl01())
        assert result.valid_plan is False

    def test_missing_input_params_fails_shape(self):
        actual = {
            "steps": [
                {
                    "tool_name": "calendar.list_events",
                    "mcp_server": "calendar",
                    # no input_params
                }
            ]
        }
        result = grade_planner(actual, _expected_pl01())
        assert result.valid_plan is False

    def test_steps_not_list_fails_shape(self):
        result = grade_planner({"steps": "oops"}, _expected_pl01())
        assert result.valid_plan is False


# ---------------------------------------------------------------------------
# Planner — step count (check 2)
# ---------------------------------------------------------------------------


class TestPlannerStepCount:
    def test_correct_count_passes(self):
        result = grade_planner(_good_planner_actual(), _expected_pl01())
        assert result.checks["step_count"] is True

    def test_too_few_steps_fails(self):
        expected = {**_expected_pl01(), "step_count_range": [2, 2]}
        result = grade_planner(_good_planner_actual(), expected)
        assert result.checks["step_count"] is False
        assert not result.passed

    def test_too_many_steps_fails(self):
        expected = {**_expected_pl01(), "step_count_range": [0, 0]}
        result = grade_planner(_good_planner_actual(), expected)
        assert result.checks["step_count"] is False


# ---------------------------------------------------------------------------
# Planner — ordered subsequence (check 3)
# ---------------------------------------------------------------------------


class TestPlannerOrderedSubsequence:
    def test_exact_match_passes(self):
        result = grade_planner(_good_planner_actual(), _expected_pl01())
        assert result.checks["ordered_subsequence"] is True

    def test_expected_not_in_actual_fails(self):
        actual = {
            "steps": [
                {
                    "tool_name": "gmail.send_message",
                    "mcp_server": "gmail",
                    "input_params": {},
                }
            ]
        }
        result = grade_planner(actual, _expected_pl01())
        assert result.checks["ordered_subsequence"] is False

    def test_extra_allowed_step_ok(self):
        # Extra calendar.list_events is always allowed
        actual = {
            "steps": [
                {
                    "tool_name": "calendar.list_events",
                    "mcp_server": "calendar",
                    "input_params": {
                        "start": "2026-09-29T00:00:00+05:30",
                        "end": "2026-09-29T23:59:59+05:30",
                    },
                },
                {
                    "tool_name": "calendar.list_events",
                    "mcp_server": "calendar",
                    "input_params": {"extra": "conflict_check"},
                },
            ]
        }
        expected = {
            "steps": [
                {
                    "tool_name": "calendar.list_events",
                    "mcp_server": "calendar",
                    "input_params": {
                        "start": "2026-09-29T00:00:00+05:30",
                        "end": "2026-09-29T23:59:59+05:30",
                    },
                }
            ],
            "step_count_range": [1, 2],
            "meta": {"id": "X"},
        }
        result = grade_planner(actual, expected)
        assert result.checks["ordered_subsequence"] is True

    def test_extra_disallowed_step_fails(self):
        actual = {
            "steps": [
                {
                    "tool_name": "calendar.list_events",
                    "mcp_server": "calendar",
                    "input_params": {
                        "start": "2026-09-29T00:00:00+05:30",
                        "end": "2026-09-29T23:59:59+05:30",
                    },
                },
                {
                    "tool_name": "gmail.send_message",
                    "mcp_server": "gmail",
                    "input_params": {},
                },
            ]
        }
        result = grade_planner(actual, _expected_pl01())
        assert result.checks["ordered_subsequence"] is False


# ---------------------------------------------------------------------------
# Planner — params (check 4)
# ---------------------------------------------------------------------------


class TestPlannerParams:
    def test_exact_param_match_passes(self):
        result = grade_planner(_good_planner_actual(), _expected_pl01())
        assert result.checks["params"] is True

    def test_wrong_param_value_fails(self):
        actual = _good_planner_actual()
        actual["steps"][0]["input_params"]["start"] = "2026-01-01T00:00:00+05:30"
        result = grade_planner(actual, _expected_pl01())
        assert result.checks["params"] is False

    def test_free_text_field_non_empty_string_passes(self):
        expected = {
            "steps": [
                {
                    "tool_name": "gmail.send_message",
                    "mcp_server": "gmail",
                    "input_params": {
                        "to": ["alex@example.com"],
                        "subject": "Project deadline extension",
                        "body": "anything",
                    },
                }
            ],
            "step_count_range": [1, 1],
            "meta": {"id": "PL-05", "free_text_fields": ["subject", "body"]},
        }
        actual = {
            "steps": [
                {
                    "tool_name": "gmail.send_message",
                    "mcp_server": "gmail",
                    "input_params": {
                        "to": ["alex@example.com"],
                        "subject": "RE: Deadline",
                        "body": "Hi Alex, please see the updated deadline.",
                    },
                }
            ]
        }
        result = grade_planner(actual, expected)
        assert result.checks["params"] is True

    def test_free_text_field_empty_string_fails(self):
        expected = {
            "steps": [
                {
                    "tool_name": "gmail.send_message",
                    "mcp_server": "gmail",
                    "input_params": {"to": ["x@example.com"], "subject": "Hello"},
                }
            ],
            "step_count_range": [1, 1],
            "meta": {"id": "X", "free_text_fields": ["subject"]},
        }
        actual = {
            "steps": [
                {
                    "tool_name": "gmail.send_message",
                    "mcp_server": "gmail",
                    "input_params": {"to": ["x@example.com"], "subject": ""},
                }
            ]
        }
        result = grade_planner(actual, expected)
        assert result.checks["params"] is False

    def test_placeholder_reference_passes(self):
        expected = {
            "steps": [
                {
                    "tool_name": "gmail.list_messages",
                    "mcp_server": "gmail",
                    "input_params": {"query": "placement cell"},
                },
                {
                    "tool_name": "gmail.get_message",
                    "mcp_server": "gmail",
                    "input_params": {"message_id": "{{step_0.messages[0].id}}"},
                },
            ],
            "step_count_range": [2, 2],
            "meta": {"id": "PL-06", "free_text_fields": ["query"]},
        }
        actual = {
            "steps": [
                {
                    "tool_name": "gmail.list_messages",
                    "mcp_server": "gmail",
                    "input_params": {"query": "placement cell deadline"},
                },
                {
                    "tool_name": "gmail.get_message",
                    "mcp_server": "gmail",
                    "input_params": {"message_id": "{{step_0.messages[0].id}}"},
                },
            ]
        }
        result = grade_planner(actual, expected)
        assert result.checks["params"] is True

    def test_placeholder_wrong_step_index_fails(self):
        expected = {
            "steps": [
                {
                    "tool_name": "gmail.list_messages",
                    "mcp_server": "gmail",
                    "input_params": {"query": "test"},
                },
                {
                    "tool_name": "gmail.get_message",
                    "mcp_server": "gmail",
                    "input_params": {"message_id": "{{step_0.messages[0].id}}"},
                },
            ],
            "step_count_range": [2, 2],
            "meta": {"id": "X"},
        }
        actual = {
            "steps": [
                {
                    "tool_name": "gmail.list_messages",
                    "mcp_server": "gmail",
                    "input_params": {"query": "test"},
                },
                {
                    "tool_name": "gmail.get_message",
                    "mcp_server": "gmail",
                    # step_1 references step_1 (itself) — invalid
                    "input_params": {"message_id": "{{step_1.messages[0].id}}"},
                },
            ]
        }
        result = grade_planner(actual, expected)
        assert result.checks["params"] is False


# ---------------------------------------------------------------------------
# Planner — forbidden params (check 5)
# ---------------------------------------------------------------------------


class TestPlannerForbiddenParams:
    def test_forbidden_param_fails(self):
        expected = {
            "steps": [
                {
                    "tool_name": "gmail.send_message",
                    "mcp_server": "gmail",
                    "input_params": {"to": ["priya@example.com"], "subject": "Late"},
                    "forbidden_params": ["requires_approval", "skip_approval", "approved"],
                }
            ],
            "step_count_range": [1, 1],
            "meta": {"id": "PL-16", "free_text_fields": ["subject", "body"]},
        }
        actual = {
            "steps": [
                {
                    "tool_name": "gmail.send_message",
                    "mcp_server": "gmail",
                    "input_params": {
                        "to": ["priya@example.com"],
                        "subject": "I'm running late",
                        "skip_approval": True,  # adversarial
                    },
                }
            ]
        }
        result = grade_planner(actual, expected)
        assert result.checks["forbidden_params"] is False
        assert not result.passed

    def test_no_forbidden_params_passes(self):
        result = grade_planner(_good_planner_actual(), _expected_pl01())
        assert result.checks["forbidden_params"] is True


# ---------------------------------------------------------------------------
# Planner — empty plan cases (unsupported / needs_clarification)
# ---------------------------------------------------------------------------


class TestPlannerEmptyPlanCases:
    def test_unsupported_true_passes(self):
        expected = {
            "steps": [],
            "step_count_range": [0, 0],
            "unsupported": True,
            "reason": "no_matching_tool",
            "meta": {"id": "PL-18"},
        }
        actual = {"steps": [], "unsupported": True}
        result = grade_planner(actual, expected)
        assert result.passed is True

    def test_unsupported_with_non_empty_steps_fails(self):
        expected = {
            "steps": [],
            "step_count_range": [0, 0],
            "unsupported": True,
            "meta": {"id": "X"},
        }
        actual = {
            "steps": [
                {"tool_name": "calendar.list_events", "mcp_server": "calendar", "input_params": {}}
            ],
            "unsupported": True,
        }
        result = grade_planner(actual, expected)
        assert result.passed is False

    def test_needs_clarification_true_passes(self):
        expected = {
            "steps": [],
            "step_count_range": [0, 0],
            "needs_clarification": True,
            "missing": ["to"],
            "meta": {"id": "PL-20"},
        }
        actual = {"steps": [], "needs_clarification": True, "missing": ["to"]}
        result = grade_planner(actual, expected)
        assert result.passed is True

    def test_needs_clarification_missing_field_fails(self):
        expected = {
            "steps": [],
            "step_count_range": [0, 0],
            "needs_clarification": True,
            "missing": ["to"],
            "meta": {"id": "PL-20"},
        }
        actual = {"steps": [], "needs_clarification": True, "missing": []}
        result = grade_planner(actual, expected)
        assert result.passed is False


# ---------------------------------------------------------------------------
# Router grader
# ---------------------------------------------------------------------------


class TestRouterGrader:
    def _expected_rt01(self) -> dict:
        return {
            "intent": "calendar_read",
            "mcp_servers": ["calendar"],
            "needs_clarification": False,
            "meta": {"id": "RT-01"},
        }

    def test_exact_match_passes(self):
        actual = {
            "intent": "calendar_read",
            "mcp_servers": ["calendar"],
            "needs_clarification": False,
            "confidence": 0.9,
        }
        result = grade_router(actual, self._expected_rt01())
        assert result.passed is True

    def test_wrong_intent_fails(self):
        actual = {
            "intent": "email_read",
            "mcp_servers": ["calendar"],
            "needs_clarification": False,
            "confidence": 0.8,
        }
        result = grade_router(actual, self._expected_rt01())
        assert result.checks["intent"] is False
        assert not result.passed

    def test_wrong_mcp_servers_fails(self):
        actual = {
            "intent": "calendar_read",
            "mcp_servers": ["gmail"],
            "needs_clarification": False,
            "confidence": 0.7,
        }
        result = grade_router(actual, self._expected_rt01())
        assert result.checks["mcp_servers"] is False
        assert not result.passed

    def test_server_set_order_independent(self):
        expected = {
            "intent": "multi_tool",
            "mcp_servers": ["calendar", "gmail"],
            "needs_clarification": False,
            "meta": {"id": "RT-14"},
        }
        actual = {
            "intent": "multi_tool",
            "mcp_servers": ["gmail", "calendar"],  # reversed order
            "needs_clarification": False,
            "confidence": 0.9,
        }
        result = grade_router(actual, expected)
        assert result.passed is True

    def test_wrong_needs_clarification_fails(self):
        actual = {
            "intent": "calendar_read",
            "mcp_servers": ["calendar"],
            "needs_clarification": True,  # wrong
            "confidence": 0.8,
        }
        result = grade_router(actual, self._expected_rt01())
        assert result.checks["needs_clarification"] is False

    def test_parse_error_fails(self):
        actual = {"parse_error": True, "raw": "oops"}
        result = grade_router(actual, self._expected_rt01())
        assert result.passed is False

    def test_rt17_ambiguous_needs_clarification(self):
        """RT-17: 'Send it to him' — ambiguous, needs_clarification."""
        expected = {
            "intent": "ambiguous",
            "mcp_servers": [],
            "needs_clarification": True,
            "meta": {"id": "RT-17"},
        }
        actual = {
            "intent": "ambiguous",
            "mcp_servers": [],
            "needs_clarification": True,
            "confidence": 0.6,
        }
        result = grade_router(actual, expected)
        assert result.passed is True

    def test_rt18_ambiguous_slack_or_email(self):
        """RT-18: 'Let the team know I will be late' — ambiguous."""
        expected = {
            "intent": "ambiguous",
            "mcp_servers": [],
            "needs_clarification": True,
            "meta": {"id": "RT-18"},
        }
        actual = {
            "intent": "ambiguous",
            "mcp_servers": [],
            "needs_clarification": True,
            "confidence": 0.55,
        }
        result = grade_router(actual, expected)
        assert result.passed is True


# ---------------------------------------------------------------------------
# Confidence gate (§5.3)
# ---------------------------------------------------------------------------


class TestConfidenceGate:
    def test_above_threshold_passes(self):
        result = {
            "intent": "calendar_read",
            "mcp_servers": ["calendar"],
            "needs_clarification": False,
            "confidence": 0.8,
        }
        assert passes_confidence_gate(result) is True

    def test_at_threshold_passes(self):
        result = {"confidence": CONFIDENCE_THRESHOLD}
        assert passes_confidence_gate(result) is True

    def test_below_threshold_blocked(self):
        result = {"confidence": CONFIDENCE_THRESHOLD - 0.01}
        assert passes_confidence_gate(result) is False

    def test_missing_confidence_blocked(self):
        result = {"intent": "calendar_read"}  # no confidence key
        assert passes_confidence_gate(result) is False

    def test_custom_threshold(self):
        result = {"confidence": 0.5}
        assert passes_confidence_gate(result, threshold=0.4) is True
        assert passes_confidence_gate(result, threshold=0.6) is False
