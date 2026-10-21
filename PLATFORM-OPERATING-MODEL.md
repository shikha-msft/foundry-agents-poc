# Platform-managed Foundry V2: POC to governed agents

## 1. Customer experience

The customer supplies a Microsoft Foundry V2 resource with a centrally owned
safety, identity, monitoring and governance baseline. Developers consume that
baseline; they do not configure observability or safety from scratch for each
agent.

- **POC Project:** users create no-code agents in the portal, select approved
  models/tools and experiment with approved data. Authorized users can create
  indexes inside their assigned Search sandbox.
- **Governed projects:** teams request access to an existing approved project,
  or request a new project from the platform team. They deploy definitions/code
  through approved pipelines and publish only after release approval.
- **Hosting:** ordinary Prompt/RAG agents run in Foundry. Custom multi-agent
  applications use customer-managed App Service or, as a target option, AKS.
- **Identity:** every agent must have an Entra Agent Identity, whether created
  manually or through a pipeline. A managed identity alone does not satisfy
  this requirement.
- **Agent 365:** customer opt-in, subject to availability, licensing and consent.
  Foundry Prompt agents use the account integration; external applications
  require their own supported onboarding/export.

This is a **platform-managed experience**, not a claim that every setting
automatically inherits from the Foundry resource.

## 2. What actually flows down

| Control | Microsoft scope/behavior | How the platform makes it transparent to developers |
|---|---|---|
| Model content filters and guardrails | Models have an assigned guardrail. A Foundry agent without a custom guardrail inherits its model deployment's guardrail; an explicit agent guardrail overrides it. Applicable controls vary by model/intervention point; agent guardrails are preview | Configure each approved deployment, restrict deployment/policy changes and agent overrides using supported permissions/processes, and verify the effective policy during onboarding/release |
| Responsible AI | RAI is broader than a runtime switch: risk ownership, evaluation, privacy, approvals and operations are still needed | Supply centrally managed test/release standards and approved datasets; teams provide business-specific acceptance evidence |
| Foundry server-side tracing | Enabled after Application Insights is connected to **each project** | Project onboarding creates/validates the connection and monitoring permissions before granting team access; a shared approved destination is possible |
| App Service/AKS application tracing | Custom orchestration, tool and application code needs instrumentation/exporter configuration | Supply approved runtime templates, configuration and deployment checks; a Foundry connection does not instrument an external host |
| Foundry Agent Identity | New-model agents receive Foundry-managed identity objects at agent creation, not on every version; legacy agents require checking | Permit managed provisioning, record identity metadata and reject missing/legacy identity from governed release |
| External Agent Identity | A custom application needs an approved blueprint, Blueprint Principal, Agent Identity and workload trust | Platform identity onboarding supplies these independently of whether Agent 365 is enabled |
| Agent 365 Foundry collection | Resource-level setting inherited by all projects/Prompt agents; requires active entitlement, tenant consent and enabled status | Opt in through the platform process, approve the account-wide impact and verify inventory/telemetry for existing and new agents |
| External Agent 365 export | App Service/AKS applications are not enrolled merely by calling a Foundry model or agent | Platform supplies custom registration, runtime grants, federation and exporter configuration when opted in |
| Data authorization | Applied by the actual tool/service identity; an agent identity object does not make every connector use it | Supply approved tools/connections and scoped data grants; test positive and negative authorization |

No claim of complete protection should be made from instructions, agent tags,
an enabled flag, or the presence of a connection alone. Verify delivery and
effective enforcement. Audio filtering and custom tool actions are not
automatically equivalent to chat-model filtering.

## 3. Platform onboarding: once per resource and per project

| Step | Platform deliverable |
|---|---|
| 1. Resource baseline | Approved Foundry V2 resource, regions/network, model deployments, quota/budget and applicable provider registrations |
| 2. Safety baseline | Approved model-deployment guardrails/content filters, controlled change permissions and supported agent controls |
| 3. POC Project | Existing project whose display name is **POC Project**, system-assigned MI, monitoring connection, developer group and approved tools |
| 4. Monitoring | Project-to-Insights mapping, host exporters, retention/redaction/access policy, alerts and a successful synthetic trace |
| 5. Data sandbox | Cosmos/Blob/PostgreSQL/Search resources and scoped identities, ingestion/connector services and allowed index-creation boundaries |
| 6. Identity policy | Supported new-model Foundry creation, owners/sponsors and identity register; custom external identities/trust as needed |
| 7. Optional Agent 365 | Tenant entitlement/consent, resource setting/status, shared-account approval, external onboarding where applicable and delivery evidence |
| 8. Governed project request | Existing/new project access approved by platform; same onboarding baseline applied before team access |
| 9. Delivery | Scoped pipeline identities, protected environments and preconfigured hosting; no resource/Graph administration for routine application delivery |

The existing `EXPERIMENTATION_PROJECT_NAME` variable remains the resource name;
`EXPERIMENTATION_PROJECT_DISPLAY_NAME=POC Project` expresses the requested
portal label without renaming existing Azure resources. Governed project
names/endpoints are supplied per approved team/environment, not hard-coded to
one permanent project.

## 4. POC Project self-service

