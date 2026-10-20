# Microsoft Foundry V2 agent POC

This proof of concept uses Azure CLI commands to create two Microsoft Foundry
V2 projects under an existing Foundry account:

| Configuration variable | Display-name variable | Intended use |
|---|---|---|
| `EXPERIMENTATION_PROJECT_NAME` | `EXPERIMENTATION_PROJECT_DISPLAY_NAME` | NoCode Experimentation Agents |
| `GOVERNED_PROJECT_NAME` | `GOVERNED_PROJECT_DISPLAY_NAME` | Governed POC Agents development |

## Implementation guides

- **[Start here: customer setup and handover runbook](./CUSTOMER-HANDOVER.md)** -
  ordered setup, persona/permission matrix, self-hosted ADO, identity checks,
  Agent 365 approval gates, acceptance evidence, troubleshooting and rollback.
- [NoCode Experimentation Agents](./01-experimentation-agents/README.md)
- [Governed POC Agents](./02-governed-agents/README.md)
- [Microsoft Agent Framework Multi-Agent App](./02-governed-agents/03-maf-multi-agent/README.md)
- [Agent 365: concepts, onboarding and operations](./agent-365/README.md)
- [Entra Agent Identity: blueprints, permissions and token flow](./agent-identity/README.md)

The base project deployment references the existing Foundry account without
changing its account settings. **Optional Agent 365 setup does modify the
shared account** and affects all its projects/Prompt Agents. Each project receives:

- A system-assigned managed identity.
- A dedicated Log Analytics workspace.
- A workspace-based Application Insights component.
- A project-level `AppInsights` connection.
- `Foundry User` on the parent Foundry account.
- `Log Analytics Reader` and `Privileged Monitoring Data Reader` on its
  Application Insights component.

## Environment configuration

Copy the customer-safe template and populate the local configuration:

```powershell
Copy-Item .env.sample .env
```

The root `.env` contains the subscription, tenant, resource group, Foundry
account, project, monitoring, Search, and App Service names for the selected
environment. It is excluded by `.gitignore`; never commit it. `.env.sample`
contains placeholders only and remains safe to share.

The script validates that the account is an `AIServices` account, is in the
expected region, and has Foundry project management enabled.

## Prerequisites

**Microsoft Foundry V2 is required.** Before running this kit, the customer
must have an existing Microsoft Foundry resource (`AIServices` account) with
Foundry project management enabled in the selected region. Classic hub-based
Azure AI Foundry projects are not supported by this kit. The base deployment
creates projects under that resource; it does not create or migrate the parent
Foundry account. Agent creation also requires an approved model deployment and
a project endpoint in the form
`https://<account-name>.services.ai.azure.com/api/projects/<project-name>`.

1. Azure CLI authenticated to the tenant configured by `AZURE_TENANT_ID`.
2. Permission to create resources in the resource group configured by
   `AZURE_RESOURCE_GROUP`.
3. Permission to create role assignments on the existing Foundry account and
   the new Application Insights components.
4. Registered resource providers:
   - `Microsoft.CognitiveServices`
   - `Microsoft.Insights`
   - `Microsoft.OperationalInsights`
   - `Microsoft.Authorization`

Confirm the customer's network configuration before deployment. The script
does not change the shared account's public/private network settings or
provision private connectivity.

## Run

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

[`azure-pipelines.yml`](./azure-pipelines.yml) can run the complete workflow
through an Azure DevOps pipeline:

1. Validate and compile both standalone agent implementations.
2. Optionally run the idempotent `deploy.ps1` infrastructure provisioning.
3. Create a new Prompt Agent version, RAG Agent version, or both.
4. Publish the Foundry creation responses as a pipeline artifact.

The pipeline has no automatic trigger because every successful agent creation
produces a new immutable version. Run it manually and select:

| Parameter | Default | Purpose |
|---|---:|---|
| `provisionInfrastructure` | `false` | Run `deploy.ps1` before creating agents |
| `createPromptAgent` | `true` | Create a new `PROMPT_AGENT_NAME` version |
| `createRagAgent` | `false` | Create a new `RAG_AGENT_NAME` version |
| `enableAgent365Foundry` | `false` | Enable and validate built-in Agent 365 integration on the Foundry resource |
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
4. If the pipeline will provision infrastructure, create a separate
   workload-federated connection and set its name in
   `ADO_INFRASTRUCTURE_SERVICE_CONNECTION`. Grant its identity
   **Contributor** on
   `AZURE_RESOURCE_GROUP` and **User Access
   Administrator** only on the scopes where `deploy.ps1` creates role
   assignments.
5. Set `ADO_INFRASTRUCTURE_ENVIRONMENT_NAME` and
   `ADO_AGENT_ENVIRONMENT_NAME` to the approved Azure DevOps environment
   names, then configure their approvals and checks.
6. For Agent 365, configure `ADO_AGENT365_SERVICE_CONNECTION` and
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

## Customer acceptance

Documentation is not a tenant deployment certification. Complete the
[clean-environment acceptance checklist](./CUSTOMER-HANDOVER.md#10-acceptance-expected-results-not-just-successful-commands)
and retain restricted evidence before customer sign-off. The PoC does not yet
wire in the separate shared harness or automated safety/evaluation gates.

For local agent creation, the governed-agent kit also supports Azure CLI REST
and `azd`-authenticated REST. See the
[governed-agent creation options](./02-governed-agents/README.md#agent-creation-options).
