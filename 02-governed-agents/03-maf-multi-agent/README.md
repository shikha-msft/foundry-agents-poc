# 03 - Microsoft Agent Framework Multi-Agent

This folder contains a governed multi-agent API built with **Microsoft Agent
Framework (MAF)** and hosted on **Azure App Service for Linux**.

For a new customer environment, follow the
[customer runbook](../../CUSTOMER-HANDOVER.md) first. Foundry Hosted Agents
are not a prerequisite. Agent 365 unattended setup remains gated on the
customer authentication/consent tests in that runbook.

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
configured by `PROJECT_ENDPOINT`. Verify the remote agents' new/legacy identity
model and Search connection authentication before granting data access. For an
Agent ID-aware RAG tool, Search permissions belong on its verified Agent
Identity, not the App Service identity.

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
| `app/agent365.py` | Secretless Agent 365 token exchange and Microsoft OpenTelemetry invocation scopes |
| `app/configuration.py` | Validated environment configuration and autonomy limits |
| `deploy.ps1` | Idempotent App Service provisioning and ZIP deployment |
| `azure-pipelines.yml` | Workload-federated Azure DevOps validation and deployment |
| `startup.sh` | Gunicorn and Uvicorn App Service startup command |
| `.env.sample` | Complete customer configuration template |
| `tests/` | Configuration, gateway, authentication, and API tests |

## Prerequisites

1. The Foundry project and `MODEL_DEPLOYMENT_NAME` deployment exist.
2. `PROMPT_AGENT_NAME` exists and is active.
3. `RAG_AGENT_NAME` exists and its verified retrieval principal has **Search
   Index Data Reader** on the approved supported Search scope.
4. The App Service managed identity has **Foundry User** on the Foundry
   account or the narrower supported project scope.
5. `GOVERNED_APPLICATION_INSIGHTS_NAME` exists.
6. For authenticated production access, an Entra application registration is
   approved for App Service Easy Auth.
7. For Agent 365, the tenant has an active license and completed consent, and
   the provisioning administrator has the required Agent ID roles plus
   `AgentIdentityBlueprint.AddRemoveCreds.All` to federate the App Service
   managed identity with the MAF Agent Identity blueprint.

## Run locally

From the PoC checkout root:

```powershell
cd .\02-governed-agents\03-maf-multi-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.sample .env
# Populate .env; set REQUIRE_APP_SERVICE_AUTH=false for local development only.
az login
python -m uvicorn app.main:app --reload --port 8000
```

Configure the copied `.env` before starting Uvicorn. The populated file is
ignored by Git. Production must use
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

## Register with Microsoft Agent 365

The MAF application is registered once as an S2S orchestrator. The Prompt and
Retrieval specialists are not separate Agent 365 registrations because they
delegate to the existing remote Foundry agents.

After deploying App Service, from this MAF folder return to the PoC root
(install the CLI only if it is not already installed):

```powershell
cd ..\..
dotnet tool install --global Microsoft.Agents.A365.DevTools.Cli
.\provision-agent365.ps1 -Scope Maf -WhatIf
.\provision-agent365.ps1 -Scope Maf
```

The provisioning script:

1. Verifies the App Service system-assigned managed identity.
2. Runs Agent 365 prerequisite validation.
3. Creates the MAF blueprint, Agent Identity, S2S grants, and registration.
4. Preserves the App Service managed identity as the secretless bootstrap
   identity for federated token exchange.
5. Configures `A365_BLUEPRINT_CLIENT_ID`, `A365_AGENT_CLIENT_ID`, and the
   Agent 365 exporter settings on App Service.

This is the intended setup sequence, not evidence of tenant validation.
The CLI may need separate configuration/interactive authentication;
`AzureCLI@2` does not establish that it can run unattended. Federation currently
uses Azure CLI Graph calls, whose token/endpoint compatibility must be verified.
Follow the [administrator setup and automation gate](../../CUSTOMER-HANDOVER.md#8-agent-365-admin-setup-before-pipeline-automation).
MAF `-WhatIf` invokes the CLI's dry-run path and still needs installed tools,
supported flags and authenticated read access.

Do not copy the generated blueprint secret into source control or App Service
settings. Runtime export uses the App Service managed identity, the blueprint
federated trust, and the Agent Identity `fmi_path` exchange.
This flow authenticates **Agent 365 telemetry**. Calls to Foundry still use
the App Service managed identity. The in-process specialist wrappers do not
each receive a separate Agent 365 registration.

## Deploy through Azure DevOps

Create a pipeline from `03-maf-multi-agent/azure-pipelines.yml`.

Pipeline configuration is read from the
`foundry-agents-poc-environment` Azure DevOps variable group:

| Variable | Purpose |
|---|---|
| `ADO_APP_SERVICE_CONNECTION` | Workload-federated ARM service connection |
| `WEB_APP_NAME` | Globally unique App Service name |
| `ENTRA_CLIENT_ID` | Approved Easy Auth application ID |
| `ADO_AGENT365_SERVICE_CONNECTION` | Connection used only by the approved Agent 365 stage |
| `ADO_AGENT365_ENVIRONMENT_NAME` | Approval-protected Agent 365 environment |

The service connection identity requires:

- **Contributor** on `AZURE_RESOURCE_GROUP` for App Service resources.
- **User Access Administrator** on the Foundry account only to assign
  **Foundry User** to the App Service managed identity.

Configure approvals on the environments named by `ADO_MAF_ENVIRONMENT_NAME`
and `ADO_AGENT365_ENVIRONMENT_NAME`. The pipeline has no automatic trigger.

The YAML supports `linuxPoolName` and `windowsPoolName` (both default to
`Microsoft-hosted`), plus `pocDirectory` (default `.`). Set OS-specific pool
names for self-hosted execution; use `pocDirectory=foundry-agents-poc` only for
a parent-repository checkout. See the [self-hosted setup](../../CUSTOMER-HANDOVER.md#7-azure-devops-and-self-hosted-vms)
for tools, Python tool cache, networking and service-account requirements.

Keep `provisionAgent365: false` until the actual unattended CLI/Graph principal
passes the runbook's acceptance gate. An ADO approval alone does not grant
Graph permissions or tenant consent. The normal deployment path leaves
Agent 365 unchanged.

## Observability

Microsoft OpenTelemetry configures Azure Monitor when
`APPLICATIONINSIGHTS_CONNECTION_STRING` is present. When Agent 365 is enabled,
the same distro adds an Agent 365 `invoke_agent` scope and exports through the
S2S endpoint. Capture:

- Request and dependency duration.
- MAF workflow failures and timeouts.
- Calls from each specialist to its remote Foundry agent.
- Foundry model and Search dependencies.
- Request ID correlation.

Do not log prompt bodies, retrieved documents, credentials, access tokens, or
Easy Auth principal payloads.

`A365_SUPPRESS_INVOKE_AGENT_INPUT=true` is mandatory in this starter kit.
Agent 365 token acquisition fails closed when the requested tenant or Agent
Identity does not match the approved configuration.
