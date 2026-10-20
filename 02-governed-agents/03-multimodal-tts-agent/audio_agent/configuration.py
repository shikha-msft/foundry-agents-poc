from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    tenant_id: str
    endpoint: str
    tts_deployment: str
    stt_deployment: str
    timeout_seconds: int
    max_upload_bytes: int
    max_synthesis_bytes: int
    require_app_service_auth: bool

    @classmethod
    def from_environment(cls) -> Settings:
        load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
        endpoint = _required("FOUNDRY_AUDIO_ENDPOINT").rstrip("/") + "/"
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path != "/openai/v1/"
        ):
            raise ValueError("FOUNDRY_AUDIO_ENDPOINT must be an HTTPS /openai/v1/ base URL.")
        auth = os.getenv("REQUIRE_APP_SERVICE_AUTH", "false").strip().lower()
        if auth not in {"true", "false"}:
            raise ValueError("REQUIRE_APP_SERVICE_AUTH must be true or false.")
        return cls(
            tenant_id=_required("AZURE_TENANT_ID"),
            endpoint=endpoint,
            tts_deployment=_required("TTS_MODEL_DEPLOYMENT_NAME"),
            stt_deployment=_required("STT_MODEL_DEPLOYMENT_NAME"),
            timeout_seconds=_integer("AUDIO_TIMEOUT_SECONDS", 60, 1, 300),
            max_upload_bytes=_integer("MAX_AUDIO_UPLOAD_BYTES", 24_000_000, 1, 24_000_000),
            max_synthesis_bytes=_integer("MAX_SYNTHESIS_BYTES", 32_000_000, 1, 32_000_000),
            require_app_service_auth=auth == "true",
        )


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value or value.startswith("<"):
        raise ValueError(f"{name} must contain a configured value, not a placeholder.")
    return value


def _integer(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as error:
        raise ValueError(f"{name} must be an integer.") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return value
