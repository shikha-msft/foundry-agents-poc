from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    AISearchIndexResource,
    AzureAISearchTool,
    AzureAISearchToolResource,
    PromptAgentDefinition,
)
from azure.core.credentials import TokenCredential
from azure.identity import (
    AzureCliCredential,
    ManagedIdentityCredential,
    WorkloadIdentityCredential,
)
from dotenv import load_dotenv

from search_index import IndexOptions, prepare_index, validate_index_name

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT.parent))
from agent_governance import verify_identity, verify_monitoring


@dataclass(frozen=True)
class Settings:
    project_endpoint: str
    tenant_id: str
    model_deployment_name: str
    agent_name: str
    application_insights_resource_name: str
    azure_cli_process_timeout: int
    search_connection_id: str
    search_index_name: str
    search_query_type: str
    search_top_k: int

    @classmethod
    def from_environment(cls, *, index_name: str | None = None) -> Settings:
        load_dotenv(_ROOT / ".env", override=False)
        timeout = _integer("AZURE_CLI_PROCESS_TIMEOUT", default=60, minimum=1)
        top_k = _integer("AZURE_AI_SEARCH_TOP_K", default=5, minimum=1, maximum=50)
        settings = cls(
            project_endpoint=_required("PROJECT_ENDPOINT").rstrip("/"),
            tenant_id=_required("AZURE_TENANT_ID"),
            model_deployment_name=_required("MODEL_DEPLOYMENT_NAME"),
            agent_name=_required("AGENT_NAME"),
            application_insights_resource_name=_required(
                "APPLICATION_INSIGHTS_RESOURCE_NAME"
            ),
            azure_cli_process_timeout=timeout,
            search_connection_id=_required("AZURE_AI_SEARCH_CONNECTION_ID"),
            search_index_name=(
                index_name.strip()
                if index_name is not None
                else _required("AZURE_AI_SEARCH_INDEX_NAME")
            ),
            search_query_type=_required("AZURE_AI_SEARCH_QUERY_TYPE"),
            search_top_k=top_k,
        )
        if not settings.project_endpoint.startswith("https://"):
            raise ValueError("PROJECT_ENDPOINT must be an HTTPS URL.")
        if "/api/projects/" not in settings.project_endpoint:
            raise ValueError(
                "PROJECT_ENDPOINT must identify a Microsoft Foundry project."
            )
        validate_index_name(settings.search_index_name)
        return settings


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required.")
    return value


def _integer(
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int | None = None,
) -> int:
    text = os.getenv(name, str(default))
    try:
        value = int(text)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer.") from error
    if value < minimum or (maximum is not None and value > maximum):
        expected = (
            f"between {minimum} and {maximum}" if maximum else f"at least {minimum}"
        )
        raise ValueError(f"{name} must be {expected}.")
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
    search_index = AISearchIndexResource(
        project_connection_id=settings.search_connection_id,
        index_name=settings.search_index_name,
        query_type=settings.search_query_type,
        top_k=settings.search_top_k,
    )
    search_tool = AzureAISearchTool(
        azure_ai_search=AzureAISearchToolResource(indexes=[search_index])
    )
    return PromptAgentDefinition(
        model=settings.model_deployment_name,
        instructions=instructions,
        temperature=0.1,
        tools=[search_tool],
    )


def create_agent(client: AIProjectClient, settings: Settings) -> dict[str, Any]:
    verify_monitoring(
        [
            connection.as_dict()
            for connection in client.connections.list(connection_type="AppInsights")
        ],
        settings.application_insights_resource_name,
    )
    result = client.agents.create_version(
        agent_name=settings.agent_name,
        body=build_create_body(settings),
    )
    body = result.as_dict()
    body["identity_verification"] = verify_identity(
        client.agents.get(agent_name=settings.agent_name).as_dict()
    )
    return body


def build_create_body(settings: Settings) -> dict[str, Any]:
    return {
        "definition": _definition(settings).as_dict(),
        "description": "Governed Azure AI Search RAG Agent for the POC Project.",
        "metadata": {
            "category": "rag",
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
    parser = argparse.ArgumentParser(description="Manage the governed RAG Agent.")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser(
        "create", help="Prepare an index and create an agent version."
    )
    prepare = commands.add_parser(
        "prepare-index",
        help="Select an existing index or create a synthetic PoC index.",
    )
    for command in (create, prepare):
        command.add_argument(
            "--index-mode",
            choices=("existing", "create"),
            help="Defaults to AZURE_AI_SEARCH_INDEX_MODE, or existing.",
        )
        command.add_argument(
            "--index-name", help="Override AZURE_AI_SEARCH_INDEX_NAME for this command."
        )
    commands.add_parser("list", help="List all agents in the configured project.")
    render = commands.add_parser(
        "render",
        help="Write the Foundry REST creation body without creating an agent.",
    )
    render.add_argument("--output", required=True)
    render.add_argument(
        "--index-name", help="Override the index name without Azure access."
    )
    invoke = commands.add_parser("invoke", help="Invoke the RAG Agent.")
    invoke.add_argument("--message", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        settings = Settings.from_environment(
            index_name=getattr(arguments, "index_name", None)
        )
        index_options = (
            IndexOptions.from_environment(arguments.index_mode)
            if arguments.command in ("create", "prepare-index")
            else None
        )
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
        if (
            arguments.command == "create"
            and index_options
            and index_options.mode == "create"
        ):
            verify_monitoring(
                [
                    connection.as_dict()
                    for connection in client.connections.list(
                        connection_type="AppInsights"
                    )
                ],
                settings.application_insights_resource_name,
            )
        if index_options is not None:
            prepared = prepare_index(
                client,
                credential,
                settings.search_connection_id,
                settings.search_index_name,
                index_options,
            )
            if arguments.command == "prepare-index":
                print(json.dumps(prepared, indent=2))
                return 0
        if arguments.command == "create":
            print(json.dumps(create_agent(client, settings), indent=2, default=str))
        elif arguments.command == "list":
            agents = [agent.as_dict() for agent in client.agents.list()]
            print(json.dumps(agents, indent=2, default=str))
        else:
            print(invoke_agent(client, settings, arguments.message))
    except ValueError as error:
        parser.error(str(error))
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
