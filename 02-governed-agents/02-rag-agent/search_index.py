from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from azure.ai.projects import AIProjectClient
from azure.core.credentials import TokenCredential
from azure.core.exceptions import ResourceExistsError
from azure.identity import get_bearer_token_provider
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters,
    HnswAlgorithmConfiguration,
    HnswParameters,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from openai import OpenAI

_DIMENSIONS = 1536
_EMBEDDING_MODEL = "text-embedding-3-small"


@dataclass(frozen=True)
class IndexOptions:
    mode: str
    embedding_endpoint: str = ""
    embedding_deployment: str = ""

    @classmethod
    def from_environment(cls, mode: str | None = None) -> IndexOptions:
        selected = (
            mode
            if mode is not None
            else os.getenv("AZURE_AI_SEARCH_INDEX_MODE", "existing")
        ).strip()
        if selected not in ("existing", "create"):
            raise ValueError("AZURE_AI_SEARCH_INDEX_MODE must be existing or create.")
        if selected == "existing":
            return cls(mode=selected)

        endpoint = os.getenv("AZURE_AI_EMBEDDING_ENDPOINT", "").strip()
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or re.fullmatch(r"[A-Za-z0-9.-]+", parsed.hostname) is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path != "/openai/v1/"
        ):
            raise ValueError(
                "Create mode requires AZURE_AI_EMBEDDING_ENDPOINT: "
                "an HTTPS resource endpoint ending /openai/v1/, without "
                "credentials, query parameters or fragments."
            )
        deployment = os.getenv("AZURE_AI_EMBEDDING_DEPLOYMENT_NAME", "").strip()
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", deployment) is None:
            raise ValueError(
                "Create mode requires AZURE_AI_EMBEDDING_DEPLOYMENT_NAME "
                "for a text-embedding-3-small deployment."
            )
        return cls(selected, endpoint, deployment)


def validate_index_name(name: str) -> None:
    if re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,127}", name) is None:
        raise ValueError(
            "The Search index name must be 2-128 lowercase letters, digits, "
            "hyphens or underscores, starting with a letter or digit."
        )


def build_index(name: str, options: IndexOptions) -> SearchIndex:
    return SearchIndex(
        name=name,
        fields=[
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SearchableField(name="title", type=SearchFieldDataType.String),
            SearchableField(name="content", type=SearchFieldDataType.String),
            # The native tool's source projection omits non-searchable URL fields.
            SearchableField(name="url", type=SearchFieldDataType.String),
            SearchField(
                name="contentVector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                hidden=True,
                vector_search_dimensions=_DIMENSIONS,
                vector_search_profile_name="synthetic-vector-profile",
            ),
        ],
        vector_search=VectorSearch(
            algorithms=[
                HnswAlgorithmConfiguration(
                    name="synthetic-hnsw", parameters=HnswParameters(metric="cosine")
                )
            ],
            profiles=[
                VectorSearchProfile(
                    name="synthetic-vector-profile",
                    algorithm_configuration_name="synthetic-hnsw",
                    vectorizer_name="synthetic-openai-vectorizer",
                )
            ],
            vectorizers=[
                AzureOpenAIVectorizer(
                    vectorizer_name="synthetic-openai-vectorizer",
                    parameters=AzureOpenAIVectorizerParameters(
                        resource_url=options.embedding_endpoint.removesuffix(
                            "/openai/v1/"
                        ),
                        deployment_name=options.embedding_deployment,
                        model_name=_EMBEDDING_MODEL,
                    ),
                )
            ],
        ),
        semantic_search=SemanticSearch(
            default_configuration_name="synthetic-semantic",
            configurations=[
                SemanticConfiguration(
                    name="synthetic-semantic",
                    prioritized_fields=SemanticPrioritizedFields(
                        title_field=SemanticField(field_name="title"),
                        content_fields=[SemanticField(field_name="content")],
                    ),
                )
            ],
        ),
    )


