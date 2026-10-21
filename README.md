# Microsoft Foundry V2 agent POC

This proof of concept runs agents against **pre-existing customer infrastructure**
provided through customer IaC or the platform team. The two-project layout is:

| Configuration variable | Display-name variable | Intended use |
|---|---|---|
| `EXPERIMENTATION_PROJECT_NAME` | `EXPERIMENTATION_PROJECT_DISPLAY_NAME` | NoCode Experimentation Agents |
| `GOVERNED_PROJECT_NAME` | `GOVERNED_PROJECT_DISPLAY_NAME` | Governed POC Agents development |

## Implementation guides

- **[Platform operating model: POC to governed agents](./PLATFORM-OPERATING-MODEL.md)** -
  centrally managed controls, inheritance boundaries, self-service data/indexes,
  Agent Identity for every agent and opt-in Agent 365.
- **[All-agent prerequisites: common and per-agent](./AGENT-PREREQUISITES-README.md)** -
  grouped no-code and governed agent requirements, providers, RBAC, Entra ID,
  Microsoft Graph and Agent 365.
- **[Customer prerequisite tables](./CUSTOMER-PREREQUISITES.md)** - required
  resources, providers, RBAC, networking, Entra Agent ID and Agent 365 readiness.
- **[Start here: customer setup and handover runbook](./CUSTOMER-HANDOVER.md)** -
  ordered setup, persona/permission matrix, self-hosted ADO, identity checks,
  Agent 365 approval gates, acceptance evidence, troubleshooting and rollback.
- [NoCode Experimentation Agents](./01-experimentation-agents/README.md)
- [Governed POC Agents](./02-governed-agents/README.md)
- [Multimodal text-to-speech and speech-to-text HTTP API](./02-governed-agents/03-multimodal-tts-agent/README.md)
- [Microsoft Agent Framework Multi-Agent App](./02-governed-agents/04-maf-multi-agent/README.md)
- [Agent 365: concepts, onboarding and operations](./agent-365/README.md)
- [Entra Agent Identity: blueprints, permissions and token flow](./agent-identity/README.md)

The PowerShell provisioning scripts are **author/test-environment helpers**,
not customer infrastructure deployment instructions. Customers should already
have the following baseline through their platform process:

- A system-assigned managed identity.
- A dedicated Log Analytics workspace.
- A workspace-based Application Insights component.
- A project-level `AppInsights` connection.
- Project MI `Foundry User` on the parent Foundry account.
- Approved project MI monitoring access (the reference helper assigns
  `Log Analytics Reader` and `Privileged Monitoring Data Reader` on Insights).

**The helpers can modify existing resources and shared account settings.**
Do not run them against customer-managed infrastructure merely to onboard an
application. Agent 365 collection affects all covered projects/Prompt agents.

## Environment configuration

Copy the customer-safe template and populate the local configuration:

```powershell
Copy-Item .env.sample .env
```

