import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from azure.core.exceptions import HttpResponseError, ResourceExistsError

import rag_agent
import search_index
from search_index import IndexOptions, prepare_index, synthetic_documents


@pytest.fixture
def options():
    return IndexOptions(
        "create", "https://mock.openai.azure.com/openai/v1/", "mock-embedding"
    )


@pytest.fixture
def services(monkeypatch):
    settings = rag_agent.Settings.from_environment()
    project = Mock()
    project.connections.get.return_value = SimpleNamespace(
        id=settings.search_connection_id,
        type="CognitiveSearch",
        target="https://mock.search.windows.net",
    )
    indexes_factory = MagicMock()
    search_factory = MagicMock()
    model_factory = MagicMock()
    indexes = indexes_factory.return_value.__enter__.return_value = Mock()
    search = search_factory.return_value.__enter__.return_value = Mock()
    model = model_factory.return_value.__enter__.return_value = Mock()
    model.embeddings.create.return_value = SimpleNamespace(
        data=[
            SimpleNamespace(index=n, embedding=[float(n)] * 1536)
            for n in reversed(range(3))
        ]
    )
    search.upload_documents.return_value = [
        SimpleNamespace(key=d["id"], succeeded=True, error_message=None)
        for d in synthetic_documents()
    ]
    monkeypatch.setattr(search_index, "SearchIndexClient", indexes_factory)
    monkeypatch.setattr(search_index, "SearchClient", search_factory)
    monkeypatch.setattr(search_index, "OpenAI", model_factory)
    return SimpleNamespace(
        settings=settings,
        project=project,
        credential=Mock(),
        indexes=indexes,
        search=search,
        model=model,
        indexes_factory=indexes_factory,
        search_factory=search_factory,
        model_factory=model_factory,
    )


def prepare(services, options):
    return prepare_index(
        services.project,
        services.credential,
        services.settings.search_connection_id,
        services.settings.search_index_name,
        options,
    )


def test_existing_is_default_without_embedding_configuration():
    assert IndexOptions.from_environment() == IndexOptions("existing")


def test_explicit_mode_overrides_environment(monkeypatch):
    monkeypatch.setenv("AZURE_AI_SEARCH_INDEX_MODE", "create")
    assert IndexOptions.from_environment("existing") == IndexOptions("existing")


def test_invalid_environment_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("AZURE_AI_SEARCH_INDEX_MODE", "replace")
    with pytest.raises(ValueError, match="existing or create"):
        IndexOptions.from_environment()


def test_create_configuration(monkeypatch, options):
    monkeypatch.setenv("AZURE_AI_SEARCH_INDEX_MODE", "create")
    monkeypatch.setenv("AZURE_AI_EMBEDDING_ENDPOINT", options.embedding_endpoint)
    monkeypatch.setenv(
        "AZURE_AI_EMBEDDING_DEPLOYMENT_NAME", options.embedding_deployment
    )
    assert IndexOptions.from_environment() == options


@pytest.mark.parametrize(
    "endpoint",
    [
        "",
        "http://mock.openai.azure.com/openai/v1/",
        "https://mock.services.ai.azure.com/api/projects/poc",
        "https://mock.openai.azure.com/openai/v1/?key=bad",
        "https://mock.openai.azure.com/openai/v1/#fragment",
        "https://user:password@mock.openai.azure.com/openai/v1/",
        "https://<foundry-account>.openai.azure.com/openai/v1/",
    ],
)
def test_invalid_embedding_endpoint_is_rejected(monkeypatch, endpoint):
    monkeypatch.setenv("AZURE_AI_EMBEDDING_ENDPOINT", endpoint)
    with pytest.raises(ValueError, match="AZURE_AI_EMBEDDING_ENDPOINT"):
        IndexOptions.from_environment("create")


def test_create_requires_embedding_deployment(monkeypatch, options):
    monkeypatch.setenv("AZURE_AI_EMBEDDING_ENDPOINT", options.embedding_endpoint)
    with pytest.raises(ValueError, match="AZURE_AI_EMBEDDING_DEPLOYMENT_NAME"):
        IndexOptions.from_environment("create")


@pytest.mark.parametrize("deployment", ["<deployment-name>", "$(UNSET_VARIABLE)"])
def test_unresolved_embedding_deployment_is_rejected(monkeypatch, options, deployment):
    monkeypatch.setenv("AZURE_AI_EMBEDDING_ENDPOINT", options.embedding_endpoint)
    monkeypatch.setenv("AZURE_AI_EMBEDDING_DEPLOYMENT_NAME", deployment)
    with pytest.raises(ValueError, match="AZURE_AI_EMBEDDING_DEPLOYMENT_NAME"):
        IndexOptions.from_environment("create")


@pytest.mark.parametrize("name", ["", "a", "UPPER", "_leading", "has space", "a" * 129])
def test_invalid_index_name(name):
    with pytest.raises(ValueError, match="index name"):
        search_index.validate_index_name(name)


