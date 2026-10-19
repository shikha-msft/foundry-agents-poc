# 02 - Governed POC Agents

This folder defines the governed-agent pattern for the project configured by
`GOVERNED_PROJECT_DISPLAY_NAME`.

The governed implementation categories are:

1. [Governed Prompt Agent](./01-prompt-agent/README.md)
2. [Governed RAG Agent](./02-rag-agent/README.md)
3. [MAF Multi-Agent App Service](./03-maf-multi-agent/README.md)

Both agents use Microsoft Foundry prompt agents, Microsoft Entra Agent ID, and
the project's mandatory Application Insights observability baseline.

## Environment

| Setting | Value |
|---|---|
| Foundry account | `FOUNDRY_ACCOUNT_NAME` |
| Foundry project resource name | `GOVERNED_PROJECT_NAME` |
| Foundry project display name | `GOVERNED_PROJECT_DISPLAY_NAME` |
| Purpose | Governed POC Agents development |
| Region | `AZURE_LOCATION` |
| Project managed identity | Record after provisioning |
| Application Insights | `GOVERNED_APPLICATION_INSIGHTS_NAME` |
| Log Analytics workspace | `GOVERNED_LOG_ANALYTICS_NAME` |
| Default chat model for the POC | `MODEL_DEPLOYMENT_NAME` |
| Available alternative chat model | `gpt-5-mini` |
| Embedding model for RAG ingestion | `text-embedding-3-small` |

## Runnable implementation

Each agent is a self-contained application under its respective folder:

| Agent | Code and configuration |
|---|---|
| Prompt | [`01-prompt-agent`](./01-prompt-agent/) |
| Azure AI Search RAG | [`02-rag-agent`](./02-rag-agent/) |
| MAF multi-agent API | [`03-maf-multi-agent`](./03-maf-multi-agent/) |

Each folder contains:

- An independently runnable Python script with `create`, `list`, and `invoke`
  commands.
- Its own governed instructions.
- A `requirements.txt`.
- A local `.env` with the POC values.
- A customer-safe `.env.sample` listing every configurable variable.

Both implementations use `azure-ai-projects` 2.6, Azure CLI authentication for
local development, managed identity when hosted in Azure, and workload
identity federation in CI/CD. See each agent's README for its installation and
execution commands.

The manually triggered
[`azure-pipelines.yml`](../azure-pipelines.yml) validates both implementations
and can create either or both agent versions through an Azure DevOps workload
identity service connection. Pipeline setup and RBAC requirements are
documented in the parent POC README.

Creating another version with the same agent name is intentional: Foundry
keeps the agent name and creates a new immutable version.

## Agent creation options

All three options create the same ordinary Microsoft Foundry Prompt Agent
definitions. The Python scripts remain the definition source of truth.

### Option 1: Azure CLI

Authenticate with Azure CLI and create a version through the Foundry REST API:

```powershell
az login
az account set --subscription "<AZURE_SUBSCRIPTION_ID from .env>"

.\create-agent-version.ps1 -Agent prompt -Method AzCli
.\create-agent-version.ps1 -Agent rag -Method AzCli
```

Use `-WhatIf` to validate and render the request without sending it:

```powershell
.\create-agent-version.ps1 -Agent prompt -Method AzCli -WhatIf
```

The wrapper uses `az account get-access-token` to request an
`https://ai.azure.com` token, then posts to the Foundry V2
`/agents/{name}/versions?api-version=v1` data-plane endpoint. It does not use
an account key or client secret.

### Option 2: Azure Developer CLI authentication

Authenticate with `azd`, then create a version using its short-lived Foundry
token:

```powershell
azd auth login --tenant-id "<AZURE_TENANT_ID from .env>"

.\create-agent-version.ps1 -Agent prompt -Method Azd
.\create-agent-version.ps1 -Agent rag -Method Azd
```

This is an `azd`-authenticated REST path. Native `azd deploy` is intentionally
not used: these are ordinary Prompt Agents, while native `azd deploy` targets
hosted agents and managed-harness agents. This avoids incorrectly converting
the agents to a different hosting model. The `microsoft.foundry` extension is
not required for this token-based path.

### Option 3: Azure DevOps pipeline

Run [`../azure-pipelines.yml`](../azure-pipelines.yml), select the agent
parameters, and use the approved workload-federated service connection. The
pipeline validates the definitions, creates selected versions, and publishes
the Foundry responses as an artifact.

