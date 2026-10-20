from __future__ import annotations

import os
from typing import Literal

from azure.core.credentials import TokenCredential
from azure.identity import (
    AzureCliCredential,
    ManagedIdentityCredential,
    WorkloadIdentityCredential,
    get_bearer_token_provider,
)
from openai import OpenAI

from .configuration import Settings

AudioFormat = Literal["wav", "mp3"]
Voice = Literal["alloy", "echo", "fable", "onyx", "nova", "shimmer"]


class AudioResponseError(RuntimeError):
    """The provider returned empty or oversized content."""


def has_audio_header(audio: bytes | bytearray, audio_format: AudioFormat) -> bool:
    if audio_format == "wav":
        return len(audio) >= 12 and audio[:4] == b"RIFF" and audio[8:12] == b"WAVE"
    return audio[:3] == b"ID3" or (len(audio) >= 2 and audio[0] == 255 and audio[1] & 224 == 224)


def build_credential(
    settings: Settings,
) -> AzureCliCredential | ManagedIdentityCredential | WorkloadIdentityCredential:
    client_id = os.getenv("AZURE_CLIENT_ID") or None
    if os.getenv("AZURE_FEDERATED_TOKEN_FILE"):
        if not client_id:
            raise ValueError("AZURE_CLIENT_ID is required for workload identity.")
        return WorkloadIdentityCredential(tenant_id=settings.tenant_id, client_id=client_id)
    if os.getenv("IDENTITY_ENDPOINT") or os.getenv("MSI_ENDPOINT"):
        return ManagedIdentityCredential(client_id=client_id)
    return AzureCliCredential(
        tenant_id=settings.tenant_id,
        process_timeout=int(os.getenv("AZURE_CLI_PROCESS_TIMEOUT", "60")),
    )


class AudioService:
    def __init__(self, settings: Settings, client: OpenAI) -> None:
        self._settings = settings
        self._client = client

    def synthesize(self, text: str, voice: Voice, audio_format: AudioFormat) -> bytes:
        chunks: list[bytes] = []
        size = 0
        with self._client.audio.speech.with_streaming_response.create(
            model=self._settings.tts_deployment,
            input=text,
            voice=voice,
            response_format=audio_format,
        ) as response:
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > self._settings.max_synthesis_bytes:
                    raise AudioResponseError("Synthesis exceeded the configured output limit.")
                chunks.append(chunk)
        if not size:
            raise AudioResponseError("Synthesis returned no audio.")
        audio = b"".join(chunks)
        if not has_audio_header(audio, audio_format):
            raise AudioResponseError("Synthesis returned an unexpected audio format.")
        return audio

    def transcribe(self, audio: bytes, audio_format: AudioFormat, language: str | None) -> str:
        content_type = "audio/wav" if audio_format == "wav" else "audio/mpeg"
        result = self._client.audio.transcriptions.create(
            model=self._settings.stt_deployment,
            file=(f"input.{audio_format}", audio, content_type),
            response_format="json",
            **({"language": language} if language else {}),
        )
        if not isinstance(result.text, str) or not result.text.strip():
            raise AudioResponseError("Transcription returned no text.")
        return result.text

    def close(self) -> None:
        self._client.close()


def create_service(settings: Settings, credential: TokenCredential) -> AudioService:
    token = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")
    return AudioService(
        settings,
        OpenAI(
            base_url=settings.endpoint,
            api_key=token,
            timeout=settings.timeout_seconds,
            max_retries=0,
        ),
    )