def test_existing_never_reads_or_mutates_search(services):
    result = prepare(services, IndexOptions("existing"))
    assert result == {
        "mode": "existing",
        "index_name": "existing-index",
        "status": "supplied",
    }
    assert services.project.mock_calls == []
    services.indexes_factory.assert_not_called()
    services.model_factory.assert_not_called()
    services.search_factory.assert_not_called()


def test_creates_vector_semantic_index_and_synthetic_documents(services, options):
    result = prepare(services, options)
    assert result["synthetic_documents_accepted"] == 3
    services.project.connections.get.assert_called_once_with(
        name="search", include_credentials=False
    )
    schema = services.indexes.create_index.call_args.args[0].serialize()
    assert schema["name"] == "existing-index"
    source_url = next(f for f in schema["fields"] if f["name"] == "url")
    assert source_url["searchable"] is True
    assert source_url["retrievable"] is True
    vector = next(f for f in schema["fields"] if f["name"] == "contentVector")
    assert vector["dimensions"] == 1536
    assert vector["retrievable"] is False
    profile = schema["vectorSearch"]["profiles"][0]
    assert (
        schema["vectorSearch"]["algorithms"][0]["hnswParameters"]["metric"] == "cosine"
    )
    assert vector["vectorSearchProfile"] == profile["name"]
    vectorizer = schema["vectorSearch"]["vectorizers"][0]
    assert profile["vectorizer"] == vectorizer["name"]
    assert vectorizer["azureOpenAIParameters"] == {
        "resourceUri": "https://mock.openai.azure.com",
        "deploymentId": "mock-embedding",
        "modelName": "text-embedding-3-small",
    }
    assert schema["semantic"]["defaultConfiguration"] == "synthetic-semantic"
    services.indexes.create_or_update_index.assert_not_called()
    services.indexes.delete_index.assert_not_called()
    documents = services.search.upload_documents.call_args.kwargs["documents"]
    assert len(documents) == 3
    for n, document in enumerate(documents):
        assert "SYNTHETIC POC DATA ONLY" in document["content"]
        assert document["url"].startswith("https://example.org/poc/")
        assert document["contentVector"] == [float(n)] * 1536
    assert services.model.embeddings.create.call_args.kwargs["dimensions"] == 1536


def test_existing_name_conflict_never_overwrites_or_loads(services, options):
    services.indexes.create_index.side_effect = ResourceExistsError("already exists")
    with pytest.raises(ValueError, match="Nothing was overwritten"):
        prepare(services, options)
    services.indexes.create_or_update_index.assert_not_called()
    services.model_factory.assert_not_called()
    services.search_factory.assert_not_called()


def test_service_failure_is_not_treated_as_an_existing_index(services, options):
    services.indexes.create_index.side_effect = HttpResponseError("access denied")
    with pytest.raises(HttpResponseError, match="access denied"):
        prepare(services, options)
    services.model_factory.assert_not_called()


@pytest.mark.parametrize(
    "kind", ["missing", "duplicate", "extra-duplicate", "wrong-dimensions"]
)
def test_invalid_embedding_output_fails_before_upload(services, options, kind):
    data = services.model.embeddings.create.return_value.data
    if kind == "missing":
        data.pop()
    elif kind == "duplicate":
        data[0].index = data[1].index
    elif kind == "extra-duplicate":
        data.append(data[0])
    else:
        data[0].embedding = [0.0]
    with pytest.raises(ValueError, match="embedding output was invalid"):
        prepare(services, options)
    services.search_factory.assert_not_called()
    services.indexes.delete_index.assert_not_called()


@pytest.mark.parametrize("incomplete", [False, True])
def test_failed_document_ingestion_is_explicit(services, options, incomplete):
    if incomplete:
        services.search.upload_documents.return_value = []
    else:
        result = services.search.upload_documents.return_value[1]
        result.succeeded = False
        result.error_message = "test ingestion failure"
    with pytest.raises(ValueError, match="synthetic ingestion failed"):
        prepare(services, options)
    services.indexes.delete_index.assert_not_called()


@pytest.mark.parametrize(
    "change",
    [
        {"id": "/another/project/connections/search"},
        {"type": "AzureBlob"},
        {"target": "http://mock.search.windows.net"},
        {"target": "https://user:password@mock.search.windows.net"},
        {"target": "https://mock.search.windows.net/indexes/other"},
    ],
)
def test_invalid_connection_is_rejected_before_creation(services, options, change):
    for key, value in change.items():
        setattr(services.project.connections.get.return_value, key, value)
    with pytest.raises(ValueError):
        prepare(services, options)
    services.indexes_factory.assert_not_called()


def test_synthetic_documents_do_not_share_mutable_state():
    documents = synthetic_documents()
    documents[0]["contentVector"] = [0.0]
    assert "contentVector" not in synthetic_documents()[0]


