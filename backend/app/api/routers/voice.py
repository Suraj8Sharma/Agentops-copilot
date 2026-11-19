"""Voice transcription router — D20.

Owner: Jigyasu

Endpoints
---------
POST /voice/transcribe (and /api/v1/voice/transcribe)
    Accepts an audio file upload via multipart/form-data, validates format and size,
    transcribes using the active STTProvider, removes temporary audio files,
    and returns a structured transcription result with timing metrics.
    Auth: JWT required.
"""

from __future__ import annotations

import logging
import time
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.core.security import CurrentUser, get_current_user
from app.voice.audio_utils import (
    normalize_language_code,
    temporary_audio_file,
    validate_audio_upload,
)
from app.voice.stt_provider import STTResult, get_stt_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


# ---------------------------------------------------------------------------
# Response Model
# ---------------------------------------------------------------------------


class TranscriptionResponse(BaseModel):
    """Response payload for audio transcription endpoint."""

    transcript: str = Field(..., description="Recognized speech text.")
    language: Optional[str] = Field(
        None, description="Detected or specified ISO language code."
    )
    confidence: Optional[float] = Field(
        None, description="Estimated transcription confidence [0.0 - 1.0], or null."
    )
    duration_seconds: Optional[float] = Field(None, description="Audio length in seconds.")
    processing_time_ms: int = Field(..., description="End-to-end processing latency in ms.")
    engine: str = Field(..., description="STT engine utilized.")


# ---------------------------------------------------------------------------
# POST /voice/transcribe
# ---------------------------------------------------------------------------


@router.post(
    "/transcribe",
    summary="Transcribe audio speech to text",
    description=(
        "Upload an audio recording (WAV, MP3, M4A, OGG, WebM, FLAC) from the mobile or web client. "
        "Returns the recognized transcript, detected language, and latency metrics."
    ),
    response_model=TranscriptionResponse,
    status_code=status.HTTP_200_OK,
)
async def transcribe_audio(
    file: Annotated[UploadFile, File(description="Recorded audio file (multipart/form-data)")],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    language: Annotated[
        Optional[str],
        Form(description="Optional ISO language hint ('en', 'hi')"),
    ] = None,
) -> TranscriptionResponse:
    """Accept multipart audio, validate, transcribe, and return clean transcript."""
    t_start = time.monotonic()
    validate_audio_upload(file)

    logger.info(
        "Voice transcription requested: user_id=%s filename=%r content_type=%r language_hint=%r",
        current_user.id,
        file.filename,
        file.content_type,
        language,
    )

    try:
        norm_lang = normalize_language_code(language)
        async with temporary_audio_file(file) as (temp_path, size_bytes, ext):
            provider = get_stt_provider()
            stt_result: STTResult = await provider.transcribe(
                audio_path=temp_path,
                language=norm_lang,
            )
    except HTTPException:
        # Re-raise known validation HTTPExceptions cleanly
        raise
    except Exception as exc:
        logger.error(
            "Transcription failed for user_id=%s filename=%r: %s",
            current_user.id,
            file.filename,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Speech transcription service encountered an unexpected error.",
        ) from exc

    total_latency_ms = int((time.monotonic() - t_start) * 1000)

    logger.info(
        "Voice transcription completed: user_id=%s engine=%s duration=%.2fs latency=%dms",
        current_user.id,
        stt_result.engine,
        stt_result.duration_seconds or 0.0,
        total_latency_ms,
    )

    # If transcription is empty, return empty transcript cleanly (user may edit or retry in UI)
    return TranscriptionResponse(
        transcript=stt_result.transcript,
        language=stt_result.language,
        confidence=stt_result.confidence,
        duration_seconds=stt_result.duration_seconds,
        processing_time_ms=total_latency_ms,
        engine=stt_result.engine,
    )
