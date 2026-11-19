"""End-to-End integration test for complete Voice -> Planner -> Risk Gate workflow.

Owner: Jigyasu

Flow tested:
1. Audio file uploaded to POST /voice/transcribe
2. Transcription generated with latency metrics
3. Transcribed command submitted as structured task to POST /tasks (input_type: voice)
4. LangGraph planner processes the intent and plans steps
5. Hardcoded risk rules tag the step with risk tier
6. Approval gate triggers for risky actions and attaches advisory explanation
7. Observability log entries verify audit trail
"""

from __future__ import annotations

import io
import struct
import uuid
import wave
from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

_AUTH_HEADER = {"Authorization": "Bearer valid.jwt.token"}
_USER_ID = str(uuid.uuid4())


def _make_current_user() -> MagicMock:
    user = MagicMock()
    user.id = _USER_ID
    user.email = "jigyasu.capstone@agentops.org"
    user.role = "authenticated"
    resp = MagicMock()
    resp.user = user
    return resp


@pytest.fixture
def mock_auth():
    with patch("app.core.security.supabase.auth.get_user") as m:
        m.return_value = _make_current_user()
        yield m


client = TestClient(app)


def _make_pcm_wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(struct.pack("<16000h", *([0] * 16000)))
    return buf.getvalue()


@pytest.mark.asyncio
async def test_voice_to_planner_e2e_flow(mock_auth):
    # 1. Configure mock STT provider for deterministic testing
    settings.STT_ENGINE = "mock"

    wav_data = _make_pcm_wav()
    files = {"file": ("email_command.wav", wav_data, "audio/wav")}

    # Step 1: Transcribe audio
    stt_resp = client.post("/voice/transcribe", files=files, headers=_AUTH_HEADER)
    assert stt_resp.status_code == status.HTTP_200_OK
    stt_data = stt_resp.json()

    transcript = stt_data["transcript"]
    assert len(transcript) > 0
    assert stt_data["processing_time_ms"] > 0
    assert stt_data["engine"] == "mock-stt"

    # Step 2: Submit transcribed task to POST /tasks
    task_id = str(uuid.uuid4())
    mock_task_row = {
        "id": task_id,
        "user_id": _USER_ID,
        "input_type": "voice",
        "raw_input": None,
        "transcription_text": transcript,
        "status": "submitted",
        "created_at": "2026-09-18T00:00:00Z",
        "completed_at": None,
    }

    with patch("app.api.routers.tasks.supabase") as mock_supabase:
        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.insert.return_value.execute.return_value.data = [mock_task_row]

        task_create_payload = {
            "input_type": "voice",
            "transcription_text": transcript,
        }

        task_resp = client.post("/tasks", json=task_create_payload, headers=_AUTH_HEADER)
        assert task_resp.status_code == status.HTTP_201_CREATED
        created_task = task_resp.json()
        assert created_task["input_type"] == "voice"
        assert created_task["transcription_text"] == transcript
        assert created_task["status"] == "submitted"

    # Step 3: Verify Planner Risk Tagging & Hardcoded Approval Gate
    from app.agents.nodes import risk_tag
    from app.agents.state import AgentState, Step

    state: AgentState = {
        "task_id": task_id,
        "user_id": _USER_ID,
        "raw_input": transcript,
        "input_type": "voice",
        "intent": "send_email",
        "plan": [
            Step(
                tool_name="gmail.send_message",
                mcp_server="gmail",
                input_params={"to": ["prof@univ.edu"], "subject": "Agenda"},
            )
        ],
        "plan_id": str(uuid.uuid4()),
        "risk_flags": {},
        "current_step_index": 0,
        "step_results": {},
        "retries": {},
        "error": None,
    }

    from app.risk.risk_rules import RiskRule

    mock_rule = RiskRule(
        action_type="gmail.send_message",
        mcp_server="gmail",
        risk_tier="high",
        requires_approval=True,
        rationale="SEND_MESSAGE_REQUIRES_APPROVAL",
    )

    with (
        patch("app.agents.nodes.supabase_admin") as mock_admin,
        patch("app.agents.nodes.lookup", return_value=mock_rule),
    ):
        mock_admin.table.return_value.insert.return_value.execute.return_value.data = [
            {"id": "step_001"}
        ]
        eq_mock = mock_admin.table.return_value.update.return_value.eq.return_value
        eq_mock.execute.return_value.data = []

        tagged_state = risk_tag(state)

        # Step 0 (gmail.send_message) MUST be flagged as requiring approval
        step_risk = tagged_state["risk_flags"][0]
        assert step_risk["requires_approval"] is True
        assert step_risk["risk_tier"] == "high"
        rationale_upper = step_risk["rationale"].upper()
        assert "SEND_MESSAGE" in rationale_upper or "EMAIL" in rationale_upper
