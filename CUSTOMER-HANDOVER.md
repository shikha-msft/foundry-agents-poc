# Customer setup and handover runbook

Start here when deploying this PoC into a new customer environment. Commands
below use PowerShell 7 unless explicitly marked Bash. Replace placeholders;
do not paste tenant-specific values or credentials into this repository.

For detailed explanations alongside this ordered runbook:

- [Agent 365 guide](./agent-365/README.md): integration paths, tenant approval,
  setup, telemetry, ADO gates and recovery.
- [Agent Identity guide](./agent-identity/README.md): blueprint objects, ID types,
  Foundry lifecycle, permissions, federation and runtime token exchange.

## 1. Scope and release gates

This kit targets **Microsoft Foundry V2 resource/projects**, not classic
hub-based projects. It references an existing Foundry account, creates two
projects with monitoring, creates Prompt/RAG agents, and deploys an optional
multi-agent coordinator to **App Service**. Foundry Hosted Agents are not
required or deployed.

Agent 365 is opt-in in the scripts. If the customer's architecture requires
Agent 365 for every agent, its licensing, consent, registration, and telemetry
checks below are **release gates**, not optional acceptance criteria.

| Capability | What this repository provides | Customer must still verify/provide |
|---|---|---|
| Observability | Project monitoring resources; MAF Azure Monitor/Agent 365 instrumentation | Trace ingestion, correlation, redaction, alerts and retention |
| Governance | Separate deployment identities, approval environments, instructions | Named owners, risk approval, access reviews and release evidence |
| Responsible AI/content safety | Instructions and test checklists | Approved Foundry content filters/guardrails and measured safety evaluations |
| Agent identity | Foundry-managed identity lifecycle; MAF Agent 365 setup/federation path | Actual identities, least-privilege grants and sign-in evidence |
| RAG | Existing Search connection/index integration | Ingestion, index schema, data ownership and document access boundaries |
| Multi-agent | App Service MAF coordinator calling remote Prompt/RAG agents | Easy Auth configuration and authorization testing |

The PoC does **not** integrate the separate sibling `agent-harness` package.
It does not implement explicit application-level Content Safety/Prompt Shields
checks, multimodal input, an MCP service, automated evaluation release gates,
or per-caller RAG document filtering. Instructions and metadata are not
enforcement. The MAF gateway invokes agents by name, not a pinned version;
verify the resolved version after changes before release.

**Validation status:** this runbook is not evidence of a successful deployment
in the customer's tenant. Complete section 10 in a clean customer environment.
In particular, MAF Agent 365 setup through an unattended ADO service connection
has not been demonstrated. Never report it as validated on the strength of a
successful Azure login or `-WhatIf`.

## 2. Who performs each step

| Persona | Responsibilities | Stop/approval boundary |
|---|---|---|
| Platform administrator | Existing account, model deployments, monitoring, network routes, Azure RBAC | Approve resource and role-assignment scopes |
| Entra/Agent 365 administrator | Availability/licensing, consent, blueprint ownership, Graph access, Easy Auth app | Approve directory grants and shared-account logging impact |
| Data/Search owner | Index/connection, synthetic dataset, retrieval principal, access tests | Approve data scope before real data is used |
| ADO administrator | Pools, workload-federated service connections, variable group, protected environments | Authorize only the intended pipelines |
| Agent developer | Definitions, local checks, agent creation, functional/safety tests | Cannot self-approve privileged grants or production release |
| Operations/release owner | Evidence register, telemetry, rollback, access review and cleanup | Sign off only after all mandatory checks pass |

One person can hold several responsibilities, but record which approved
identity performs each privileged operation.

## 3. Permission matrix

Azure roles, Entra administrator roles and Microsoft Graph API permissions
are different grants. **Contributor does not authorize role assignment or
Graph provisioning.** A human's Entra role is not an application permission
on a pipeline service principal.