def synthetic_documents() -> list[dict[str, Any]]:
    return [
        {
            "id": "SYN-ONB-001",
            "title": "Synthetic Aurora Demo onboarding policy",
            "content": (
                "SYNTHETIC POC DATA ONLY. This is fictitious, not real company policy. "
                "New Aurora Demo team members must complete security induction "
                "within 7 calendar days of joining. Access requests go through "
                "the Aurora Demo Access Desk and require manager approval."
            ),
            "url": "https://example.org/poc/aurora/onboarding",
        },
        {
            "id": "SYN-SUP-001",
            "title": "Synthetic Aurora Demo support policy",
            "content": (
                "SYNTHETIC POC DATA ONLY. This is fictitious, not real company policy. "
                "Aurora Demo support operates Monday to Friday, 09:00 to 17:00 UTC. "
                "Priority 2 requests have a target first response time of "
                "4 business hours."
            ),
            "url": "https://example.org/poc/aurora/support",
        },
        {
            "id": "SYN-RET-001",
            "title": "Synthetic Aurora Demo artifact retention policy",
            "content": (
                "SYNTHETIC POC DATA ONLY. This is fictitious, not real company policy. "
                "Aurora Demo project artifacts are retained for 30 calendar days "
                "after project closure, then removed by the demo platform custodian. "
                "This rule does not govern real company records."
            ),
            "url": "https://example.org/poc/aurora/retention",
        },
    ]


def prepare_index(
    project: AIProjectClient,
    credential: TokenCredential,
    connection_id: str,
    index_name: str,
    options: IndexOptions,
) -> dict[str, Any]:
    validate_index_name(index_name)
    if options.mode == "existing":
        return {"mode": "existing", "index_name": index_name, "status": "supplied"}
    if options.mode != "create":
        raise ValueError("Index mode must be existing or create.")

    connection = project.connections.get(
        name=connection_id.rsplit("/", 1)[-1], include_credentials=False
    )
    if connection.id.casefold() != connection_id.casefold():
        raise ValueError("The Search connection must belong to the configured project.")
    if connection.type != "CognitiveSearch":
        raise ValueError("The configured project connection must be CognitiveSearch.")
    endpoint = connection.target
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "The Search connection target must be an HTTPS service endpoint."
        )

    with SearchIndexClient(endpoint=endpoint, credential=credential) as indexes:
        try:
            indexes.create_index(build_index(index_name, options))
        except ResourceExistsError as error:
            raise ValueError(
                f"Index '{index_name}' already exists. Select existing mode to reuse "
                "it unchanged, or choose a different name. Nothing was overwritten."
            ) from error

    print(
        f"Created synthetic index '{index_name}'. If loading fails, this index is "
        "retained for inspection; no existing index or documents are replaced.",
        file=sys.stderr,
    )
    documents = synthetic_documents()
    with OpenAI(
        base_url=options.embedding_endpoint,
        api_key=get_bearer_token_provider(
            credential, "https://cognitiveservices.azure.com/.default"
        ),
        timeout=60,
        max_retries=0,
    ) as embeddings:
        result = embeddings.embeddings.create(
            model=options.embedding_deployment,
            input=[document["content"] for document in documents],
            dimensions=_DIMENSIONS,
        )
    vectors = {item.index: item.embedding for item in result.data}
    if (
        len(result.data) != len(documents)
        or set(vectors) != set(range(len(documents)))
        or any(len(vector) != _DIMENSIONS for vector in vectors.values())
    ):
        raise ValueError(
            f"Index '{index_name}' was created but embedding output was invalid; "
            f"expected one {_DIMENSIONS}-dimension vector per synthetic document."
        )
    for number, document in enumerate(documents):
        document["contentVector"] = vectors[number]
    with SearchClient(
        endpoint=endpoint, index_name=index_name, credential=credential
    ) as search:
        uploaded = search.upload_documents(documents=documents)
    if len(uploaded) != len(documents) or any(not item.succeeded for item in uploaded):
        failures = "; ".join(
            f"{item.key}: {item.error_message}"
            for item in uploaded
            if not item.succeeded
        )
        raise ValueError(
            f"Index '{index_name}' was created but synthetic ingestion failed: "
            f"{failures or 'incomplete indexing response'}. Inspect before retrying."
        )
    return {
        "mode": "create",
        "index_name": index_name,
        "status": "created",
        "synthetic_documents_accepted": len(uploaded),
    }