| User action | Ready-to-consume platform capability | Extra permission boundary |
|---|---|---|
| Create a portal Prompt agent | Approved model deployment and native new-model agent creation | Foundry User on the project; parent Reader as needed |
| Add Search retrieval | Approved Search connection, populated index and working native-tool identity | The native tool's documented/tested roles may exceed Reader; do not assume per-agent isolation |
| Create an index | Approved Search sandbox and ingestion/embedding path | Human/setup identity needs Search Service Contributor; document ingestion needs Search Index Data Contributor and embedding inference rights where selected |
| Connect Blob/ADLS knowledge | Approved Search ingestion/indexer or direct-access tool | Storage data-plane roles and ADLS ACLs on the actual ingestion/tool identity |
| Query Cosmos DB | Platform-supplied constrained MCP/OpenAPI/function tool | Cosmos native data-plane RBAC; partition/query/result limits |
| Query PostgreSQL | Platform-supplied constrained MCP/OpenAPI/function tool | Entra database identity and SQL grants |
| Test agent | Monitoring/safety baseline already configured by platform | User still runs business, grounding, injection and authorization checks |

Index authoring rights belong to approved users/setup identities, not to every
agent runtime. Search schema-management roles can be service-wide: use a
separate sandbox service if hard isolation is needed. A Foundry project role
does not grant index creation.
Users create indexes through the supported Search portal or approved indexing
workflow; this is not an unrestricted index-management tool exposed to the model.

Connections alone do not implement Cosmos/PostgreSQL/direct-Blob tools.
This repository documents those tool patterns; it does not ship those
connector services. Users do not bypass the platform baseline with personal
credentials, arbitrary SQL, or production-data connections.

## 5. Governed delivery

1. Request an approved existing project or a new platform-onboarded project.
2. Supply the platform-issued project endpoint, approved deployment names,
   monitoring component and data connections to the protected variable group.
3. Deploy Prompt/RAG definitions through the root pipeline. Definitions do not
   override the model guardrail. The scripts check the project's approved
   AppInsights connection and require agent-level blueprint/identity UUIDs.
4. For MAF, use the package-only pipeline path against an existing App Service.
   Platform-owned MI, custom identity IDs and monitoring must already exist.
   Agent 365 settings are validated when opted in.
5. Publish only after effective-policy, identity, functional, safety, data-access,
   trace-delivery and, where selected, Agent 365 checks pass.

The creation checks read Foundry identity metadata, not Entra object enabled
state or sign-in logs. Platform identity verification is still required.
Identity-check failure can occur after a version was created: the scripts fail
explicitly and do not delete it. Inspect it before retrying.

`render` and PowerShell `-WhatIf` remain offline previews and are not evidence
of platform readiness. Existing-index reuse does not grant ingestion rights.
The code checks connection configuration, not trace delivery or effective
guardrail policy. Those remain platform/release acceptance checks.

## 6. Hosting and identity coverage

| Workload | Current repository support | Remaining release conditions |
|---|---|---|
| Portal Prompt agents | No-code instructions; Foundry-managed identity lifecycle | Platform onboarding verifies identity for each new agent; portal creation is not intercepted by this repository |
| Governed Prompt/RAG | SDK, REST and pipeline creation; project-monitoring/identity metadata checks | Directory-state verification, effective guardrail and telemetry evidence; RAG tool authorization |
| App Service MAF | Application tracing; custom Agent ID S2S path for opt-in Agent 365; package-only delivery to preconfigured host | Custom identity/trust is required even if Agent 365 is off. Package checks confirm IDs/configuration, not directory state. Foundry inference still uses workload MI |
| AKS multi-agent | Target hosting option, not an implemented deployment in this kit | Customer cluster/image/registry, workload federation, application manifests, ingress/auth, instrumentation and verified custom Agent ID/365 token flow. Current MAF Agent 365 bootstrap defaults to ManagedIdentityCredential, not an AKS workload-identity implementation |
| Audio TTS/STT | Direct model API and optional application monitoring | No custom Agent ID/365 integration yet; blocked from release under the all-agents identity requirement until implemented and verified |

Foundry **Prompt Agent hosting** does not require the separate Foundry
**Hosted Agent** container service. AKS and custom connector implementation
must be designed/approved separately; no cluster is provisioned by this change.

## 7. Agent 365 opt-in

- Platform/tenant administrators approve licensing, consent, privacy/residency
  and account-wide collection before opting in.
- Check actual state: Microsoft documents that collection can default on when
  Agent 365 is enabled for the tenant. Repository flags defaulting off do not
  disable a previously enabled account.
- For supported Foundry Prompt agents, existing and new projects inherit the
  resource's collection setting. There is no per-agent/project override.
- Do not equate collection enablement with verified inventory enrollment.
  Check actual visibility and activity for both existing and newly created agents.
- External MAF/audio/AKS applications need their own supported registration
  and export; resource-level collection does not automatically enroll them.
- No Mail/Teams/Files Graph permission or agent user mailbox is required just
  to run these inference/retrieval agents.

## 8. References

- [All-agent prerequisite tables](./AGENT-PREREQUISITES-README.md)
- [Detailed customer prerequisites](./CUSTOMER-PREREQUISITES.md)
- [Customer handover](./CUSTOMER-HANDOVER.md)
- [No-code portal workflow](./01-experimentation-agents/README.md)
- [Agent Identity](./agent-identity/README.md)
- [Agent 365](./agent-365/README.md)
- [Microsoft guardrail inheritance](https://learn.microsoft.com/azure/foundry/guardrails/guardrails-overview)
- [Microsoft project tracing](https://learn.microsoft.com/azure/foundry/observability/how-to/trace-agent-setup)
- [Microsoft Agent 365 collection scope](https://learn.microsoft.com/azure/foundry/agents/how-to/configure-agent-365-data-collection)
