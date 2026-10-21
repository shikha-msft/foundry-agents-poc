# Customer prerequisites - platform, access, Agent ID and Agent 365

**Customer infrastructure must already exist, provisioned through customer IaC
or the platform team.** The PowerShell provisioning scripts in this repository
are author/test-environment helpers, not the customer's infrastructure delivery
process. Do not run them over customer-managed resources to satisfy this list.

The customer application team consumes approved resource IDs, endpoints,
identities and configuration. Platform/identity teams own infrastructure,
provider registration, role assignments, tenant consent and identity trust.
Agent definitions/versions are application deliverables; Foundry-managed
identity objects can be created by Foundry when those agents are created.

Use the tables as a readiness checklist. Record **Ready / Blocked / Not
applicable**, owner and evidence for every applicable row before onboarding.
Do not mark a resource ready merely because a similarly named test resource
or an old deployment-output file exists.

The [platform operating model](./PLATFORM-OPERATING-MODEL.md) defines the
customer experience: **POC Project** for portal self-service, approved governed
projects and pipelines for productionization, Agent Identity for every agent,
and opt-in Agent 365. Platform onboarding supplies each project's tracing and
the approved model-deployment guardrail baseline; not all controls inherit
directly from the Foundry resource. External-host instrumentation/identity is
separate.

## 1. Required resources and platform configuration

**Baseline** means required for the two-project layout in this kit.
**RAG**, **MAF**, **Agent ID** and **Agent 365** rows apply when using that
capability; customer-mandated capabilities remain release gates.

