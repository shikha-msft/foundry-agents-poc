from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.orchestration import MultiAgentResult


class FakeRuntime:
    def __init__(self, *, timeout: bool = False) -> None:
        self.timeout = timeout
        self.closed = False

    async def run(self, message: str) -> MultiAgentResult:
        if self.timeout:
            raise TimeoutError
        return MultiAgentResult(
            answer=f"coordinated: {message}",
            participants=("PromptSpecialist", "RetrievalSpecialist", "AutonomousManager"),
        )

    def close(self) -> None:
        self.closed = True


def test_chat_requires_easy_auth_header(monkeypatch) -> None:
    monkeypatch.setenv("REQUIRE_APP_SERVICE_AUTH", "true")
    runtime = FakeRuntime()
    app = create_app(lambda _: runtime)

    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "hello"})

    assert response.status_code == 401
    assert runtime.closed is True


def test_chat_returns_multi_agent_response(monkeypatch) -> None:
    monkeypatch.setenv("REQUIRE_APP_SERVICE_AUTH", "true")
    runtime = FakeRuntime()
    app = create_app(lambda _: runtime)

    with TestClient(app) as client:
        response = client.post(
            "/api/chat",
            json={"message": "hello"},
            headers={"X-MS-CLIENT-PRINCIPAL-ID": "user", "X-Request-ID": "request-1"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "coordinated: hello",
        "participants": [
            "PromptSpecialist",
            "RetrievalSpecialist",
            "AutonomousManager",
        ],
        "request_id": "request-1",
    }


def test_chat_maps_workflow_timeout(monkeypatch) -> None:
    monkeypatch.setenv("REQUIRE_APP_SERVICE_AUTH", "false")
    app = create_app(lambda _: FakeRuntime(timeout=True))

    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "hello"})

    assert response.status_code == 504
