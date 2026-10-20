import pytest

from audio_agent import configuration


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setattr(configuration, "load_dotenv", lambda *args, **kwargs: False)
    values = {
        "AZURE_TENANT_ID": "11111111-1111-4111-8111-111111111111",
        "FOUNDRY_AUDIO_ENDPOINT": "https://mock.openai.azure.com/openai/v1/",
        "TTS_MODEL_DEPLOYMENT_NAME": "test-tts",
        "STT_MODEL_DEPLOYMENT_NAME": "test-stt",
        "AUDIO_TIMEOUT_SECONDS": "60",
        "MAX_AUDIO_UPLOAD_BYTES": "24000000",
        "MAX_SYNTHESIS_BYTES": "32000000",
        "REQUIRE_APP_SERVICE_AUTH": "false",
        "APPLICATIONINSIGHTS_CONNECTION_STRING": "",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    for key in (
        "AZURE_CLIENT_ID",
        "AZURE_FEDERATED_TOKEN_FILE",
        "IDENTITY_ENDPOINT",
        "MSI_ENDPOINT",
    ):
        monkeypatch.delenv(key, raising=False)
