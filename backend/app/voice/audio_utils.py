"""Audio validation and temporary storage utilities for AgentOps voice pipeline.

Owner: Jigyasu (D20 Voice Pipeline)

Enforces:
- Extension & MIME type whitelist suitable for mobile & desktop audio
- File size bounds (default 25 MB max, non-empty)
- Deterministic cleanup of temporary audio files after transcription
- Safe duration extraction without crashing on unknown formats
"""

from __future__ import annotations

import contextlib
import logging
import os
import tempfile
from typing import AsyncIterator, Tuple

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings

logger = logging.getLogger(__name__)

# Permitted audio extensions and their normalized canonical extension
ALLOWED_AUDIO_EXTENSIONS: dict[str, str] = {
    ".wav": ".wav",
    ".mp3": ".mp3",
    ".m4a": ".m4a",
    ".aac": ".m4a",
    ".ogg": ".ogg",
    ".opus": ".ogg",
    ".webm": ".webm",
    ".flac": ".flac",
    ".mp4": ".m4a",
}

# Permitted MIME types
ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {
        "audio/wav",
        "audio/x-wav",
        "audio/wave",
        "audio/vnd.wave",
        "audio/mpeg",
        "audio/mp3",
        "audio/mp4",
        "audio/x-m4a",
        "audio/m4a",
        "audio/aac",
        "audio/ogg",
        "audio/opus",
        "audio/webm",
        "audio/flac",
        "audio/x-flac",
        "application/octet-stream",  # often sent by generic mobile clients
    }
)


def get_audio_extension(filename: str | None, content_type: str | None) -> str:
    """Determine the file extension from filename or content type."""
    if filename:
        _, ext = os.path.splitext(filename)
        ext_lower = ext.lower()
        if ext_lower in ALLOWED_AUDIO_EXTENSIONS:
            return ALLOWED_AUDIO_EXTENSIONS[ext_lower]

    if content_type:
        mime_clean = content_type.split(";")[0].strip().lower()
        if "wav" in mime_clean:
            return ".wav"
        if "mp3" in mime_clean or "mpeg" in mime_clean:
            return ".mp3"
        if "m4a" in mime_clean or "aac" in mime_clean or "mp4" in mime_clean:
            return ".m4a"
        if "ogg" in mime_clean or "opus" in mime_clean:
            return ".ogg"
        if "webm" in mime_clean:
            return ".webm"
        if "flac" in mime_clean:
            return ".flac"

    return ""


def validate_audio_metadata(filename: str | None, content_type: str | None) -> str:
    """Validate audio filename / MIME type and return canonical extension.

    Raises:
        HTTPException(400): If the format is not recognized or supported.
    """
    ext = get_audio_extension(filename, content_type)
    if not ext:
        logger.warning(
            "Rejected audio upload with unsupported format [filename=%r, content_type=%r]",
            filename,
            content_type,
        )
        supported = ", ".join(sorted(ALLOWED_AUDIO_EXTENSIONS.keys()))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported audio format. Supported audio formats: {supported}",
        )
    return ext


def get_audio_duration_seconds(file_path: str) -> float | None:
    """Attempt to calculate audio duration in seconds safely using pyav or wave."""
    try:
        import av

        with av.open(file_path) as container:
            if container.duration is not None:
                return float(container.duration) / float(av.time_base)
            # Alternatively look at the first audio stream
            if container.streams.audio:
                stream = container.streams.audio[0]
                if stream.duration is not None and stream.time_base is not None:
                    return float(stream.duration * stream.time_base)
    except Exception as exc:
        logger.debug("av duration inspection failed for %s: %s", file_path, exc)

    # Fallback to wave for wav files
    if file_path.lower().endswith(".wav"):
        try:
            import wave

            with wave.open(file_path, "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0:
                    return float(frames) / float(rate)
        except Exception:
            pass

    return None


def normalize_language_code(language: str | None) -> str | None:
    """Normalize input language string to ISO 639-1 code suitable for Whisper.

    Examples:
        'en-US' -> 'en'
        'hi-IN' -> 'hi'
        'en-US (Auto-detect)' -> None
        'auto' -> None
        '' -> None
    """
    if not language:
        return None
    cleaned = language.strip().lower()
    if cleaned in ("auto", "auto-detect", "none", "null") or "auto" in cleaned:
        return None
    if cleaned.startswith("en"):
        return "en"
    if cleaned.startswith("hi"):
        return "hi"
    # Return 2-letter prefix if available
    parts = cleaned.split("-")[0].split("_")[0]
    return parts if len(parts) == 2 else None


@contextlib.asynccontextmanager
async def temporary_audio_file(
    file: UploadFile,
    max_size_bytes: int | None = None,
) -> AsyncIterator[Tuple[str, int, str]]:
    """Save an UploadFile to a temporary file on disk with safe bounds & guaranteed cleanup.

    Yields:
        Tuple of (temp_file_path, file_size_bytes, extension)

    Raises:
        HTTPException(400): If file is empty or corrupted.
        HTTPException(413): If file exceeds max_size_bytes.
    """
    limit = max_size_bytes or settings.STT_MAX_AUDIO_SIZE_BYTES
    ext = validate_audio_metadata(file.filename, file.content_type)

    temp_fd, temp_path = tempfile.mkstemp(suffix=ext, prefix="agentops_voice_")
    bytes_written = 0

    try:
        with os.fdopen(temp_fd, "wb") as temp_file:
            chunk_size = 64 * 1024  # 64 KB chunks
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > limit:
                    max_mb = limit // (1024 * 1024)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Audio file exceeds maximum permitted size of {max_mb} MB.",
                    )
                temp_file.write(chunk)

        if bytes_written == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded audio file is empty (0 bytes).",
            )

        yield temp_path, bytes_written, ext


    finally:
        # Guarantee removal of the temporary file from disk
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                logger.debug("Cleaned up temporary audio file: %s", temp_path)
            except OSError as err:
                logger.warning("Failed to remove temporary audio file %s: %s", temp_path, err)


def validate_audio_upload(file: UploadFile) -> None:
    """Fast pre-validation of UploadFile presence and headers."""
    if not file or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No audio file provided in upload request.",
        )
