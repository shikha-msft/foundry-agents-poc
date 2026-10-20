[CmdletBinding(SupportsShouldProcess)]
param(
    [ValidateSet("All", "Foundry", "Maf")]
    [string] $Scope = "All",
    [string] $SubscriptionId,
    [string] $TenantId,
    [string] $ResourceGroupName,
    [string] $FoundryAccountName,
    [string] $WebAppName,
    [string] $MafAgentName,
    [ValidateSet("s2s")]
    [string] $AuthMode = "s2s"
)

$ErrorActionPreference = "Stop"
$mafPath = Join-Path $PSScriptRoot "02-governed-agents\04-maf-multi-agent"
$generatedConfigPath = Join-Path $mafPath "a365.generated.config.json"
$outputPath = Join-Path $PSScriptRoot "agent365-provisioning-output.json"

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

        if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

function Resolve-Setting {
    param(
        [string] $ParameterValue,
        [Parameter(Mandatory)][string] $EnvironmentName
    )

    if (-not [string]::IsNullOrWhiteSpace($ParameterValue)) {
        return $ParameterValue
    }

    $value = [Environment]::GetEnvironmentVariable($EnvironmentName)
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Set $EnvironmentName in .env or pass the corresponding command-line parameter."
    }
    return $value
}

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory)][string] $Command,
        [Parameter(Mandatory)][string[]] $Arguments
    )

    $output = & $Command @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "$Command failed with exit code $LASTEXITCODE.`n$output"
    }
    return $output
}

function Write-JsonFile {
    param(
        [Parameter(Mandatory)][string] $Path,
        [Parameter(Mandatory)] $Value
    )

    [System.IO.File]::WriteAllText(
        $Path,
        ($Value | ConvertTo-Json -Depth 20),
        [System.Text.UTF8Encoding]::new($false)
    )
}

function Add-ManagedIdentityFederatedCredential {
    param(
        [Parameter(Mandatory)][string] $BlueprintClientId,
        [Parameter(Mandatory)][string] $ManagedIdentityPrincipalId,
        [Parameter(Mandatory)][string] $TenantId
    )

    $blueprintObjectId = Invoke-NativeCommand -Command "az" -Arguments @(
        "ad", "app", "show",
        "--id", $BlueprintClientId,
        "--query", "id",
        "--output", "tsv"
    )
    $blueprintObjectId = ([string] $blueprintObjectId).Trim()
    if ([string]::IsNullOrWhiteSpace($blueprintObjectId)) {
        throw "The Agent Identity blueprint application could not be resolved."
    }

    $credentialName = "maf-app-service-managed-identity"
    $credentials = Invoke-NativeCommand -Command "az" -Arguments @(
        "rest",
        "--method", "get",
        "--url", "https://graph.microsoft.com/v1.0/applications/$blueprintObjectId/federatedIdentityCredentials",
        "--output", "json"
    ) | ConvertFrom-Json
    $existing = $credentials.value | Where-Object { $_.name -eq $credentialName } | Select-Object -First 1
    $issuer = "https://login.microsoftonline.com/$TenantId/v2.0"

    if ($existing) {
        if (
            $existing.subject -ne $ManagedIdentityPrincipalId -or
            $existing.issuer -ne $issuer -or
            $existing.audiences -notcontains "api://AzureADTokenExchange"
        ) {
            throw "Federated credential '$credentialName' exists with different identity settings."
        }
        return
    }

    $bodyFile = [System.IO.Path]::GetTempFileName()
    try {
        Write-JsonFile -Path $bodyFile -Value @{
            name = $credentialName
            issuer = $issuer
            subject = $ManagedIdentityPrincipalId
            audiences = @("api://AzureADTokenExchange")
            description = "MAF App Service system-assigned managed identity"
        }
        Invoke-NativeCommand -Command "az" -Arguments @(
            "rest",
            "--method", "post",
            "--url", "https://graph.microsoft.com/v1.0/applications/$blueprintObjectId/federatedIdentityCredentials",
            "--headers", "Content-Type=application/json",
            "--body", "@$bodyFile",
            "--output", "none"
        ) | Out-Null
    }
    finally {
        Remove-Item -LiteralPath $bodyFile -Force -ErrorAction SilentlyContinue
    }
}

Import-DotEnv -Path (Join-Path $PSScriptRoot ".env")

$SubscriptionId = Resolve-Setting $SubscriptionId "AZURE_SUBSCRIPTION_ID"
$TenantId = Resolve-Setting $TenantId "AZURE_TENANT_ID"
$ResourceGroupName = Resolve-Setting $ResourceGroupName "AZURE_RESOURCE_GROUP"
$FoundryAccountName = Resolve-Setting $FoundryAccountName "FOUNDRY_ACCOUNT_NAME"

if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    throw "Azure CLI is required. Install it from https://aka.ms/installazurecli."
}

Invoke-NativeCommand -Command "az" -Arguments @(
    "account", "set",
    "--subscription", $SubscriptionId
) | Out-Null

$result = [ordered]@{
    tenantId = $TenantId
    foundry = $null
    maf = $null
}

