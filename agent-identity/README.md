# Microsoft Entra Agent Identity - concepts and implementation

## 1. The simple explanation

Think of an **Agent Identity as the agent's identity card**. A **blueprint**
is the identity template/management object used to create and authenticate
those identities. **Permissions** determine what an agent can actually do.

These are separate things:

- Creating an identity does not grant access to Search or Microsoft Graph.
- Creating an agent does not prove every tool uses its Agent Identity.
- Agent 365 registration/telemetry does not automatically apply content safety.

For inventory and telemetry onboarding, read the
[Agent 365 guide](../agent-365/README.md). For end-to-end deployment, start with
the [customer runbook](../CUSTOMER-HANDOVER.md).

Customer platform/identity teams must supply the resources, grants, custom
blueprint/agent registration and federation in the
[customer prerequisite tables](../CUSTOMER-PREREQUISITES.md). The PowerShell
helpers described here are for the author's test environment. Foundry-managed
blueprints/identities are an exception to pre-creation: Foundry manages them
when application agents are created; do not pre-create duplicates.

## 2. The identity objects

```text
Agent Identity Blueprint (application object)
  | Defines an agent type; holds credentials/federated trust
  |
  +-- Blueprint Principal (service principal in the tenant)
  |
  +-- Agent Identity A (specialized service principal)
  +-- Agent Identity B (specialized service principal)
```

This is a conceptual relationship, not a tenant object dump.

| Term | Meaning | Important distinction |
|---|---|---|
| Blueprint | Application-level management/authentication template | Not a prompt, YAML agent definition or Azure deployment template |
| Blueprint Principal | Tenant service principal for the blueprint | Separate from both blueprint application object and agent identities |
| Agent Identity | Specialized service principal for an agent instance | Has independently scoped grants; credentials belong on the blueprint |
| Owner | Identity/object management responsibility | Ownership is not equivalent to arbitrary tenant-wide consent |
| Sponsor | Accountable person/group as supported by the object/API | Record sponsor and review process explicitly |
| Managed identity (MI) | Azure workload identity, e.g. App Service system-assigned MI | Not automatically an Entra Agent Identity |
| Federated identity credential (FIC) | Trust allowing an external/workload assertion to authenticate a blueprint | Does not itself grant Search, Graph or telemetry permission |

When provisioning manually, create/verify the Blueprint Principal explicitly;
do not assume creating the blueprint application also created its principal.
Foundry/CLI-managed setup may perform these lifecycle operations for you.

## 3. Do not mix up the IDs

| Identifier | Use in this PoC |
|---|---|
| Tenant ID | Entra directory and token authority |
| Blueprint application/client ID (`appId`) | `A365_BLUEPRINT_CLIENT_ID`; blueprint OAuth client |
| Blueprint application object ID (`id`) | Directory management, including selecting the application to add FIC |
| Blueprint principal object ID | Blueprint's tenant service principal; not the application object |
| Agent Identity application/client ID | `A365_AGENT_CLIENT_ID`; agent OAuth client and current `fmi_path` value |
| Agent Identity principal object ID | Azure RBAC assignee and directory permission-grant target |
| App Service MI principal object ID | Federation subject for this system-assigned MI deployment |
| Optional user-assigned MI client ID | `A365_BOOTSTRAP_CLIENT_ID` selects bootstrap MI when deliberately configured |
| Foundry agent name/version/identifier | Foundry resource/definition selection; not a substitute for an Entra principal |

Never put a client ID into an object-ID-only operation or grant data roles to
the blueprint merely because its ID appears first in a response.

## 4. Which identity does each job?

```text
Human/ADO deployment identity -> creates resources and agent definitions
App Service MI               -> calls Foundry agents/models
Verified RAG tool principal  -> queries Search
App Service MI               -> blueprint trust -> Agent ID -> Agent 365 export
PoC caller                   -> approved network -> MAF API (Easy Auth optional)
```

The current MAF application does **not** exchange the caller's token for
per-user downstream access. Its Agent ID exchange is S2S and currently used
for Agent 365 telemetry. Foundry inference uses the workload/managed/CLI
credential selected by
[authentication.py](../02-governed-agents/04-maf-multi-agent/app/authentication.py).

