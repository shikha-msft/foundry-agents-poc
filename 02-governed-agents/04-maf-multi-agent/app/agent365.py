from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from azure.core.credentials import TokenCredential
from azure.identity import ManagedIdentityCredential
from microsoft.opentelemetry import use_microsoft_opentelemetry
from microsoft.opentelemetry.a365.core import (
    AgentDetails,
    BaggageBuilder,
    CallerDetails,
    GenAiRequestParameters,
    InvokeAgentScope,
    InvokeAgentScopeDetails,
    Request,
    ServiceEndpoint,
    UserDetails,
)

from .configuration import Settings

_TOKEN_EXCHANGE_SCOPE = "api://AzureADTokenExchange/.default"
_OBSERVABILITY_SCOPE = "api://9b975845-388f-4429-889e-eab1ef63949c/.default"


@dataclass(frozen=True)
class _CachedToken:
    token: str
    expires_on: int


class Agent365TokenResolver:
    def __init__(
        self,
        settings: Settings,
        bootstrap: TokenCredential | None = None,
        http: httpx.Client | None = None,
    ) -> None:
        if not settings.agent365_blueprint_client_id:
            raise ValueError("A365_BLUEPRINT_CLIENT_ID is required.")
        if not settings.agent365_agent_client_id:
            raise ValueError("A365_AGENT_CLIENT_ID is required.")
        self._tenant_id = settings.tenant_id
        self._blueprint_client_id = settings.agent365_blueprint_client_id
        self._agent_client_id = settings.agent365_agent_client_id
        self._bootstrap = bootstrap or ManagedIdentityCredential(
            client_id=settings.agent365_bootstrap_client_id
        )
        self._http = http or httpx.Client(timeout=30)
        self._owns_bootstrap = bootstrap is None
        self._owns_http = http is None
        self._cached: _CachedToken | None = None
        self._lock = threading.Lock()

    def resolve(self, agent_id: str, tenant_id: str) -> str | None:
        if agent_id.lower() != self._agent_client_id.lower():
            raise ValueError("Agent 365 exporter requested a token for an unexpected agent.")
        if tenant_id.lower() != self._tenant_id.lower():
            raise ValueError("Agent 365 exporter requested a token for an unexpected tenant.")

        with self._lock:
            if self._cached and self._cached.expires_on > int(time.time()) + 300:
                return self._cached.token

            token = self._exchange_token()
            self._cached = token
            return token.token

    def _exchange_token(self) -> _CachedToken:
        assertion = self._bootstrap.get_token(_TOKEN_EXCHANGE_SCOPE)
        endpoint = f"https://login.microsoftonline.com/{self._tenant_id}/oauth2/v2.0/token"
        common = {
            "grant_type": "client_credentials",
            "client_assertion_type": ("urn:ietf:params:oauth:client-assertion-type:jwt-bearer"),
        }

        parent_response = self._http.post(
            endpoint,
            data={
                **common,
                "client_id": self._blueprint_client_id,
                "scope": _TOKEN_EXCHANGE_SCOPE,
                "client_assertion": assertion.token,
                "fmi_path": self._agent_client_id,
            },
        )
        self._ensure_success(parent_response)
        parent_token = parent_response.json().get("access_token")
        if not isinstance(parent_token, str) or not parent_token:
            raise RuntimeError("Agent 365 parent token response was invalid.")

        response = self._http.post(
            endpoint,
            data={
                **common,
                "client_id": self._agent_client_id,
                "scope": _OBSERVABILITY_SCOPE,
                "client_assertion": parent_token,
            },
        )
        self._ensure_success(response)
        payload = response.json()
        token = payload.get("access_token")
        lifetime = payload.get("expires_in")
        if (
            not isinstance(token, str)
            or not token
            or type(lifetime) is not int
            or lifetime <= 0
            or str(payload.get("token_type", "")).lower() != "bearer"
        ):
            raise RuntimeError("Agent 365 token response was invalid.")
        return _CachedToken(token=token, expires_on=int(time.time()) + lifetime)

    @staticmethod
    def _ensure_success(response: httpx.Response) -> None:
        if response.is_error:
            raise RuntimeError(f"Agent 365 token exchange failed with HTTP {response.status_code}.")

    def close(self) -> None:
        if self._owns_http:
            self._http.close()
        if self._owns_bootstrap:
            self._bootstrap.close()


class Agent365Observability:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._resolver = Agent365TokenResolver(settings) if settings.agent365_enabled else None

        app_insights = _application_insights_connection_string()
        if app_insights or settings.agent365_enabled:
            use_microsoft_opentelemetry(
                enable_azure_monitor=bool(app_insights),
                azure_monitor_connection_string=app_insights,
                enable_a365=settings.agent365_enabled,
                a365_token_resolver=self._resolver.resolve if self._resolver else None,
                a365_enable_observability_exporter=settings.agent365_enabled,
                a365_use_s2s_endpoint=settings.agent365_use_s2s_endpoint,
                a365_suppress_invoke_agent_input=(settings.agent365_suppress_invoke_agent_input),
            )

    @contextmanager
    def invocation(
        self,
        *,
        request_id: str,
        caller_id: str | None,
    ) -> Iterator[InvokeAgentScope | None]:
        if not self._settings.agent365_enabled:
            yield None
            return

        agent_id = self._settings.agent365_agent_client_id
        agent_name = self._settings.agent365_agent_name
        blueprint_id = self._settings.agent365_blueprint_client_id
        if not agent_id or not agent_name or not blueprint_id:
            raise RuntimeError("Agent 365 settings are incomplete.")

        endpoint = urlsplit(self._settings.project_endpoint)
        baggage = (
            BaggageBuilder()
            .tenant_id(self._settings.tenant_id)
            .agent_id(agent_id)
            .agent_name(agent_name)
            .agent_blueprint_id(blueprint_id)
            .session_id(request_id)
        )
        if caller_id:
            baggage.user_id(caller_id)

        with (
            baggage.build(),
            InvokeAgentScope.start(
                request=Request(
                    content=None,
                    session_id=request_id,
                    conversation_id=request_id,
                ),
                scope_details=InvokeAgentScopeDetails(
                    endpoint=ServiceEndpoint(hostname=endpoint.hostname or ""),
                    request_parameters=GenAiRequestParameters(
                        model=self._settings.model_deployment_name,
                    ),
                ),
                agent_details=AgentDetails(
                    agent_id=agent_id,
                    agent_name=agent_name,
                    agent_blueprint_id=blueprint_id,
                    tenant_id=self._settings.tenant_id,
                    provider_name="Microsoft Agent Framework",
                ),
                caller_details=(
                    CallerDetails(user_details=UserDetails(user_id=caller_id))
                    if caller_id
                    else None
                ),
            ) as scope,
        ):
            try:
                yield scope
            except Exception as error:
                scope.record_error(RuntimeError(type(error).__name__))
                raise

    def close(self) -> None:
        if self._resolver:
            self._resolver.close()


def _application_insights_connection_string() -> str | None:
    import os

    value = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "").strip()
    return value or None
