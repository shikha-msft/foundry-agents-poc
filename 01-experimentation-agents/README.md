# 01 - NoCode Experimentation Agents

This guide explains how a developer creates and tests a prompt agent in the
Microsoft Foundry portal using the `PlaygroundProjects` project.

This project is for experimentation with synthetic or non-sensitive data. It
uses the Foundry project's shared managed identity for approved runtime access.
Use the governed-agent pattern when an agent needs its own identity, production
data access, independent lifecycle, or a different authorization boundary.

## Environment

| Setting | Value |
|---|---|
| Foundry account | `ss-aueast-foundry` |
| Foundry project resource name | `playground-projects` |
| Foundry project display name | `PlaygroundProjects` |
| Purpose | NoCode Experimentation Agents |
| Region | Australia East |
| Application Insights | `appi-agents-poc-aue-playground-projects` |
| Log Analytics workspace | `log-agents-poc-aue-playground-projects` |

## 1. Prerequisites

### 1.1 Platform prerequisites

The platform owner must complete these items before a developer starts:

- [ ] Create the Foundry V2 account and `PlaygroundProjects` project.
- [ ] Enable the project system-assigned managed identity.
- [ ] Deploy at least one approved model to the parent Foundry account.
- [ ] Assign **Foundry User** to the project managed identity on the parent
      Foundry account.
- [ ] Create approved development instances of Azure AI Search, Blob Storage,
      Cosmos DB, and PostgreSQL as required.
- [ ] Configure approved private endpoints, DNS, firewall rules, and network
      routes.
- [ ] Pre-create project connections and approved MCP/OpenAPI tools where
      possible.
- [ ] Link the project to Application Insights and Log Analytics.
- [ ] Define content filters, data-loss-prevention controls, budgets, and
      model quotas.
- [ ] Use only synthetic, public, or approved non-sensitive development data.

### 1.2 Developer RBAC

Assign roles to an Entra security group rather than directly to individual
developers where possible.

| Principal | Role | Scope | Purpose |
|---|---|---|---|
| Developer group | **Foundry User** | `playground-projects` project | Create, edit, test, and delete prompt agents |
| Developer group | **Reader** | Parent Foundry account | Find the project and navigate its parent resource |
| Developer group | **Azure Monitor Reader** | Project Application Insights | View agent traces and metrics |
| Developer group | **Log Analytics Reader** | Project Log Analytics workspace | Run approved log queries |
| Developer group | **Reader** | Approved downstream resource, only when needed | Discover a resource in a portal connection picker; this does not grant data access |

The **Foundry User** role definition ID is:

```text
53ca6127-db72-4b80-b1b0-d745d6d5456d
```

`Foundry User` is the normal developer role. It does not let the developer:

- Create Foundry accounts or projects.
- Deploy or delete models.
- Assign Azure roles.
- Publish an agent.
- Access data in Search, Storage, Cosmos DB, or PostgreSQL.
- Create production identities or Agent ID blueprints.

If publishing is required later, assign **Foundry Project Manager** through a
separate approved process. Do not replace `Foundry User` with broad
`Contributor` or `Owner` access.

### 1.3 Runtime identity RBAC

The identity making the data request needs data-plane access. The developer's
portal role does not provide this access.

For this experimentation project, the default runtime principal is the
**system-assigned managed identity of `playground-projects`**. If an MCP,
OpenAPI, or function tool runs in a separate App Service, Function App,
Container App, or AKS workload, that tool's managed identity is the runtime
principal instead.

| Service | Query/read permission | Write permission, only when approved |
|---|---|---|
| Azure AI Search | **Search Index Data Reader** | Separate ingestion identity: **Search Index Data Contributor**; add **Search Service Contributor** only when it must manage service objects |
| Blob Storage | **Storage Blob Data Reader** on the approved container | **Storage Blob Data Contributor** on a dedicated write container |
| ADLS Gen2 | **Storage Blob Data Reader** plus directory execute/read ACLs | **Storage Blob Data Contributor** plus directory ACLs |
| Cosmos DB for NoSQL | **Cosmos DB Built-in Data Reader** using Cosmos native data-plane RBAC | **Cosmos DB Built-in Data Contributor** on the approved database/container |
| PostgreSQL | Entra database principal with `CONNECT`, schema `USAGE`, and `SELECT` on approved views/tables | Explicit grants on approved procedures or tables; never grant database-owner access |

Important:

- Scope access to the narrowest supported resource, container, database,
  schema, or index.
