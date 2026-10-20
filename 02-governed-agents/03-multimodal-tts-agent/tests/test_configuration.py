from unittest.mock import Mock

import pytest

from audio_agent.configuration import Settings
from audio_agent.service import build_credential, create_service


def test_default_settings():
    settings = Settings.from_environment()
    assert settings.endpoint == "https://mock.openai.azure.com/openai/v1/"
    assert settings.max_upload_bytes == 24_000_000
    assert settings.require_app_service_auth is False


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("AZURE_TENANT_ID", ""),
        ("TTS_MODEL_DEPLOYMENT_NAME", "<deployment>"),
        ("STT_MODEL_DEPLOYMENT_NAME", ""),
        ("FOUNDRY_AUDIO_ENDPOINT", "http://mock/openai/v1/"),
        ("FOUNDRY_AUDIO_ENDPOINT", "https://mock/api/projects/project"),
        ("FOUNDRY_AUDIO_ENDPOINT", "https://user:secret@mock/openai/v1/"),
        ("FOUNDRY_AUDIO_ENDPOINT", "https://mock/openai/v1/?api-key=secret"),
        ("REQUIRE_APP_SERVICE_AUTH", "yes"),
        ("MAX_AUDIO_UPLOAD_BYTES", "24000001"),
        ("MAX_AUDIO_UPLOAD_BYTES", "0"),
        ("MAX_SYNTHESIS_BYTES", "abc"),
        ("AUDIO_TIMEOUT_SECONDS", "301"),
    ],
)
def test_invalid_settings(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        Settings.from_environment()


def test_credential_selection(monkeypatch):
    from audio_agent import service

    cli = Mock()
    managed = Mock()
    workload = Mock()
    monkeypatch.setattr(service, "AzureCliCredential", cli)
    monkeypatch.setattr(service, "ManagedIdentityCredential", managed)
    monkeypatch.setattr(service, "WorkloadIdentityCredential", workload)
    settings = Settings.from_environment()
    assert build_credential(settings) is cli.return_value
    monkeypatch.setenv("IDENTITY_ENDPOINT", "http://managed-identity")
    assert build_credential(settings) is managed.return_value
    monkeypatch.setenv("AZURE_FEDERATED_TOKEN_FILE", "federated-token")
    with pytest.raises(ValueError, match="AZURE_CLIENT_ID"):
        build_credential(settings)
    monkeypatch.setenv("AZURE_CLIENT_ID", "test-client")
    assert build_credential(settings) is workload.return_value


def test_client_uses_entra_tokens_timeout_and_no_retries(monkeypatch):
    from audio_agent import service

    constructor = Mock()
    token_factory = Mock()
    monkeypatch.setattr(service, "OpenAI", constructor)
    monkeypatch.setattr(service, "get_bearer_token_provider", token_factory)
    credential = Mock()
    created = create_service(Settings.from_environment(), credential)
    token_factory.assert_called_once_with(
        credential, "https://cognitiveservices.azure.com/.default"
    )
    assert constructor.call_args.kwargs["api_key"] is token_factory.return_value
    assert constructor.call_args.kwargs["max_retries"] == 0
    assert constructor.call_args.kwargs["timeout"] == 60
    created.close()
    constructor.return_value.close.assert_called_once()
