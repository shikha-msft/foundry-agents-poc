# Microsoft Foundry V2 agent POC

This proof of concept uses Azure CLI commands to create two Microsoft Foundry
V2 projects under an existing Foundry account:

| Azure resource name | Display name | Intended use |
|---|---|---|
| `playground-projects` | `PlaygroundProjects` | NoCode Experimentation Agents |
| `poc-project` | `POC Project` | Governed POC Agents development |

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

## Existing account

The script defaults target:

- Subscription: `c6a4ffe5-6f74-4846-b4e1-57386c4b7935`
- Resource group: `rg-foundry-demo`
- Foundry account: `ss-aueast-foundry`
- Region: `australiaeast`

The script validates that the account is an `AIServices` account, is in the
expected region, and has Foundry project management enabled.

## Prerequisites

1. Azure CLI authenticated to tenant
   `16b3c013-d300-468d-ac64-7eda0820b6d3`.
2. Permission to create resources in `rg-foundry-demo`.
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

Optional overrides:

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
| `agentServiceConnection` | `foundry-poc-agent-wif` | Least-privilege agent deployment connection using workload identity federation |
| `infrastructureServiceConnection` | `foundry-poc-infra-wif` | Elevated infrastructure connection used only when provisioning is selected |
| `provisionInfrastructure` | `false` | Run `deploy.ps1` before creating agents |
| `createPromptAgent` | `true` | Create a new `gov-prompt-agent-poc` version |
| `createRagAgent` | `false` | Create a new `gov-rag-agent-poc` version |
| `searchIndexName` | Empty | Required when `createRagAgent` is selected |

### Pipeline setup

1. Create an Azure Resource Manager service connection using **workload
   identity federation**. Name it `foundry-poc-agent-wif`, or enter its actual
   name when the pipeline is queued. Do not create a client secret.
2. Grant its identity **Foundry User** on `poc-project` for agent creation.
3. If the pipeline will provision infrastructure, create a separate
   workload-federated connection named `foundry-poc-infra-wif`. Grant its
   identity **Contributor** on `rg-foundry-demo` and **User Access
   Administrator** only on the scopes where `deploy.ps1` creates role
   assignments.
4. Create the Azure DevOps environments `foundry-poc-infrastructure` and
   `foundry-poc-agents`, then configure the required approvals and checks.
5. Create a pipeline from `foundry-agents-poc/azure-pipelines.yml`.

The pipeline authenticates with `AzureCLI@2`; the Python SDK then uses that
federated Azure CLI session. It does not upload either local `.env` file and
does not require stored Azure client secrets.

After a RAG Agent version is created, grant **Search Index Data Reader** to
the exact Agent Identity returned in the pipeline artifact. The pipeline
service identity and the created RAG Agent Identity are different principals.

For local agent creation, the governed-agent kit also supports Azure CLI REST
and `azd`-authenticated REST. See the
[governed-agent creation options](./02-governed-agents/README.md#agent-creation-options).
