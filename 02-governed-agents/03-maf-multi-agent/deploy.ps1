[CmdletBinding(SupportsShouldProcess)]
param(
    [string] $SubscriptionId = "c6a4ffe5-6f74-4846-b4e1-57386c4b7935",
    [string] $TenantId = "16b3c013-d300-468d-ac64-7eda0820b6d3",
    [string] $ResourceGroupName = "rg-foundry-demo",
    [string] $Location = "australiaeast",
    [string] $AppServicePlanName = "asp-maf-agents-poc-aue",
    [Parameter(Mandatory)]
    [string] $WebAppName,
    [string] $Sku = "B1",
    [string] $FoundryAccountName = "ss-aueast-foundry",
    [string] $ProjectEndpoint = "https://ss-aueast-foundry.services.ai.azure.com/api/projects/poc-project",
    [string] $ModelDeploymentName = "gpt-5.4-mini",
    [string] $PromptAgentName = "gov-prompt-agent-poc",
    [string] $RagAgentName = "gov-rag-agent-poc",
    [string] $ApplicationInsightsName = "appi-agents-poc-aue-poc-project",
    [string] $EntraClientId,
    [switch] $SkipPackageDeploy,
    [switch] $SkipRoleAssignment
)

$ErrorActionPreference = "Stop"
$foundryUserRoleId = "53ca6127-db72-4b80-b1b0-d745d6d5456d"