Before creating the RAG Agent through any option, populate
`AZURE_AI_SEARCH_INDEX_NAME` in its `.env` or the Azure DevOps variable group.

## 1. Important Foundry identity behavior

For Foundry prompt agents, do not manually create a duplicate Entra blueprint
before creating the agent.

This implementation uses the newer Foundry agent object model exposed by
`azure-ai-projects` 2.6. Foundry creates the managed blueprint and Agent
Identity as part of `client.agents.create_version(...)`.

Each successful creation returns a blueprint type, blueprint ID, blueprint
principal, blueprint client/application ID, Agent Identity, and agent GUID.
Record those values in the approved governance register rather than in the
shareable repository.

The older Agent Application publishing model used a shared development
identity and created a distinct identity when publishing. Do not apply that
assumption to this code. Always use the blueprint and `instance_identity`
returned by the created agent version, and verify the identifiers again when a
new version or endpoint is promoted.

```text
Governed project managed identity
        |
        | Foundry-managed federated trust
        v
Prompt managed blueprint                 RAG managed blueprint
        |                                       |
        v                                       v
Prompt Agent Identity                    RAG Agent Identity
        |                                       |
Prompt-only permissions                  Search/data permissions
```

The project managed identity participates in Foundry's managed authentication
chain. The **Agent Identity** returned for the agent receives downstream data
roles for tools that support Agent ID authentication.

## 2. Prerequisites

### 2.1 Tenant and Agent ID prerequisites

- [ ] Microsoft Entra Agent ID is available in the tenant.
- [ ] Tenant policy permits Microsoft Foundry to provision Agent ID objects.
- [ ] Blueprint and Agent Identity naming, owner, sponsor, review, and
      decommissioning standards are approved.
- [ ] Workload identity restrictions and Conditional Access policies for
      workload identities are defined.
- [ ] Production credentials use workload identity federation; no client
      secrets are stored in agent configuration.
- [ ] The customer has an approved process to review Agent ID audit and
      sign-in logs.

Foundry developers do not need broad Graph permissions for the Foundry-managed
identity lifecycle.

If an identity administrator must manage Agent ID objects manually, use an
approved administrative identity with the minimum required Entra role:

| Activity | Minimum administrative role or authority |
|---|---|
| Manage blueprint lifecycle | **Agent ID Developer** or **Agent ID Administrator** |
| Add secrets or certificates to a blueprint | **Agent ID Administrator** |
| Grant Graph delegated permissions | **Cloud Application Administrator** or **Application Administrator** |
| Grant Graph application permissions | **Privileged Role Administrator** |
| Create identities from an existing blueprint | Blueprint owner or approved Agent ID provisioning identity |

Typical Microsoft Graph permissions for a separate approved provisioning
client include:

- `AgentIdentityBlueprint.Create`
- `AgentIdentityBlueprint.ReadWrite.All`
- `AgentIdentityBlueprintPrincipal.Create`
- `AgentIdentityBlueprint.AddRemoveCreds.All`
- `AgentIdentityBlueprint.UpdateAuthProperties.All`
- `AgentIdentity.Create.All`
- `AgentIdentity.ReadWrite.All`
- `AppRoleAssignment.ReadWrite.All` only when it grants application roles
- `DelegatedPermissionGrant.ReadWrite.All` only for delegated/OBO grants

Do not grant these permissions to every agent developer. Azure CLI tokens are
not suitable for direct Agent ID Graph provisioning because they include a
directory scope that Agent ID APIs reject.

### 2.2 Foundry RBAC

| Principal | Role | Scope | Purpose |
|---|---|---|---|
| Agent developer group | **Foundry User** | `GOVERNED_PROJECT_NAME` | Create, configure, and test agents |
| Agent developer group | **Reader** | Parent Foundry account | Portal navigation |
| Publisher/team lead | **Foundry Project Manager** | Foundry account/project as required | Promote or publish an approved agent endpoint |
| Project managed identity | **Foundry User** | Parent Foundry account | Use project models and capabilities |
| Developer/evaluator group | **Azure Monitor Reader** | Project Application Insights | View traces and metrics |
| Developer/evaluator group | **Log Analytics Reader** | Project Log Analytics workspace | Query approved telemetry |
| Role-assignment administrator | **Role Based Access Control Administrator**, **User Access Administrator**, or approved equivalent | Exact downstream scope | Assign roles to the Agent Identity returned at creation |

`Contributor` or `Owner` alone does not grant Foundry data-plane agent
development access. Developers still require `Foundry User`.

### 2.3 Project prerequisites

