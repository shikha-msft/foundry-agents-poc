from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.core.credentials import TokenCredential
from azure.identity import (
    AzureCliCredential,
    ManagedIdentityCredential,
    WorkloadIdentityCredential,
)
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    project_endpoint: str
    tenant_id: str
    model_deployment_name: str
    agent_name: str
    application_insights_resource_name: str
    azure_cli_process_timeout: int

    @classmethod
    def from_environment(cls) -> Settings:
        load_dotenv(_ROOT / ".env", override=False)
        timeout_text = os.getenv("AZURE_CLI_PROCESS_TIMEOUT", "60")
        try:
            timeout = int(timeout_text)
        except ValueError as error:
            raise ValueError("AZURE_CLI_PROCESS_TIMEOUT must be an integer.") from error
        if timeout < 1:
            raise ValueError("AZURE_CLI_PROCESS_TIMEOUT must be greater than zero.")

        settings = cls(
            project_endpoint=_required("PROJECT_ENDPOINT").rstrip("/"),
            tenant_id=_required("AZURE_TENANT_ID"),
            model_deployment_name=_required("MODEL_DEPLOYMENT_NAME"),
            agent_name=_required("AGENT_NAME"),
            application_insights_resource_name=_required(
                "APPLICATION_INSIGHTS_RESOURCE_NAME"
            ),
            azure_cli_process_timeout=timeout,
        )
        if not settings.project_endpoint.startswith("https://"):
            raise ValueError("PROJECT_ENDPOINT must be an HTTPS URL.")
        if "/api/projects/" not in settings.project_endpoint:
            raise ValueError(
                "PROJECT_ENDPOINT must identify a Microsoft Foundry project."
            )
        return settings


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required.")
    return value


def build_credential(settings: Settings) -> TokenCredential:
    client_id = os.getenv("AZURE_CLIENT_ID") or None
    if os.getenv("AZURE_FEDERATED_TOKEN_FILE"):
        if not client_id:
            raise ValueError("AZURE_CLIENT_ID is required for workload identity.")
        return WorkloadIdentityCredential(
            tenant_id=settings.tenant_id,
            client_id=client_id,
        )
    if os.getenv("IDENTITY_ENDPOINT") or os.getenv("MSI_ENDPOINT"):
        return ManagedIdentityCredential(client_id=client_id)
    return AzureCliCredential(
        tenant_id=settings.tenant_id,
        process_timeout=settings.azure_cli_process_timeout,
    )


def _definition(settings: Settings) -> PromptAgentDefinition:
    instructions = (_ROOT / "instructions.md").read_text(encoding="utf-8").strip()
    return PromptAgentDefinition(
        model=settings.model_deployment_name,
        instructions=instructions,
        temperature=0.2,
    )


def create_agent(client: AIProjectClient, settings: Settings) -> dict[str, Any]:
    result = client.agents.create_version(
        agent_name=settings.agent_name,
        body=build_create_body(settings),
    )
    return result.as_dict()


def build_create_body(settings: Settings) -> dict[str, Any]:
    return {
        "definition": _definition(settings).as_dict(),
        "description": "Governed Prompt Agent for the POC Project.",
        "metadata": {
            "category": "prompt",
            "governance": "governed-poc",
            "observability": settings.application_insights_resource_name,
        },
    }


def invoke_agent(client: AIProjectClient, settings: Settings, message: str) -> str:
    response = client.get_openai_client().responses.create(
        model=settings.model_deployment_name,
        input=message,
        extra_body={
            "agent_reference": {
                "name": settings.agent_name,
                "type": "agent_reference",
            }
        },
    )
    return response.output_text


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the governed Prompt Agent.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create", help="Create a new Prompt Agent version.")
    commands.add_parser("list", help="List all agents in the configured project.")
    render = commands.add_parser(
        "render",
        help="Write the Foundry REST creation body without creating an agent.",
    )
    render.add_argument("--output", required=True)
    invoke = commands.add_parser("invoke", help="Invoke the Prompt Agent.")
    invoke.add_argument("--message", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        settings = Settings.from_environment()
    except ValueError as error:
        parser.error(str(error))

    if arguments.command == "render":
        Path(arguments.output).write_text(
            json.dumps(build_create_body(settings), indent=2),
            encoding="utf-8",
        )
        return 0

    try:
        credential = build_credential(settings)
    except ValueError as error:
        parser.error(str(error))

    client = AIProjectClient(
        endpoint=settings.project_endpoint,
        credential=credential,
        allow_preview=True,
    )
    try:
        if arguments.command == "create":
            print(json.dumps(create_agent(client, settings), indent=2, default=str))
        elif arguments.command == "list":
            agents = [agent.as_dict() for agent in client.agents.list()]
            print(json.dumps(agents, indent=2, default=str))
        else:
            print(invoke_agent(client, settings, arguments.message))
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
