# 04 - Microsoft Agent Framework Multi-Agent

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
Azure App Service (Easy Auth optional for controlled PoC)
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

All infrastructure and platform grants must already be supplied by customer
IaC/the platform team. Complete the
[customer prerequisite tables](../../CUSTOMER-PREREQUISITES.md), including:

| Area | Required existing state |
|---|---|
| Foundry V2 | Governed project/endpoint, approved model deployment and project monitoring |
| Remote agents | Active Prompt/RAG definitions; RAG tool principal verified with approved Search reader access |
| Host | Linux Python 3.12 web app/plan, system-assigned MI, startup/build/health configuration |
| PoC access | Easy Auth not required; if omitted, empty `ENTRA_CLIENT_ID`, `REQUIRE_APP_SERVICE_AUTH=false`, and approved network restrictions |
| Runtime RBAC | App Service MI Foundry access; separate actual retrieval-principal Search access |
| Agent ID | Platform-approved custom blueprint, Blueprint Principal, agent identity, grants and MI federation |
| Agent 365 | Licensing, tenant consent, orchestrator registration, exporter settings and delivery evidence |
| Operations | Network/DNS/feed access, monitoring configuration, redaction and scoped package-deployment permissions |

For a controlled PoC, Easy Auth and its app registration are optional. Without
it, use the settings below and verify platform Authentication is not still
requiring login:

```dotenv
ENTRA_CLIENT_ID=
REQUIRE_APP_SERVICE_AUTH=false
```

These are explicit PoC overrides; templates/code retain authentication-enabled
defaults for direct application startup. The test deployment helper/pipeline
now explicitly defaults Easy Auth **off** and sets both platform authentication
and the application check to match. Restrict the endpoint to approved networks; do not publicly expose an
unauthenticated API. Production must use authentication. App Service MI,
Agent ID and Agent 365 service authentication remain separate and unchanged.

## Run locally

From the PoC checkout root:

```powershell
cd .\02-governed-agents\04-maf-multi-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.sample .env
# Populate .env; set REQUIRE_APP_SERVICE_AUTH=false for local/controlled PoC use.
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

## Customer application delivery

Use the customer's approved package-only delivery pipeline to the existing web
app. Platform teams own the infrastructure, identities, role assignments, Easy
Auth and runtime configuration. Application developers do not need resource-
group Contributor or role-assignment authority for routine code delivery.

The bundled MAF pipeline defaults to **package-only** delivery with
`provisionInfrastructure=false` and `provisionAgent365=false`.
[`deploy-package.ps1`](./deploy-package.ps1) validates platform configuration
and deploys only the application ZIP. It does not create resources, assign
roles, configure Easy Auth, change app settings, or register agents.

The host must already have its system-assigned MI, custom blueprint/agent
client IDs and Application Insights configuration. Agent Identity is required
even when Agent 365 is off; when on, the script also validates the S2S exporter
configuration. These are metadata/configuration checks, not proof of directory
state, token exchange, guardrail enforcement or telemetry delivery.
Startup/build settings and authentication/network restrictions remain platform
prerequisites. The combined helper below is now explicit author/test opt-in.

AKS is a target hosting alternative, not a deployed option in this kit.
See the [platform operating model](../../PLATFORM-OPERATING-MODEL.md#6-hosting-and-identity-coverage)
for its additional workload identity/exporter and deployment requirements.

## Test environment only: deploy to Azure App Service

The following helper is retained for the author's own test environment, not
customer infrastructure setup.

Set `WEB_APP_NAME` and the remaining required test settings in the ignored
`.env`. Easy Auth is an optional feature, **off by default**:

```powershell
# Controlled PoC: disables platform Easy Auth and the application auth check.
.\deploy.ps1

# Opt in: requires an approved non-empty application client GUID.
.\deploy.ps1 -EnableEasyAuth -EntraClientId "<application-client-guid>"
```

The opt-in can also read `ENTRA_CLIENT_ID` from configuration. Supplying a
client ID alone no longer enables the feature. Enabling it with a missing,
placeholder or invalid client ID fails before Azure changes.
**Default/off deployment explicitly disables existing platform Easy Auth**;
do not run this PoC helper over an authenticated production app.

The script:

1. Creates or updates the configured Linux App Service plan and Python 3.12 web app.
2. Enables a system-assigned managed identity.
3. Assigns **Foundry User** to that identity.
4. Configures the existing POC Foundry agents and Application Insights.
5. Enables Easy Auth only with `-EnableEasyAuth`; otherwise explicitly disables it.
6. Packages only the application, startup command, and runtime requirements.
7. Deploys through App Service ZIP deployment with Oryx build enabled.

For an infrastructure-only preview:

```powershell
.\deploy.ps1 -WhatIf
```

Use the optional feature only within the intended access model. Off mode sets
`REQUIRE_APP_SERVICE_AUTH=false` for controlled PoC testing and is unsuitable
for public production use. Production must retain authentication.

Run isolated deployment tests (no Azure access or real dotenv files used):

```powershell
.\tests\test_deployment.ps1
```

## Register with Microsoft Agent 365

For customer onboarding, registration, consent, federation and export settings
are existing platform/identity prerequisites. The commands below document the
author/test helper; customers consume approved IDs/settings and verify delivery
rather than rerunning setup.

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

The bundled pipeline uses package-only delivery by default. Select
`provisionInfrastructure=true` only in the author's approved test environment
to use the combined helper. Package deployment needs scoped web-app delivery
and configuration-read rights; it does not need resource-group Contributor or
role-assignment authority. The infrastructure permissions below apply only to
the explicit test provisioning mode.

Pipeline configuration is read from the
`foundry-agents-poc-environment` Azure DevOps variable group:

| Variable | Purpose |
|---|---|
| `ADO_APP_SERVICE_CONNECTION` | Workload-federated ARM service connection |
| `WEB_APP_NAME` | Globally unique App Service name |
| `ENTRA_CLIENT_ID` | Optional for controlled PoC; leave empty when Easy Auth is omitted |
| `ADO_AGENT365_SERVICE_CONNECTION` | Connection used only by the approved Agent 365 stage |
| `ADO_AGENT365_ENVIRONMENT_NAME` | Approval-protected Agent 365 environment |

Queue-time parameter `enableEasyAuth` defaults to `false` and applies only
when `provisionInfrastructure=true`. In that test mode it controls both
platform authentication and the application's auth check and requires
`ENTRA_CLIENT_ID` when enabled. Package-only delivery does not change existing
authentication, even with the default false parameter. The platform must
preconfigure the approved PoC or production boundary.

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