| Scope | Resource/prerequisite that must exist | Required configuration/evidence | Owner |
|---|---|---|---|
| Baseline | Entra tenant and enabled Azure subscription | Approved tenant/subscription IDs, region, policies, budget and workload ownership | Platform/tenant administrator |
| Baseline | Resource group(s) | Approved resource IDs, naming/tags, locks and IaC ownership; map configuration to the actual topology | Platform |
| Baseline | **Microsoft Foundry V2 resource** | `Microsoft.CognitiveServices/accounts`, kind `AIServices`, project management enabled; supported region/network configuration. Classic hub-based projects are not supported | Platform |
| Baseline | Experimentation Foundry V2 project | `EXPERIMENTATION_PROJECT_NAME`, display name, resource ID and system-assigned MI principal ID | Platform |
| Baseline | Governed Foundry V2 project | `GOVERNED_PROJECT_NAME`, display name, resource ID, system-assigned MI and `PROJECT_ENDPOINT` | Platform |
| Baseline | Chat model deployment | Approved deployment/version, quota/capacity and content-filter configuration; `MODEL_DEPLOYMENT_NAME` must name a deployment, not just a catalog model | Platform/AI owner |
| Audio API | TTS and transcription model deployments | Separate approved deployments for `/audio/speech` and `/audio/transcriptions`; supported formats/voices and quota; `TTS_MODEL_DEPLOYMENT_NAME` and `STT_MODEL_DEPLOYMENT_NAME` | Platform/AI owner |
| Audio API | OpenAI-compatible resource endpoint and HTTP runtime | `FOUNDRY_AUDIO_ENDPOINT` ends `/openai/v1/`, not `/api/projects/...`; customer-owned Python API hosting if deployed remotely; audio privacy/consent and network policy | Platform/application/security |
| Baseline | Experimentation Log Analytics workspace | `EXPERIMENTATION_LOG_ANALYTICS_NAME`, retention, approved ingestion/query connectivity and access policy | Platform/operations |
| Baseline | Governed Log Analytics workspace | `GOVERNED_LOG_ANALYTICS_NAME`, retention, approved ingestion/query connectivity and access policy | Platform/operations |
| Baseline | Experimentation workspace-based Application Insights | `EXPERIMENTATION_APPLICATION_INSIGHTS_NAME`, linked to its approved workspace | Platform/operations |
| Baseline | Governed workspace-based Application Insights | `GOVERNED_APPLICATION_INSIGHTS_NAME`, linked to its approved workspace; also consumed by the MAF app | Platform/operations |
| Baseline | Each project's Application Insights connection | Project `AppInsights` connection targets the correct component; tracing and ingestion verified. Test helper uses an API-key/connection-string connection; validate customer policy compatibility | Platform/AI owner |
| Baseline | Runtime and operator identities/RBAC | All applicable assignments in section 3 exist, with exact object IDs and scopes | Platform/identity |
| Baseline | Content safety/RAI configuration | Approved model filters/guardrails, test dataset, risk owner, measurable evaluation thresholds and release approval | AI/security |
| RAG | Azure AI Search service | Supported region/tier/features and approved network access; authentication mode documented | Data/platform |
| RAG | Populated Search index, or approved synthetic-index creation | Default `existing` mode uses `AZURE_AI_SEARCH_INDEX_NAME` unchanged. Optional `create` mode creates a separate synthetic PoC index; see the [RAG index options](./02-governed-agents/02-rag-agent/README.md#choose-an-existing-index-or-create-a-synthetic-index) for setup permissions and embedding prerequisites | Data owner |
| RAG | Search project connection | Full `AZURE_AI_SEARCH_CONNECTION_ID`, correct service/index, actual authentication principal and query/top-K settings | Data/platform |
| RAG | Ingestion pipeline and its identity | Approved source, separate ingestion/write permissions, refresh/deletion process. The optional three-document synthetic seed is not a customer-data ingestion pipeline | Data owner |
| RAG - synthetic create only | Approved embedding and index setup | Existing `text-embedding-3-small` deployment, `AZURE_AI_EMBEDDING_ENDPOINT` ending `/openai/v1/`, deployment name, setup/ingestion permissions, and Search system-assigned MI embedding access. Helper does not grant roles or change service settings | Data/platform |
| RAG/MAF | Embedding deployment if the chosen ingestion/query design needs it | Approved model/deployment and vector dimensions consistent with index; not required for a text-only Prompt agent | Data/AI owner |
| MAF | Linux App Service plan | `APP_SERVICE_PLAN_NAME`, approved SKU/capacity supporting required runtime/Always On configuration | Platform |
| MAF | Existing Linux Python web app | `WEB_APP_NAME`, Python 3.12, approved HTTPS/network configuration, package deployment access, startup command `startup.sh` and health path `/healthz` | Platform/application operations |
| MAF | Web app system-assigned MI | Enabled, stable principal ID recorded; Foundry access and blueprint federation configured as applicable | Platform/identity |
| MAF | App configuration/build settings | Correct project/model/agent names, tenant, monitoring connection, autonomy limits; Oryx/remote-build settings if that packaging path is used | Platform/application operations |
| MAF - optional for PoC | Entra app registration/service principal for Easy Auth | Not required for the controlled PoC. If enabled: `ENTRA_CLIENT_ID`, correct tenant/issuer, audiences, caller policy and redirect URI as applicable | Identity/platform |
| MAF - controlled PoC | Endpoint access boundary | Without Easy Auth: leave `ENTRA_CLIENT_ID` empty, set `REQUIRE_APP_SERVICE_AUTH=false`, and restrict access through approved network controls. Do not expose an unauthenticated API publicly. Production requires authentication | Platform/security |
| Agent ID | Tenant feature availability and identity policy | Supported Agent ID APIs, owner/sponsor standards, credential/federation policy and approved provisioning client where needed | Identity |
| Agent 365 | Tenant entitlement and integration state | Licensing, tenant consent, shared-account approval, registration/export prerequisites in section 6 | Agent 365 administrator |
| All selected capabilities | Monitoring and operations | Alerts/dashboards, log access, retention/redaction, incident process, review dates and restricted evidence storage | Operations/security |

The two-workspace/two-component layout mirrors the reference test setup.
If the customer uses shared monitoring or multiple resource groups, the
platform team must approve and validate the mappings; do not overwrite its
topology to match the helper scripts.

**Easy Auth is optional for this PoC.** It authenticates callers to the MAF
HTTP API; it is separate from App Service MI access to Foundry, Entra Agent ID
and Agent 365. Omitting it does not remove those service-to-service prerequisites.
Configuration templates/code retain authentication-enabled defaults; explicitly
apply the controlled-PoC settings above and verify actual App Service
Authentication state. An app setting alone does not disable platform Easy Auth.

For the author's test helper, `-EnableEasyAuth` explicitly opts in; for its MAF
pipeline, select `enableEasyAuth=true`. Both default off for PoC and explicitly
disable existing platform auth in off mode. A client ID alone does not enable
the feature. Direct application startup retains its authentication-enabled
default unless `REQUIRE_APP_SERVICE_AUTH=false` is supplied.

## 2. Azure resource providers

Provider availability/registration is a **subscription/platform prerequisite**,
not an agent-developer task. Verify the required namespaces are available and,
where registration is required, in `Registered` state. Register only services
used by the approved design; Entra Agent ID and Agent 365 consent are not Azure
resource-provider registrations.

| Namespace | Required for | Applicability/owner |
|---|---|---|
| `Microsoft.CognitiveServices` | Foundry resource/projects, models (including audio) and project connections | Baseline; platform. Direct audio APIs do not require a separate Speech resource/provider |
| `Microsoft.Insights` | Application Insights and monitoring configuration | Baseline; platform |
| `Microsoft.OperationalInsights` | Log Analytics workspaces | Baseline; platform |
| `Microsoft.Authorization` | Azure role assignments | Baseline; platform verifies availability/registration behavior |
| `Microsoft.Search` | Azure AI Search | RAG; platform |
| `Microsoft.Web` | App Service plan/web app and runtime configuration | MAF; platform |
| `Microsoft.ContainerService` | Customer-managed AKS cluster | Target multi-agent hosting option only; no deployment manifests/pipeline supplied |
| `Microsoft.ContainerRegistry` | ACR for customer container images | Conditional on customer image/registry choice |
| `Microsoft.Network` | VNets/subnets, private endpoints, private DNS and related network resources | When customer topology requires them; network/platform |
| `Microsoft.ManagedIdentity` | User-assigned managed identities | Only if selected; do not infer a separate user-assigned MI is needed for system-assigned identities |
| `Microsoft.Storage` | Blob/ADLS ingestion sources or separately selected storage | Conditional, not a standalone prerequisite of the current Prompt/MAF runtime |
| `Microsoft.KeyVault` | Customer-managed secret/certificate storage | Conditional; do not introduce secrets merely because a vault exists |
| `Microsoft.DocumentDB` | Cosmos DB integration | Only for an approved extension, not the implemented Search RAG path |
| `Microsoft.DBforPostgreSQL` | Azure Database for PostgreSQL integration | Only for an approved extension |
| `Microsoft.Compute` | Azure VM used as a self-hosted ADO agent | Only if the agent VM is Azure-hosted; pool registration is separate |

Network/provider dependencies can vary by customer IaC module. The platform
team must include any additional namespaces used by its approved topology.

## 3. Azure RBAC and data permissions

These are **pre-assigned platform permissions**, not permissions every
developer or VM should receive. Use least-privilege custom roles where approved.
Allow for propagation and check inherited access before testing denial.

| Principal | Role/access | Scope | Purpose/condition |
|---|---|---|---|
| Agent developer group | **Foundry User** | Approved experimentation/governed project | Create, configure and test agent definitions |
| Portal developer group | **Reader** | Parent Foundry account as needed | Portal navigation; not agent data-plane authorization |
| Publisher/endpoint owner | **Foundry Project Manager** as required by supported operation | Approved project/account scope | Endpoint/publication management; separate from ordinary creation |
| Each project system-assigned MI | **Foundry User** | Parent Foundry account in the reference baseline | Model/project capabilities; validate narrower supported scopes if adopted |
| Each project MI | **Log Analytics Reader** | Its Application Insights component in the test helper's assignments | Reference helper behavior; platform must validate effective monitoring access in its policy/topology |
| Each project MI | **Privileged Monitoring Data Reader** | Its Application Insights component | Reference monitoring baseline; separately approve privileged telemetry access |
| Actual RAG retrieval principal | **Search Index Data Reader** | Approved supported Search service/index scope | Query approved index; confirm tool actually authenticates as this principal |
| Search ingestion identity | Approved ingestion permissions, e.g. **Search Index Data Contributor** | Approved Search scope | Write/refresh index data; never automatically grant to query-only agent |
| Search setup operator | **Search Service Contributor** and additional data rights only if setup requires them | Approved Search scope | Manage schema/configuration; not a default runtime grant |
| App Service MI | **Foundry User** | Parent Foundry account in reference deployment, or verified narrower scope | MAF model/remote-agent calls; not Graph administration |
| Monitoring reviewers | **Log Analytics Reader** | Approved workspace | Query telemetry |
| Monitoring reviewers | Approved Insights read role, e.g. **Monitoring Reader** | Approved Insights component | Metrics/resource monitoring; does not override restricted log/data policies |
| Agent creation ADO service principal | **Foundry User** | Governed project | Create versions; no general resource creation/Graph grants needed |
| Audio API runtime/local developer | **Cognitive Services OpenAI User**, or verified equivalent audio data-plane rights | Approved audio model account | Direct synthesis/transcription; a project agent-creation role alone is not proof of model access |
| Customer application deployment principal | Approved package-deployment permissions, e.g. **Website Contributor** with customer-validated deployment actions | Existing web app/slots as appropriate | Application package delivery only; no automatic RG Contributor or RBAC administrator requirement |
| Platform IaC principal | **Contributor** or scoped resource-management role | Resources it owns | Platform provisioning/change control, not routine agent development |
| Platform role-assignment principal | **Role Based Access Control Administrator**, **User Access Administrator**, or approved equivalent/conditional delegation | Exact role-assignment scopes | Establish approved grants; Contributor alone cannot do this |
| Foundry Agent 365 configuration operator | Account read/write, e.g. **Contributor** | Foundry account only | Platform-approved logging change; not tenant consent |
| MAF registration/configuration operator | App identity read and app-settings update authority | Existing web app | Separate from Graph blueprint provisioning/consent |

The two monitoring assignments on the project MI above explicitly inventory
what the test script assigns. They are not a claim that these roles at that
scope are the universal minimum for every customer monitoring design.

If Blob/ADLS, Cosmos or PostgreSQL are later added, approve separate data-plane
grants: Storage Blob Data Reader plus ADLS ACLs as needed; Cosmos native data
RBAC; or PostgreSQL Entra principal/SQL grants. Azure Contributor is not a
substitute. These are not required by the current Search-only implementation.

## 4. Network, security and application readiness

| Prerequisite | Required ready state | Owner |
|---|---|---|
| Routes/firewalls/private DNS | Foundry, Search, App Service, SCM/deployment and monitoring endpoints reachable from the appropriate caller/runtime; private FQDNs resolve correctly | Network/platform |
| Platform control-plane access | Approved Entra and ARM endpoints reachable from operators/ADO | Network/identity |
| Agent 365/Graph egress | Approved Microsoft Graph, Entra token and Agent 365 endpoints reachable for setup/runtime as applicable | Network/identity |
| Package/tool feeds | Approved Python/.NET/ADO download feeds or mirrors; TLS validation retained | Platform/ADO |
| Secret handling | Approved restricted store, rotation/revocation and no credentials in Git, ordinary variable groups or logs | Security/identity |
| Monitoring authentication | Existing connection-string/SDK path permitted by policy or a separately implemented/validated alternative | Platform/security |
| RAG access boundary | Approved synthetic dataset first; document-level/caller security design when needed | Data/security |
| Safety gates | Content filters/guardrails configured; injection/exfiltration/groundedness evaluation thresholds approved | AI/security |
| Application artifacts | Prompt/RAG versions created and verified before MAF invocation; version routing recorded | Application team |

The current PoC does not implement explicit app-level Content Safety calls,
per-user Search filtering or the separate shared harness. Existing resources
and Entra sign-in alone do not close those functional gaps.

The [03 audio API](./02-governed-agents/03-multimodal-tts-agent/README.md)
implements file-based synthesis/transcription, not a Foundry Prompt Agent.
It does not yet implement custom Agent ID/Agent 365 token/export integration.
If mandatory for every agent, that integration is a release blocker for the
audio sample; do not assume the existing MAF registration or Prompt Agent
account logging covers it.

## 5. Entra Agent ID prerequisites

Foundry-managed and customer-managed identity paths differ. **Do not pre-create
duplicate blueprints for Foundry-managed agents.** Foundry can create its
managed objects when the application team creates a new-model agent.

| Path/area | Required prerequisite/state | Owner/evidence |
|---|---|---|
| Tenant | Agent ID available; supported Graph/Foundry APIs and identity creation permitted by tenant policy | Identity administrator |
| Administrative authority | Approved Agent Identity Developer/Administrator, blueprint ownership or other documented authority appropriate to the operation | Identity administrator verifies current role/ownership requirements; not all roles confer consent authority |
| Governance | Owner, sponsor, naming, review/expiry, workload restrictions and decommissioning process | Identity/security |
| Foundry managed path | Platform permits Foundry-managed identity provisioning; application creator has Foundry project access | No blanket Graph provisioning grants on every developer |
| Foundry model check | New-model agent identity verified from agent-level details; legacy shared identity explicitly recorded or blocked if isolation is mandatory | Application/identity teams after agent creation |
| Custom MAF blueprint | Approved blueprint application and its Blueprint Principal established by identity team's process | Application/client ID, application object ID and principal object ID recorded separately |
| Custom MAF agent identity | Agent Identity associated with the approved blueprint; sponsor/owner and resource grants verified | Agent client ID and principal object ID recorded separately |
| Graph provisioning authentication | Dedicated, supported client flow with explicit scopes/application permissions and tenant-approved credentials/federation | Ordinary interactive Azure CLI tokens may be rejected by Agent ID APIs |
| Graph consent | Necessary permissions consented using authorized administrator/process | Human roles, app permissions and Azure RBAC are separate grants |
| Runtime blueprint trust | FIC trusts the deployed App Service system-assigned MI | Subject = MI principal ID; issuer = tenant v2 URL; audience = `api://AzureADTokenExchange` |
| Runtime settings | `A365_BLUEPRINT_CLIENT_ID`, `A365_AGENT_CLIENT_ID`, tenant and agent name supplied securely/configured correctly | Platform/identity; IDs are not interchangeable with principal object IDs |
| Runtime grants | Only approved resource permissions on actual agent principal; S2S telemetry grants for current MAF export path | Identity/resource owner |
| Audit readiness | Sign-in/audit review, positive/negative authorization evidence and identity register | Identity/operations |

### Graph permission request checklist

The identity team selects only operations it performs and validates current
delegated/application support, ownership restrictions and admin-consent roles.
This is **not a blanket bundle** to grant to a VM, developer or runtime agent.

| Operation | Permission candidates to verify | When applicable |
|---|---|---|
| Create blueprint | `AgentIdentityBlueprint.Create` | Custom provisioning |
| Read/update blueprint | `AgentIdentityBlueprint.ReadWrite.All` | Custom lifecycle management |
| Create Blueprint Principal | `AgentIdentityBlueprintPrincipal.Create` | Custom provisioning |
| Create agent identity | `AgentIdentity.Create.All` | Custom provisioning |
| Read/update agent identities | `AgentIdentity.ReadWrite.All` | Custom lifecycle management |
| Add blueprint credential/federation | `AgentIdentityBlueprint.AddRemoveCreds.All` plus required read access | App Service bootstrap trust |
| Update blueprint authentication properties | `AgentIdentityBlueprint.UpdateAuthProperties.All` if required by selected setup | Validate against exact API/CLI operations |
| Assign resource application roles | `AppRoleAssignment.ReadWrite.All` only when required | S2S/resource grants |
| Grant delegated permissions | `DelegatedPermissionGrant.ReadWrite.All` only when required | OBO/delegated extensions, not current S2S runtime |

The current helper does not implement a supported bring-your-own-blueprint
parameter or a dedicated Graph-client authentication path. Customer platform
setup must supply consistent identity/registration/trust state; changing IDs in
app settings alone does not migrate a registration. Detailed concepts and
token flow are in the [Agent Identity guide](./agent-identity/README.md).

## 6. Agent 365 prerequisites

| Area | Required prerequisite/state | Owner/evidence |
|---|---|---|
| Licensing/availability | Active customer entitlement and feature availability for selected integration | Agent 365/tenant administrator; do not infer from Azure subscription |
| Tenant consent | Required Agent 365 tenant-level consent completed | Authorized identity administrator and consent record |
| Shared-account approval | All covered Foundry projects/Prompt agents approved for collection, including experimentation and unrelated workloads | Account owner/security; no per-agent opt-out under that account |
| Privacy/residency | Tenant-geography processing, retention, redaction and viewer access approved | Privacy/security/operations |
| Foundry collection | Existing account configured with `a365LoggingEnabled=true`, `a365Status=Enabled` using supported API | Platform supplies fresh read evidence; enabled is not proof of delivery |
| MAF registration | Existing custom S2S orchestrator registration mapped to the correct blueprint/agent identity | Agent 365/identity team; one registration for current coordinator |
| Identity trust/grants | Section 5 custom blueprint, principal, agent, MI trust and S2S permissions ready | Identity team; specialist wrappers are not separate registrations |
| MAF runtime configuration | `AGENT365_ENABLED=true`, name/tenant/client IDs, `AGENT365_AUTH_MODE=s2s`, exporter and S2S endpoint enabled, input suppression true | Platform/application operations |
| Export connectivity | Entra/Agent 365 endpoints reachable from web app; correct tenant/audience | Network/identity |
| Admin setup tooling | Approved .NET 8/Agent 365 CLI version and supported authenticated client flow, if used by platform setup | Platform/identity; not required on every agent developer's machine |
| Automation gate | Actual noninteractive Graph/CLI principal proven without cached human login or browser/device-code prompt | Identity/ADO; ARM WIF login alone is insufficient |
| Delivery evidence | Separate synthetic invocations for portal experiment, Prompt, RAG and MAF received under expected agent identities | Operations/application owner |
| Recovery | Partial-failure ownership, registration reuse, exact grant/federation rollback and retained telemetry policy | Platform/identity/operations |

The customer need not run `provision-agent365.ps1`; its platform/identity
process provides these states. The helper's preview API/CLI assumptions are
test references only. See the [Agent 365 guide](./agent-365/README.md) for
concepts, checks and known unattended setup limitations.

## 7. ADO and workstation prerequisites

| Scope | Required prerequisite/state | Owner |
|---|---|---|
| Application ADO | Project/repo, authorized agent-creation WIF service connection, variable group and protected application environment | ADO/platform |
| Application ADO | `foundry-agents-poc-environment` populated from approved platform outputs, not author/test `.env` | ADO/application |
| Application ADO | Correct `pocDirectory` and approved Linux pool; Python 3.12 in ADO tool cache for `UsePythonVersion@0`, Bash, Git, Azure CLI and feeds | ADO |
| Customer MAF delivery | Customer-owned package-only pipeline targeting existing web app; protected connection with scoped deployment rights | ADO/application/platform |
| Self-hosted VM | Dedicated low-privilege OS account, pool registration, network/DNS/feed access and cleanup policy | ADO/platform; VM does not need Azure administrator RBAC just to run jobs |
| Test helper stages only | Windows pool with Azure CLI, PowerShell 7/Windows PowerShell; .NET 8/CLI for custom registration | Author/test environment, not a mandatory customer infra-provisioning path |
| Local application testing | Python 3.12, Git, approved dependencies and correctly scoped Azure CLI login | Application developer |
| Optional operator tooling | PowerShell 7/Azure CLI for administrative read checks; Graph/CLI tools only on approved setup hosts | Platform/identity |
| Evidence/secrets | Restricted artifacts/register, no generated credential files in ordinary build artifacts | ADO/security |

For customer agent creation, keep `provisionInfrastructure=false` and
`enableAgent365Foundry=false`; platform prerequisites are already satisfied.
The MAF YAML now defaults `provisionInfrastructure=false` and uses the
package-only delivery script. It validates platform-owned MI, custom identity
IDs and monitoring configuration without creating resources or changing app
settings. Custom identity is required even when Agent 365 is off. Directory
state, federation and delivery still need platform evidence. The combined
helper runs only with explicit author/test infrastructure opt-in. Keep
`provisionAgent365=false` when identity/registration is already platform-owned.

## 8. Platform-to-application handover checklist

| Deliverable | Must be supplied before application onboarding |
|---|---|
| Resource inventory | Tenant/subscription/resource group(s), Foundry account/projects, model deployments, Search/index/connection, workspaces/Insights, web app/plan resource IDs |
| Application configuration | Approved values for root and per-app templates, endpoints, names and non-secret identity IDs; monitoring values through approved configuration channel |
| Access inventory | Principal object ID, role, exact scope, approver, propagation/positive-and-negative test evidence |
| Directory inventory | Blueprint/client/object IDs, Blueprint Principal, Agent Identity IDs, sponsors, trust, consent and registration evidence as applicable |
| Network/security | Connectivity/DNS evidence, content filters, data access policy and approved safety/evaluation plan |
| Operations | Telemetry receipt/correlation, retention/redaction, alerts, incident/recovery contacts and review dates |
| Ownership acceptance | Platform, data, identity/Agent 365 and application owners sign off their applicable rows |

Do not create agent versions until baseline/project prerequisites are ready;
do not invoke real-data RAG until its actual tool identity and data boundary
are approved. Foundry-managed identity evidence is finalized after agent
creation, not fabricated ahead of time.

## References

- [Customer handover runbook](./CUSTOMER-HANDOVER.md)
- [Foundry RBAC](https://learn.microsoft.com/azure/foundry/concepts/rbac-foundry)
- [New versus legacy Foundry identity](https://learn.microsoft.com/azure/foundry/agents/how-to/migrate-agent-applications)
- [Entra Agent ID setup](https://learn.microsoft.com/entra/agent-id/identity-platform/agent-id-setup-instructions)
- [Foundry Agent 365 collection](https://learn.microsoft.com/azure/foundry/agents/how-to/configure-agent-365-data-collection)
- [Agent 365 CLI](https://learn.microsoft.com/microsoft-agent-365/developer/agent-365-cli)

This is a readiness specification, not confirmation that the customer's
resources, permissions, licenses or tenant integrations have been validated.