if ($Scope -in @("All", "Foundry")) {
    $foundryResourceId = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroupName/providers/Microsoft.CognitiveServices/accounts/$FoundryAccountName"
    $foundryUrl = "https://management.azure.com${foundryResourceId}?api-version=2026-03-15-preview"

    if ($WhatIfPreference) {
        Write-Host "What if: Enable Agent 365 data collection on $foundryResourceId"
        $result.foundry = [ordered]@{
            resourceId = $foundryResourceId
            requestedLoggingEnabled = $true
            status = "WhatIf"
        }
    }
    elseif ($PSCmdlet.ShouldProcess($foundryResourceId, "Enable Agent 365 data collection")) {
        $bodyFile = [System.IO.Path]::GetTempFileName()
        try {
            Write-JsonFile -Path $bodyFile -Value @{
                properties = @{
                    a365LoggingEnabled = $true
                }
            }
            Invoke-NativeCommand -Command "az" -Arguments @(
                "rest",
                "--method", "patch",
                "--url", $foundryUrl,
                "--headers", "Content-Type=application/json",
                "--body", "@$bodyFile",
                "--output", "none"
            ) | Out-Null
        }
        finally {
            Remove-Item -LiteralPath $bodyFile -Force -ErrorAction SilentlyContinue
        }

        $foundryState = Invoke-NativeCommand -Command "az" -Arguments @(
            "rest",
            "--method", "get",
            "--url", $foundryUrl,
            "--query", "properties.{loggingEnabled:a365LoggingEnabled,status:a365Status}",
            "--output", "json"
        ) | ConvertFrom-Json

        if ($foundryState.loggingEnabled -ne $true) {
            throw "Foundry did not persist a365LoggingEnabled=true."
        }
        if ($foundryState.status -ne "Enabled") {
            throw "Agent 365 status is '$($foundryState.status)'. Complete tenant licensing and consent before retrying."
        }

        $result.foundry = [ordered]@{
            resourceId = $foundryResourceId
            loggingEnabled = $foundryState.loggingEnabled
            status = $foundryState.status
        }
    }
}

if ($Scope -in @("All", "Maf")) {
    $WebAppName = Resolve-Setting $WebAppName "WEB_APP_NAME"
    $MafAgentName = Resolve-Setting $MafAgentName "AGENT365_MAF_AGENT_NAME"

    if (-not (Get-Command a365 -ErrorAction SilentlyContinue)) {
        throw "Agent 365 CLI is required. Install it with: dotnet tool install --global Microsoft.Agents.A365.DevTools.Cli"
    }

    $managedIdentityPrincipalId = Invoke-NativeCommand -Command "az" -Arguments @(
        "webapp", "identity", "show",
        "--name", $WebAppName,
        "--resource-group", $ResourceGroupName,
        "--query", "principalId",
        "--output", "tsv"
    )
    $managedIdentityPrincipalId = ([string] $managedIdentityPrincipalId).Trim()
    if ([string]::IsNullOrWhiteSpace($managedIdentityPrincipalId)) {
        throw "The MAF App Service must have a system-assigned managed identity before Agent 365 setup."
    }

    $setupArguments = @(
        "setup", "all",
        "--agent-name", $MafAgentName,
        "--tenant-id", $TenantId,
        "--authmode", $AuthMode
    )
    if ($WhatIfPreference) {
        $setupArguments += "--dry-run"
        Push-Location $mafPath
        try {
            Invoke-NativeCommand -Command "a365" -Arguments $setupArguments | Write-Host
        }
        finally {
            Pop-Location
        }
        $result.maf = [ordered]@{
            agentName = $MafAgentName
            authMode = $AuthMode
            managedIdentityPrincipalId = $managedIdentityPrincipalId
            status = "WhatIf"
        }
    }
    elseif ($PSCmdlet.ShouldProcess($MafAgentName, "Register MAF orchestrator with Agent 365")) {
        Push-Location $mafPath
        try {
            Invoke-NativeCommand -Command "a365" -Arguments @("setup", "requirements") | Write-Host
            Invoke-NativeCommand -Command "a365" -Arguments $setupArguments | Write-Host
        }
        finally {
            Pop-Location
        }

        if (-not (Test-Path -LiteralPath $generatedConfigPath -PathType Leaf)) {
            throw "Agent 365 CLI did not create a365.generated.config.json."
        }

        $generated = Get-Content -LiteralPath $generatedConfigPath -Raw | ConvertFrom-Json
        if (
            [string]::IsNullOrWhiteSpace($generated.agentBlueprintId) -or
            [string]::IsNullOrWhiteSpace($generated.agenticAppId)
        ) {
            throw "Agent 365 setup did not return the blueprint and agent identity client IDs."
        }

        Add-ManagedIdentityFederatedCredential `
            -BlueprintClientId $generated.agentBlueprintId `
            -ManagedIdentityPrincipalId $managedIdentityPrincipalId `
            -TenantId $TenantId

        Invoke-NativeCommand -Command "az" -Arguments @(
            "webapp", "config", "appsettings", "set",
            "--name", $WebAppName,
            "--resource-group", $ResourceGroupName,
            "--settings",
            "AGENT365_ENABLED=true",
            "A365_BLUEPRINT_CLIENT_ID=$($generated.agentBlueprintId)",
            "A365_AGENT_CLIENT_ID=$($generated.agenticAppId)",
            "ENABLE_A365_OBSERVABILITY_EXPORTER=true",
            "A365_USE_S2S_ENDPOINT=true",
            "A365_SUPPRESS_INVOKE_AGENT_INPUT=true",
            "--output", "none"
        ) | Out-Null

        $result.maf = [ordered]@{
            agentName = $MafAgentName
            authMode = $AuthMode
            managedIdentityPrincipalId = $managedIdentityPrincipalId
            blueprintClientId = $generated.agentBlueprintId
            agentClientId = $generated.agenticAppId
            agentInstanceId = $generated.agentInstanceId
            agentRegistrationId = $generated.agentRegistrationId
            status = "Provisioned"
        }
    }
}

Write-JsonFile -Path $outputPath -Value $result
$result | ConvertTo-Json -Depth 10
