# Microsoft Agent 365 - concepts and customer setup

## 1. Start with the distinction

**Agent 365 helps an organization inventory, observe and govern agents.
Entra Agent Identity identifies an agent and enables it to authenticate.**
They work together, but they are not interchangeable.

An identity does not automatically prove Agent 365 registration or telemetry
delivery. Agent 365 enablement does not automatically grant access to Search,
apply content safety checks, or authorize a user to invoke an agent.

Read the [Agent Identity guide](../agent-identity/README.md) for blueprint,
identity and token details. Follow the [customer handover runbook](../CUSTOMER-HANDOVER.md)
for the overall deployment sequence and acceptance gates.

## 2. What Agent 365 adds

| Concept | Meaning | Evidence to retain |
|---|---|---|
| Inventory/registration | An agent is represented in the organization's management experience | Registration identifier, owner, sponsor and verified identity mapping |
| Observability | Supported invocation telemetry is exported for monitoring | A real synthetic invocation visible under the correct agent |
| Governance | Administrators apply the controls available for the tenant/integration | Approved policy configuration and a tested result |
| Identity integration | Agent records and activity are associated with an Entra agent identity | Agent client/principal IDs matching the approved register |

Available controls depend on licensing, tenant rollout and integration type.
This PoC implements the integration paths below; it does not implement every
Agent 365 capability or certify customer compliance.

## 3. How this PoC integrates

```text
Foundry resource
  +-- experimentation Prompt agents --+
  +-- governed Prompt agent ----------+--> built-in Foundry collection
  +-- governed RAG Prompt agent ------+             |
                                                   v
                                               Agent 365
                                                   ^
App Service MAF coordinator                         |
  +-- Microsoft OpenTelemetry + Agent ID token -----+
  +-- Prompt specialist -> remote Foundry Prompt agent
  +-- Retrieval specialist -> remote Foundry RAG agent
```

| Agent type | Integration path | Scope |
|---|---|---|
| Portal-created Prompt agents | Foundry built-in collection | All projects/Prompt agents in the configured Foundry account |
| Code-created Prompt/RAG agents | Same built-in collection; RAG is a Prompt agent with retrieval | Same account-wide setting |
| App Service MAF coordinator | Custom S2S registration and SDK export | One orchestrator registration |
| In-process specialist wrappers | Included in coordinator execution; remote targets use Foundry integration | Not separate custom registrations in this code |
| Direct-model TTS/STT HTTP sample | No Agent 365 exporter/registration wired in this sample | Not automatically covered by Foundry Prompt Agent collection or the MAF registration; mandatory integration remains a release gate |
| Other hosting/agent types | Not established by these scripts | Assess supported integration separately |

Foundry Hosted Agents are **not** required. App Service remains the coordinator
host. The Foundry account may contain agents outside this PoC: account-wide
logging cannot be restricted to only the two new projects.

## 4. Prerequisites and responsible people

For customer onboarding, infrastructure, registration, consent, federation and
platform settings are supplied through customer IaC/platform/identity processes.
The scripts described later are author/test helpers, not mandatory customer
setup. Use the full [customer prerequisite tables](../CUSTOMER-PREREQUISITES.md).

### Platform prerequisites

| Area | Existing prerequisite |
|---|---|
| Foundry V2 | `AIServices` resource, both projects/MIs, approved model, monitoring/connections; no classic hub-based projects |
| Agent applications | Working Prompt/RAG definitions before delivery tests |
| MAF host | App Service/plan, MI, app settings and remote Foundry access; Easy Auth optional for controlled PoC with approved network restrictions |
| Custom identity | Blueprint, Blueprint Principal, agent identity, resource grants and MI trust |
| Providers/RBAC/network | Applicable rows in the complete customer matrix, pre-established by platform owners |
| Administrator tooling | Azure CLI/PowerShell and approved .NET/Agent 365 CLI only if used by platform setup; not a universal developer-machine requirement |

### Tenant and governance prerequisites

The Entra/Agent 365 administrator must approve:

1. Tenant feature availability, active licensing and completed tenant consent.
2. Owners/sponsors, registration naming, review dates and retirement process.
3. The Foundry account-wide change, including experimentation/unrelated agents.
4. Telemetry access, retention, privacy and processing location in the tenant
   geography. Do not assume Foundry resource region determines Agent 365 residency.
5. The setup identity, its Graph permissions and the permitted authentication flow.

### Permissions: separate the two setup paths

| Task | Identity/access required |
|---|---|
| Enable Foundry collection | Azure principal with account read/write, such as Contributor at that account; licensing/consent handled by tenant administrator |
| Register custom MAF agent | Approved Agent ID provisioning operator/client plus the CLI's documented registration/consent authority |
| Add blueprint federation | Approved Graph authority to modify blueprint credentials, including `AgentIdentityBlueprint.AddRemoveCreds.All` where applicable |
| Read MI/update App Service settings | Azure access to read the app identity and update the app configuration |
| Export at runtime | App Service MI trusted by the blueprint plus approved agent S2S grants; not directory administrator rights |

