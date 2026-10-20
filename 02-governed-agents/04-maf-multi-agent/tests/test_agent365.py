from __future__ import annotations

import time

import httpx
import pytest
from azure.core.credentials import AccessToken

from app.agent365 import Agent365TokenResolver
from app.configuration import Settings


class FakeCredential:
    def get_token(self, *scopes: str, **kwargs: object) -> AccessToken:
        assert scopes == ("api://AzureADTokenExchange/.default",)
        assert not kwargs
        return AccessToken("bootstrap-token", int(time.time()) + 3600)

    def close(self) -> None:
        return None


def _settings() -> Settings:
    return Settings(
        project_endpoint=("https://example.services.ai.azure.com/api/projects/example-project"),
        tenant_id="11111111-1111-4111-8111-111111111111",
        model_deployment_name="model",
        prompt_agent_name="prompt",
        rag_agent_name="rag",
        max_round_count=6,
        max_stall_count=2,
        workflow_timeout_seconds=120,
        require_app_service_auth=True,
        agent365_enabled=True,
        agent365_agent_name="maf-orchestrator",
        agent365_auth_mode="s2s",
        agent365_blueprint_client_id="22222222-2222-4222-8222-222222222222",
        agent365_agent_client_id="33333333-3333-4333-8333-333333333333",
        agent365_bootstrap_client_id=None,
        agent365_exporter_enabled=True,
        agent365_use_s2s_endpoint=True,
        agent365_suppress_invoke_agent_input=True,
    )


def test_agent365_token_resolver_uses_fmi_chain() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = request.content.decode()
        if "fmi_path" in body:
            return httpx.Response(
                200,
                json={"access_token": "parent-token"},
            )
        return httpx.Response(
            200,
            json={
                "access_token": "observability-token",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    resolver = Agent365TokenResolver(
        _settings(),
        bootstrap=FakeCredential(),
        http=client,
    )

    token = resolver.resolve(
        "33333333-3333-4333-8333-333333333333",
        "11111111-1111-4111-8111-111111111111",
    )

    assert token == "observability-token"
    assert len(requests) == 2
    assert "parent-token" in requests[1].content.decode()


def test_agent365_token_resolver_rejects_wrong_agent() -> None:
    resolver = Agent365TokenResolver(
        _settings(),
        bootstrap=FakeCredential(),
        http=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(500))),
    )

    with pytest.raises(ValueError, match="unexpected agent"):
        resolver.resolve(
            "44444444-4444-4444-8444-444444444444",
            "11111111-1111-4111-8111-111111111111",
        )