| Identity | Required Azure access | Directory/data access |
|---|---|---|
| Agent creation service connection | **Foundry User** on the governed project | No broad Graph permissions for Foundry-managed creation |
| Infrastructure service connection | **Contributor** on the target resource group | **User Access Administrator** or approved RBAC administrator at every scope where the script assigns roles: parent Foundry account and new Insights components |
| App Service deployment service connection | **Contributor** on the target resource group; role-assignment authority on the parent Foundry account | No Graph grants needed solely to deploy the web app |
| Foundry Agent 365 service connection | Account read/write, e.g. **Contributor** at the account scope | Tenant licensing/consent completed separately |
| MAF Agent 365 setup operator/client | Read App Service identity; update its app settings | Approved Agent ID/Graph setup and consent authority; see section 8 |
| App Service managed identity | **Foundry User** on the account (the deploy script assigns here) | Bootstrap for Agent 365 token exchange, not a directory administrator |
| Actual RAG tool principal | **Search Index Data Reader** on the approved supported Search scope | Verify the identity actually used; no ingestion/write access by default |
| Monitoring reviewers | **Log Analytics Reader** on the workspace plus approved Insights read access | No prompt/document payload access unless separately approved |

For portal users also grant parent-account **Reader** as needed for navigation.
Publication/endpoint management can require **Foundry Project Manager**; do not
assume a creator is also an authorized publisher. If custom roles or conditional
RBAC delegation are used, validate the actions against the scripts.

## 4. Prepare the customer environment

1. Record tenant/subscription, region, resource group, existing Foundry account,
   project names, model deployment names, Search service/index, owners and
   approved data classification.
2. **Prerequisite: Microsoft Foundry V2.** Confirm an existing Microsoft
   Foundry resource (`AIServices` account) has Foundry project management
   enabled in the selected region. Classic hub-based Azure AI Foundry projects
   are not supported. This kit creates projects under the existing resource;
   it does not create or migrate the parent account. Before agent creation,
   confirm the project endpoint uses
   `https://<account-name>.services.ai.azure.com/api/projects/<project-name>`.
   Deploy an approved chat model with sufficient quota. This kit does not
   create the model or the Search ingestion pipeline.
3. Confirm providers are registered: `Microsoft.CognitiveServices`,
   `Microsoft.Insights`, `Microsoft.OperationalInsights`,
   `Microsoft.Authorization`, and `Microsoft.Web` for App Service. A subscription
   administrator handles registration if resource-group permissions are insufficient.
4. Approve network access. Scripts do not create private endpoints, DNS zones
   or a private App Service topology. Do not enable public access to bypass
   customer policy.
5. Clone the PoC repository. All subsequent relative paths assume the checkout
   root contains [deploy.ps1](./deploy.ps1) and
   [azure-pipelines.yml](./azure-pipelines.yml).
6. Install customer-approved Git, Azure CLI, PowerShell 7 and Python 3.12.
   Check `git --version`, `az version`, `$PSVersionTable.PSVersion` and
   `python --version`. .NET 8 SDK and the Agent 365 CLI are needed only for
   the MAF registration path.
7. From the checkout root:

   ```powershell
   Copy-Item .env.sample .env
   az login --tenant "<tenant-id>"
   az account set --subscription "<subscription-id>"
   az account show --query "{subscription:id,tenant:tenantId}" --output json
   ```

8. Populate every applicable placeholder in the root `.env`. Root scripts read
   that file; the Python applications read their **own folder's** `.env`.
   Copy each selected application's `.env.sample` to its `.env` and keep tenant,
   endpoint, model, agent names and monitoring values consistent. The standalone
   scripts use `AGENT_NAME`; root configuration uses `PROMPT_AGENT_NAME` and
   `RAG_AGENT_NAME`.
9. Do not set local managed/workload identity variables unless using those
   authentication methods. Use Azure CLI login for ordinary local development.
   Never upload populated `.env` files to ADO.

**Expected result:** approved configuration and a correctly scoped login; no
resources have been deployed. Local environment variables override root dotenv
values, so clear stale values before switching customer environments.

## 5. Provision projects, then create agents

### 5.1 Projects and monitoring - platform administrator

From the checkout root:

```powershell
.\deploy.ps1 -WhatIf
.\deploy.ps1
```

Preview still needs authenticated read access; it is not an offline test.
Review the planned scopes before the second command. Expect two projects,
two Log Analytics workspaces, two Application Insights components, project
connections and the role assignments documented in the
[main README](./README.md). Store the generated `deployment-output.json` in
restricted handover evidence. Confirm resources and connections in Azure;
an output file alone does not prove current health.

### 5.2 Prompt and RAG - developer and data owner

