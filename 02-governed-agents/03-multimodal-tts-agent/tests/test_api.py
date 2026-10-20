import json
from dataclasses import replace

import httpx
import pytest
from azure.core.exceptions import ClientAuthenticationError
from fastapi.testclient import TestClient
from openai import OpenAI

from audio_agent.configuration import Settings
from audio_agent.main import create_app
from audio_agent.service import AudioService

WAV = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"test-audio"
MP3 = b"ID3test-audio"


def api(handler, settings=None, api_key="test-token"):
    service = AudioService(
        settings or Settings.from_environment(),
        OpenAI(
            base_url="https://mock.openai.azure.com/openai/v1/",
            api_key=api_key,
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
            max_retries=0,
        ),
    )
    app = create_app(lambda _: service)
    return TestClient(app)


@pytest.mark.parametrize(
    ("audio_format", "media_type"), [("wav", "audio/wav"), ("mp3", "audio/mpeg")]
)
def test_synthesis_success(audio_format, media_type):
    audio = WAV if audio_format == "wav" else MP3

    def provider(request):
        assert request.url.path == "/openai/v1/audio/speech"
        body = json.loads(request.content)
        assert body == {
            "model": "test-tts",
            "input": "Hello",
            "voice": "alloy",
            "response_format": audio_format,
        }
        return httpx.Response(200, content=audio, headers={"Content-Type": media_type})

    with api(provider) as client:
        response = client.post(
            "/api/speech", json={"text": "Hello", "response_format": audio_format}
        )
    assert response.status_code == 200
    assert response.content == audio
    assert response.headers["content-type"] == media_type
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-request-id"]


@pytest.mark.parametrize(
    "payload",
    [
        {"text": ""},
        {"text": "   "},
        {"text": "x" * 4097},
        {"text": "hello", "voice": "unapproved"},
        {"text": "hello", "response_format": "invalid"},
        {"text": "hello", "unapproved_option": "ignored"},
    ],
)
def test_synthesis_rejects_invalid_input(payload):
    def provider(request):
        pytest.fail("Invalid input must not call provider")

    with api(provider) as client:
        response = client.post("/api/speech", json=payload)
    assert response.status_code == 422


def test_synthesis_accepts_exact_text_boundary():
    with api(lambda _: httpx.Response(200, content=WAV)) as client:
        response = client.post("/api/speech", json={"text": "x" * 4096})
    assert response.status_code == 200


@pytest.mark.parametrize("chunked", [False, True])
def test_synthesis_json_body_limit(chunked):
    content = b" " * 32_769
    if chunked:
        content = iter([content[:16_000], content[16_000:]])
    with api(lambda _: pytest.fail("Oversized JSON must not call provider")) as client:
        response = client.post(
            "/api/speech", content=content, headers={"Content-Type": "application/json"}
        )
    assert response.status_code == 413


def test_synthesis_rejects_unexpected_provider_format():
    with api(lambda _: httpx.Response(200, content=b"not-audio")) as client:
        response = client.post("/api/speech", json={"text": "Hello"})
    assert response.status_code == 502


@pytest.mark.parametrize(
    ("content_type", "body", "filename"),
    [("audio/wav", WAV, b"input.wav"), ("audio/mpeg", MP3, b"input.mp3")],
)
def test_transcription_success(content_type, body, filename):
    def provider(request):
        assert request.url.path == "/openai/v1/audio/transcriptions"
        assert filename in request.content
        assert body in request.content
        assert b"test-stt" in request.content
        assert b'name="language"' in request.content
        return httpx.Response(200, json={"text": "Hello world"})

    with api(provider) as client:
        response = client.post(
            "/api/transcriptions?language=en", content=body, headers={"Content-Type": content_type}
        )
    assert response.status_code == 200
    assert response.json()["text"] == "Hello world"
    assert response.json()["request_id"] == response.headers["x-request-id"]


@pytest.mark.parametrize(
    ("content_type", "body", "status"),
    [
        ("application/json", b"{}", 415),
        ("audio/wav", b"", 400),
        ("audio/wav", b"not-wav", 415),
        ("audio/mpeg", b"not-mp3", 415),
    ],
)
def test_transcription_rejects_invalid_audio(content_type, body, status):
    with api(lambda _: pytest.fail("Invalid upload must not call provider")) as client:
        response = client.post(
            "/api/transcriptions", content=body, headers={"Content-Type": content_type}
        )
    assert response.status_code == status


@pytest.mark.parametrize("chunked", [False, True])
def test_transcription_limit_enforced(monkeypatch, chunked):
    monkeypatch.setenv("MAX_AUDIO_UPLOAD_BYTES", str(len(WAV) - 1))
    content = iter([WAV[:12], WAV[12:]]) if chunked else WAV
    with api(lambda _: pytest.fail("Oversized upload must not call provider")) as client:
        response = client.post(
            "/api/transcriptions", content=content, headers={"Content-Type": "audio/wav"}
        )
    assert response.status_code == 413