function Invoke-AzCli {
    param([Parameter(Mandatory)][string[]] $Arguments)

    $output = & az @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI command failed: az $($Arguments -join ' ')`n$output"
    }
    return $output
}

Invoke-AzCli -Arguments @(
    "account", "set",
    "--subscription", $SubscriptionId
) | Out-Null

$foundryAccountId = Invoke-AzCli -Arguments @(
    "cognitiveservices", "account", "show",
    "--name", $FoundryAccountName,
    "--resource-group", $ResourceGroupName,
    "--query", "id",
    "--output", "tsv"
)

$appInsightsConnectionString = Invoke-AzCli -Arguments @(
    "monitor", "app-insights", "component", "show",
    "--app", $ApplicationInsightsName,
    "--resource-group", $ResourceGroupName,
    "--query", "connectionString",
    "--output", "tsv"
)

if ($PSCmdlet.ShouldProcess($AppServicePlanName, "Create or update Linux App Service plan")) {
    Invoke-AzCli -Arguments @(
        "appservice", "plan", "create",
        "--name", $AppServicePlanName,
        "--resource-group", $ResourceGroupName,
        "--location", $Location,
        "--sku", $Sku,
        "--is-linux",
        "--output", "none"
    ) | Out-Null
}

$webAppExists = $false
try {
    Invoke-AzCli -Arguments @(
        "webapp", "show",
        "--name", $WebAppName,
        "--resource-group", $ResourceGroupName,
        "--output", "none"
    ) | Out-Null
    $webAppExists = $true
}
catch {
    $webAppExists = $false
}

if (-not $webAppExists -and $PSCmdlet.ShouldProcess($WebAppName, "Create Python 3.12 web app")) {
    Invoke-AzCli -Arguments @(
        "webapp", "create",
        "--name", $WebAppName,
        "--resource-group", $ResourceGroupName,
        "--plan", $AppServicePlanName,
        "--runtime", "PYTHON:3.12",
        "--output", "none"
    ) | Out-Null
}

if ($PSCmdlet.ShouldProcess($WebAppName, "Enable system-assigned managed identity")) {
    $principalId = Invoke-AzCli -Arguments @(
        "webapp", "identity", "assign",
        "--name", $WebAppName,
        "--resource-group", $ResourceGroupName,
        "--query", "principalId",
        "--output", "tsv"
    )

    if (-not $SkipRoleAssignment) {
        $existingAssignment = Invoke-AzCli -Arguments @(
            "role", "assignment", "list",
            "--assignee-object-id", $principalId,
            "--scope", $foundryAccountId,
            "--role", $foundryUserRoleId,
            "--query", "[0].id",
            "--output", "tsv"
        )
        if (-not $existingAssignment) {
            Invoke-AzCli -Arguments @(
                "role", "assignment", "create",
                "--assignee-object-id", $principalId,
                "--assignee-principal-type", "ServicePrincipal",
                "--role", $foundryUserRoleId,
                "--scope", $foundryAccountId,
                "--output", "none"
            ) | Out-Null
        }
    }
}

$requireAuth = if ($EntraClientId) { "true" } else { "false" }
if ($PSCmdlet.ShouldProcess($WebAppName, "Configure application settings")) {
    Invoke-AzCli -Arguments @(
        "webapp", "config", "appsettings", "set",
        "--name", $WebAppName,
        "--resource-group", $ResourceGroupName,
        "--settings",
        "PROJECT_ENDPOINT=$ProjectEndpoint",
        "AZURE_TENANT_ID=$TenantId",
        "MODEL_DEPLOYMENT_NAME=$ModelDeploymentName",
        "PROMPT_AGENT_NAME=$PromptAgentName",
        "RAG_AGENT_NAME=$RagAgentName",
        "MAF_MAX_ROUND_COUNT=6",
        "MAF_MAX_STALL_COUNT=2",
        "MAF_WORKFLOW_TIMEOUT_SECONDS=120",
        "REQUIRE_APP_SERVICE_AUTH=$requireAuth",
        "APPLICATIONINSIGHTS_CONNECTION_STRING=$appInsightsConnectionString",
        "SCM_DO_BUILD_DURING_DEPLOYMENT=true",
        "ENABLE_ORYX_BUILD=true",
        "--output", "none"
    ) | Out-Null

    Invoke-AzCli -Arguments @(
        "webapp", "config", "set",
        "--name", $WebAppName,
        "--resource-group", $ResourceGroupName,
        "--startup-file", "startup.sh",
        "--always-on", "true",
        "--http20-enabled", "true",
        "--generic-configurations", '{"healthCheckPath":"/healthz"}',
        "--output", "none"
    ) | Out-Null
}

if ($EntraClientId -and $PSCmdlet.ShouldProcess($WebAppName, "Enable Microsoft Entra authentication")) {
    Invoke-AzCli -Arguments @(
        "webapp", "auth", "update",
        "--name", $WebAppName,
        "--resource-group", $ResourceGroupName,
        "--enabled", "true",
        "--action", "LoginWithAzureActiveDirectory",
        "--aad-client-id", $EntraClientId,
        "--aad-token-issuer-url", "https://sts.windows.net/$TenantId/",
        "--output", "none"
    ) | Out-Null
}

if (-not $SkipPackageDeploy -and $PSCmdlet.ShouldProcess($WebAppName, "Deploy MAF application package")) {
    $stagingDirectory = Join-Path ([System.IO.Path]::GetTempPath()) "maf-app-$([guid]::NewGuid())"
    $zipPath = "$stagingDirectory.zip"
    try {
        New-Item -ItemType Directory -Path $stagingDirectory | Out-Null
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot "app") `
            -Destination (Join-Path $stagingDirectory "app") -Recurse
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot "requirements.txt") `
            -Destination $stagingDirectory
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot "startup.sh") `
            -Destination $stagingDirectory
        Compress-Archive -Path (Join-Path $stagingDirectory "*") -DestinationPath $zipPath

        Invoke-AzCli -Arguments @(
            "webapp", "deploy",
            "--name", $WebAppName,
            "--resource-group", $ResourceGroupName,
            "--src-path", $zipPath,
            "--type", "zip",
            "--restart", "true",
            "--output", "none"
        ) | Out-Null
    }
    finally {
        if (Test-Path -LiteralPath $zipPath) {
            Remove-Item -LiteralPath $zipPath -Force
        }
        if (Test-Path -LiteralPath $stagingDirectory) {
            Remove-Item -LiteralPath $stagingDirectory -Recurse -Force
        }
    }
}

if ($WhatIfPreference) {
    [ordered]@{
        webAppName = $WebAppName
        planned = $true
        promptAgentName = $PromptAgentName
        ragAgentName = $RagAgentName
        entraAuthenticationEnabled = [bool]$EntraClientId
    } | ConvertTo-Json
    return
}

$hostName = Invoke-AzCli -Arguments @(
    "webapp", "show",
    "--name", $WebAppName,
    "--resource-group", $ResourceGroupName,
    "--query", "defaultHostName",
    "--output", "tsv"
)

[ordered]@{
    webAppName = $WebAppName
    url = "https://$hostName"
    healthUrl = "https://$hostName/healthz"
    managedIdentityPrincipalId = $principalId
    promptAgentName = $PromptAgentName
    ragAgentName = $RagAgentName
    entraAuthenticationEnabled = [bool]$EntraClientId
} | ConvertTo-Json