- [ ] At least one approved model deployment exists.
- [ ] Project Application Insights connection is healthy.
- [ ] Foundry server-side tracing is enabled.
- [ ] Content filters and guardrails are approved.
- [ ] Prompt-injection and data-exfiltration tests are defined.
- [ ] Release/publishing approval and rollback procedures are defined.
- [ ] Only synthetic or approved non-production data is used before the
      created Agent Identity receives its reviewed roles.

## 3. Create the managed blueprint and Agent Identity

The managed blueprint and Agent Identity are created indirectly by Foundry
when the code creates the agent version.

1. Open the selected agent folder and install its `requirements.txt`.
2. Run `python prompt_agent.py create` or `python rag_agent.py create`.
3. Capture the returned `blueprint`, `blueprint_reference`,
   `instance_identity`, and `agent_guid` values.
4. List the agent again with the selected script's `list` command.
5. Record the identity information in the governance register.
6. Assign downstream roles only to the returned Agent Identity.
7. Run positive and negative authorization tests.

If the identity fields do not appear immediately, wait for provisioning and
refresh. Do not work around the delay by creating an unrelated application
registration.

The managed blueprint is attached to the agent response rather than the
project ARM response. Query the agent through the Foundry data plane instead
of looking only at the ARM resource identified by `GOVERNED_PROJECT_NAME`.

## 4. Create the two agent categories

### Category A - Governed Prompt Agent

The Prompt Agent:

- Uses approved instructions and model configuration.
- Has no RAG data permissions by default.
- Can receive only the API or MCP permissions required for its business task.
- Receives a managed blueprint and Agent Identity when its version is created.

Follow [01-prompt-agent/README.md](./01-prompt-agent/README.md).

### Category B - Governed RAG Agent

The RAG Agent:

- Uses Azure AI Search or a reviewed file-search/vector-store pattern.
- Receives read-only retrieval permissions by default.
- Requires citation, groundedness, and access-boundary evaluations.
- Receives its own managed blueprint and Agent Identity at creation.

Follow [02-rag-agent/README.md](./02-rag-agent/README.md).

## 5. Record and authorize each identity

Repeat these steps separately for the Prompt and RAG agents:

1. Create the agent version.
2. Record the agent version, blueprint ID, blueprint principal, Agent Identity,
   and agent GUID from the response.
3. Obtain approval from the agent owner, data owner, security owner, and role
   assignment administrator.
4. Assign downstream permissions to that Agent Identity.
5. Complete functional, safety, security, authorization, and trace validation.
6. Promote or publish only the approved version and endpoint.
7. Re-read the promoted agent details and verify that its identity IDs still
   match the approved governance record.

Never assume that roles automatically transfer when Foundry returns a new
Agent Identity for a later lifecycle operation.

## 6. Permission profiles

### 6.1 Prompt Agent profile

Start with no downstream data roles.

Add only the permission needed for an approved tool:

| Capability | Permission target |
|---|---|
| Entra-protected MCP API | Exact API app role or delegated scope |
| A2A agent call | Exact downstream agent/API audience and approved role |
| Key Vault secret, only if unavoidable | **Key Vault Secrets User** on the dedicated vault |

Do not grant Search, Storage, Cosmos DB, or PostgreSQL access unless the Prompt
Agent is explicitly redesigned as a data-connected agent.

### 6.2 RAG Agent profile

| Retrieval pattern | Published RAG Agent Identity permission |
|---|---|
| Query an existing Azure AI Search index | **Search Index Data Reader** on the approved Search service/index |
| Foundry feature must manage Search objects | Add **Search Index Data Contributor** and **Search Service Contributor** only when the selected feature requires them |
| Read Blob through an Agent ID-aware MCP tool | **Storage Blob Data Reader** on the approved container |
| Read ADLS Gen2 through a tool | **Storage Blob Data Reader** plus required directory ACLs |
| Query Cosmos DB through an Agent ID-aware tool | **Cosmos DB Built-in Data Reader** at the approved account/database/container scope |
| Query PostgreSQL through an Agent ID-aware tool | Entra principal plus `CONNECT`, schema `USAGE`, and `SELECT` on approved views/functions |

For tools that do not yet support Agent Identity authentication, the tool host
uses its own managed identity. Document that exception and keep the tool
identity's permissions separate from the Agent Identity.

## 7. Observability enabled by default

Both agent categories use the existing project monitoring baseline:

- Application Insights: `GOVERNED_APPLICATION_INSIGHTS_NAME`
- Log Analytics: `GOVERNED_LOG_ANALYTICS_NAME`

