"""Speech-to-Text (STT) Provider abstraction and implementations.

Owner: Jigyasu (D20 Voice Pipeline)

Architecture:
- Abstract `STTProvider` interface enabling zero-downtime engine substitution.
- `FasterWhisperProvider`: Local high-efficiency Whisper implementation using
  CTranslate2. Supports CPU int8 quantization, lazy singleton loading, language
  auto-detection (English, Hindi, Hinglish), and genuine confidence calculation.
- `CloudFallbackSTTProvider`: Cloud-hosted fallback utilizing Gemini multimodal
  or Groq audio API when local compute is constrained.
- `MockSTTProvider`: Predictable, fast mock provider for CI/CD and offline testing.
"""

from __future__ import annotations

import abc
import asyncio
import logging
import math
import os
import time
from typing import Optional

from pydantic import BaseModel, Field

from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output Schema
# ---------------------------------------------------------------------------


class STTResult(BaseModel):
    """Normalized Speech-to-Text transcription result."""

    transcript: str = Field(..., description="Recognized speech text.")
    language: Optional[str] = Field(
        None, description="Detected or specified ISO language code (e.g., 'en', 'hi')."
    )
    confidence: Optional[float] = Field(
        None, description="Average confidence score [0.0 - 1.0] if provided by engine, else null."
    )
    duration_seconds: Optional[float] = Field(None, description="Total audio duration in seconds.")
    processing_time_ms: int = Field(
        ..., description="Wall-clock transcription latency in milliseconds."
    )
    engine: str = Field(
        ..., description="Name of the STT engine that performed the transcription."
    )


# ---------------------------------------------------------------------------
# Abstract Base Class
# ---------------------------------------------------------------------------


class STTProvider(abc.ABC):
    """Abstract interface for STT providers."""

    @abc.abstractmethod
    async def transcribe(
        self,
        audio_path: str,
        language: str | None = None,
    ) -> STTResult:
        """Transcribe an audio file into text.

        Args:
            audio_path: Absolute path to the normalized audio file on disk.
            language: Optional language hint (e.g. 'en', 'hi'). If None, auto-detected.

        Returns:
            STTResult containing transcript, confidence, language, and performance metrics.
        """
        pass


# ---------------------------------------------------------------------------
# Faster-Whisper Provider (Local CTranslate2)
# ---------------------------------------------------------------------------


class FasterWhisperProvider(STTProvider):
    """High-performance local Whisper provider powered by faster-whisper (CTranslate2)."""

    _model = None
    _lock = asyncio.Lock()

    def __init__(
        self,
        model_size: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
    ):
        self.model_size = model_size or getattr(settings, "STT_MODEL_SIZE", "base")
        self.device = device or getattr(settings, "STT_DEVICE", "cpu")
        self.compute_type = compute_type or getattr(settings, "STT_COMPUTE_TYPE", "int8")

    def _get_model(self):
        """Lazy load model singleton."""
        if FasterWhisperProvider._model is None:
            logger.info(
                "Loading faster-whisper model [size=%s, device=%s, compute_type=%s]...",
                self.model_size,
                self.device,
                self.compute_type,
            )
            from faster_whisper import WhisperModel

            FasterWhisperProvider._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                download_root=None,
            )
            logger.info("faster-whisper model loaded successfully.")
        return FasterWhisperProvider._model

    def _run_transcription_sync(
        self,
        audio_path: str,
        language: str | None = None,
    ) -> STTResult:
        """Synchronous worker running inside thread pool to prevent blocking event loop."""
        from .audio_utils import get_audio_duration_seconds

        t0 = time.monotonic()
        model = self._get_model()

        # Execute transcription
        # beam_size=5 for quality, vad_filter=True to suppress non-speech silence
        segments, info = model.transcribe(
            audio_path,
            language=language,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )

        segment_texts: list[str] = []
        log_probs: list[float] = []

        for seg in segments:
            text = seg.text.strip()
            if text:
                segment_texts.append(text)
            if hasattr(seg, "avg_logprob") and seg.avg_logprob is not None:
                log_probs.append(seg.avg_logprob)

        full_transcript = " ".join(segment_texts).strip()
        latency_ms = int((time.monotonic() - t0) * 1000)

        # Genuine confidence score calculated from average log probabilities
        confidence: float | None = None
        if log_probs:
            mean_log_prob = sum(log_probs) / len(log_probs)
            # Probability = exp(log_prob)
            try:
                prob = math.exp(mean_log_prob)
                confidence = round(min(1.0, max(0.0, prob)), 2)
            except OverflowError:
                confidence = None

        detected_lang = info.language if hasattr(info, "language") else language
        duration = getattr(info, "duration", None)
        if duration is None:
            duration = get_audio_duration_seconds(audio_path)
        if duration is not None:
            duration = round(float(duration), 2)

        return STTResult(
            transcript=full_transcript,
            language=detected_lang,
            confidence=confidence,
            duration_seconds=duration,
            processing_time_ms=latency_ms,
            engine=f"faster-whisper-{self.model_size}",
        )

    async def transcribe(
        self,
        audio_path: str,
        language: str | None = None,
    ) -> STTResult:
        try:
            # Offload synchronous CTranslate2 C++ inference to worker thread
            return await asyncio.to_thread(self._run_transcription_sync, audio_path, language)
        except Exception as e:
            logger.warning(
                "FasterWhisperProvider failed (%s); attempting Cloud fallback transcription...",
                e,
                exc_info=True,
            )
            gemini_key = getattr(settings, "GEMINI_API_KEY", "")
            if gemini_key:
                try:
                    fallback = CloudFallbackSTTProvider()
                    return await fallback.transcribe(audio_path, language)
                except Exception as fallback_err:
                    logger.error("Cloud fallback transcription also failed: %s", fallback_err)
            raise


