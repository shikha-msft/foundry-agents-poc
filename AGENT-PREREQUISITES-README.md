Below is the consolidated prerequisite list for **all no-code and governed samples in this PoC**, grouped into common requirements and agent-specific additions.

**Customer infrastructure and platform permissions should already be supplied through IaC/platform teams.** Developers should not need to run the repository's infrastructure-provisioning scripts.

> **Three separate permission systems:** Azure RBAC controls Azure resources; Entra roles control directory administration; Microsoft Graph permissions authorize the provisioning client's directory API operations. One does not replace the others.

**Operating model:** the customer platform supplies the baseline before users
enter **POC Project** or a governed project. Developers select approved
models/tools; they do not configure monitoring and safety from scratch.
Model guardrails can be inherited, but project tracing and external-host
identity/export require platform wiring. See the
[platform operating model](./PLATFORM-OPERATING-MODEL.md) for the authoritative
scope/ownership matrix and current implementation gaps.

## 1. Common platform prerequisites

These form the shared PoC baseline. Additional services are required only for agents that use them.

| Area | Prerequisite | Owner |
|---|---|---|
| Tenant/subscription | Approved Entra tenant, active Azure subscription, resource groups, region, budget and workload owner | Platform/identity |
| **Microsoft Foundry V2** | Foundry resource: `Microsoft.CognitiveServices/accounts`, kind `AIServices`, with project management enabled. **Not a classic hub-based project** | Platform |
| Projects | Existing **experimentation project** for portal/no-code work and **governed project** for governed Prompt/RAG and MAF integration | Platform |
| Project identities | System-assigned managed identity enabled on each project; principal IDs recorded | Platform/identity |
| Models | Approved model deployments, supported versions/regions, adequate quota and capacity. Audio and embeddings need their own compatible deployments | AI/platform |
| Observability | Approved Application Insights and Log Analytics resources, project connections, retention, access controls and verified ingestion | Platform/operations |
| Network | Correct routes, private DNS, firewalls and HTTPS connectivity to Foundry, Entra, monitoring and selected downstream services | Network |
| Responsible AI | Approved instructions, content filters/guardrails where supported, risk owner, evaluation dataset and acceptance thresholds | AI/security |
| Data governance | Approved data classification, consent, retention, redaction and prompt/response logging policy | Security/data owner |
| Identity governance | Named owner/sponsor, identity inventory, access-review and retirement processes | Identity/application owner |

**Important:** Creating a no-code agent in the portal does not inherently mean it lacks an Agent Identity. New-model Prompt agents can receive Foundry-managed identities regardless of whether they were created through the portal or SDK. Verify the actual identity model.

### Common resource providers

Provider registration is a **subscription/platform responsibility**, not a developer permission.

| Namespace | Required when |
|---|---|
| `Microsoft.CognitiveServices` | Foundry, model deployments and project connections--including audio models |
| `Microsoft.Insights` | Application Insights |
| `Microsoft.OperationalInsights` | Log Analytics |
| `Microsoft.Authorization` | Azure RBAC operations; platform verifies availability rather than assuming manual registration is needed |
| `Microsoft.Search` | Azure AI Search retrieval |
| `Microsoft.Web` | MAF App Service hosting; audio API if hosted on App Service |
| `Microsoft.Network` | Private endpoints, VNets, private DNS and related networking |
| `Microsoft.ManagedIdentity` | User-assigned managed identities, **if selected**; not a separate blanket requirement for system-assigned MI |
| `Microsoft.Storage` | Blob/ADLS sources or separately selected storage |
| `Microsoft.KeyVault` | Customer-approved secret/certificate storage, if used |
| `Microsoft.DocumentDB` | Optional Cosmos DB integration |
| `Microsoft.DBforPostgreSQL` | Optional PostgreSQL integration |
| `Microsoft.Compute` | An Azure VM hosting a self-hosted pipeline agent, if used |
| `Microsoft.ContainerService` | Customer-managed AKS multi-agent hosting, if selected; no AKS deployment is implemented in this kit |
| `Microsoft.ContainerRegistry` | ACR image storage, if selected for the AKS/customer container workflow |