Foundry server-side tracing captures the agent, model, and supported tool
operations. Custom MCP/OpenAPI services must propagate W3C trace context and
emit their own dependency telemetry.

### Agent 365

The parent Foundry resource provides built-in Agent 365 integration for the
Prompt and RAG agents. Run `..\provision-agent365.ps1 -Scope Foundry` after
tenant licensing and consent are complete. The setting applies to every
project and Prompt Agent under that Foundry resource.

The MAF application follows a separate SDK path because it is hosted in App
Service. It receives one S2S Agent 365 registration for the orchestrator and
uses Microsoft OpenTelemetry for Agent 365 and Azure Monitor export. The
in-process specialists are not duplicate registrations of the remote Prompt
and RAG agents.

### Required trace dimensions

Capture or correlate:

- Foundry project ID.
- Agent application resource ID.
- Agent name and version.
- Blueprint ID.
- Distinct Agent Identity object ID.
- Model deployment and version.
- Invocation, trace, and span IDs.
- Tool name, target service type, duration, status, and error category.
- Token usage, latency, retries, and throttling.
- Evaluation run and release version.

Do not record access tokens, connection strings, passwords, raw secrets,
personal data, or sensitive tool payloads.

### Required dashboards and alerts

Provide dashboards for:

- Invocations, success rate, and latency percentiles.
- Model calls, token use, cost, throttling, and failures.
- Tool/retrieval calls and dependency failures.
- Prompt and RAG evaluation results.
- Authentication and authorization failures by Agent Identity.
- Search latency and empty retrievals for the RAG Agent.

Configure alerts for:

- Agent error-rate or latency threshold exceeded.
- Model throttling or quota exhaustion.
- Tool authentication/authorization failure spike.
- No telemetry from an active governed agent.
- RAG citation, groundedness, or relevance regression.
- Abnormal token or monitoring cost growth.

## 8. Governance register

Complete this table as each agent is created:

| Field | Prompt Agent | RAG Agent |
|---|---|---|
| Foundry agent name | `PROMPT_AGENT_NAME` | `RAG_AGENT_NAME` |
| Agent version | Record after creation | Record after creation |
| Agent GUID | Record after creation | Record after creation |
| Blueprint type | Record after creation | Record after creation |
| Blueprint ID | Record after creation | Record after creation |
| Blueprint principal object ID | Record after creation | Record after creation |
| Blueprint client/application ID | Record after creation | Record after creation |
| Agent Identity object ID | Record after creation | Record after creation |
| Owner | To be assigned | To be assigned |
| Sponsor | To be assigned | To be assigned |
| Downstream roles | None by default | Search reader by default |
| Application Insights | `GOVERNED_APPLICATION_INSIGHTS_NAME` | `GOVERNED_APPLICATION_INSIGHTS_NAME` |
| Review/expiry date | To be assigned | To be assigned |

## 9. Acceptance criteria

- [x] Prompt Agent creation returned a managed blueprint and Agent Identity.
- [ ] RAG Agent creation returns its own managed blueprint and Agent Identity.
- [ ] Both agents can be tested using only synthetic data.
- [ ] Prompt Agent has no RAG data permissions.
- [ ] RAG Agent has only approved read permissions.
- [ ] Roles are assigned to the exact Agent Identity recorded for each agent.
- [ ] Successful and failed calls appear in Application Insights.
- [ ] Traces can be filtered or correlated by Agent Identity.
- [ ] Authentication failures are visible without exposing credentials.
- [ ] Owners, sponsors, permissions, evidence, and expiry are recorded.
- [ ] Disabling an Agent Identity prevents downstream tool access.
- [ ] Removing the agent also triggers identity, role, connection, and
      monitoring cleanup.

## References

- [Agent identity concepts in Microsoft Foundry](https://learn.microsoft.com/azure/foundry/agents/concepts/agent-identity)
- [Agent identity blueprints](https://learn.microsoft.com/entra/agent-id/agent-blueprint)
- [Create an Agent Identity blueprint](https://learn.microsoft.com/entra/agent-id/create-blueprint)
- [Agent ID setup instructions](https://learn.microsoft.com/entra/agent-id/identity-platform/agent-id-setup-instructions)
- [Foundry tracing setup](https://learn.microsoft.com/azure/foundry/observability/how-to/trace-agent-setup)
- [Foundry RBAC](https://learn.microsoft.com/azure/foundry/concepts/rbac-foundry)
