[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [ValidateSet("prompt", "rag")]
    [string] $Agent,

    [Parameter(Mandatory)]
    [ValidateSet("AzCli", "Azd")]
    [string] $Method,

    [ValidateSet("existing", "create")]
    [string] $SearchIndexMode,

    [string] $SearchIndexName
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
if ($Agent -eq "prompt" -and ($SearchIndexMode -or $SearchIndexName)) {
    throw "SearchIndexMode and SearchIndexName apply only to the RAG Agent."
}
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
        $renderArguments = @($configuration.Script, "render", "--output", $bodyPath)
        if ($SearchIndexName) {
            $renderArguments += @("--index-name", $SearchIndexName)
        }
        & python @renderArguments
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

            $accessToken = $tokenResponse.accessToken
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

        }

        if ([string]::IsNullOrWhiteSpace($accessToken)) {
            throw "Authentication did not return an access token."
        }
        $headers = @{
            Authorization = "Bearer $accessToken"
            "Content-Type" = "application/json"
        }
        $connections = @()
        $nextLink = "$projectEndpoint/connections?api-version=v1&connectionType=AppInsights"
        while ($nextLink) {
            if (-not $nextLink.StartsWith("$projectEndpoint/", [StringComparison]::OrdinalIgnoreCase)) {
                throw "Connection pagination returned a URL outside the approved project."
            }
            $page = Invoke-RestMethod -Method Get -Uri $nextLink -Headers $headers
            $connections += @($page.value)
            $nextLink = $page.nextLink
        }
        $governanceScript = Join-Path $root "agent_governance.py"
        @{ value = $connections } | ConvertTo-Json -Depth 20 |
            & python $governanceScript monitoring --expected-name $env:APPLICATION_INSIGHTS_RESOURCE_NAME |
            Out-Host
        if ($LASTEXITCODE -ne 0) {
            throw "Project monitoring validation failed; no agent version was created."
        }

        if ($Agent -eq "rag") {
            $prepareArguments = @($configuration.Script, "prepare-index")
            if ($SearchIndexMode) {
                $prepareArguments += @("--index-mode", $SearchIndexMode)
            }
            if ($SearchIndexName) {
                $prepareArguments += @("--index-name", $SearchIndexName)
            }
            Push-Location $configuration.Folder
            try {
                & python @prepareArguments | Out-Host
                if ($LASTEXITCODE -ne 0) {
                    throw "RAG index preparation failed; no agent version was created."
                }
            }
            finally {
                Pop-Location
            }
        }
        $created = Invoke-RestMethod -Method Post -Uri $requestUrl -Headers $headers `
            -Body (Get-Content -LiteralPath $bodyPath -Raw)
        $details = Invoke-RestMethod -Method Get `
            -Uri "$projectEndpoint/agents/${escapedAgentName}?api-version=v1" -Headers $headers
        $identityJson = $details | ConvertTo-Json -Depth 20 |
            & python $governanceScript identity
        if ($LASTEXITCODE -ne 0) {
            throw "Agent Identity validation failed. The created version was not deleted; inspect it before retrying."
        }
        $created | Add-Member -NotePropertyName identity_verification `
            -NotePropertyValue ($identityJson | ConvertFrom-Json) -Force
        $created | ConvertTo-Json -Depth 20
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
