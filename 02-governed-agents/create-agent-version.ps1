[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [ValidateSet("prompt", "rag")]
    [string] $Agent,

    [Parameter(Mandatory)]
    [ValidateSet("AzCli", "Azd")]
    [string] $Method
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$configuration = if ($Agent -eq "prompt") {
    @{
        Folder = Join-Path $root "01-prompt-agent"
        Script = "prompt_agent.py"
    }
}
else {
    @{
        Folder = Join-Path $root "02-rag-agent"
        Script = "rag_agent.py"
    }
}

function Import-DotEnv {
    param([Parameter(Mandatory)][string] $Path)

    $importedNames = @()
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match "^\s*#" -or $line -notmatch "^\s*([^=]+)=(.*)$") {
            continue
        }

        $name = $Matches[1].Trim()
        $value = $Matches[2].Trim()
        if (-not [System.Environment]::GetEnvironmentVariable($name, "Process")) {
            [System.Environment]::SetEnvironmentVariable($name, $value, "Process")
            $importedNames += $name
        }
    }

    return $importedNames
}

$environmentPath = Join-Path $configuration.Folder ".env"
if (-not (Test-Path -LiteralPath $environmentPath)) {
    throw "Missing $environmentPath. Copy .env.sample to .env and populate it."
}

$importedEnvironmentNames = @(Import-DotEnv -Path $environmentPath)
$projectEndpoint = $env:PROJECT_ENDPOINT.TrimEnd("/")
$agentName = $env:AGENT_NAME
$tenantId = $env:AZURE_TENANT_ID
if (-not $projectEndpoint -or -not $agentName -or -not $tenantId) {
    throw "PROJECT_ENDPOINT, AGENT_NAME, and AZURE_TENANT_ID are required."
}

$escapedAgentName = [System.Uri]::EscapeDataString($agentName)
$requestUrl = "$projectEndpoint/agents/$escapedAgentName/versions?api-version=v1"
$bodyPath = Join-Path ([System.IO.Path]::GetTempPath()) "$Agent-agent-$([guid]::NewGuid()).json"

try {
    Push-Location $configuration.Folder
    try {
        & python $configuration.Script render --output $bodyPath
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to render the $Agent Agent definition."
        }
    }
    finally {
        Pop-Location
    }

    if ($PSCmdlet.ShouldProcess(
            "$projectEndpoint/agents/$agentName",
            "Create $Agent Agent version with $Method"
        )) {
        if ($Method -eq "AzCli") {
            $tokenOutput = & az account get-access-token `
                --resource "https://ai.azure.com" `
                --tenant $tenantId `
                --output json 2>&1
            if ($LASTEXITCODE -ne 0) {
                throw "Azure CLI is not authenticated. Run az login --tenant $tenantId."
            }

            try {
                $tokenResponse = $tokenOutput | ConvertFrom-Json
            }
            catch {
                throw "Azure CLI returned an unexpected token response."
            }

            $headers = @{
                Authorization = "Bearer $($tokenResponse.accessToken)"
                "Content-Type" = "application/json"
            }
            Invoke-RestMethod `
                -Method Post `
                -Uri $requestUrl `
                -Headers $headers `
                -Body (Get-Content -LiteralPath $bodyPath -Raw) |
                ConvertTo-Json -Depth 20
        }
        else {
            $tokenOutput = & azd auth token `
                --scope "https://ai.azure.com/.default" `
                --tenant-id $tenantId `
                --no-prompt 2>&1
            if ($LASTEXITCODE -ne 0) {
                throw "azd is not authenticated. Run azd auth login --tenant-id $tenantId."
            }

            try {
                $tokenResponse = $tokenOutput | ConvertFrom-Json
            }
            catch {
                throw "azd returned an unexpected token response. Upgrade azd and authenticate again."
            }

            $accessToken = if ($tokenResponse.token) {
                $tokenResponse.token
            }
            elseif ($tokenResponse.accessToken) {
                $tokenResponse.accessToken
            }
            else {
                throw "azd did not return an access token."
            }

            $headers = @{
                Authorization = "Bearer $accessToken"
                "Content-Type" = "application/json"
            }
            Invoke-RestMethod `
                -Method Post `
                -Uri $requestUrl `
                -Headers $headers `
                -Body (Get-Content -LiteralPath $bodyPath -Raw) |
                ConvertTo-Json -Depth 20
        }
    }
}
finally {
    if (Test-Path -LiteralPath $bodyPath) {
        Remove-Item -LiteralPath $bodyPath -Force -WhatIf:$false
    }
    foreach ($name in $importedEnvironmentNames) {
        [System.Environment]::SetEnvironmentVariable($name, $null, "Process")
    }
}