Human Entra roles, Graph application/delegated permissions and Azure RBAC are
different. Contributor and an ADO environment approval do not confer Graph
permissions or tenant consent. See the [identity permission matrix](../agent-identity/README.md#6-permissions-and-consent).

## 5. Configure the environment

From the PoC checkout root, copy the root `.env.sample` to `.env` if not already
configured. Populate the tenant, subscription, resource group and Foundry account.
MAF setup also needs `WEB_APP_NAME` and `AGENT365_MAF_AGENT_NAME`.

Authenticate to the approved tenant/subscription. Azure CLI authentication
does **not** prove the Agent 365 CLI or Graph operations are authenticated.
Do not use an administrator's cached session to make an unattended job appear
functional.

The root script reads the root `.env`. Local MAF execution reads its own
[configuration template](../02-governed-agents/04-maf-multi-agent/.env.sample).
For customers, App Service runtime settings are supplied through the platform's
approved configuration process; the test helpers can configure them in the
author's environment.

## 6. Enable Foundry built-in collection

**Customer prerequisite:** the platform team has already enabled collection
with shared-account approval. Use the read check below to verify state.
For the author's test environment only, the helper commands are:

```powershell
.\provision-agent365.ps1 -Scope Foundry -WhatIf
.\provision-agent365.ps1 -Scope Foundry
```

The [provisioning script](../provision-agent365.ps1):

1. Selects the configured Azure subscription.
2. PATCHes the existing Foundry account with `a365LoggingEnabled=true` using
   ARM API `2026-03-15-preview`.
3. Reads the account state back.
4. Fails if the flag is not true or `a365Status` is not `Enabled`.
5. Writes its result to the ignored `agent365-provisioning-output.json`.

Preview needs authenticated access and is not a live delivery test.
The result `Enabled` is necessary, but is **not proof of telemetry ingestion**.

For a fresh read:

```powershell
$accountId = "<full-Foundry-account-resource-id>"
az rest --method get `
  --url "https://management.azure.com${accountId}?api-version=2026-03-15-preview" `
  --query "properties.{loggingEnabled:a365LoggingEnabled,status:a365Status}" `
  --output json
```

Expected configuration: `loggingEnabled: true`, `status: "Enabled"`.
Verify the preview API remains supported in the customer's environment.

## 7. Register the App Service coordinator

**Customer prerequisite:** identity/platform teams provide the existing
registration, grants and federation described in the
[Agent 365 matrix](../CUSTOMER-PREREQUISITES.md#6-agent-365-prerequisites).
Do not run the helper over those objects simply to onboard application code.
The following explains administrator/test-helper behavior.

Use an approved administrator workstation for initial onboarding.
If the CLI is not installed, install the customer-approved version of
`Microsoft.Agents.A365.DevTools.Cli` using the documented .NET tool process.
Record the version and inspect `a365 setup --help`; CLI syntax/authentication
can evolve independently of this repository.

From the PoC checkout root:

```powershell
.\provision-agent365.ps1 -Scope Maf -WhatIf
.\provision-agent365.ps1 -Scope Maf
```

The intended sequence in the script is:

1. Read the existing App Service system-assigned MI principal ID.
2. Run `a365 setup requirements`.
3. Run `a365 setup all --agent-name ... --tenant-id ... --authmode s2s`.
4. Read `agentBlueprintId` and `agenticAppId` from the MAF folder's generated
   `a365.generated.config.json`.
5. Establish a blueprint federated credential trusting the App Service MI.
6. Set the blueprint/agent client IDs and enable runtime export in App Service.

**Important boundaries:**

- MAF `-WhatIf` reads the app identity and invokes CLI `setup all --dry-run`.
  It is not offline; verify installed CLI flag support and authentication.
- The federation helper uses Azure CLI Graph calls. Ordinary interactive CLI
  tokens can be rejected by Agent ID APIs. The script does not implement a
  dedicated Graph-client authentication flow.
- There is no bring-your-own-blueprint parameter in the current script.
- A failure may occur after objects have been created. Do not blindly rerun
  setup or delete objects without checking existing state and ownership.
- These commands describe the implementation, not a verified tenant setup.

`-Scope All` runs both Foundry and MAF paths. Use it only after both approvals;
it is not an atomic transaction.

## 8. Runtime settings and telemetry

The implementation is in
[app/agent365.py](../02-governed-agents/04-maf-multi-agent/app/agent365.py) and
[app/configuration.py](../02-governed-agents/04-maf-multi-agent/app/configuration.py).

| Setting | Meaning |
|---|---|
| `AGENT365_ENABLED` | Enables custom MAF integration; default false |
| `AGENT365_MAF_AGENT_NAME` | Registered orchestrator's display/name setting |
| `AGENT365_AUTH_MODE` | Current implementation accepts `s2s` only |
| `A365_BLUEPRINT_CLIENT_ID` | Blueprint application/client ID, not object ID |
| `A365_AGENT_CLIENT_ID` | Agent Identity application/client ID, not principal object ID |
| `A365_BOOTSTRAP_CLIENT_ID` | Optional user-assigned MI selection; default deployment uses system-assigned MI |
| `ENABLE_A365_OBSERVABILITY_EXPORTER` | Must be true when integration is enabled |
| `A365_USE_S2S_ENDPOINT` | Must be true for this S2S implementation |
| `A365_SUPPRESS_INVOKE_AGENT_INPUT` | Defaults true; suppresses invocation input |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Enables Azure Monitor export separately |

MAF emits an invocation scope with tenant, agent, blueprint, request/session and
caller information when available. Request content is set to `None`; errors
record the exception type rather than its raw message in the Agent 365 scope.
Do not treat these measures as blanket redaction of every library/platform log.

Agent 365 and Application Insights are different destinations. A trace in one
does not prove delivery to the other.

## 9. ADO and self-hosted execution

For normal customer onboarding keep platform mutation flags disabled and
consume existing configuration. The supplied MAF YAML defaults to package-only
delivery with `provisionInfrastructure=false`; the combined author/test helper
requires explicit infrastructure opt-in. Custom Agent Identity remains required
even when Agent 365 is off; the registration stage must not be rerun merely
to populate missing settings.

The [main pipeline](../azure-pipelines.yml) uses `enableAgent365Foundry` for
account collection. The [MAF pipeline](../02-governed-agents/04-maf-multi-agent/azure-pipelines.yml)
uses `provisionAgent365` for custom registration. Both flags default false.

Use `ADO_AGENT365_SERVICE_CONNECTION` and the approval-protected
`ADO_AGENT365_ENVIRONMENT_NAME`. The VM runs the job; the service connection
principal supplies Azure permissions. Use OS-specific pools as described in
the [handover runbook](../CUSTOMER-HANDOVER.md#7-azure-devops-and-self-hosted-vms).

**Do not enable unattended MAF registration until demonstrated under its actual
provisioning identity:** supported CLI authentication, consented Graph access,
no browser/device-code prompt, no cached human login, federation verification,
telemetry delivery and safe partial-failure recovery. ARM workload identity
federation alone does not establish these.

## 10. Verification and failure diagnosis

| Test | Expected evidence |
|---|---|
| Foundry configuration | Fresh account GET returns enabled flag/status |
| Registration | MAF inventory/registration maps to the intended tenant, blueprint and agent |
| Federation | MI subject, tenant issuer and exchange audience match the [identity guide](../agent-identity/README.md#8-app-service-runtime-token-exchange) |
| Foundry delivery | Invoke portal experiment, Prompt and RAG separately; find each required activity under its correct agent |
| MAF delivery | Authenticated synthetic `/api/chat` invocation appears under coordinator identity |
| Azure Monitor | Corresponding app/model/retrieval telemetry and failure evidence |
| Privacy | No tokens, secrets, unapproved prompt bodies or retrieved documents in either destination |

Record UTC time, request/trace IDs and version/build, and allow for ingestion
delay. Retain restricted evidence rather than screenshots of secret settings.

| Symptom | Action |
|---|---|
| `NotLicensed`/`Disabled` | Administrator checks licensing, rollout and tenant consent |
| Graph 403 | Validate provisioning client permissions, ownership, API and token flow; more Azure Contributor access will not fix it |
| Browser prompt in ADO | Stop custom registration; use admin-led setup until unattended auth is proven |
| Enabled but no activity | Check synthetic invocation, tenant/agent mapping, connectivity and exporter failures |
| Missing MAF IDs/configuration | Validate registration result and app settings; do not invent IDs |
| Existing federation mismatch | Stop and review the trust; do not overwrite another workload's credential |

## 11. Credential handling, rollback and retirement

Generated CLI configuration can contain secrets even though runtime export
uses federation. Do not commit, print, email or publish generated configuration.
Git ignore rules do not secure it; apply restricted storage and retention.
Rotate/revoke exposed credentials through the incident process.

To pause custom MAF export, approved operators can set `AGENT365_ENABLED=false`,
restart and verify the app. This does not unregister the agent, revoke grants
or disable Foundry collection.

Disabling Foundry collection requires the shared-account owner's approval:
PATCH the same account with `{"properties":{"a365LoggingEnabled":false}}` and
verify by GET. It affects all covered projects and does not erase existing data.
Restore recorded prior state rather than assuming collection was previously off.

Retirement must separately address registration, agent grants, federation,
identity ownership and retained telemetry. Do not delete the shared account or
a blueprint used by other agents. Follow the
[handover recovery procedure](../CUSTOMER-HANDOVER.md#12-rollback-reruns-and-cleanup).

## 12. Microsoft references

- [Foundry Agent 365 integration](https://learn.microsoft.com/azure/foundry/agents/concepts/agent-365-integration)
- [Configure Foundry collection](https://learn.microsoft.com/azure/foundry/agents/how-to/configure-agent-365-data-collection)
- [Agent 365 registration](https://learn.microsoft.com/microsoft-agent-365/developer/registration)
- [Agent 365 CLI](https://learn.microsoft.com/microsoft-agent-365/developer/agent-365-cli)
- [Custom client registration](https://learn.microsoft.com/microsoft-agent-365/developer/custom-client-app-registration)

Record customer-tested API/CLI versions. No live tenant registration, consent
or delivery validation is implied by this guide.
