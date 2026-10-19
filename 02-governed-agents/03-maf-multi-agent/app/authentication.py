from __future__ import annotations

import os

from azure.core.credentials import TokenCredential
from azure.identity import (
    AzureCliCredential,
    ManagedIdentityCredential,
    WorkloadIdentityCredential,
)

from .configuration import Settings


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
        process_timeout=int(os.getenv("AZURE_CLI_PROCESS_TIMEOUT", "60")),
    )