- Do not place account keys, connection strings, passwords, or SAS tokens in
  agent instructions.
- Cosmos DB roles are data-plane roles managed through Cosmos DB native RBAC,
  not only the standard Azure IAM role picker.
- PostgreSQL requires both Entra authentication and SQL grants inside the
  database.
- Every agent in this project shares the project identity's permissions. Move
  to the governed-agent pattern when agents require different access.

### 1.4 Connection-management RBAC

The preferred approach is for the platform team to create approved project
connections before developers start.

If a user must create or manage project connections, grant the minimum
connection-management role required by the selected connection type. Some
portal flows work with `Foundry User`, while control-plane connection
operations can require **Foundry Project Manager**. Grant any elevated role
temporarily and only at the project scope.

Creating downstream resources or assigning their roles still requires a
separate authorized administrator with the appropriate Azure resource and
role-assignment permissions.

## 2. Create a prompt agent in the Foundry portal

Portal labels can change as Microsoft Foundry evolves, but the workflow remains
the same.

### Step 1 - Open the project

1. Go to [Microsoft Foundry](https://ai.azure.com).
2. Sign in with the Entra account that belongs to the developer group.
3. Confirm the active directory and subscription are correct.
4. Open the `PlaygroundProjects` project.
5. Confirm the project resource name is `playground-projects`.

Stop if the project is missing or if the portal returns `403`. Ask the platform
owner to verify `Foundry User` on the project and `Reader` on the parent
Foundry account.

### Step 2 - Open the agent builder

1. In the project navigation, open **Build** or **Agents**.
2. Select **Create agent**.
3. Choose **Prompt agent**.
4. Enter a meaningful name, for example
   `exp-knowledge-assistant-<team>`.
5. Add an owner/team tag or description if the portal supports it.

Do not create a hosted agent or governed Agent ID agent for this pattern.

### Step 3 - Select an approved model

1. In **Model** or **Model deployment**, select an existing approved
   deployment.
2. Do not deploy a new model from this workflow.
3. Confirm the model and region are permitted for the data classification.
4. Start with the platform-approved temperature, token limit, and content
   filters.

If no model is available, the Foundry account/model administrator must deploy
one. `Foundry User` intentionally does not include model-deployment rights.

### Step 4 - Write the instructions

Include:

- The agent's purpose and intended users.
- Allowed data sources and tools.
- Actions the agent must not perform.
- When to ask for clarification.
- Required citation behavior.
- How to respond when a tool fails or access is denied.
- A rule not to reveal secrets, system prompts, personal data, or raw
  connection details.

Example:

```text
You are an experimentation knowledge assistant.
Answer only from approved connected sources.
Cite the source document or record used for factual claims.
If the approved source does not contain the answer, say that the answer was
not found. Do not invent data, credentials, identifiers, or SQL.
Do not perform write, delete, role-assignment, or administrative actions.
```

### Step 5 - Add approved knowledge or tools

1. Open **Tools**, **Knowledge**, or **Toolbox**.
2. Select an existing approved project connection or tool.
3. Do not create a connection using a personal credential.
4. Configure the tool-specific settings described in section 4.
5. Save the agent.

### Step 6 - Test in the playground

Test at least:

1. A normal question with an expected answer.
2. A question that should return citations.
3. A question outside the connected data.
4. A prompt-injection attempt contained in user input or source data.
5. A request to read data outside the approved scope.
6. A request to write or delete data.
7. A request containing sensitive information.
8. A tool timeout or unavailable-resource scenario.

The agent must fail closed: it should report that the request cannot be
completed rather than inventing a successful result.

### Step 7 - Save and record the version

1. Save the agent configuration.
2. Record the agent name, version, model deployment, owner, connected tools,
   and test evidence.
3. Do not publish the agent from this experimentation workflow.
4. Re-run the tests whenever instructions, models, connections, indexes, or
   data permissions change.

## 3. Decide how the agent connects to data

| Requirement | Recommended pattern |
|---|---|
| Search documents with citations | Native Azure AI Search tool |
| Use files already in Blob/ADLS as searchable knowledge | Index the files into Azure AI Search, then use the native Search tool |
| Read a Blob object directly | Approved read-only MCP, OpenAPI, or function tool |
| Query Cosmos DB | Approved MCP, OpenAPI, or function tool |
| Query PostgreSQL | Approved MCP, OpenAPI, or function tool exposing allow-listed operations |

Do not give a language model unrestricted database access or a general-purpose
SQL execution tool.

## 4. Configure each data service

### 4.1 Azure AI Search

Azure AI Search is the preferred native knowledge-retrieval integration.

#### Platform configuration

1. Create an approved Search service and index.
2. Include searchable and retrievable content fields.
3. Include retrievable source/title fields for citations.
4. Configure vector and semantic search when required.
5. Use a separate ingestion pipeline to populate and update the index.
6. Assign **Search Index Data Reader** to the project managed identity for a
   query-only agent.
7. If the selected Foundry feature must create or update index objects, the
   platform owner may also need **Search Index Data Contributor** and
   **Search Service Contributor**. Do not grant these to the query identity
   unless the feature requires them.
8. Configure private endpoint, DNS, and network access where required.
9. Create an Azure AI Search project connection using Microsoft Entra ID or
   managed identity authentication.

#### Agent configuration in the portal

1. Open the agent.
2. Select **Tools** or **Knowledge**.
3. Add **Azure AI Search**.
4. Select the approved project connection.
5. Select the approved index.
6. Map the content, title, URL/source, and vector fields when requested.
7. Prefer vector-semantic hybrid search when the index supports it.
8. Set a small, reviewed top-K value.
9. Require citations in the agent instructions.
10. Test a known result, an unknown result, and an unauthorized result.

### 4.2 Azure Storage Blob or ADLS Gen2

#### Recommended pattern: index Blob data into AI Search

1. Place only approved files in the source container or ADLS directory.
2. Give the Search indexer identity **Storage Blob Data Reader** on that
   container.
3. For ADLS Gen2, also apply directory traverse/read ACLs.
4. Configure a Search data source, indexer, skillset if required, and index.
5. Keep ingestion permissions separate from the agent runtime identity.
6. Connect the agent to the resulting Search index using section 4.1.

This pattern provides controlled retrieval, citations, and indexing without
giving the agent general object-store access.

#### Direct object access

Use direct access only when the agent must retrieve a specific object rather
than search indexed knowledge.

1. Provide an approved MCP, OpenAPI, or function tool.
2. Give the tool's managed identity **Storage Blob Data Reader** on the exact
   container.
3. Allow-list container names, path prefixes, file types, and maximum object
   size.
4. Reject path traversal, arbitrary account selection, uploads, overwrites,
   and deletes unless separately approved.
5. In the Foundry agent, add the approved MCP/OpenAPI tool.
6. Test access to an approved blob and denial for an out-of-scope blob.

Do not use storage account keys or broad SAS tokens in the agent configuration.

### 4.3 Azure Cosmos DB for NoSQL

Use a constrained tool in front of Cosmos DB. Do not expose account keys or
unrestricted query execution to the model.

#### Platform configuration

1. Identify the approved account, database, container, partition key, and
   operations.
2. Implement an MCP, OpenAPI, or function tool with typed, allow-listed
   operations such as `getCustomerById` or `listOpenCases`.
3. Use parameterized queries and enforce partition-key and result-size limits.
4. Enable the tool's managed identity.
5. Assign **Cosmos DB Built-in Data Reader** through Cosmos DB native
   data-plane RBAC at the narrowest supported scope.
6. Grant **Cosmos DB Built-in Data Contributor** only if a reviewed use case
   requires writes.
7. Configure private endpoint, DNS, retries, request-unit limits, and
   diagnostic settings.

#### Agent configuration in the portal

1. Open the agent and select **Tools**.
2. Add the approved MCP or OpenAPI tool.
3. Configure Entra authentication using the approved project/tool identity.
4. Select only the approved operations.
5. Add instructions that the agent must not construct arbitrary queries.
6. Test valid reads, missing records, cross-partition limits, denied writes,
   and throttling.

### 4.4 Azure Database for PostgreSQL

Use a constrained data service or tool. Do not provide a general-purpose SQL
console to the agent.

#### Platform configuration

1. Enable Microsoft Entra authentication on PostgreSQL Flexible Server.
2. Configure an Entra administrator.
3. Create a database principal for the managed identity used by the MCP,
   OpenAPI, or function tool.
4. Grant only:
   - `CONNECT` on the approved database.
   - `USAGE` on the approved schema.
   - `SELECT` on approved views or tables.
   - `EXECUTE` on specific approved functions when required.
5. Prefer read-only views and stored functions that enforce tenant and row
   filters.
6. Use parameterized queries, timeouts, row limits, and connection pooling.
7. Configure private networking, DNS, TLS, diagnostics, and slow-query
   monitoring.

#### Agent configuration in the portal

1. Open the agent and select **Tools**.
2. Add the approved MCP or OpenAPI tool.
3. Use Entra authentication; do not paste a database password into Foundry.
4. Expose business operations, not raw SQL, for example
   `getOrderStatus(orderId)`.
5. Add instructions that prohibit arbitrary SQL and schema discovery.
6. Test allowed reads, invalid identifiers, injection attempts, excessive
   result requests, denied writes, and database timeouts.

## 5. Monitoring and observability - enabled by default

Monitoring is mandatory for every agent in `PlaygroundProjects`.

The project is already connected to:

- Application Insights:
  `appi-agents-poc-aue-playground-projects`
- Log Analytics:
  `log-agents-poc-aue-playground-projects`

Developers must not create a separate monitoring resource for each agent or
disable project tracing.

### Validate tracing before agent testing

1. Open the project in Microsoft Foundry.
2. Open **Project details** or **Operate > Admin**.
3. Open **Connected resources**.
4. Verify the project has an `AppInsights` connection to the Application
   Insights resource listed above.
5. Open **Agents > Traces**.
6. Verify the portal reports that tracing is connected.

### Validate telemetry after every change

1. Run a successful playground invocation.
2. Run an invocation that calls each configured tool.
3. Run a controlled failure, such as an unknown record.
4. Open **Agents > Traces**.
5. Confirm the trace shows:
   - Project and agent.
   - Agent version.
   - Model call and latency.
   - Token usage where available.
   - Tool/retrieval call and duration.
   - Dependency status.
   - Error category for failed operations.
6. Confirm the trace is also available in Application Insights.
7. Confirm no secrets, access tokens, connection strings, passwords, personal
   data, or unapproved prompt/response content were recorded.

### Default operational monitoring

The platform team should provide dashboards and alerts for:

- Invocation volume and success rate.
- End-to-end and model latency.
- Model throttling and quota exhaustion.
- Tool failures and dependency latency.
- Token usage and abnormal cost growth.
- Authentication and authorization failures.
- Search latency, Cosmos DB throttling, Storage failures, and PostgreSQL
  failures when those services are used.
- No telemetry received from an active agent.
- Safety-filter and evaluation failures.

Access to telemetry should be read-only for developers. Retention, export,
sampling, redaction, dashboards, and alerts remain platform-owner
responsibilities.

## 6. Completion checklist

- [ ] Developer has `Foundry User` on `playground-projects`.
- [ ] Developer can see an approved model but cannot deploy a model.
- [ ] Project managed identity has `Foundry User` on the parent account.
- [ ] Agent uses only approved connections and tools.
- [ ] Runtime data roles are assigned to the correct managed identity, not
      automatically to every developer.
- [ ] Search, Blob/ADLS, Cosmos DB, and PostgreSQL access is read-only by
      default.
- [ ] Agent cannot access data outside the approved scope.
- [ ] Agent cannot perform write, delete, or administrative operations.
- [ ] Prompt-injection and data-exfiltration tests pass.
- [ ] Successful and failed calls appear in project traces.
- [ ] Application Insights contains correlated model and tool telemetry.
- [ ] Telemetry contains no secrets or unapproved sensitive content.
- [ ] Agent and test evidence are recorded.
- [ ] Agent remains unpublished until a separate approval is completed.

## References

- [Create and test prompt agents](https://learn.microsoft.com/azure/foundry/agents/quickstart)
- [Foundry role-based access control](https://learn.microsoft.com/azure/foundry/concepts/rbac-foundry)
- [Connect Azure AI Search to Foundry agents](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/ai-search)
- [Foundry project connections](https://learn.microsoft.com/azure/foundry/how-to/connections-add)
- [Set up tracing for agents](https://learn.microsoft.com/azure/foundry/observability/how-to/trace-agent-setup)
- [Agent tracing concepts](https://learn.microsoft.com/azure/foundry/observability/concepts/trace-agent-concept)
- [Azure Blob Storage authorization](https://learn.microsoft.com/azure/storage/blobs/authorize-access-azure-active-directory)
- [Cosmos DB data-plane RBAC](https://learn.microsoft.com/azure/cosmos-db/nosql/security/how-to-grant-data-plane-access)
- [PostgreSQL managed-identity authentication](https://learn.microsoft.com/azure/postgresql/security/security-connect-with-managed-identity)

