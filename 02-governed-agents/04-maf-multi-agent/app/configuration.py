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
    agent365_enabled: bool
    agent365_agent_name: str | None
    agent365_auth_mode: str
    agent365_blueprint_client_id: str | None
    agent365_agent_client_id: str | None
    agent365_bootstrap_client_id: str | None
    agent365_exporter_enabled: bool
    agent365_use_s2s_endpoint: bool
    agent365_suppress_invoke_agent_input: bool

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
            agent365_enabled=_boolean("AGENT365_ENABLED", False),
            agent365_agent_name=_optional("AGENT365_MAF_AGENT_NAME"),
            agent365_auth_mode=os.getenv("AGENT365_AUTH_MODE", "s2s").strip().lower(),
            agent365_blueprint_client_id=_optional("A365_BLUEPRINT_CLIENT_ID"),
            agent365_agent_client_id=_optional("A365_AGENT_CLIENT_ID"),
            agent365_bootstrap_client_id=_optional("A365_BOOTSTRAP_CLIENT_ID"),
            agent365_exporter_enabled=_boolean(
                "ENABLE_A365_OBSERVABILITY_EXPORTER",
                True,
            ),
            agent365_use_s2s_endpoint=_boolean("A365_USE_S2S_ENDPOINT", True),
            agent365_suppress_invoke_agent_input=_boolean(
                "A365_SUPPRESS_INVOKE_AGENT_INPUT",
                True,
            ),
        )
        if not settings.project_endpoint.startswith("https://"):
            raise ValueError("PROJECT_ENDPOINT must be an HTTPS URL.")
        if "/api/projects/" not in settings.project_endpoint:
            raise ValueError("PROJECT_ENDPOINT must identify a Microsoft Foundry project.")
        if settings.agent365_auth_mode != "s2s":
            raise ValueError("AGENT365_AUTH_MODE must be s2s for the MAF orchestrator.")
        if settings.agent365_enabled:
            required_agent365 = {
                "AGENT365_MAF_AGENT_NAME": settings.agent365_agent_name,
                "A365_BLUEPRINT_CLIENT_ID": settings.agent365_blueprint_client_id,
                "A365_AGENT_CLIENT_ID": settings.agent365_agent_client_id,
            }
            missing = [name for name, value in required_agent365.items() if not value]
            if missing:
                raise ValueError(
                    f"Agent 365 is enabled but these settings are missing: {', '.join(missing)}."
                )
            if not settings.agent365_exporter_enabled:
                raise ValueError(
                    "ENABLE_A365_OBSERVABILITY_EXPORTER must be true when Agent 365 is enabled."
                )
            if not settings.agent365_use_s2s_endpoint:
                raise ValueError(
                    "A365_USE_S2S_ENDPOINT must be true for Agent 365 S2S authentication."
                )
        return settings


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required.")
    return value


def _optional(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


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