**Entra Agent ID, Microsoft Graph and Agent 365 are not Azure resource-provider namespaces to register.**

## 2. Common Azure RBAC

Assign access to the **principal performing the operation**, at the narrowest supported scope.

| Principal/persona | Role/access | Scope/purpose |
|---|---|---|
| Portal/SDK agent developer | **Foundry User** | Selected project; create, configure and test agents |
| Portal developer | **Reader** | Parent Foundry account, as needed for navigation |
| Agent publisher | **Foundry Project Manager**, where required | Separate publication/endpoint-management authority |
| Project MI | **Foundry User** in the repository's reference configuration | Parent Foundry account; validate supported narrower scope |
| Monitoring reviewer | **Monitoring Reader** | Approved Application Insights component |
| Log reviewer | **Log Analytics Reader** | Approved workspace; restricted telemetry may require additional authorization |
| Agent-creation pipeline principal | **Foundry User** | Governed project--not subscription Owner |
| Platform provisioning principal | **Contributor** or approved custom management role | Only resources it manages |
| Role-assignment administrator | **Role Based Access Control Administrator**, **User Access Administrator**, or approved equivalent | Exact scopes where grants are established |

The test helpers also assign project-MI monitoring roles, including **Privileged Monitoring Data Reader**. These are **reference-helper assignments, not universal minimum permissions**; the customer must approve the actual monitoring access required.

**Contributor alone cannot assign Azure roles and does not provide Microsoft Graph consent.**

## 3. Agent-specific prerequisites

### A. No-code experimentation agents -- Foundry portal

| Area | Additional prerequisite |
|---|---|
| Resources | Experimentation project, approved chat deployment and working project monitoring |
| Developer access | Foundry User on the experimentation project; Reader on the parent account as needed |
| Identity | Tenant permits Foundry-managed identity provisioning for new-model agents; legacy/shared-project identity behavior explicitly identified |
| Graph | **No blanket Graph provisioning permissions on every portal developer** |
| Data/tools | Platform-approved connections and tool endpoints; downstream data permissions on the identity actually making requests |
| Safety | Synthetic/public/approved non-sensitive data, approved tools and no uncontrolled write/admin actions |
| Agent 365 | Foundry account-level collection, if required; see section 5 |

**Plain no-code Prompt agents do not require Search, Storage, Cosmos DB or PostgreSQL merely to exist.**

### B. Governed 01 -- Prompt Agent

| Area | Additional prerequisite |
|---|---|
| Resources | Governed project and approved chat model deployment |
| Creator | Foundry User on the governed project |
| Agent Identity | Foundry permitted to create its managed blueprint/principals; verify and record the resulting agent identity |
| Graph | No custom Graph provisioning client needed for the normal Foundry-managed creation path |
| Governance | Versioned instructions, change approval, RAI acceptance criteria and verified telemetry |
| Agent 365 | Built-in Foundry collection, if required; no separate custom MAF-style registration |

**No Search, embedding model, audio model or App Service is required for this Prompt Agent.**

### C. Governed 02 -- RAG Agent

All governed Prompt prerequisites apply, plus:

| Area | Additional prerequisite |
|---|---|
| Search resources | Existing Azure AI Search service with supported tier/features and approved connectivity |
| Project connection | Approved Search connection with the correct service endpoint and authentication mode |
| Existing-index option | Populated, validated index; compatible fields, semantic configuration and vector configuration where selected |
| Citations | Searchable/retrievable content and source fields; the tested native-tool template uses a **searchable and retrievable `url` field** |
| Authentication | Search supports the connection's selected authentication mode; Entra connections cannot work against an API-key-only service |
| Native-tool runtime RBAC | Validate the actual tool principal. **Our live-tested setup required Search Service Contributor + Search Index Data Contributor on the project MI**; Reader alone did not work |
| Least privilege | Approve those broader native-tool grants explicitly. Do not mistake them for query-only permissions or assume per-agent Search isolation |
| Ingestion | Separate ingestion identity, approved sources, refresh/deletion process and data-quality controls |
| Security | Groundedness/citation checks, missing-evidence behavior and any required document/user authorization design |

#### Additional prerequisites only for "create synthetic index"

