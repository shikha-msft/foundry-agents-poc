[CmdletBinding(SupportsShouldProcess)]
param(
    [string] $SubscriptionId,
    [string] $TenantId,
    [string] $ResourceGroupName,
    [string] $Location,
    [string] $AppServicePlanName,
    [string] $WebAppName,
    [string] $Sku,
    [string] $FoundryAccountName,
    [string] $ProjectEndpoint,
    [string] $ModelDeploymentName,
    [string] $PromptAgentName,
    [string] $RagAgentName,
    [string] $ApplicationInsightsName,
    [string] $EntraClientId,
    [switch] $SkipPackageDeploy,
    [switch] $SkipRoleAssignment
)

$ErrorActionPreference = "Stop"
$foundryUserRoleId = "53ca6127-db72-4b80-b1b0-d745d6d5456d"

function Import-DotEnv {
    param([Parameter(Mandatory)][string] $Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return
    }

    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }

        $parts = $trimmed.Split("=", 2)
        if ($parts.Count -ne 2) {
            throw "Invalid .env entry in ${Path}: $line"
        }

        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        if (
            $value.Length -ge 2 -and
            (($value.StartsWith('"') -and $value.EndsWith('"')) -or
             ($value.StartsWith("'") -and $value.EndsWith("'")))
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

function Resolve-Setting {
    param(
        [string] $ParameterValue,
        [Parameter(Mandatory)][string] $EnvironmentName,
        [switch] $AllowEmpty
    )

    if (-not [string]::IsNullOrWhiteSpace($ParameterValue)) {
        return $ParameterValue
    }

    $value = [Environment]::GetEnvironmentVariable($EnvironmentName)
    if (-not $AllowEmpty -and [string]::IsNullOrWhiteSpace($value)) {
        throw "Set $EnvironmentName in .env or pass the corresponding command-line parameter."
    }
    return $value
}

Import-DotEnv -Path (Join-Path $PSScriptRoot "..\..\.env")
Import-DotEnv -Path (Join-Path $PSScriptRoot ".env")

$SubscriptionId = Resolve-Setting $SubscriptionId "AZURE_SUBSCRIPTION_ID"
$TenantId = Resolve-Setting $TenantId "AZURE_TENANT_ID"
$ResourceGroupName = Resolve-Setting $ResourceGroupName "AZURE_RESOURCE_GROUP"
$Location = Resolve-Setting $Location "AZURE_LOCATION"
$AppServicePlanName = Resolve-Setting $AppServicePlanName "APP_SERVICE_PLAN_NAME"
$WebAppName = Resolve-Setting $WebAppName "WEB_APP_NAME"
$Sku = Resolve-Setting $Sku "APP_SERVICE_SKU"
$FoundryAccountName = Resolve-Setting $FoundryAccountName "FOUNDRY_ACCOUNT_NAME"
$ProjectEndpoint = Resolve-Setting $ProjectEndpoint "PROJECT_ENDPOINT"
$ModelDeploymentName = Resolve-Setting $ModelDeploymentName "MODEL_DEPLOYMENT_NAME"
$PromptAgentName = Resolve-Setting $PromptAgentName "PROMPT_AGENT_NAME"
$RagAgentName = Resolve-Setting $RagAgentName "RAG_AGENT_NAME"
$ApplicationInsightsName = Resolve-Setting $ApplicationInsightsName "GOVERNED_APPLICATION_INSIGHTS_NAME"
$EntraClientId = Resolve-Setting $EntraClientId "ENTRA_CLIENT_ID" -AllowEmpty

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