def test_transcription_accepts_exact_upload_boundary(monkeypatch):
    monkeypatch.setenv("MAX_AUDIO_UPLOAD_BYTES", str(len(WAV)))
    with api(lambda _: httpx.Response(200, json={"text": "At limit"})) as client:
        response = client.post(
            "/api/transcriptions", content=WAV, headers={"Content-Type": "audio/wav"}
        )
    assert response.status_code == 200


@pytest.mark.parametrize("content", [b"", b"123456"])
def test_invalid_synthesis_output(content):
    settings = replace(Settings.from_environment(), max_synthesis_bytes=5)
    with api(lambda _: httpx.Response(200, content=content), settings) as client:
        response = client.post("/api/speech", json={"text": "Hello"})
    assert response.status_code == 502


@pytest.mark.parametrize("text", ["", "   ", None])
def test_empty_transcription_is_failure(text):
    with api(lambda _: httpx.Response(200, json={"text": text})) as client:
        response = client.post(
            "/api/transcriptions", content=WAV, headers={"Content-Type": "audio/wav"}
        )
    assert response.status_code == 502


@pytest.mark.parametrize(
    ("upstream_status", "expected"), [(401, 502), (403, 502), (429, 429), (500, 502)]
)
def test_upstream_errors_are_sanitized(upstream_status, expected, caplog):
    with api(
        lambda _: httpx.Response(upstream_status, json={"error": {"message": "private-payload"}})
    ) as client:
        response = client.post("/api/speech", json={"text": "private-text"})
    assert response.status_code == expected
    assert "private-payload" not in response.text + caplog.text
    assert "private-text" not in caplog.text


@pytest.mark.parametrize(("timeout", "expected"), [(False, 502), (True, 504)])
def test_connection_errors(timeout, expected):
    def provider(request):
        error = httpx.ReadTimeout if timeout else httpx.ConnectError
        raise error("private-payload", request=request)

    with api(provider) as client:
        response = client.post("/api/speech", json={"text": "Hello"})
    assert response.status_code == expected
    assert "private-payload" not in response.text


def test_credential_failure_is_sanitized(caplog):
    def token():
        raise ClientAuthenticationError("private-credential-error")

    with api(lambda _: pytest.fail("No inference without a token"), api_key=token) as client:
        response = client.post("/api/speech", json={"text": "Hello"})
    assert response.status_code == 503
    assert "private-credential-error" not in response.text + caplog.text


@pytest.mark.parametrize(("length", "expected"), [("not-a-number", 400), ("-1", 400)])
def test_invalid_content_length(length, expected):
    with api(lambda _: pytest.fail("Invalid size must not call provider")) as client:
        response = client.post(
            "/api/transcriptions",
            content=WAV,
            headers={"Content-Type": "audio/wav", "Content-Length": length},
        )
    assert response.status_code == expected


def test_language_rejected_before_provider_call():
    with api(lambda _: pytest.fail("Invalid language must not call provider")) as client:
        response = client.post(
            "/api/transcriptions?language=english",
            content=WAV,
            headers={"Content-Type": "audio/wav"},
        )
    assert response.status_code == 422


def test_authentication_optional_and_enforced_when_enabled(monkeypatch):
    monkeypatch.setenv("REQUIRE_APP_SERVICE_AUTH", "true")
    with api(lambda _: httpx.Response(200, content=WAV)) as client:
        rejected = client.post("/api/speech", json={"text": "Hello"})
        allowed = client.post(
            "/api/speech",
            json={"text": "Hello"},
            headers={"X-MS-CLIENT-PRINCIPAL-ID": "platform-validated-caller"},
        )
    assert rejected.status_code == 401
    assert allowed.status_code == 200


def test_health_readiness_and_closure():
    with api(lambda _: pytest.fail("Health checks must not invoke provider")) as client:
        service = client.app.state.service
        assert client.get("/healthz").json() == {"status": "healthy"}
        assert client.get("/readyz").json() == {"status": "ready"}
    assert service._client.is_closed()


def test_openapi_matches_binary_and_json_contracts():
    with api(lambda _: pytest.fail("Schema must not invoke models")) as client:
        schema = client.get("/openapi.json").json()
    speech = schema["paths"]["/api/speech"]["post"]
    assert set(speech["responses"]["200"]["content"]) == {"audio/wav", "audio/mpeg"}
    assert "application/json" in speech["requestBody"]["content"]
    transcription = schema["paths"]["/api/transcriptions"]["post"]
    assert set(transcription["requestBody"]["content"]) == {"audio/wav", "audio/mpeg"}
    assert "application/json" in transcription["responses"]["200"]["content"]