Use **POC Project** as the experimentation display name. Governed teams request
access to an existing approved project or a new platform-onboarded one; update
their endpoint/variable group rather than assuming one fixed governed project.
The platform supplies project monitoring and approved model-deployment
guardrails before team access. This is not universal resource-level inheritance:
see the [control-scope matrix](./PLATFORM-OPERATING-MODEL.md#2-what-actually-flows-down).

The root `.env` contains the subscription, tenant, resource group, Foundry
account, project, monitoring, Search, and App Service names for the selected
environment. It is excluded by `.gitignore`; never commit it. `.env.sample`
contains placeholders only and remains safe to share.

The script validates that the account is an `AIServices` account, is in the
expected region, and has Foundry project management enabled.

## Prerequisites

**All infrastructure, provider registrations and platform grants are customer
prerequisites.** The full [prerequisite tables](./CUSTOMER-PREREQUISITES.md)
include exact resources, principals, scopes, owners and conditional requirements.

| Area | Must already be ready | Responsible team |
|---|---|---|
| Foundry V2 | `AIServices` account with project management enabled; experimentation/governed projects and MIs; approved model deployment/quota | Platform/AI |
| Observability | Both Log Analytics workspaces, workspace-based Insights components, project connections, tracing and approved monitoring access | Platform/operations |
| RAG | Search service, project connection and approved retrieval-principal access; reuse a populated index by default, or explicitly create a synthetic PoC index using the [RAG index options](./02-governed-agents/02-rag-agent/README.md#choose-an-existing-index-or-create-a-synthetic-index) and pre-approved setup/embedding permissions | Data/platform |
| Audio API | OpenAI-compatible audio endpoint, separate TTS/transcription deployments, runtime model permissions and approved audio-data policy; no separate Speech resource | Platform/AI |
| MAF | Existing Linux Python 3.12 App Service/plan, MI and app settings; Easy Auth optional for controlled PoC, with approved network restrictions if omitted | Platform/identity |
| Resource providers | CognitiveServices, Insights, OperationalInsights, Authorization; Search/Web for selected capabilities; conditional providers listed in the full matrix | Platform |
| RBAC | Foundry developer/runtime roles, Search data roles, monitoring roles and application-deployment rights at exact approved scopes | Platform/data/identity |
| Entra Agent ID | Tenant support, approved provisioning authority/consent, identity ownership, custom MAF blueprint/principal/agent and MI trust; Foundry creates its own managed objects with new agents | Identity |
| Agent 365 | Licensing, tenant consent, account-wide/residency approval, platform-enabled Foundry collection, custom MAF registration/grants and export settings | Agent 365/identity/platform |
| Network/ADO | Approved routes/private DNS/egress, package feeds, application WIF connections, pools, variables and protected environments | Network/ADO |

Classic hub-based projects are not supported. Use the project endpoint
`https://<account-name>.services.ai.azure.com/api/projects/<project-name>`.
Agent developers do not need general resource-creation or role-assignment
authority merely because the author uses provisioning helpers in a test tenant.

Confirm the customer's network configuration before deployment. The script
does not change the shared account's public/private network settings or
provision private connectivity.

## Test environment only: infrastructure helper

The commands below are retained for the author's own test environment.
**Customer onboarding starts with the prerequisite tables, not these commands.**
The helper creates/updates projects, monitoring, connections, providers and RBAC.

From `foundry-agents-poc`:

```powershell
.\deploy.ps1
```

To validate prerequisites and show the actions without creating resources:

```powershell
.\deploy.ps1 -WhatIf
```

Command-line parameters can override values loaded from `.env`:

```powershell
.\deploy.ps1 `
  -SubscriptionId "<subscription-id>" `
  -ResourceGroupName "<resource-group>" `
  -FoundryAccountName "<foundry-account>" `
  -Location "<azure-region>"
```

The script is idempotent: it uses PUT operations for resources and skips role
assignments that already exist. It writes non-secret resource identifiers to
`deployment-output.json`.

## Microsoft Agent 365 provisioning

For customers, licensing, consent, registration, federation and platform
configuration are pre-established by the platform/identity team. The following
commands document **test helpers**, not mandatory customer setup steps.
See the [Agent 365 prerequisite table](./CUSTOMER-PREREQUISITES.md#6-agent-365-prerequisites).

Agent 365 is opt-in because it requires tenant licensing, tenant consent, and
privileged Entra permissions that are not granted to normal agent developers.

The integration follows the supported hosting model:

- The Foundry resource uses built-in Agent 365 integration. Setting
  `a365LoggingEnabled=true` applies to every project and Prompt Agent in the
  resource, including experimentation, Prompt, and RAG agents. Foundry does
  not provide a per-project or per-agent override.
- The App Service-hosted MAF application is registered once as a standard S2S
  Agent 365 orchestrator. Its in-process Prompt and Retrieval specialists are
  not registered again because they delegate to the separately inventoried
  remote Prompt and RAG agents.
- Microsoft OpenTelemetry exports MAF invocation telemetry without recording
  prompt or response bodies.

Prerequisites:

The following are administrator prerequisites, not proof that an unattended
service connection can run the Agent 365 CLI. Follow the
[Graph/authentication and automation gates](./CUSTOMER-HANDOVER.md#8-agent-365-admin-setup-before-pipeline-automation)
before enabling MAF registration in ADO.

1. Agent 365 is licensed and enabled in the Entra tenant.
2. Tenant-level Agent 365 consent is complete.
3. The administrator running setup has Azure **Contributor**, **Agent ID
   Developer**, and, for S2S grants, **Agent ID Administrator** or the
   documented higher role. The identity must also be allowed to add federated
   credentials to Agent Identity blueprints
   (`AgentIdentityBlueprint.AddRemoveCreds.All`).
4. The Agent 365 CLI is installed:

   ```powershell
   dotnet tool install --global Microsoft.Agents.A365.DevTools.Cli
   ```

5. The MAF App Service is deployed with its system-assigned managed identity
   before MAF registration.

Preview both provisioning paths:

```powershell
.\provision-agent365.ps1 -Scope All -WhatIf
```

Enable and validate Foundry integration:

```powershell
.\provision-agent365.ps1 -Scope Foundry
```

Register the MAF orchestrator, establish its S2S identity configuration, and
configure the App Service:

```powershell
.\provision-agent365.ps1 -Scope Maf
```

The script fails if Foundry reports `Disabled` or `NotLicensed`. Generated
Agent 365 configuration can contain credentials, so
`a365.generated.config.json` and `agent365-provisioning-output.json` are
excluded from Git.

## Azure DevOps pipeline

[`azure-pipelines.yml`](./azure-pipelines.yml) includes application stages and
optional author/test-environment provisioning stages:

1. Validate and compile the standalone Prompt/RAG agents and test the audio API.
2. Optionally run the idempotent `deploy.ps1` infrastructure provisioning.
3. Create a new Prompt Agent version, RAG Agent version, or both.
4. Publish the Foundry creation responses as a pipeline artifact.

The pipeline has no automatic trigger because every successful agent creation
produces a new immutable version. Run it manually and select:

| Parameter | Default | Purpose |
|---|---:|---|
| `provisionInfrastructure` | `false` | Author/test helper only; keep false for customer pre-existing infrastructure |
| `createPromptAgent` | `true` | Create a new `PROMPT_AGENT_NAME` version |
| `createRagAgent` | `false` | Create a new `RAG_AGENT_NAME` version |
| `ragIndexMode` | `existing` | Reference a supplied index unchanged, or explicitly select `create` to create and seed a synthetic PoC index |
| `ragIndexName` | `$(AZURE_AI_SEARCH_INDEX_NAME)` | Supplied or new index name; defaults to the approved environment variable group |
| `enableAgent365Foundry` | `false` | Test/platform change stage; keep false when customer platform has configured collection |
| `linuxPoolName` | `Microsoft-hosted` | Linux self-hosted pool, or hosted Ubuntu by default |
| `windowsPoolName` | `Microsoft-hosted` | Windows self-hosted pool, or hosted Windows by default |
| `pocDirectory` | `.` | PoC path relative to the checkout root; use `foundry-agents-poc` for a parent-repository checkout |

### Pipeline setup

1. Create the Azure DevOps variable group named
   `foundry-agents-poc-environment` using the variables listed in
   `.env.sample`.
2. Create an Azure Resource Manager service connection using **workload
   identity federation** and set its name in the variable group's
   `ADO_AGENT_SERVICE_CONNECTION`. Do not create a client secret.
3. Grant its identity **Foundry User** on the project identified by
   `GOVERNED_PROJECT_NAME` for agent creation.
4. **Author/test environment only:** if the pipeline will provision infrastructure, create a separate
   workload-federated connection and set its name in
   `ADO_INFRASTRUCTURE_SERVICE_CONNECTION`. Grant its identity
   **Contributor** on
   `AZURE_RESOURCE_GROUP` and **User Access
   Administrator** only on the scopes where `deploy.ps1` creates role
   assignments.
5. Set `ADO_AGENT_ENVIRONMENT_NAME` to the approved application environment.
   `ADO_INFRASTRUCTURE_ENVIRONMENT_NAME` is for the optional test helper stage,
   not a requirement to provision customer infrastructure from this repository.
6. Only for an approved test/platform Agent 365 change, configure `ADO_AGENT365_SERVICE_CONNECTION` and
   `ADO_AGENT365_ENVIRONMENT_NAME`. Protect the environment with an Agent 365
   administrator approval.
7. Create a pipeline from `azure-pipelines.yml` for a standalone PoC repository,
   or `foundry-agents-poc/azure-pipelines.yml` in a parent checkout (set
   `pocDirectory` accordingly). For self-hosted agents, complete the
   [OS-specific pool and tool setup](./CUSTOMER-HANDOVER.md#7-azure-devops-and-self-hosted-vms).

The pipeline authenticates with `AzureCLI@2`; the Python SDK then uses that
federated Azure CLI session. It does not upload either local `.env` file and
does not require stored Azure client secrets.

After a RAG Agent version is created, resolve the agent-level identity and
verify the Search connection's actual retrieval principal before granting
**Search Index Data Reader**. A version response may not contain all identity
fields. Follow the [identity checks](./CUSTOMER-HANDOVER.md#53-resolve-the-blueprintidentity-model-before-granting-roles).
The pipeline service identity and runtime retrieval identity are different.

The supplied MAF pipeline still calls a **combined infrastructure/configuration/
package deployment script**. `provisionAgent365=false` does not make that pipeline
package-only. Customers should deploy the application through their own approved
delivery pipeline to the existing web app; do not grant infrastructure/RBAC
administration simply to run the reference MAF pipeline unchanged.

Easy Auth is an optional MAF test-deployment feature: pipeline parameter
`enableEasyAuth` defaults to `false`; `true` requires `ENTRA_CLIENT_ID`.
The test helper's equivalent is `-EnableEasyAuth`. Off mode explicitly disables
platform Easy Auth and the application's auth check, including on an existing
app. Use only within the approved controlled-PoC network boundary.

## Customer acceptance

Documentation is not a tenant deployment certification. Complete the
[clean-environment acceptance checklist](./CUSTOMER-HANDOVER.md#10-acceptance-expected-results-not-just-successful-commands)
and retain restricted evidence before customer sign-off. The PoC does not yet
wire in the separate shared harness or automated safety/evaluation gates.

For local agent creation, the governed-agent kit also supports Azure CLI REST
and `azd`-authenticated REST. See the
[governed-agent creation options](./02-governed-agents/README.md#agent-creation-options).
