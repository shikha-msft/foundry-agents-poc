from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    project_endpoint: str
    tenant_id: str
    model_deployment_name: str
    prompt_agent_name: str
    rag_agent_name: str
    max_round_count: int
    max_stall_count: int
    workflow_timeout_seconds: int
    require_app_service_auth: bool

    @classmethod
    def from_environment(cls) -> Settings:
        load_dotenv(_ROOT / ".env", override=False)
        settings = cls(
            project_endpoint=_required("PROJECT_ENDPOINT").rstrip("/"),
            tenant_id=_required("AZURE_TENANT_ID"),
            model_deployment_name=_required("MODEL_DEPLOYMENT_NAME"),
            prompt_agent_name=_required("PROMPT_AGENT_NAME"),
            rag_agent_name=_required("RAG_AGENT_NAME"),
            max_round_count=_integer("MAF_MAX_ROUND_COUNT", 6, 1, 12),
            max_stall_count=_integer("MAF_MAX_STALL_COUNT", 2, 1, 6),
            workflow_timeout_seconds=_integer(
                "MAF_WORKFLOW_TIMEOUT_SECONDS",
                120,
                10,
                600,
            ),
            require_app_service_auth=_boolean("REQUIRE_APP_SERVICE_AUTH", True),
        )
        if not settings.project_endpoint.startswith("https://"):
            raise ValueError("PROJECT_ENDPOINT must be an HTTPS URL.")
        if "/api/projects/" not in settings.project_endpoint:
            raise ValueError("PROJECT_ENDPOINT must identify a Microsoft Foundry project.")
        return settings


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required.")
    return value


def _integer(name: str, default: int, minimum: int, maximum: int) -> int:
    text = os.getenv(name, str(default))
    try:
        value = int(text)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer.") from error
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return value


def _boolean(name: str, default: bool) -> bool:
    text = os.getenv(name, str(default)).strip().lower()
    if text in {"1", "true", "yes"}:
        return True
    if text in {"0", "false", "no"}:
        return False
    raise ValueError(f"{name} must be true or false.")
