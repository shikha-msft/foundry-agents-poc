[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string] $SubscriptionId,
    [Parameter(Mandatory)][string] $ResourceGroupName,
    [Parameter(Mandatory)][string] $WebAppName
)

$ErrorActionPreference = "Stop"
if (-not $PSCmdlet.ShouldProcess($WebAppName, "Validate platform configuration and deploy application package only")) {
    return
}

function Invoke-AzureRead {
    param([string[]] $Arguments)
    $result = & az @Arguments --subscription $SubscriptionId --output json
    if ($LASTEXITCODE -ne 0) {
        throw "Azure configuration read failed. No platform configuration was changed."
    }
    return ($result | ConvertFrom-Json)
}

$target = @("--name", $WebAppName, "--resource-group", $ResourceGroupName)
$identity = Invoke-AzureRead -Arguments (@("webapp", "identity", "show") + $target)
if (-not $identity.principalId -or $identity.type -notmatch "SystemAssigned") {
    throw "Platform prerequisite missing: App Service system-assigned managed identity."
}
$settings = Invoke-AzureRead -Arguments (
    @("webapp", "config", "appsettings", "list") + $target +
    @("--query", "[?name=='A365_BLUEPRINT_CLIENT_ID' || name=='A365_AGENT_CLIENT_ID' || name=='AGENT365_ENABLED' || name=='AGENT365_AUTH_MODE' || name=='AGENT365_MAF_AGENT_NAME' || name=='ENABLE_A365_OBSERVABILITY_EXPORTER' || name=='A365_USE_S2S_ENDPOINT' || name=='A365_SUPPRESS_INVOKE_AGENT_INPUT']")
)
$values = @{}
foreach ($setting in $settings) { $values[$setting.name] = $setting.value }
foreach ($name in @("A365_BLUEPRINT_CLIENT_ID", "A365_AGENT_CLIENT_ID")) {
    $id = [guid]::Empty
    if (-not [guid]::TryParse($values[$name], [ref]$id) -or $id -eq [guid]::Empty) {
        throw "Platform prerequisite missing: $name. Agent Identity is required even when Agent 365 is off."
    }
}
if ($values["AGENT365_ENABLED"] -notin @("true", "false")) {
    throw "Platform must explicitly configure AGENT365_ENABLED=true or false."
}
if ($values["AGENT365_ENABLED"] -eq "true") {
    if ($values["AGENT365_AUTH_MODE"] -ne "s2s" -or -not $values["AGENT365_MAF_AGENT_NAME"]) {
        throw "Platform Agent 365 S2S registration settings are incomplete."
    }
    foreach ($name in @("ENABLE_A365_OBSERVABILITY_EXPORTER", "A365_USE_S2S_ENDPOINT", "A365_SUPPRESS_INVOKE_AGENT_INPUT")) {
        if ($values[$name] -ne "true") {
            throw "Platform prerequisite: $name must be true for Agent 365 export."
        }
    }
}
$monitoringCount = Invoke-AzureRead -Arguments (
    @("webapp", "config", "appsettings", "list") + $target +
    @("--query", "length([?name=='APPLICATIONINSIGHTS_CONNECTION_STRING' && value!=''])")
)
if ($monitoringCount -ne 1) {
    throw "Platform prerequisite missing: Application Insights runtime configuration."
}

$staging = Join-Path ([IO.Path]::GetTempPath()) "maf-package-$([guid]::NewGuid())"
$zip = "$staging.zip"
try {
    New-Item -ItemType Directory -Path $staging | Out-Null
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "app") -Destination $staging -Recurse
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "requirements.txt"), (Join-Path $PSScriptRoot "startup.sh") -Destination $staging
    Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $zip
    & az webapp deploy @target --subscription $SubscriptionId --src-path $zip --type zip --restart true --output none
    if ($LASTEXITCODE -ne 0) {
        throw "MAF application package deployment failed."
    }
}
finally {
    if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
    if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
}
Write-Output "MAF package deployed. Platform configuration was not changed; verify readiness and telemetry before release."
