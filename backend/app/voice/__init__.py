"""Voice input and Speech-to-Text (STT) package for AgentOps Copilot.

Owner: Jigyasu (D20 Voice Pipeline)
"""

from .audio_utils import temporary_audio_file, validate_audio_upload
from .stt_provider import STTProvider, STTResult, get_stt_provider

__all__ = [
    "STTProvider",
    "STTResult",
    "get_stt_provider",
    "temporary_audio_file",
    "validate_audio_upload",
]
