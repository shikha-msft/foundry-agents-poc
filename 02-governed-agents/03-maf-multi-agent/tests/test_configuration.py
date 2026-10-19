from __future__ import annotations

import pytest

from app.configuration import Settings


def test_settings_load_governed_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "PROJECT_ENDPOINT",
        "https://example.services.ai.azure.com/api/projects/example-project",
    )
    monkeypatch.setenv("AZURE_TENANT_ID", "tenant")
    monkeypatch.setenv("MODEL_DEPLOYMENT_NAME", "gpt-5.4-mini")
    monkeypatch.setenv("PROMPT_AGENT_NAME", "prompt")
    monkeypatch.setenv("RAG_AGENT_NAME", "rag")
    monkeypatch.setenv("REQUIRE_APP_SERVICE_AUTH", "true")

    settings = Settings.from_environment()

    assert settings.max_round_count == 6
    assert settings.max_stall_count == 2
    assert settings.require_app_service_auth is True
    assert settings.agent365_enabled is False


def test_round_limit_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAF_MAX_ROUND_COUNT", "20")

    with pytest.raises(ValueError, match="between 1 and 12"):
        Settings.from_environment()


def test_agent365_requires_registered_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT365_ENABLED", "true")
    monkeypatch.delenv("A365_BLUEPRINT_CLIENT_ID", raising=False)
    monkeypatch.delenv("A365_AGENT_CLIENT_ID", raising=False)

    with pytest.raises(ValueError, match="A365_BLUEPRINT_CLIENT_ID"):
        Settings.from_environment()
