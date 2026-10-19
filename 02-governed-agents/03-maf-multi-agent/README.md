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
        |      +-- PROMPT_AGENT_NAME (Foundry managed Prompt Agent)
        |
        +-- Retrieval Specialist
        |      |
        |      +-- RAG_AGENT_NAME (Foundry managed RAG Agent)
        |
        +-- Autonomous Manager
               |
               +-- plans, delegates, and synthesizes
                   with bounded rounds and no write tools
```

The App Service system-assigned managed identity authenticates to the project
configured by `PROJECT_ENDPOINT`. The remote Prompt and RAG agents retain their own Foundry
managed blueprints and Agent Identities. In particular, Search permissions
remain on the RAG Agent Identity, not on the App Service identity.

## Agent responsibilities

| Agent | Type | Responsibility |
|---|---|---|
| Prompt Specialist | MAF agent with a governed tool | Calls `PROMPT_AGENT_NAME` for reasoning and drafting |
| Retrieval Specialist | MAF agent with a governed tool | Calls `RAG_AGENT_NAME` and preserves citations |
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

1. The Foundry project and `MODEL_DEPLOYMENT_NAME` deployment exist.
2. `PROMPT_AGENT_NAME` exists and is active.
3. `RAG_AGENT_NAME` exists and its exact Agent Identity has **Search Index
   Data Reader** on the approved Search service or index.
4. The App Service managed identity has **Foundry User** on the Foundry
   account or the narrower supported project scope.
5. `GOVERNED_APPLICATION_INSIGHTS_NAME` exists.
6. For authenticated production access, an Entra application registration is
   approved for App Service Easy Auth.

## Run locally

```powershell
cd foundry-agents-poc\02-governed-agents\03-maf-multi-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
az login
python -m uvicorn app.main:app --reload --port 8000
```

Copy `.env.sample` to `.env` and set `REQUIRE_APP_SERVICE_AUTH=false` only for
local development. The populated `.env` is ignored by Git. Production must use
Easy Auth and `REQUIRE_APP_SERVICE_AUTH=true`.

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

Set `WEB_APP_NAME` and `ENTRA_CLIENT_ID` in the ignored `.env`, then run:

```powershell
.\deploy.ps1
```

The script:

1. Creates or updates the configured Linux App Service plan and Python 3.12 web app.
2. Enables a system-assigned managed identity.
3. Assigns **Foundry User** to that identity.
4. Configures the existing POC Foundry agents and Application Insights.
5. Enables Easy Auth when `EntraClientId` is supplied.
6. Packages only the application, startup command, and runtime requirements.
7. Deploys through App Service ZIP deployment with Oryx build enabled.

For an infrastructure-only preview:

```powershell
.\deploy.ps1 -WhatIf
```

Do not deploy production without `EntraClientId`. When it is omitted,
`REQUIRE_APP_SERVICE_AUTH` is set to `false` to support local/controlled POC
testing and the endpoint is not suitable for public production use.

## Deploy through Azure DevOps

Create a pipeline from `03-maf-multi-agent/azure-pipelines.yml`.

Pipeline configuration is read from the
`foundry-agents-poc-environment` Azure DevOps variable group:

| Variable | Purpose |
|---|---|
| `ADO_APP_SERVICE_CONNECTION` | Workload-federated ARM service connection |
| `WEB_APP_NAME` | Globally unique App Service name |
| `ENTRA_CLIENT_ID` | Approved Easy Auth application ID |

The service connection identity requires:

- **Contributor** on `AZURE_RESOURCE_GROUP` for App Service resources.
- **User Access Administrator** on the Foundry account only to assign
  **Foundry User** to the App Service managed identity.

Configure an approval on the Azure DevOps environment selected by the pipeline
parameter. The pipeline has no automatic trigger.

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
