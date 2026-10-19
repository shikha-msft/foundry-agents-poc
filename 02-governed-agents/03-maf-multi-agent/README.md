# 03 - Microsoft Agent Framework Multi-Agent

This folder contains a governed multi-agent API built with **Microsoft Agent
Framework (MAF)** and hosted on **Azure App Service for Linux**.

## Architecture

```text
Authenticated caller
        |
        v
Azure App Service + Easy Auth
        |
        v
MAF Magentic workflow
        |
        +-- Prompt Specialist
        |      |
        |      +-- gov-prompt-agent-poc (Foundry managed Prompt Agent)
        |
        +-- Retrieval Specialist
        |      |
        |      +-- gov-rag-agent-poc (Foundry managed RAG Agent)
        |
        +-- Autonomous Manager
               |
               +-- plans, delegates, and synthesizes
                   with bounded rounds and no write tools
```

The App Service system-assigned managed identity authenticates to the
`poc-project`. The remote Prompt and RAG agents retain their own Foundry
managed blueprints and Agent Identities. In particular, Search permissions
remain on the RAG Agent Identity, not on the App Service identity.

## Agent responsibilities

| Agent | Type | Responsibility |
|---|---|---|
| Prompt Specialist | MAF agent with a governed tool | Calls `gov-prompt-agent-poc` for reasoning and drafting |
| Retrieval Specialist | MAF agent with a governed tool | Calls `gov-rag-agent-poc` and preserves citations |
| Autonomous Manager | MAF Magentic manager | Builds a plan, delegates, and synthesizes the final response |

Autonomy is bounded by:

- `MAF_MAX_ROUND_COUNT`, default `6`, maximum `12`.
- `MAF_MAX_STALL_COUNT`, default `2`.
- `MAF_WORKFLOW_TIMEOUT_SECONDS`, default `120`.
- No write, deployment, RBAC, shell, or administrative tools.
- Explicit failure when a remote agent or workflow returns no output.

## Files

| Path | Purpose |
|---|---|
| `app/main.py` | FastAPI endpoints, App Service authentication check, and telemetry startup |
| `app/orchestration.py` | MAF Prompt, RAG, and autonomous Magentic workflow |
| `app/foundry_gateway.py` | Invokes existing Foundry agents with `agent_reference` |
| `app/authentication.py` | Workload identity, managed identity, and Azure CLI authentication |
| `app/configuration.py` | Validated environment configuration and autonomy limits |
| `deploy.ps1` | Idempotent App Service provisioning and ZIP deployment |
| `azure-pipelines.yml` | Workload-federated Azure DevOps validation and deployment |
| `startup.sh` | Gunicorn and Uvicorn App Service startup command |
| `.env.sample` | Complete customer configuration template |
| `tests/` | Configuration, gateway, authentication, and API tests |

## Prerequisites

1. The Foundry project and `gpt-5.4-mini` deployment exist.
2. `gov-prompt-agent-poc` exists and is active.
3. `gov-rag-agent-poc` exists and its exact Agent Identity has **Search Index
   Data Reader** on the approved Search service or index.
4. The App Service managed identity has **Foundry User** on the Foundry
   account or the narrower supported project scope.
5. `appi-agents-poc-aue-poc-project` exists.
6. For authenticated production access, an Entra application registration is
   approved for App Service Easy Auth.

## Run locally

```powershell
cd foundry-agents-poc\02-governed-agents\03-maf-multi-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
az login --tenant 16b3c013-d300-468d-ac64-7eda0820b6d3
python -m uvicorn app.main:app --reload --port 8000
```

The checked-in local `.env` sets `REQUIRE_APP_SERVICE_AUTH=false`. Production
must use Easy Auth and `REQUIRE_APP_SERVICE_AUTH=true`.

Test locally:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/chat `
  -ContentType application/json `
  -Body '{"message":"Summarize the governed onboarding requirements."}'
```

Endpoints:

- `GET /healthz` - process health.
- `GET /readyz` - MAF runtime readiness.
- `POST /api/chat` - authenticated multi-agent execution.

## Deploy to Azure App Service

Choose a globally unique web app name:

```powershell
.\deploy.ps1 `
  -WebAppName "<globally-unique-app-name>" `
  -EntraClientId "<approved-entra-application-client-id>"
```

The script:

1. Creates or updates a Linux B1 App Service plan and Python 3.12 web app.
2. Enables a system-assigned managed identity.
3. Assigns **Foundry User** to that identity.
4. Configures the existing POC Foundry agents and Application Insights.
5. Enables Easy Auth when `EntraClientId` is supplied.
6. Packages only the application, startup command, and runtime requirements.
7. Deploys through App Service ZIP deployment with Oryx build enabled.

For an infrastructure-only preview:

```powershell
.\deploy.ps1 -WebAppName "<app-name>" -WhatIf
```

Do not deploy production without `EntraClientId`. When it is omitted,
`REQUIRE_APP_SERVICE_AUTH` is set to `false` to support local/controlled POC
testing and the endpoint is not suitable for public production use.

## Deploy through Azure DevOps

Create a pipeline from `03-maf-multi-agent/azure-pipelines.yml`.

Pipeline parameters:

| Parameter | Purpose |
|---|---|
| `azureServiceConnection` | Workload-federated ARM service connection |
| `webAppName` | Globally unique App Service name |
| `entraClientId` | Approved Easy Auth application ID |

The service connection identity requires:

- **Contributor** on `rg-foundry-demo` for App Service resources.
- **User Access Administrator** on the Foundry account only to assign
  **Foundry User** to the App Service managed identity.

Configure an approval on the `foundry-poc-maf-app` Azure DevOps environment.
The pipeline has no automatic trigger.

## Observability

When `APPLICATIONINSIGHTS_CONNECTION_STRING` is present,
`azure-monitor-opentelemetry` configures Azure Monitor tracing. Capture:

- Request and dependency duration.
- MAF workflow failures and timeouts.
- Calls from each specialist to its remote Foundry agent.
- Foundry model and Search dependencies.
- Request ID correlation.

Do not log prompt bodies, retrieved documents, credentials, access tokens, or
Easy Auth principal payloads.