# ---------------------------------------------------------------------------
# Cloud Fallback Provider (Gemini Audio Multimodal / Groq)
# ---------------------------------------------------------------------------


class CloudFallbackSTTProvider(STTProvider):
    """Cloud-hosted STT provider using configured Gemini or Groq multimodal APIs."""

    async def transcribe(
        self,
        audio_path: str,
        language: str | None = None,
    ) -> STTResult:
        from .audio_utils import get_audio_duration_seconds

        t0 = time.monotonic()
        gemini_api_key = getattr(settings, "GEMINI_API_KEY", "")

        if not gemini_api_key:
            raise RuntimeError("Cloud STT fallback requested but GEMINI_API_KEY is not configured.")

        from google import genai
        from google.genai import types

        client = genai.Client(api_key=gemini_api_key)

        prompt = (
            "Listen to this audio recording of a user voice command. "
            "Transcribe the EXACT spoken words accurately in their original language "
            "(English, Hindi, or Hinglish). Do NOT translate into another language. "
            "Output ONLY the plain transcript text with no markdown, quotes, or commentary."
        )

        with open(audio_path, "rb") as f:
            audio_bytes = f.read()

        mime_type = "audio/wav"
        if audio_path.endswith(".mp3"):
            mime_type = "audio/mp3"
        elif audio_path.endswith(".m4a"):
            mime_type = "audio/m4a"
        elif audio_path.endswith(".ogg"):
            mime_type = "audio/ogg"
        elif audio_path.endswith(".webm"):
            mime_type = "audio/webm"

        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                prompt,
            ],
        )

        transcript = (response.text or "").strip()
        latency_ms = int((time.monotonic() - t0) * 1000)
        duration = get_audio_duration_seconds(audio_path)

        return STTResult(
            transcript=transcript,
            language=language or "auto",
            confidence=None,  # Gemini doesn't produce token-level confidence score
            duration_seconds=round(duration, 2) if duration else None,
            processing_time_ms=latency_ms,
            engine="cloud-gemini-multimodal",
        )


# ---------------------------------------------------------------------------
# Mock Provider (Fast, Offline, Deterministic for Tests)
# ---------------------------------------------------------------------------


class MockSTTProvider(STTProvider):
    """Mock STT provider for offline test suites and simulated voice inputs."""

    def __init__(
        self,
        fixed_transcript: str = (
            "Schedule a team meeting with Professor Rawat on Thursday at 3 PM "
            "and email him the agenda"
        ),
    ):
        self.fixed_transcript = fixed_transcript

    async def transcribe(
        self,
        audio_path: str,
        language: str | None = None,
    ) -> STTResult:
        from .audio_utils import get_audio_duration_seconds

        t0 = time.monotonic()
        await asyncio.sleep(0.01)  # small non-zero async tick

        # Check if filename indicates a multilingual or specialized test case
        filename = os.path.basename(audio_path).lower()
        if "hindi" in filename:
            transcript = "गुरुवार को दोपहर 3 बजे प्रोफेसर रावत के साथ मीटिंग शेड्यूल करें"
            detected_lang = "hi"
        elif "hinglish" in filename:
            transcript = (
                "Thursday ko 3 PM par Professor Rawat ke saath meeting schedule karo "
                "aur agenda email kar do"
            )
            detected_lang = "hi"
        elif "email" in filename:
            transcript = "Email the weekly project status report to Ishani"
            detected_lang = "en"
        elif "empty" in filename:
            transcript = ""
            detected_lang = "en"
        else:
            transcript = self.fixed_transcript
            detected_lang = language or "en"

        duration = get_audio_duration_seconds(audio_path) or 3.5
        latency_ms = int((time.monotonic() - t0) * 1000) + 12

        return STTResult(
            transcript=transcript,
            language=detected_lang,
            confidence=0.94 if transcript else 0.0,
            duration_seconds=round(duration, 2),
            processing_time_ms=latency_ms,
            engine="mock-stt",
        )


# ---------------------------------------------------------------------------
# Factory Function
# ---------------------------------------------------------------------------

_provider_instances: dict[str, STTProvider] = {}


def get_stt_provider(engine_name: str | None = None) -> STTProvider:
    """Retrieve or instantiate the configured STT provider singleton.

    Args:
        engine_name: 'faster-whisper', 'cloud', or 'mock'. Defaults to settings.STT_ENGINE.
    """
    engine = (engine_name or getattr(settings, "STT_ENGINE", "faster-whisper")).lower().strip()

    if engine not in _provider_instances:
        if engine in ("mock", "test"):
            _provider_instances[engine] = MockSTTProvider()
        elif engine in ("cloud", "gemini"):
            _provider_instances[engine] = CloudFallbackSTTProvider()
        else:
            _provider_instances[engine] = FasterWhisperProvider()

    return _provider_instances[engine]