Easy Auth is not required for the controlled PoC. If omitted, use an empty
`ENTRA_CLIENT_ID`, `REQUIRE_APP_SERVICE_AUTH=false` and approved network
restrictions; do not publicly expose an unauthenticated endpoint. This does not
remove MI/Agent ID service authentication or resource grants.
If enabled, Easy Auth caller authentication still does not automatically provide
per-user Search authorization. The PoC does not implement user-level retrieval filters.

## 5. Foundry-managed identities: new versus legacy

### Prerequisites

| Area | Required prerequisite/owner |
|---|---|
| Foundry V2 | Existing resource/projects/MIs, not classic hubs; platform team |
| Models/monitoring | Approved model deployment, working endpoint, Insights/workspace connections; platform team |
| Developer access | Pre-assigned Foundry project data-plane role; platform access owner |
| Tenant Agent ID | Feature/API availability, permitted identity lifecycle, owners/sponsors; identity team |
| Downstream access | Approved data owner, actual runtime principal and scoped grants; data/platform teams |
| Custom MAF identity | Blueprint, Blueprint Principal, agent identity, supported provisioning client/consent and MI FIC; identity team |

See the [complete Entra Agent ID prerequisites](../CUSTOMER-PREREQUISITES.md#5-entra-agent-id-prerequisites)
for operation-specific Graph permission candidates and ID handover requirements.

The [migration guide](https://learn.microsoft.com/azure/foundry/agents/how-to/migrate-agent-applications)
distinguishes:

| Model | Identity behavior | Consequence |
|---|---|---|
| New agent object model | Unique blueprint and identity at agent creation | Verify agent-level identity before assigning downstream access |
| Legacy development agents | Can share a project identity | Shared permissions/blast radius; not per-agent isolation |
| Legacy Agent Application publication | Separate identity associated with the published application | Recheck grants; development grants do not prove published access |

This kit targets the new object model using `azure-ai-projects` 2.6. The
[Prompt script](../02-governed-agents/01-prompt-agent/prompt_agent.py) and
[RAG script](../02-governed-agents/02-rag-agent/rag_agent.py) call
`client.agents.create_version(...)`. Foundry manages identity provisioning;
the scripts do not call Graph to create a separate blueprint.

**A new version is not necessarily a new identity.** Reusing a legacy agent
name and creating another version does not establish migration.

### Verify what was created

1. Create the selected agent following its application README.
2. Record name, version, endpoint, SDK/API version and creation response.
3. Use the script's `list` command and inspect agent-level details in Foundry.
   Version responses can omit agent-level identity fields.
4. Resolve `blueprint` and `instance_identity` and verify their Entra objects.
   The migration guide currently illustrates this agent-details API:

   ```powershell
   $projectEndpoint = "<PROJECT_ENDPOINT>"
   $agentName = "<agent-name>"
   az rest --method get --resource "https://ai.azure.com" `
     --url "$projectEndpoint/agents/${agentName}?api-version=2025-11-15-preview" `
     --query "{name:name,blueprint:blueprint,identity:instance_identity}" --output json
   ```

5. If identity is missing/null, check API support, tenant rollout and legacy
   status. Do not assume an indefinite provisioning delay or invent an ID.
6. Verify the Search connection's authentication mode and actual runtime
   principal before assigning data access. A connection using a different
   MI/key is not evidence of Agent ID-based retrieval.
7. Record exact client/object IDs and approved roles, then test success and denial.

If distinct Agent Identity is mandatory for every customer agent, unresolved
legacy/shared identity is a release blocker.

## 6. Permissions and consent

### Three permission systems

| System | Purpose | Example |
|---|---|---|
| Azure RBAC | Azure resources and supported data-plane actions | Foundry User, Search Index Data Reader |
| Entra administrator roles | Human/administrative directory authority | Approved Agent Identity Developer/Administrator role |
| Graph API permissions | What the Graph calling client may request | Agent identity creation or blueprint credential modification |

Azure Contributor grants neither directory administration nor role-assignment
authority. A human Entra role does not automatically appear as an application
permission on an ADO service principal. Graph admin consent and ADO environment
approval are independent approvals.

### Permission profiles

| Principal/activity | Minimum intended profile |
|---|---|
| Foundry developer/creation pipeline | Foundry User on governed project; parent Reader for portal navigation as needed |
| Role-assignment operator | Narrowly scoped RBAC administration for the approved target |
| Prompt runtime | No downstream data access unless an approved tool needs it |
| RAG runtime | Search Index Data Reader on supported approved scope for the actual tool principal |
| App Service MI | Foundry User as assigned by the deploy script, plus blueprint federation for telemetry |
| Agent ID runtime | Approved resource grants needed for its task; no blanket directory provisioning permissions |

### Separate Graph provisioning client

Use current Microsoft documentation to map the selected workflow to exact
delegated/application permissions and admin-consent roles. Typical operations:

| Operation | Permission candidates to review |
|---|---|
| Create blueprint | `AgentIdentityBlueprint.Create` |
| Read/update blueprint | `AgentIdentityBlueprint.ReadWrite.All` |
| Create blueprint principal | `AgentIdentityBlueprintPrincipal.Create` |
| Create/read/update agent identities | `AgentIdentity.Create.All`, `AgentIdentity.ReadWrite.All` |
| Add blueprint federated trust | `AgentIdentityBlueprint.AddRemoveCreds.All` plus necessary read access |
| Grant application permissions | `AppRoleAssignment.ReadWrite.All` only if required |
| Grant delegated/OBO permissions | `DelegatedPermissionGrant.ReadWrite.All` only if required |

These are operation candidates, **not a blanket permission bundle**. Validate
API availability, ownership restrictions and CLI-specific requirements.
Grant downstream permissions to the agent principal that actually calls the
resource, not automatically to the Blueprint Principal or deployment pipeline.

For direct Agent ID Graph operations, use a supported, explicitly scoped
Graph client flow. Ordinary interactive Azure CLI tokens can contain rejected
directory scopes; do not assume `az login` or `DefaultAzureCredential` supplies
an acceptable Agent ID provisioning token. This restriction is distinct from
using Azure CLI credentials to call the Foundry data plane.

## 7. Custom App Service blueprint provisioning

For customers, the identity team supplies this state through its approved
process before application onboarding. The sequence below explains the
author/test helper; it is not a requirement to run it on customer resources.

The [Agent 365 provisioning script](../provision-agent365.ps1) uses the CLI for
custom coordinator setup:

```text
a365 setup requirements
       |
a365 setup all --agent-name ... --tenant-id ... --authmode s2s
       |
generated configuration: agentBlueprintId + agenticAppId
       |
resolve blueprint application object ID
       |
add FIC trusting the App Service system-assigned MI
       |
configure App Service blueprint/agent client IDs and exporter
```

The script expects the CLI to establish the appropriate blueprint, identity,
registration and grants. Verify each result; a file containing IDs is not proof
of correct consent or runtime authentication.

For this PoC the custom MAF coordinator has **one** Agent 365 identity/registration.
Its in-process specialist wrappers are not separately provisioned Agent
Identities; the remote Foundry agents have their own verified lifecycle.

### Can I supply my own blueprint?

Conceptually, a custom application can use a customer-owned blueprint, provided
its Blueprint Principal, agent identities, federation, ownership, grants and
Agent 365 registration are configured consistently.

**The current script does not support a bring-your-own-blueprint parameter.**
Do not replace generated IDs or assume changing app settings migrates a
registration. A supported reuse workflow needs explicit implementation and
validation of all associated objects.

This kit also does not offer custom blueprint substitution for Foundry-managed
agent creation. Leave Foundry-managed identity lifecycle to Foundry.

## 8. App Service runtime token exchange

Implemented in [Agent365TokenResolver](../02-governed-agents/04-maf-multi-agent/app/agent365.py).
Credentials/trust belong to the blueprint; the agent identity does not hold
its own password/certificate.

### Federation values established by the script

| Property | Value |
|---|---|
| Credential name | `maf-app-service-managed-identity` |
| Issuer | `https://login.microsoftonline.com/<tenant-id>/v2.0` |
| Subject | App Service MI **principal object ID** |
| Audience | `api://AzureADTokenExchange` |

The helper resolves the blueprint's application object ID, checks existing
federation and refuses to reuse a same-name trust with a mismatched subject,
issuer or exchange audience. It currently calls untyped application Graph URLs
through `az rest`; compatibility with the approved Agent ID Graph token/API
must be verified. Do not interpret this implementation as a validated
alternative to Microsoft's typed blueprint endpoint guidance.

### What happens during export

```text
1. App Service MI requests bootstrap assertion
   scope: api://AzureADTokenExchange/.default

2. Blueprint requests a parent token at the tenant's /oauth2/v2.0/token
   grant_type: client_credentials
   client_id: blueprint client ID
   client_assertion: MI assertion
   scope: api://AzureADTokenExchange/.default
   fmi_path: agent client ID

3. Agent requests the final resource token
   grant_type: client_credentials
   client_id: agent client ID
   client_assertion: parent token
   scope: Agent 365 observability resource /.default

4. Exporter uses the resulting agent token to send telemetry
```

The current observability scope in code is
`api://9b975845-388f-4429-889e-eab1ef63949c/.default`.
The resolver checks requested tenant/agent, validates token responses and caches
the final token until five minutes before expiry.

This is not the RFC 8693 token-exchange grant, not a user OBO flow, and not a
token path currently used by the Foundry gateway. The implementation uses the
configured tenant for both exchanges; cross-tenant scenarios need separate
design and validation.

## 9. Provisioning from ADO

Deployment identity, Graph provisioning identity and runtime Agent Identity
must not be confused:

- The self-hosted VM needs OS/tool/network access to execute jobs.
- Azure authority normally comes from the WIF ARM service connection.
- Agent ID Graph operations require separately approved client permissions
  and a supported authentication mechanism.
- The runtime App Service MI and agent identity do not need broad setup rights.

The optional MAF registration stage is **not verified for unattended execution**.
Keep it disabled until the exact CLI/Graph principal works without interactive
prompts or cached human tokens and the resulting federation/export is proven.
See the [automation gate](../CUSTOMER-HANDOVER.md#84-gate-for-unattended-maf-registration).

## 10. Verify, troubleshoot and retire

### Acceptance checklist

- [ ] Agent name/version and new/legacy model recorded.
- [ ] Blueprint application, Blueprint Principal and Agent Identity verified.
- [ ] Client IDs and principal object IDs recorded separately.
- [ ] Actual tool authentication principal confirmed.
- [ ] Exact data grants approved; synthetic positive and denied-access tests pass.
- [ ] MAF federation issuer/subject/audience match the deployed MI.
- [ ] Agent 365 token/export behavior verified without logging tokens.
- [ ] Foundry calls still use the documented managed/workload credential path.
- [ ] Owners, sponsors, expiry/review dates and retirement responsibilities recorded.

| Problem | Likely investigation |
|---|---|
| Missing identity fields | Agent-level versus version response, legacy model, API/tenant support |
| Blueprint Principal missing | Provisioning did not establish the tenant principal; administrator verifies it |
| Graph 403 | Calling client scopes/roles, ownership, supported API and token flow |
| `AADSTS700211`/no matching FIC | MI assertion issuer/subject/audience and correct tenant/blueprint |
| `AADSTS82001` | Unsupported grant path; verify `client_credentials` and `fmi_path` flow |
| Agent resource access denied | Grants on the actual agent principal, audience and propagation |
| Wrong existing FIC | Stop and review shared trust; do not overwrite to force success |
| Local MAF Agent 365 export fails | Current default bootstrap requires MI; Azure CLI login alone is not equivalent |

Do not decode/print access tokens into shared logs to diagnose these issues.
Use approved sign-in/audit records and sanitized error metadata.

On retirement, first stop traffic and inventory shared dependencies. Revoke
exact runtime grants and custom federation, retire Agent 365 registration as
applicable, then remove custom identity objects only through the approved
directory workflow. A shared blueprint must not be deleted while other
identities depend on it. Use Foundry lifecycle controls for Foundry-managed
objects; verify orphaned grants rather than assuming deletion cleaned everything.
Preserve required audit evidence and retained telemetry.

## 11. Microsoft references

- [Foundry identity concepts](https://learn.microsoft.com/azure/foundry/agents/concepts/agent-identity)
- [New and legacy agent object models](https://learn.microsoft.com/azure/foundry/agents/how-to/migrate-agent-applications)
- [Entra Agent ID setup](https://learn.microsoft.com/entra/agent-id/identity-platform/agent-id-setup-instructions)
- [Create a blueprint](https://learn.microsoft.com/entra/agent-id/create-blueprint)
- [Foundry RBAC](https://learn.microsoft.com/azure/foundry/concepts/rbac-foundry)

API and tenant support evolve. This guide explains source behavior and the
required verification process, not proof of successful customer provisioning.
