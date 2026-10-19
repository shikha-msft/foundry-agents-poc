from __future__ import annotations

import asyncio
from dataclasses import dataclass

from agent_framework import Agent, AgentResponse
from agent_framework.foundry import FoundryChatClient
from agent_framework.orchestrations import MagenticBuilder
from azure.core.credentials import TokenCredential

from .configuration import Settings
from .foundry_gateway import FoundryAgentGateway, RemoteFoundryAgentGateway

_PROMPT_SPECIALIST_INSTRUCTIONS = """
You are the Prompt Specialist in a governed multi-agent workflow.
Always call consult_prompt_agent exactly once for the user's task.
Return the remote agent's useful reasoning to the manager.
Do not claim access to enterprise knowledge or invent tool results.
""".strip()

_RAG_SPECIALIST_INSTRUCTIONS = """
You are the Retrieval Specialist in a governed multi-agent workflow.
Always call consult_rag_agent exactly once when the task needs factual or
enterprise knowledge. Preserve citations from the remote RAG agent.
If retrieval is unavailable or ungrounded, state that explicitly.
""".strip()

_AUTONOMOUS_MANAGER_INSTRUCTIONS = """
You are a bounded autonomous coordinator.
Create a short plan, delegate to the Prompt Specialist and Retrieval
Specialist only when their capabilities are relevant, and synthesize a final
answer. Prefer cited retrieved evidence for factual enterprise claims.
Never perform writes, deployments, role assignments, or administrative
actions. Do not continue after the task is answered or a required dependency
is unavailable.
""".strip()


@dataclass(frozen=True)
class MultiAgentResult:
    answer: str
    participants: tuple[str, ...]


class MultiAgentRuntime:
    def __init__(
        self,
        settings: Settings,
        credential: TokenCredential,
        *,
        gateway: FoundryAgentGateway | None = None,
        chat_client: FoundryChatClient | None = None,
    ) -> None:
        self._settings = settings
        self._gateway = gateway or RemoteFoundryAgentGateway(settings, credential)
        self._owns_gateway = gateway is None
        self._chat_client = chat_client or FoundryChatClient(
            project_endpoint=settings.project_endpoint,
            model=settings.model_deployment_name,
            credential=credential,
            allow_preview=True,
        )

    async def run(self, message: str) -> MultiAgentResult:
        workflow = self._build_workflow()
        result = await asyncio.wait_for(
            workflow.run(message),
            timeout=self._settings.workflow_timeout_seconds,
        )
        outputs = result.get_outputs()
        if not outputs or not isinstance(outputs[-1], AgentResponse):
            raise RuntimeError("MAF workflow did not produce a final AgentResponse.")
        answer = outputs[-1].text.strip()
        if not answer:
            raise RuntimeError("MAF workflow produced an empty final answer.")
        return MultiAgentResult(
            answer=answer,
            participants=(
                "PromptSpecialist",
                "RetrievalSpecialist",
                "AutonomousManager",
            ),
        )

    def _build_workflow(self):
        settings = self._settings
        gateway = self._gateway

        async def consult_prompt_agent(question: str) -> str:
            """Ask the approved remote Foundry Prompt Agent."""
            return await gateway.invoke(settings.prompt_agent_name, question)

        async def consult_rag_agent(question: str) -> str:
            """Ask the approved remote Foundry RAG Agent and preserve citations."""
            return await gateway.invoke(settings.rag_agent_name, question)

        prompt_specialist = Agent(
            client=self._chat_client,
            name="PromptSpecialist",
            description="Uses the approved governed Foundry Prompt Agent.",
            instructions=_PROMPT_SPECIALIST_INSTRUCTIONS,
            tools=[consult_prompt_agent],
        )
        retrieval_specialist = Agent(
            client=self._chat_client,
            name="RetrievalSpecialist",
            description="Uses the approved governed Foundry RAG Agent.",
            instructions=_RAG_SPECIALIST_INSTRUCTIONS,
            tools=[consult_rag_agent],
        )
        autonomous_manager = Agent(
            client=self._chat_client,
            name="AutonomousManager",
            description="Bounded autonomous coordinator with no side-effect tools.",
            instructions=_AUTONOMOUS_MANAGER_INSTRUCTIONS,
        )
        return MagenticBuilder(
            participants=[prompt_specialist, retrieval_specialist],
            manager_agent=autonomous_manager,
            max_round_count=settings.max_round_count,
            max_stall_count=settings.max_stall_count,
            intermediate_output_from=[prompt_specialist, retrieval_specialist],
            name="GovernedMafMultiAgent",
        ).build()

    def close(self) -> None:
        if self._owns_gateway and isinstance(
            self._gateway,
            RemoteFoundryAgentGateway,
        ):
            self._gateway.close()
