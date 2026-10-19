# Microsoft Foundry V2 agent POC

This proof of concept uses Azure CLI commands to create two Microsoft Foundry
V2 projects under an existing Foundry account:

| Configuration variable | Display-name variable | Intended use |
|---|---|---|
| `EXPERIMENTATION_PROJECT_NAME` | `EXPERIMENTATION_PROJECT_DISPLAY_NAME` | NoCode Experimentation Agents |
| `GOVERNED_PROJECT_NAME` | `GOVERNED_PROJECT_DISPLAY_NAME` | Governed POC Agents development |

## Implementation guides

- [NoCode Experimentation Agents](./01-experimentation-agents/README.md)
- [Governed POC Agents](./02-governed-agents/README.md)
- [Microsoft Agent Framework Multi-Agent App](./02-governed-agents/03-maf-multi-agent/README.md)

The existing Foundry account is referenced and is not modified. Each project
receives:

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

The existing account currently permits public network access. The script does
not change that shared account setting.

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
6. Create a pipeline from `foundry-agents-poc/azure-pipelines.yml`.

The pipeline authenticates with `AzureCLI@2`; the Python SDK then uses that
federated Azure CLI session. It does not upload either local `.env` file and
does not require stored Azure client secrets.

After a RAG Agent version is created, grant **Search Index Data Reader** to
the exact Agent Identity returned in the pipeline artifact. The pipeline
service identity and the created RAG Agent Identity are different principals.

For local agent creation, the governed-agent kit also supports Azure CLI REST
and `azd`-authenticated REST. See the
[governed-agent creation options](./02-governed-agents/README.md#agent-creation-options).