@pytest.fixture
def cli(monkeypatch):
    client_factory = Mock()
    client_factory.return_value.connections.list.return_value = [
        SimpleNamespace(
            as_dict=lambda: {
                "type": "AppInsights",
                "target": "/subscriptions/mock/providers/Microsoft.Insights/components/mock-insights",
            }
        )
    ]
    credential_factory = Mock()
    prepare_mock = Mock(return_value={"status": "supplied"})
    create = Mock(return_value={"version": "test"})
    monkeypatch.setattr(rag_agent, "AIProjectClient", client_factory)
    monkeypatch.setattr(rag_agent, "build_credential", credential_factory)
    monkeypatch.setattr(rag_agent, "prepare_index", prepare_mock)
    monkeypatch.setattr(rag_agent, "create_agent", create)
    return SimpleNamespace(
        client_factory=client_factory,
        credential_factory=credential_factory,
        prepare=prepare_mock,
        create=create,
    )


def test_cli_create_defaults_to_existing(cli, capsys):
    assert rag_agent.main(["create"]) == 0
    assert cli.prepare.call_args.args[-1] == IndexOptions("existing")
    cli.create.assert_called_once()
    assert json.loads(capsys.readouterr().out) == {"version": "test"}


def test_cli_can_supply_index_without_environment_value(cli, monkeypatch):
    monkeypatch.delenv("AZURE_AI_SEARCH_INDEX_NAME")
    assert rag_agent.main(["create", "--index-name", "supplied-index"]) == 0
    assert cli.prepare.call_args.args[3] == "supplied-index"
    assert cli.create.call_args.args[1].search_index_name == "supplied-index"


def test_cli_create_mode_prepares_before_agent(cli, monkeypatch, options):
    monkeypatch.setenv("AZURE_AI_EMBEDDING_ENDPOINT", options.embedding_endpoint)
    monkeypatch.setenv(
        "AZURE_AI_EMBEDDING_DEPLOYMENT_NAME", options.embedding_deployment
    )
    calls = Mock()
    calls.attach_mock(cli.prepare, "prepare")
    calls.attach_mock(cli.create, "create")
    assert rag_agent.main(["create", "--index-mode", "create"]) == 0
    assert cli.prepare.call_args.args[-1] == options
    assert [call[0] for call in calls.mock_calls] == ["prepare", "create"]


def test_cli_preparation_failure_does_not_create_agent(cli):
    cli.prepare.side_effect = ValueError("index conflict")
    with pytest.raises(SystemExit) as error:
        rag_agent.main(["create"])
    assert error.value.code == 2
    cli.create.assert_not_called()
    cli.client_factory.return_value.close.assert_called_once()


def test_create_without_monitoring_does_not_seed_index(cli, monkeypatch, options):
    monkeypatch.setenv("AZURE_AI_EMBEDDING_ENDPOINT", options.embedding_endpoint)
    monkeypatch.setenv(
        "AZURE_AI_EMBEDDING_DEPLOYMENT_NAME", options.embedding_deployment
    )
    cli.client_factory.return_value.connections.list.return_value = []
    with pytest.raises(SystemExit) as error:
        rag_agent.main(["create", "--index-mode", "create"])
    assert error.value.code == 2
    cli.prepare.assert_not_called()
    cli.create.assert_not_called()


def test_prepare_only_does_not_create_an_agent(cli, capsys):
    assert rag_agent.main(["prepare-index", "--index-mode", "existing"]) == 0
    assert json.loads(capsys.readouterr().out) == {"status": "supplied"}
    cli.create.assert_not_called()


def test_render_stays_offline_even_when_create_is_configured(
    cli, monkeypatch, tmp_path
):
    monkeypatch.setenv("AZURE_AI_SEARCH_INDEX_MODE", "create")
    output = tmp_path / "definition.json"
    assert (
        rag_agent.main(
            ["render", "--output", str(output), "--index-name", "preview-index"]
        )
        == 0
    )
    index = json.loads(output.read_text())["definition"]["tools"][0]["azure_ai_search"][
        "indexes"
    ][0]
    assert index["index_name"] == "preview-index"
    cli.prepare.assert_not_called()
    cli.client_factory.assert_not_called()
    cli.credential_factory.assert_not_called()


def test_invalid_create_settings_fail_before_any_azure_client(cli):
    with pytest.raises(SystemExit) as error:
        rag_agent.main(["create", "--index-mode", "create"])
    assert error.value.code == 2
    cli.client_factory.assert_not_called()
    cli.credential_factory.assert_not_called()


@pytest.mark.parametrize("command", ["list", "invoke"])
def test_non_creation_commands_never_prepare_index(cli, monkeypatch, command):
    monkeypatch.setenv("AZURE_AI_SEARCH_INDEX_MODE", "create")
    cli.client_factory.return_value.agents.list.return_value = []
    monkeypatch.setattr(rag_agent, "invoke_agent", Mock(return_value="offline"))
    args = [command] if command == "list" else [command, "--message", "synthetic"]
    assert rag_agent.main(args) == 0
    cli.prepare.assert_not_called()


@pytest.mark.skipif(
    shutil.which("pwsh") is None, reason="PowerShell 7 is not installed"
)
def test_rest_entrypoint_modes_and_whatif():
    result = subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-File",
            str(Path(__file__).with_name("test_rest_entrypoint.ps1")),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "9 REST entrypoint scenarios passed." in result.stdout
