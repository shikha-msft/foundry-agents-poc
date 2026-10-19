from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.configuration import Settings
from app.foundry_gateway import RemoteFoundryAgentGateway


class FakeResponses:
    def __init__(self) -> None:
        self.arguments: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.arguments = kwargs
        return SimpleNamespace(output_text="remote answer")


class FakeProjectClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()
        self.closed = False

    def get_openai_client(self) -> SimpleNamespace:
        return SimpleNamespace(responses=self.responses)

    def close(self) -> None:
        self.closed = True


def _settings() -> Settings:
    return Settings(
        project_endpoint="https://example.services.ai.azure.com/api/projects/poc",
        tenant_id="tenant",
        model_deployment_name="gpt-5.4-mini",
        prompt_agent_name="prompt",
        rag_agent_name="rag",
        max_round_count=6,
        max_stall_count=2,
        workflow_timeout_seconds=120,
        require_app_service_auth=True,
        agent365_enabled=False,
        agent365_agent_name=None,
        agent365_auth_mode="s2s",
        agent365_blueprint_client_id=None,
        agent365_agent_client_id=None,
        agent365_bootstrap_client_id=None,
        agent365_exporter_enabled=True,
        agent365_use_s2s_endpoint=True,
        agent365_suppress_invoke_agent_input=True,
    )


async def test_gateway_uses_agent_reference() -> None:
    client = FakeProjectClient()
    gateway = RemoteFoundryAgentGateway(
        _settings(),
        object(),
        project_client=client,
    )

    answer = await gateway.invoke("rag", "question")

    assert answer == "remote answer"
    assert client.responses.arguments["extra_body"] == {
        "agent_reference": {"name": "rag", "type": "agent_reference"}
    }
    gateway.close()
    assert client.closed is True