| Area | Required |
|---|---|
| Index name | New, unused index name; existing indexes are not overwritten |
| Embedding model | Existing `text-embedding-3-small` deployment, producing **1,536-dimensional** vectors |
| Setup principal | Foundry connection-read access, **Search Service Contributor**, **Search Index Data Contributor**, and embedding inference permission |
| Embedding inference RBAC | **Cognitive Services OpenAI User**, or verified equivalent, on the embedding account |
| Query vectorizer | Search service system-assigned MI enabled and authorized to call the embedding model |
| Semantic ranking | Already enabled for the configured semantic/hybrid query mode |
| Approval | Synthetic-data ingestion and embedding/Search charges approved |

Supplying an existing index **does not require granting the application creator ingestion permissions**. Runtime-native-tool permissions remain a separate requirement.

### D. Governed 03 -- Multimodal TTS/STT sample

This is currently a **direct-model HTTP application**, not a Foundry Prompt Agent.

| Area | Additional prerequisite |
|---|---|
| Models | Separate approved TTS and transcription deployments supporting their respective audio API routes |
| Endpoint | OpenAI-compatible **resource endpoint ending `/openai/v1/`**, not the project endpoint |
| Runtime RBAC | Local developer/hosted runtime has **Cognitive Services OpenAI User**, or verified equivalent, on the audio model account |
| Hosting | Python 3.12 and approved dependencies; customer-provided HTTP hosting if deployed remotely |
| Identity | Workload/managed identity for hosted inference, or scoped developer authentication locally |
| Audio governance | Consent, audio/transcript privacy, upload/output limits, approved voices/formats and AI-generated speech disclosure |
| Observability | Application instrumentation and verified Application Insights export; do not assume Prompt Agent tracing covers this API |
| Agent ID/365 | **Not wired into this sample today.** If mandatory for every agent, custom identity/registration/export integration is a release blocker |

**No separate Azure AI Speech resource or Speech SDK is required.** Easy Auth remains optional for the controlled PoC.

### E. Governed 04 -- MAF multi-agent application

| Area | Additional prerequisite |
|---|---|
| Dependencies | Working remote governed Prompt and RAG agents |
| Host | Existing Linux App Service plan/web app, Python 3.12, startup/build settings and health checks |
| Runtime identity | App Service system-assigned MI enabled |
| Foundry RBAC | App Service MI has approved Foundry model/agent invocation access; the reference uses Foundry User on the parent account |
| Search RBAC | Assigned separately to the verified RAG retrieval principal--not automatically the App Service MI |
| Deployment access | Scoped package-deployment rights, such as customer-validated **Website Contributor** permissions |
| Custom Agent ID | Blueprint, Blueprint Principal, Agent Identity and MI federation, required independently of Agent 365 opt-in; current token exchange is used for Agent 365 S2S |
| Agent 365 | One coordinator registration, approved telemetry grants and configured exporter |
| Governance | Bounded rounds/timeouts, no administrative tools and approved orchestration tests |

The in-process Prompt/Retrieval specialist wrappers **do not require separate Agent 365 registrations** in this implementation.

AKS is a customer target option, not a second implemented deployment path.
Its cluster, image, workload federation, ingress/auth, monitoring and custom
Agent ID/365 runtime integration require separate approved implementation.

## 4. Entra Agent ID and Microsoft Graph prerequisites

### Administrative and identity prerequisites

| Requirement | Applies to |
|---|---|
| Tenant supports Agent ID and permits the required identity lifecycle | New-model Foundry agents and custom identities |
| **Agent ID Developer** or **Agent ID Administrator**, subject to tenant creation policy/ownership | Custom blueprint provisioning--not every agent developer |
| Authorized consent administrator | Graph permissions; Microsoft documents **Privileged Role Administrator** for Graph application-permission consent and Application/Cloud Application Administrator for delegated consent |
| Dedicated supported Graph client with explicitly approved permissions | Custom provisioning; ordinary Azure CLI login is not sufficient proof |
| Blueprint + Blueprint Principal + Agent Identity | Custom MAF identity path; **do not pre-create duplicates for Foundry-managed agents** |
| Federated identity credential | Trust from the custom blueprint to App Service MI; correct tenant issuer, MI principal-ID subject and token-exchange audience |
| Owner/sponsor and lifecycle record | Every applicable identity |

