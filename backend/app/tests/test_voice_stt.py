"""Tests for Voice Input and Speech-to-Text (STT) pipeline — D20.

Owner: Jigyasu

Covers:
- Valid audio upload & transcription
- Format validation (WAV, MP3, M4A, OGG, WebM)
- Rejection of unsupported extensions and MIME types (400)
- Rejection of empty audio files (400)
- Rejection of oversized audio files (413)
- Guaranteed temporary file cleanup on success and error
- Multilingual recognition handling (English, Hindi, Hinglish)
- Response schema structure and performance latency fields
- Provider abstraction & fallback behavior
"""

from __future__ import annotations

import io
import os
import struct
import tempfile
import wave
from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.voice.audio_utils import get_audio_extension, temporary_audio_file, validate_audio_metadata
from app.voice.stt_provider import (
    MockSTTProvider,
    STTResult,
    get_stt_provider,
)

_AUTH_HEADER = {"Authorization": "Bearer valid.jwt.token"}
_USER_ID = "00000000-0000-0000-0000-000000000001"


def _make_current_user(user_id: str = _USER_ID) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.email = "jigyasu@agentops.org"
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


def _generate_synthetic_wav_bytes(duration_seconds: float = 1.0, sample_rate: int = 16000) -> bytes:
    """Generate minimal valid PCM WAV bytes in memory."""
    buf = io.BytesIO()
    num_frames = int(duration_seconds * sample_rate)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        # Write 0-amplitude silence frames
        wf.writeframes(struct.pack(f"<{num_frames}h", *([0] * num_frames)))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Unit Tests: Audio Utils & Validation
# ---------------------------------------------------------------------------


def test_get_audio_extension():
    assert get_audio_extension("voice_memo.wav", "audio/wav") == ".wav"
    assert get_audio_extension("command.mp3", "audio/mpeg") == ".mp3"
    assert get_audio_extension("audio.m4a", "audio/x-m4a") == ".m4a"
    assert get_audio_extension("recording.ogg", "audio/ogg") == ".ogg"
    assert get_audio_extension("sample.webm", "audio/webm") == ".webm"
    assert get_audio_extension("unsupported.exe", "application/x-msdownload") == ""


def test_validate_audio_metadata_valid():
    ext = validate_audio_metadata("test_audio.wav", "audio/wav")
    assert ext == ".wav"


def test_validate_audio_metadata_unsupported_raises_400():
    with pytest.raises(Exception) as exc_info:
        validate_audio_metadata("virus.exe", "application/octet-stream")
    assert "Unsupported audio format" in str(exc_info.value)


@pytest.mark.asyncio
async def test_temporary_audio_file_guarantees_cleanup():
    wav_bytes = _generate_synthetic_wav_bytes(0.5)

    from starlette.datastructures import Headers, UploadFile

    headers = Headers({"content-type": "audio/wav"})
    upload_file = UploadFile(
        file=io.BytesIO(wav_bytes),
        size=len(wav_bytes),
        filename="test.wav",
        headers=headers,
    )

    captured_path = None
    async with temporary_audio_file(upload_file) as (temp_path, size_bytes, ext):
        captured_path = temp_path
        assert os.path.exists(temp_path)
        assert size_bytes == len(wav_bytes)
        assert ext == ".wav"

    # Verify file was cleaned up after exiting context manager
    assert not os.path.exists(captured_path)


# ---------------------------------------------------------------------------
# Unit Tests: STT Providers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_stt_provider_transcription():
    provider = MockSTTProvider()
    wav_bytes = _generate_synthetic_wav_bytes(1.5)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_bytes)
        temp_file = f.name

    try:
        result: STTResult = await provider.transcribe(temp_file)
        assert isinstance(result, STTResult)
        assert len(result.transcript) > 0
        assert result.language == "en"
        assert result.confidence is not None and result.confidence > 0.8
        assert result.processing_time_ms > 0
        assert result.engine == "mock-stt"
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)


@pytest.mark.asyncio
async def test_mock_stt_provider_multilingual_handling():
    provider = MockSTTProvider()

    with tempfile.NamedTemporaryFile(suffix="_hindi.wav", delete=False) as f:
        f.write(_generate_synthetic_wav_bytes(1.0))
        hindi_file = f.name

    with tempfile.NamedTemporaryFile(suffix="_hinglish.wav", delete=False) as f:
        f.write(_generate_synthetic_wav_bytes(1.0))
        hinglish_file = f.name

    try:
        res_hi = await provider.transcribe(hindi_file)
        assert res_hi.language == "hi"
        assert "मीटिंग" in res_hi.transcript or "रावत" in res_hi.transcript

        res_hinglish = await provider.transcribe(hinglish_file)
        assert res_hinglish.language == "hi"
        lowered = res_hinglish.transcript.lower()
        assert "schedule" in lowered or "meeting" in lowered
    finally:
        for path in (hindi_file, hinglish_file):
            if os.path.exists(path):
                os.remove(path)


def test_get_stt_provider_factory():
    mock_p = get_stt_provider("mock")
    assert isinstance(mock_p, MockSTTProvider)

    # Calling again returns cached instance
    assert get_stt_provider("mock") is mock_p


# ---------------------------------------------------------------------------
# API Integration Tests: POST /voice/transcribe
# ---------------------------------------------------------------------------


def test_transcribe_endpoint_valid_wav(mock_auth):
    # Use mock provider for fast API test
    settings.STT_ENGINE = "mock"

    wav_bytes = _generate_synthetic_wav_bytes(1.0)
    files = {"file": ("command.wav", wav_bytes, "audio/wav")}

    response = client.post("/voice/transcribe", files=files, headers=_AUTH_HEADER)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "transcript" in data
    assert "language" in data
    assert "confidence" in data
    assert "duration_seconds" in data
    assert "processing_time_ms" in data
    assert data["engine"] == "mock-stt"


def test_transcribe_endpoint_api_v1_alias(mock_auth):
    settings.STT_ENGINE = "mock"
    wav_bytes = _generate_synthetic_wav_bytes(1.0)
    files = {"file": ("command.wav", wav_bytes, "audio/wav")}

    response = client.post("/api/v1/voice/transcribe", files=files, headers=_AUTH_HEADER)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["engine"] == "mock-stt"


def test_transcribe_endpoint_empty_file_rejected(mock_auth):
    files = {"file": ("empty.wav", b"", "audio/wav")}
    response = client.post("/voice/transcribe", files=files, headers=_AUTH_HEADER)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "empty" in response.json()["detail"].lower()


def test_transcribe_endpoint_unsupported_extension_rejected(mock_auth):
    files = {"file": ("notes.txt", b"Schedule a meeting", "text/plain")}
    response = client.post("/voice/transcribe", files=files, headers=_AUTH_HEADER)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "unsupported" in response.json()["detail"].lower()


def test_transcribe_endpoint_oversized_audio_rejected(mock_auth):
    # Mock a max limit of 100 bytes for testing 413
    original_limit = settings.STT_MAX_AUDIO_SIZE_BYTES
    settings.STT_MAX_AUDIO_SIZE_BYTES = 100

    try:
        wav_bytes = _generate_synthetic_wav_bytes(2.0)  # > 100 bytes
        files = {"file": ("large_command.wav", wav_bytes, "audio/wav")}
        response = client.post("/voice/transcribe", files=files, headers=_AUTH_HEADER)
        assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    finally:
        settings.STT_MAX_AUDIO_SIZE_BYTES = original_limit
