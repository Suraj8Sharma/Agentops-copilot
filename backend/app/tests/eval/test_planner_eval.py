"""
Tests for planner eval (D26 §9).

Tests use mocked LLM calls — no live API, no DB.

Run with: pytest app/tests/eval/test_planner_eval.py -v
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.llm.groq_client  # noqa: F401
from app.eval.planner_eval import PROMPT_VERSION, run_planner
from app.eval.scorers import grade_planner

# ---------------------------------------------------------------------------
# Helper mock response
# ---------------------------------------------------------------------------


def _mock_llm_response(text: str):
    resp = MagicMock()
    resp.text = text
    return resp


# ---------------------------------------------------------------------------
# run_planner — basic shape tests (spec §9: valid plan JSON, step structure)
# ---------------------------------------------------------------------------


class TestRunPlannerValidPlanJSON:
    @pytest.mark.asyncio
    async def test_valid_plan_json_returned(self):
        """run_planner returns a dict with 'steps' list."""
        payload = json.dumps(
            {
                "steps": [
                    {
                        "tool_name": "calendar.list_events",
                        "mcp_server": "calendar",
                        "input_params": {
                            "start": "2026-09-29T00:00:00+05:30",
                            "end": "2026-09-29T23:59:59+05:30",
                        },
                    }
                ]
            }
        )

        with patch("app.llm.groq_client.call_groq", new_callable=AsyncMock) as mock_groq:
            mock_groq.return_value = _mock_llm_response(payload)
            result = await run_planner(
                "What's on my calendar tomorrow?", now="2026-09-28T09:00:00+05:30"
            )

        assert "steps" in result
        assert isinstance(result["steps"], list)
        assert len(result["steps"]) == 1
        step = result["steps"][0]
        assert step["tool_name"] == "calendar.list_events"
        assert step["mcp_server"] == "calendar"
        assert "input_params" in step

    @pytest.mark.asyncio
    async def test_step_count_range_single_step(self):
        """PL-01: step_count_range [1,1] — one step expected."""
        payload = json.dumps(
            {
                "steps": [
                    {
                        "tool_name": "calendar.list_events",
                        "mcp_server": "calendar",
                        "input_params": {
                            "start": "2026-09-29T00:00:00+05:30",
                            "end": "2026-09-29T23:59:59+05:30",
                        },
                    }
                ]
            }
        )
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
            "step_count_range": [1, 1],
            "meta": {"id": "PL-01"},
        }

        with patch("app.llm.groq_client.call_groq", new_callable=AsyncMock) as mock_groq:
            mock_groq.return_value = _mock_llm_response(payload)
            actual = await run_planner(
                "What's on my calendar tomorrow?", now="2026-09-28T09:00:00+05:30"
            )

        grade = grade_planner(actual, expected)
        assert grade.valid_plan is True
        assert grade.checks["step_count"] is True

    @pytest.mark.asyncio
    async def test_correct_mcp_server_per_step(self):
        """Each step must use the correct mcp_server (calendar for calendar tools)."""
        payload = json.dumps(
            {
                "steps": [
                    {
                        "tool_name": "gmail.send_message",
                        "mcp_server": "gmail",  # correct server for gmail tool
                        "input_params": {
                            "to": ["test@example.com"],
                            "subject": "Hello",
                            "body": "Hi",
                        },
                    }
                ]
            }
        )
        expected = {
            "steps": [
                {
                    "tool_name": "gmail.send_message",
                    "mcp_server": "gmail",
                    "input_params": {"to": ["test@example.com"], "subject": "Hello", "body": "Hi"},
                }
            ],
            "step_count_range": [1, 1],
            "meta": {"id": "X", "free_text_fields": ["subject", "body"]},
        }

        with patch("app.llm.groq_client.call_groq", new_callable=AsyncMock) as mock_groq:
            mock_groq.return_value = _mock_llm_response(payload)
            actual = await run_planner("Email test@example.com", now="2026-09-28T09:00:00+05:30")

        grade = grade_planner(actual, expected)
        assert grade.valid_plan is True
        assert grade.checks.get("ordered_subsequence") is True

    @pytest.mark.asyncio
    async def test_parse_error_returned_on_invalid_json(self):
        """If model returns garbage, run_planner returns parse_error."""
        with patch("app.llm.groq_client.call_groq", new_callable=AsyncMock) as mock_groq:
            mock_groq.return_value = _mock_llm_response("not json at all")
            result = await run_planner("What's on my calendar?", now="2026-09-28T09:00:00+05:30")

        assert result.get("parse_error") is True
        assert result["steps"] == []

    @pytest.mark.asyncio
    async def test_markdown_fences_stripped(self):
        """Model wraps JSON in ```json ... ``` — should still parse."""
        payload = (
            "```json\n"
            + json.dumps(
                {
                    "steps": [
                        {
                            "tool_name": "calendar.list_events",
                            "mcp_server": "calendar",
                            "input_params": {},
                        }
                    ]
                }
            )
            + "\n```"
        )

        with patch("app.llm.groq_client.call_groq", new_callable=AsyncMock) as mock_groq:
            mock_groq.return_value = _mock_llm_response(payload)
            result = await run_planner("What's on my calendar?")

        assert "steps" in result
        assert result.get("parse_error") is None

    @pytest.mark.asyncio
    async def test_unsupported_output_returned(self):
        """Model indicates request is out of scope."""
        payload = json.dumps({"steps": [], "unsupported": True, "reason": "no_matching_tool"})

        with patch("app.llm.groq_client.call_groq", new_callable=AsyncMock) as mock_groq:
            mock_groq.return_value = _mock_llm_response(payload)
            result = await run_planner("Merge PR 17")

        assert result["steps"] == []
        assert result.get("unsupported") is True

    @pytest.mark.asyncio
    async def test_needs_clarification_output_returned(self):
        """Model indicates essential info is missing."""
        payload = json.dumps({"steps": [], "needs_clarification": True, "missing": ["to"]})

        with patch("app.llm.groq_client.call_groq", new_callable=AsyncMock) as mock_groq:
            mock_groq.return_value = _mock_llm_response(payload)
            result = await run_planner("Email my professor that I will miss class")

        assert result["steps"] == []
        assert result.get("needs_clarification") is True
        assert "to" in result.get("missing", [])

    @pytest.mark.asyncio
    async def test_temperature_zero_passed_to_groq(self):
        """run_planner must call the LLM at temperature=0."""
        payload = json.dumps({"steps": []})

        with patch("app.llm.groq_client.call_groq", new_callable=AsyncMock) as mock_groq:
            mock_groq.return_value = _mock_llm_response(payload)
            await run_planner("Test", now="2026-09-28T09:00:00+05:30")

        call_kwargs = mock_groq.call_args
        assert call_kwargs.kwargs.get("temperature") == 0

    def test_prompt_version_constant_is_string(self):
        """PROMPT_VERSION must be a non-empty string."""
        assert isinstance(PROMPT_VERSION, str)
        assert len(PROMPT_VERSION) > 0