### Graph permissions -- select by operation

These belong to the **approved provisioning/administration client**, not automatically the runtime agent.

| Operation | Permission to assess |
|---|---|
| Create blueprint | `AgentIdentityBlueprint.Create` |
| Manage blueprint | `AgentIdentityBlueprint.ReadWrite.All` |
| Create Blueprint Principal | `AgentIdentityBlueprintPrincipal.Create` |
| Create agent identity | `AgentIdentity.Create.All` |
| Manage agent identities | `AgentIdentity.ReadWrite.All` |
| Configure blueprint credentials/federation | `AgentIdentityBlueprint.AddRemoveCreds.All` |
| Change blueprint authentication properties | `AgentIdentityBlueprint.UpdateAuthProperties.All`, if required |
| Assign application permissions | `AppRoleAssignment.ReadWrite.All`, if required |
| Grant delegated/OBO permissions | `DelegatedPermissionGrant.ReadWrite.All`, **only for a selected delegated/OBO design** |

Validate delegated/application support and ownership restrictions against the actual APIs. **Do not grant this entire table as a blanket bundle.** The present PoC does not require Mail, Teams, Files or directory-wide user-reading permissions merely to run Prompt/RAG/audio.

## 5. Agent 365 prerequisites

| Requirement | Foundry no-code/Prompt/RAG | MAF |
|---|---|---|
| Active entitlement and tenant feature availability | Required | Required |
| Completed tenant-level consent | Required | Required |
| Privacy, residency, retention and viewer-access approval | Required | Required |
| Foundry collection | `a365LoggingEnabled=true` and `a365Status=Enabled` | Does not replace custom export |
| Configuration authority | Account read/write, e.g. Contributor on the Foundry account | App configuration authority plus approved identity/registration authority |
| Custom registration | Not the MAF custom-registration path | One S2S coordinator registration mapped to the correct identity |
| Runtime authentication | Foundry-managed integration | MI federation, Agent ID token exchange and approved Agent 365 observability S2S grants |
| Delivery proof | Synthetic invocation visible under expected identity | Synthetic coordinator invocation visible under expected identity |

**Foundry collection is account-wide:** every project/Prompt agent under that account inherits it, with no per-agent override. Current Microsoft documentation also states collection can default on once the tenant enables Agent 365--check actual state rather than assuming it is off.

**The audio sample is not automatically covered by either integration.**

## 6. Optional additions--not blanket requirements

| Capability | Additional prerequisites |
|---|---|
| Blob/ADLS tools | Storage connection, **Storage Blob Data Reader**, and ADLS ACLs where needed |
| Cosmos DB tools | Connection and **Cosmos DB Built-in Data Reader** through native data-plane RBAC |
| PostgreSQL tools | Entra database principal plus `CONNECT`, schema `USAGE` and approved `SELECT` grants |
| Easy Auth | Separate Entra app registration/service principal, issuer/audience/caller configuration. **Optional for controlled PoC; network restrictions required if omitted** |
| Azure DevOps | Authorized WIF service connections, variable groups, protected environments, agent pool and network/feed access |
| Unattended Agent ID/365 setup | Separately proven Graph/CLI noninteractive authentication; ARM WIF login alone is insufficient |
| Additional Content Safety service | Separate resource/connection/runtime permissions only if the approved design explicitly uses it |

### Key readiness caveats

- An Agent Identity does **not** prove its tools use that identity.
- Agent 365 registration does **not** enable content safety or grant Search access.
- A monitoring connection or "Enabled" flag is **not proof of telemetry delivery**.
- Mandatory per-user retrieval security and audio Agent ID/365 integration are **not satisfied merely by provisioning these resources**.

Repository reference: [Customer prerequisite matrix](./CUSTOMER-PREREQUISITES.md).

Microsoft references: [Agent ID prerequisites](https://learn.microsoft.com/entra/agent-id/create-blueprint), [native Search tool setup](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/ai-search), and [Foundry Agent 365 collection](https://learn.microsoft.com/azure/foundry/agents/how-to/configure-agent-365-data-collection).
