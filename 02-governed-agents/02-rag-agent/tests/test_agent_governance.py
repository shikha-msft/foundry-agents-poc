import json
from copy import deepcopy
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import agent_governance
import prompt_agent
import rag_agent
from agent_governance import verify_identity, verify_monitoring

IDENTITY = {
    "client_id": "11111111-1111-4111-8111-111111111111",
    "principal_id": "22222222-2222-4222-8222-222222222222",
}
AGENT = {"blueprint": IDENTITY.copy(), "instance_identity": IDENTITY.copy()}
CONNECTION = {
    "type": "AppInsights",
    "target": "/subscriptions/mock/resourceGroups/mock/providers/"
    "Microsoft.Insights/components/mock-insights",
}


def test_expected_monitoring_connection_is_required():
    assert verify_monitoring([CONNECTION], "mock-insights") == {
        "application_insights": "mock-insights",
        "check": "connection_configuration_only",
    }


@pytest.mark.parametrize(
    "connections",
    [
        [],
        [{"type": "CognitiveSearch"}],
        [{**CONNECTION, "target": CONNECTION["target"] + "-wrong"}],
    ],
)
def test_wrong_or_missing_monitoring_is_rejected(connections):
    with pytest.raises(ValueError, match="no AppInsights connection"):
        verify_monitoring(connections, "mock-insights")


@pytest.mark.parametrize("name", ["", "<component>", "$(UNRESOLVED)", "path/component"])
def test_unresolved_monitoring_name_is_rejected(name):
    with pytest.raises(ValueError, match="approved component name"):
        verify_monitoring([CONNECTION], name)


def test_new_model_identity_metadata_is_required():
    assert verify_identity(AGENT) == AGENT


@pytest.mark.parametrize("field", ["blueprint", "instance_identity"])
def test_legacy_or_missing_identity_is_rejected(field):
    agent = deepcopy(AGENT)
    del agent[field]
    with pytest.raises(ValueError, match=f"missing {field}"):
        verify_identity(agent)


@pytest.mark.parametrize("field", ["blueprint", "instance_identity"])
@pytest.mark.parametrize("key", ["client_id", "principal_id"])
@pytest.mark.parametrize(
    "value", [None, "", "not-a-uuid", "00000000-0000-0000-0000-000000000000"]
)
def test_incomplete_identity_is_rejected(field, key, value):
    agent = deepcopy(AGENT)
    agent[field][key] = value
    with pytest.raises(ValueError, match=f"{field}.{key}"):
        verify_identity(agent)


@pytest.fixture(params=[prompt_agent, rag_agent])
def creation(request, monkeypatch):
    module = request.param
    monkeypatch.setattr(module, "load_dotenv", lambda *args, **kwargs: False)
    settings = module.Settings.from_environment()
    client = Mock()
    client.connections.list.return_value = [SimpleNamespace(as_dict=lambda: CONNECTION)]
    client.agents.create_version.return_value.as_dict.return_value = {"version": "1"}
    client.agents.get.return_value.as_dict.return_value = AGENT
    return module, client, settings


def test_creation_uses_model_guardrails_and_records_identity(creation):
    module, client, settings = creation
    result = module.create_agent(client, settings)
    client.agents.get.assert_called_once_with(agent_name=settings.agent_name)
    assert result["identity_verification"] == AGENT
    definition = client.agents.create_version.call_args.kwargs["body"]["definition"]
    assert "rai_config" not in definition
    assert definition["model"] == settings.model_deployment_name


def test_missing_project_monitoring_blocks_creation(creation):
    module, client, settings = creation
    client.connections.list.return_value = []
    with pytest.raises(ValueError, match="configure project tracing"):
        module.create_agent(client, settings)
    client.agents.create_version.assert_not_called()


def test_missing_identity_fails_after_creation_without_deletion(creation):
    module, client, settings = creation
    client.agents.get.return_value.as_dict.return_value = {}
    with pytest.raises(ValueError, match="cannot be released"):
        module.create_agent(client, settings)
    client.agents.create_version.assert_called_once()
    client.agents.delete.assert_not_called()


@pytest.mark.parametrize(
    "command,payload",
    [
        (["identity"], AGENT),
        (["monitoring", "--expected-name", "mock-insights"], {"value": [CONNECTION]}),
    ],
)
def test_shared_cli_accepts_rest_metadata(monkeypatch, capsys, command, payload):
    monkeypatch.setattr("sys.argv", ["agent_governance.py", *command])
    monkeypatch.setattr("sys.stdin", StringIO(json.dumps(payload)))
    assert agent_governance.main() == 0
    assert json.loads(capsys.readouterr().out)


@pytest.mark.parametrize(
    "payload", ["[]", '{"value":null}', '{"value":[null]}', "invalid-json"]
)
def test_shared_cli_rejects_malformed_rest_metadata(monkeypatch, payload):
    monkeypatch.setattr(
        "sys.argv",
        ["agent_governance.py", "monitoring", "--expected-name", "mock-insights"],
    )
    monkeypatch.setattr("sys.stdin", StringIO(payload))
    with pytest.raises(SystemExit) as error:
        agent_governance.main()
    assert error.value.code == 2