Follow the [Prompt setup](./02-governed-agents/01-prompt-agent/README.md) and
[RAG setup](./02-governed-agents/02-rag-agent/README.md), in that order.
Configure each folder's `.env` **before** `create` or `invoke`.

1. Create the Prompt Agent with synthetic data; record its name/version.
2. For RAG, first create/approve the Search connection and populated index.
   Validate vector/semantic settings against the actual schema.
3. Create the RAG Agent; save its creation response in restricted evidence.
4. Resolve and verify its actual identity as described below.
5. Grant approved read access to the verified retrieval principal.
6. Invoke both agents. Expect useful Prompt output and a RAG answer grounded
   in the synthetic source with citations. A fluent answer alone is not proof
   of successful retrieval.

Creation is **not idempotent**: rerunning `create` creates another version.
Do not rerun creation simply to diagnose an invocation or permission failure.

### 5.3 Resolve the blueprint/identity model before granting roles

The [current migration guide](https://learn.microsoft.com/azure/foundry/agents/how-to/migrate-agent-applications)
distinguishes two models:

| Agent | Identity behavior | Customer action |
|---|---|---|
| New agent object model | Unique agent identity and blueprint at agent creation | Inspect agent-level `blueprint` and `instance_identity` and register actual IDs |
| Legacy agent/application model | Development can use a shared project identity; legacy publication has a separate identity | Record the shared blast radius; do not claim per-agent isolation |

This kit uses the newer SDK/object model, but an SDK version or an old agent
name alone does not prove which model exists in a customer's tenant. Creating
another version of a legacy agent is not proof of migration.

Use each script's `list` command, then inspect agent details in Foundry. The
version-creation response may not contain all **agent-level** identity fields.
If necessary, retrieve agent details using the API documented for that tenant;
the migration guide currently illustrates:

```powershell
$projectEndpoint = "<PROJECT_ENDPOINT>"
$agentName = "<agent-name>"
az rest --method get --resource "https://ai.azure.com" `
  --url "$projectEndpoint/agents/${agentName}?api-version=2025-11-15-preview" `
  --query "{name:name,blueprint:blueprint,identity:instance_identity}" --output json
```

Record the actual API/SDK version with this result. If identity fields are null,
resolve legacy behavior or an unsupported API/tenant rollout with the platform
administrator. Do not keep waiting indefinitely, grant access to an arbitrary
principal, or create a duplicate blueprint as a workaround.

Record both **application/client IDs** and **service principal object IDs**.
Azure RBAC targets the principal object ID. Verify the token/sign-in identity
and tool connection authentication mode before assigning Search roles; a
connection using a different identity/key does not establish per-agent access.
If the customer requires distinct identity for every agent, shared legacy
identity is a release blocker.

## 6. Deploy the App Service coordinator

1. Follow the [MAF guide](./02-governed-agents/03-maf-multi-agent/README.md).
   Configure its local template before starting the API.
2. Have the Entra administrator create/approve the Easy Auth app registration,
   tenant, supported audiences and caller access policy. Configure the web
   redirect URI, if browser sign-in is used:
   `https://<web-app-name>.azurewebsites.net/.auth/login/aad/callback`.
3. Set `ENTRA_CLIENT_ID` and deploy from the MAF folder with `.\deploy.ps1`.
   The deployment identity needs the permissions in section 3.
4. Verify App Service Authentication is enabled, unauthenticated callers are
   rejected/redirected, and the tenant/audience/caller restrictions match policy.
   Production requires `REQUIRE_APP_SERVICE_AUTH=true`.
5. Test using an approved authenticated client through the actual App Service
   endpoint. Do not fake the `X-MS-CLIENT-PRINCIPAL-ID` header; the application
   trusts Easy Auth to establish that boundary.

**Identity flow in plain language:**

```text
ADO service connection -> creates/deploys resources (deployment only)
App Service managed identity -> calls Foundry agents/models
Verified remote RAG tool identity -> reads the Search index
App Service managed identity -> blueprint federation -> Agent ID token
                            -> Agent 365 telemetry
```

The current MAF Agent ID token resolver is for **telemetry**, not Foundry
inference authentication. One Agent 365 registration covers the coordinator;
the in-process specialist wrappers are not independently registered identities.

## 7. Azure DevOps and self-hosted VMs

### 7.1 Create connections and protected environments

1. Create the variable group `foundry-agents-poc-environment` from the root
   [.env.sample](./.env.sample). It is not automatically imported from dotenv.
   Populate applicable placeholders; do not put generated Agent 365 secrets
   in ordinary variables.
2. Create separate **Azure Resource Manager / workload identity federation**
   service connections. Enter their names in:
   `ADO_AGENT_SERVICE_CONNECTION`, `ADO_INFRASTRUCTURE_SERVICE_CONNECTION`,
   `ADO_APP_SERVICE_CONNECTION`, `ADO_AGENT365_SERVICE_CONNECTION`.
3. The Azure administrator grants the connection **principal** the matching
   roles from section 3, at the stated scopes. Do not grant all four identities
   subscription Owner. Verify tenant, subscription and WIF subject/issuer.
4. Create environments named by `ADO_INFRASTRUCTURE_ENVIRONMENT_NAME`,
   `ADO_AGENT_ENVIRONMENT_NAME`, `ADO_MAF_ENVIRONMENT_NAME` and
   `ADO_AGENT365_ENVIRONMENT_NAME`. Add appropriate approvers/checks.
5. Explicitly authorize each pipeline to use only its connections, environment,
   variable group and agent pools. Do not enable unrestricted pipeline access.
6. Create the main pipeline from `azure-pipelines.yml` and the MAF pipeline from
   `02-governed-agents/03-maf-multi-agent/azure-pipelines.yml`.

### 7.2 Prepare the self-hosted machines

The VM runs jobs; **the federated service connection supplies Azure authority**.
The VM does not need an Azure administrator role or a subscription-wide managed
identity just to execute these pipelines.

The existing tasks mix Bash and Windows PowerShell paths. Use **two OS-specific
pools** rather than putting a Linux job on a Windows VM or vice versa:

| Pool | Jobs | Required tools/configuration |
|---|---|---|
| Linux | Validation, standalone agent creation | Bash, Git, Azure CLI, Python 3.12, pip, ADO agent prerequisites |
| Windows | Project/App Service deployment; Agent 365 stages | Git, Azure CLI, PowerShell 7 (`pwsh`), Windows PowerShell; .NET 8 for MAF registration |

1. In ADO **Organization settings > Agent pools**, create restricted Linux and
   Windows self-hosted pools. Download the current agent on each machine and
   follow the OS-specific configuration instructions. Use a dedicated low-
   privilege OS service account. Registration credentials are not Azure runtime
   credentials; prefer short-lived registration authorization and revoke it
   after configuration.
2. Install tools under administrator control, then restart the agent service
   so its account sees the updated PATH. Do not run unattended jobs using an
   administrator's cached `az login` or `a365` browser session.
3. Provision Python 3.12 in the ADO agent tool cache for `UsePythonVersion@0`.
   Having `python` on PATH alone does not satisfy that task on self-hosted
   agents. See Microsoft's self-hosted Python task guidance below.
4. Permit outbound HTTPS to the organization's ADO/artifact endpoints, Entra,
   ARM, Foundry and approved package feeds. Deployment also needs App Service
   and its SCM endpoint; MAF registration needs Microsoft Graph and Agent 365.
   .NET/Python/tool downloads need their approved feeds or internal mirrors.
   Use the linked official agent networking list, not this summary as a complete
   firewall allowlist.
5. For private resources, verify VNet routing and private DNS resolution from
   the **agent service context** and separately from App Service/Foundry.
   A successful ARM call does not prove data-plane or SCM reachability.
6. Confirm both agents are online with the expected OS and tool capabilities.
   Avoid untrusted PR jobs on privileged persistent machines; clear workspaces,
   auth caches and generated files between customer environments.

Both YAMLs expose these queue-time parameters:

| Parameter | Default | Self-hosted value |
|---|---|---|
| `linuxPoolName` | `Microsoft-hosted` | Your approved Linux pool name |
| `windowsPoolName` | `Microsoft-hosted` | Your approved Windows pool name |

The default preserves `ubuntu-latest`/`windows-latest`. Set **both** parameters
for a fully self-hosted run. The YAML checks OS demands, not network reachability
or successful tool installation.

### 7.3 Run in controlled stages

1. Main pipeline: set all mutation parameters false for a validation-only run.
   `createPromptAgent` defaults true, so explicitly clear it.
2. Main pipeline: set `provisionInfrastructure=true` and both creation flags
   false. Verify project/monitoring resources.
3. Main pipeline: set the approved creation flags true and infrastructure
   false. Download the restricted `foundry-agent-responses` artifact; resolve
   agent-level identities before assigning data roles.
4. Complete Prompt/RAG tests before running the MAF pipeline.
5. Run the MAF pipeline with `provisionAgent365=false`; verify authentication,
   model calls and retrieval.
6. Enable Foundry Agent 365 only after section 8 approval. Keep MAF
   `provisionAgent365=false` until its separate unattended authentication
   acceptance test passes.

For a parent repository containing this PoC as a subfolder, set the YAML
`pocDirectory` parameter to `foundry-agents-poc`; for a standalone PoC checkout
leave it as `.`. Multi-repository checkouts/custom checkout paths require an
explicitly reviewed path adjustment.

## 8. Agent 365: admin setup before pipeline automation

### 8.1 Tenant approval

The Entra/Agent 365 administrator must confirm:

- Tenant availability, active licensing and completed Agent 365 consent.
- Owner/sponsor and lifecycle process for custom agent blueprints/identities.
- **Account-wide impact:** Foundry logging affects all projects and Prompt
  Agents in the account, including experimentation and agents outside this PoC.
  There is no per-agent opt-out under that account.
- Approval for Agent 365 telemetry processing/location in the tenant geography,
  retention, access and privacy requirements. Suppressed MAF invocation input
  does not prove equivalent redaction for every platform telemetry path.
- A recovery plan and evidence location before changing the shared account.

### 8.2 Foundry built-in integration

From the checkout root, using the approved Azure identity:

```powershell
.\provision-agent365.ps1 -Scope Foundry -WhatIf
.\provision-agent365.ps1 -Scope Foundry
```

The script PATCHes the existing account using `2026-03-15-preview` and checks
that `a365LoggingEnabled=true` and `a365Status=Enabled`. Verify the same values
with a fresh ARM read:

```powershell
$accountId = "<full-Foundry-account-resource-id>"
az rest --method get `
  --url "https://management.azure.com${accountId}?api-version=2026-03-15-preview" `
  --query "properties.{loggingEnabled:a365LoggingEnabled,status:a365Status}" `
  --output json
```

`Enabled` proves configuration/licensing status, **not telemetry delivery**.
Invoke agents and verify receipt in section 10.

### 8.3 App Service coordinator registration

Use an approved administrator workstation for the first setup. Install the
customer-approved Agent 365 CLI version; record `dotnet tool list --global`
and `a365 --help` output in evidence. Inspect `a365 setup --help` before using
the script: CLI commands/configuration evolve.

From the checkout root:

```powershell
.\provision-agent365.ps1 -Scope Maf -WhatIf
.\provision-agent365.ps1 -Scope Maf
```

Unlike the Foundry preview, **MAF `-WhatIf` calls the CLI with `--dry-run` and
reads App Service identity**. It is not offline, may need authentication and
must be checked against the installed CLI's supported flags.

The script runs `a365 setup requirements` and `a365 setup all`, reads the
generated blueprint/agent IDs, adds App Service managed-identity federation,
then enables the exporter settings. The CLI itself may require additional
tenant-owned client configuration or interactive authentication. Do not assume
`AzureCLI@2` login authenticates the CLI.

For a separate Graph provisioning client, the administrator should map the
actual supported operations to consented API permissions:

| Operation | Permission candidates to validate against current API/CLI |
|---|---|
| Blueprint creation/read/update | `AgentIdentityBlueprint.Create`, `AgentIdentityBlueprint.ReadWrite.All` |
| Blueprint principal creation | `AgentIdentityBlueprintPrincipal.Create` |
| Agent creation/read/update | `AgentIdentity.Create.All`, `AgentIdentity.ReadWrite.All` |
| Add blueprint federated credential | `AgentIdentityBlueprint.AddRemoveCreds.All` and required read access |
| Assign application roles | `AppRoleAssignment.ReadWrite.All` only when required |
| Grant delegated/OBO access | `DelegatedPermissionGrant.ReadWrite.All` only when required; current runtime is S2S |

This is an operation checklist, not a blanket grant request. Confirm delegated
versus application availability, ownership constraints, CLI-required additional
permissions, the human administrator's role and the authorized admin-consent
role using current Microsoft guidance. Never copy human role names into a
service principal permission request.

**Current script boundary:** federation uses `az ad app show` and `az rest`
against Graph. Agent ID endpoints can reject ordinary interactive Azure CLI
tokens with unsupported directory scopes. The script does not implement a
dedicated Graph-client authentication path or a bring-your-own-blueprint
parameter. On Graph 403 or unsupported endpoint/authentication, stop and have
the identity administrator establish a supported path; do not broaden all
pipeline identities or substitute an unrelated application registration.

### 8.4 Gate for unattended MAF registration

Keep the optional ADO registration stage disabled until all of these pass:

1. Record the exact CLI version, supported authentication mode and required
   tenant-owned configuration. Current CLI documentation describes interactive
   authentication for the Microsoft-managed app; ARM WIF alone is not proof
   of CLI app-only support.
2. Demonstrate the CLI and Graph federation operations under the **actual
   noninteractive provisioning principal**, with approved consent and no
   browser/device-code prompt or cached human session.
3. Verify correct blueprint, blueprint principal, agent identity, S2S grants
   and federation; demonstrate telemetry export from the App Service identity.
4. Test partial failure/re-run behavior in a disposable environment. The Azure
   infrastructure scripts are designed for repeat execution; do not assume
   `a365 setup all` has identical idempotency semantics.
5. Obtain identity/security sign-off and protect the ADO environment.

If this cannot pass, use approved administrator-led registration and leave
only normal application deployments in ADO. This is a documented limitation,
not permission to store an administrator's token on the VM.

## 9. Evidence register

Keep a restricted customer register, not secrets in the repository:

| Field | Required evidence |
|---|---|
| Environment | Tenant/subscription, resource IDs, region, network topology |
| Agent release | Name, actual version, endpoint/version selector, SDK/API versions, commit/build |
| Identity | New/legacy model, blueprint application/client and object IDs, blueprint principal ID, agent application/client and principal object IDs |
| Authorization | Connection authentication mode, exact role/scope, owner/data-owner approval, denied-access result |
| MAF | Web app ID, managed identity principal ID, Easy Auth app ID, caller policy |
| Agent 365 | Consent/licensing approval, account-wide/residency approval, registration IDs, federation issuer/subject/audience |
| Operations | Synthetic invocation timestamp/request/trace IDs, receipt evidence in both telemetry systems, redaction and alert results |
| Lifecycle | Owner, sponsor, risk approval, expiry/review date, rollback reference |

Generated `a365.generated.config.json` can contain credentials. Keep it in
approved restricted storage; never publish it as an unrestricted build artifact,
paste it in a ticket or dump it to a pipeline log. `.gitignore` is not encryption.
If exposed, revoke/rotate the credential and follow the incident process.

## 10. Acceptance: expected results, not just successful commands

Use a new disposable customer environment and an engineer who did not author
the kit. Record **pass/fail/not run**, UTC time, principal, build/version and
evidence for each row. All applicable checks must pass before handover.

| Check | Procedure | Expected result |
|---|---|---|
| Project setup | Inspect both projects, monitoring and connections after deployment | Correct names/region, identities and approved role scopes |
| Identity model | Inspect each agent's actual identity and Entra record | IDs match the register; distinct identities if required |
| Prompt function | Invoke a harmless synthetic task | Nonempty relevant output, no retrieval permission required |
| RAG positive | Ask for a unique fact present only in the test index | Correct source fact/citation and successful Search dependency |
| RAG negative | In a disposable setup remove the exact reader grant (ensure no other inherited access), then repeat after propagation | Search authorization denied; no fabricated source answer; restore only the approved grant and confirm success |
| Data boundary | Try restricted-document and cross-user questions | Required access policy enforced; current code alone does not implement user-level filtering |
| Safety | Run approved injection, prohibited-content and exfiltration test cases | Approved guardrail outcomes and measured customer thresholds; no secrets/source leakage |
| Unauthenticated API | Call `/api/chat` through App Service without login | 401/403 or Easy Auth redirect, never a generated answer |
| Authenticated API | Call via approved Easy Auth client with a synthetic question | JSON `answer`, `participants`, nonempty `request_id` |
| Readiness | Authenticated GET `/healthz` and `/readyz` | `{"status":"healthy"}` and `{"status":"ready"}`; these do not test downstream permissions |
| Failure behavior | Exercise a controlled unavailable dependency/timeout | Visible failure, no success-shaped fabricated result; workflow timeout is HTTP 504 |
| Azure telemetry | Record UTC time/request ID, invoke success and controlled failure, inspect Insights after ingestion | Matching request/dependency/log evidence, duration/failure correlation |
| Agent 365 configuration | Fresh ARM read plus Entra/Agent 365 registration inspection | Foundry enabled; MAF IDs, sponsor and grants match the register |
| Federation | Inspect blueprint FIC under approved Graph client | Subject is the App Service MI object ID, tenant v2 issuer, audience `api://AzureADTokenExchange` |
| Agent 365 delivery | Invoke Prompt, RAG, portal experiment and MAF separately, inspect each in the Agent 365 experience | Each required invocation attributable to the expected agent, not merely an enabled flag |
| Privacy | Inspect representative success/failure telemetry in both destinations | No tokens/secrets, unapproved prompt bodies or retrieved documents |
| ADO isolation | Run with actual service connections and no cached human login | All allowed actions succeed; unapproved grants/operations remain denied |
| Recovery | Rehearse the approved rollback in a disposable environment | Previous service behavior restored and evidence retained |

For MAF, a PowerShell authenticated request can use a token acquired by an
approved client for the configured API audience (not an ARM or Graph token):

```powershell
$webAppName = "<web-app-name>"
$requestId = [guid]::NewGuid().ToString()
Invoke-RestMethod -Method Post `
  -Uri "https://$webAppName.azurewebsites.net/api/chat" `
  -Headers @{ Authorization = "Bearer $env:POC_API_ACCESS_TOKEN"; "X-Request-ID" = $requestId } `
  -ContentType "application/json" `
  -Body '{"message":"Summarize the synthetic onboarding source and cite it."}'
```

Do not print/store the token in evidence. For Azure telemetry, start with the
Application Insights resource's Logs view:

```kusto
union withsource=TelemetryTable isfuzzy=true requests, dependencies, traces, exceptions
| where timestamp > ago(30m)
| project timestamp, TelemetryTable, operation_Id, customDimensions
| order by timestamp desc
```

Narrow by the recorded request ID/custom dimensions and follow `operation_Id`
when available. Schema and instrumentation vary; a matching timestamp alone
does not prove end-to-end correlation. If querying workspace-native tables,
use `AppRequests`, `AppDependencies`, `AppTraces`, `AppExceptions` and their
`TimeGenerated`/`OperationId`/`Properties` fields instead. Agent 365 delivery is
a separate check; an Azure Monitor trace does not prove it.

## 11. Troubleshooting

| Symptom | Inspect first | Safe next action |
|---|---|---|
| Agent creation 401/403 | Tenant, project endpoint, token audience, connection principal and project data-plane role | Correct the exact scope/credential; Contributor is not a Foundry data-plane grant |
| Graph 403 | Calling client's consented scopes/roles, object ownership, typed endpoint, supported token flow | Identity administrator validates Graph auth; do not retry with broader Azure RBAC |
| Null/missing identity | Agent-level details, actual API and legacy/new model | Follow section 5.3; do not invent IDs or assume a version response contains them |
| RAG 403/no evidence | Actual tool principal, connection authentication, Search scope, RBAC propagation and index schema | Check exact grant and synthetic source; do not grant the pipeline identity runtime data rights |
| Foundry `NotLicensed`/`Disabled` | Tenant license, consent and fresh account state | Agent 365 administrator resolves tenant prerequisites; preserve partial-change evidence |
| CLI opens browser in ADO | CLI auth mode/version and cached developer login dependency | Stop optional stage; use approved admin-led setup until section 8.4 passes |
| Blueprint/FIC mismatch | Registered blueprint, MI subject, issuer and audience | Stop; review existing trust before changing it or rerunning registration |
| App API 401/redirect | Easy Auth tenant/audience, calling client and user/app assignments | Acquire a token for the configured API or use approved browser flow; never forge principal headers |
| API 504 | Workflow timeout, model/Search latency, throttling and bounded rounds | Inspect dependencies before changing limits |
| No telemetry | Exporter flags, monitored resource, tenant, endpoint connectivity, ingestion time and exporter failures | Send one synthetic invocation and correlate IDs; do not enable payload logging to diagnose auth |
| Tool/download failure on VM | Agent service PATH, Python cache, .NET/tool version, approved feeds/proxy | Correct agent image/cache and restart its service; do not disable TLS verification |
| Private endpoint timeout/403 | DNS/routing/firewalls from agent and runtime separately | Fix approved private connectivity, not public access settings |
| Working directory missing | Standalone vs parent checkout, `pocDirectory`, pipeline authorization | Set the correct relative directory; do not copy configuration into arbitrary folders |

## 12. Rollback, reruns and cleanup

1. Before changes, record current account logging flag/status, agent versions
   and endpoint selection, App Service configuration and approved role grants.
   Store any sensitive configuration backup securely.
2. On failure, stop downstream stages and capture errors/IDs without tokens.
   A script failure is not a transaction rollback: Foundry logging or Agent 365
   objects may already exist.
3. For agent behavior rollback, select the previously approved version at the
   endpoint using supported Foundry controls. Because code invokes by name,
   verify which version name-based calls resolve to; endpoint selection alone
   is not proof that every caller rolled back. Re-run functional/access tests.
4. For MAF code rollback, redeploy the previous approved package/build and
   verify Easy Auth and telemetry settings. Do not disable authentication to
   restore service.
5. To pause MAF Agent 365 export, an approved operator can set
   `AGENT365_ENABLED=false` in App Service and restart/verify the app. This does
   not delete its registration, revoke grants or disable Foundry logging.
6. To disable Foundry collection, get the shared-account owner's approval,
   PATCH the same ARM account/API with
   `{"properties":{"a365LoggingEnabled":false}}`, and verify by GET. This
   affects **every project/agent** in that account; it does not erase already
   collected telemetry or de-register identities. Restore the recorded prior
   state, not an assumed default.
7. Treat generated Agent 365 configuration as state during recovery. Inspect
   existing registration/blueprint/agent before rerunning `setup all`; approve
   reuse or cleanup rather than creating duplicates blindly.
8. For retirement, inventory dependencies, revoke exact agent data grants and
   custom federation, retire the custom registration/identity/blueprint through
   the supported administrator process, and confirm no other agent uses them.
   Foundry-managed identities must follow Foundry lifecycle controls.
9. Delete only explicitly approved PoC resource IDs and dedicated monitoring
   resources after retention/export decisions. **Never delete the existing
   shared Foundry account or the resource group as a cleanup shortcut.**
10. Remove temporary pipeline authority and VM auth caches, securely handle
    named generated credential files per retention policy, and record closure.

## 13. Official references

- [Foundry RBAC](https://learn.microsoft.com/azure/foundry/concepts/rbac-foundry)
- [Foundry identity concepts](https://learn.microsoft.com/azure/foundry/agents/concepts/agent-identity)
- [New versus legacy identity model](https://learn.microsoft.com/azure/foundry/agents/how-to/migrate-agent-applications)
- [Foundry Agent 365 collection](https://learn.microsoft.com/azure/foundry/agents/how-to/configure-agent-365-data-collection)
- [Agent 365 CLI authentication and setup](https://learn.microsoft.com/microsoft-agent-365/developer/agent-365-cli)
- [Custom Agent 365 client registration](https://learn.microsoft.com/microsoft-agent-365/developer/custom-client-app-registration)
- [Entra Agent ID setup](https://learn.microsoft.com/entra/agent-id/identity-platform/agent-id-setup-instructions)
- [Azure DevOps self-hosted agents](https://learn.microsoft.com/azure/devops/pipelines/agents/agents)
- [Agent network requirements](https://learn.microsoft.com/azure/devops/pipelines/agents/windows-agent#networking)
- [UsePythonVersion on self-hosted agents](https://learn.microsoft.com/azure/devops/pipelines/tasks/reference/use-python-version-v0#how-can-i-configure-a-self-hosted-agent-to-use-this-task)
- [ADO workload identity service connections](https://learn.microsoft.com/azure/devops/pipelines/library/connect-to-azure)
- [App Service authentication](https://learn.microsoft.com/azure/app-service/overview-authentication-authorization)

Preview APIs and CLI behavior can change. Record tested versions and rerun
acceptance checks for the customer's deployment rather than assuming this
document validates tenant availability or unattended authentication.
