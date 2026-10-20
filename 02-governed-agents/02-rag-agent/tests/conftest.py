import pytest

import rag_agent


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setattr(rag_agent, "load_dotenv", lambda *args, **kwargs: False)
    values = {
        "PROJECT_ENDPOINT": "https://mock.services.ai.azure.com/api/projects/poc",
        "AZURE_TENANT_ID": "11111111-1111-4111-8111-111111111111",
        "MODEL_DEPLOYMENT_NAME": "mock-chat",
        "AGENT_NAME": "mock-rag",
        "APPLICATION_INSIGHTS_RESOURCE_NAME": "mock-insights",
        "AZURE_CLI_PROCESS_TIMEOUT": "60",
        "AZURE_AI_SEARCH_CONNECTION_ID": "/subscriptions/mock/providers/"
        "Microsoft.CognitiveServices/accounts/mock/projects/poc/connections/search",
        "AZURE_AI_SEARCH_INDEX_NAME": "existing-index",
        "AZURE_AI_SEARCH_QUERY_TYPE": "vector_semantic_hybrid",
        "AZURE_AI_SEARCH_TOP_K": "5",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    for key in (
        "AZURE_AI_SEARCH_INDEX_MODE",
        "AZURE_AI_EMBEDDING_ENDPOINT",
        "AZURE_AI_EMBEDDING_DEPLOYMENT_NAME",
        "AZURE_CLIENT_ID",
        "AZURE_FEDERATED_TOKEN_FILE",
        "IDENTITY_ENDPOINT",
        "MSI_ENDPOINT",
    ):
        monkeypatch.delenv(key, raising=False)
