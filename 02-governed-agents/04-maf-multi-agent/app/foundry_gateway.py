from __future__ import annotations

import asyncio
from typing import Protocol

from azure.ai.projects import AIProjectClient
from azure.core.credentials import TokenCredential

from .configuration import Settings


class FoundryAgentGateway(Protocol):
    async def invoke(self, agent_name: str, message: str) -> str: ...


class RemoteFoundryAgentGateway:
    def __init__(
        self,
        settings: Settings,
        credential: TokenCredential,
        *,
        project_client: AIProjectClient | None = None,
    ) -> None:
        self._settings = settings
        self._client = project_client or AIProjectClient(
            endpoint=settings.project_endpoint,
            credential=credential,
            allow_preview=True,
        )
        self._openai_client = self._client.get_openai_client()

    async def invoke(self, agent_name: str, message: str) -> str:
        return await asyncio.to_thread(self._invoke_sync, agent_name, message)

    def _invoke_sync(self, agent_name: str, message: str) -> str:
        response = self._openai_client.responses.create(
            model=self._settings.model_deployment_name,
            input=message,
            extra_body={
                "agent_reference": {
                    "name": agent_name,
                    "type": "agent_reference",
                }
            },
        )
        if not response.output_text:
            raise RuntimeError(f"Foundry agent {agent_name} returned no text output.")
        return response.output_text

    def close(self) -> None:
        self._client.close()
