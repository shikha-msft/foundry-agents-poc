$ErrorActionPreference = "Stop"
$temporaryRoot = [System.IO.Path]::GetFullPath(
    (Join-Path ([System.IO.Path]::GetTempPath()) "rag-entrypoint-$([guid]::NewGuid())")
)
[System.IO.Directory]::CreateDirectory($temporaryRoot) | Out-Null
$helper = Join-Path $temporaryRoot "create-agent-version.ps1"
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "..\..\create-agent-version.ps1") -Destination $helper
foreach ($folder in @("01-prompt-agent", "02-rag-agent")) {
    $path = Join-Path $temporaryRoot $folder
    [System.IO.Directory]::CreateDirectory($path) | Out-Null
    [System.IO.File]::WriteAllText(
        (Join-Path $path ".env"),
        "PROJECT_ENDPOINT=https://mock.services.ai.azure.com/api/projects/poc`nAGENT_NAME=mock-agent`nAZURE_TENANT_ID=11111111-1111-4111-8111-111111111111`n"
    )
}

$state = @{
    calls = [System.Collections.Generic.List[string]]::new()
    preparationFails = $false
}

function python {
    $state.calls.Add("python $($args -join ' ')")
    if ($args[1] -eq "render") {
        $position = [array]::IndexOf($args, "--output")
        [System.IO.File]::WriteAllText($args[$position + 1], '{"definition":{}}')
    }
    if ($args[1] -eq "prepare-index" -and $state.preparationFails) {
        $global:LASTEXITCODE = 1
    }
    else {
        $global:LASTEXITCODE = 0
    }
}

function az {
    $state.calls.Add("az")
    $global:LASTEXITCODE = 0
    '{"accessToken":"offline-test-token"}'
}

function azd {
    $state.calls.Add("azd")
    $global:LASTEXITCODE = 0
    '{"token":"offline-test-token"}'
}

function Invoke-RestMethod {
    param($Method, $Uri, $Headers, $Body)
    $state.calls.Add("rest")
    @{ version = "offline" }
}

function Assert-Condition {
    param([bool] $Condition, [string] $Message)
    if (-not $Condition) {
        throw $Message
    }
}

try {
    & $helper -Agent rag -Method AzCli -SearchIndexMode create -SearchIndexName preview-index -WhatIf
    Assert-Condition ($state.calls.Count -eq 1) "WhatIf must render only; no preparation or authentication."
    Assert-Condition ($state.calls[0] -match "--index-name preview-index") "WhatIf lost the supplied index name."

    foreach ($mode in @("existing", "create")) {
        $state.calls.Clear()
        & $helper -Agent rag -Method AzCli -SearchIndexMode $mode -SearchIndexName selected-index
        Assert-Condition ($state.calls.Count -eq 4) "Expected render, prepare, authentication, REST."
        Assert-Condition ($state.calls[1] -match "prepare-index --index-mode $mode --index-name selected-index") "Index mode/name not forwarded."
        Assert-Condition ($state.calls[2] -eq "az" -and $state.calls[3] -eq "rest") "Preparation must precede REST creation."
    }

    $state.calls.Clear()
    & $helper -Agent rag -Method Azd -SearchIndexMode existing
    Assert-Condition ($state.calls[1] -match "prepare-index --index-mode existing") "Azd path skipped index preparation."
    Assert-Condition ($state.calls[2] -eq "azd" -and $state.calls[3] -eq "rest") "Azd authentication path changed."

    $state.calls.Clear()
    $state.preparationFails = $true
    $failed = $false
    try {
        & $helper -Agent rag -Method AzCli -SearchIndexMode create
    }
    catch {
        if ($_.Exception.Message -notmatch "RAG index preparation failed") {
            throw
        }
        $failed = $true
    }
    Assert-Condition $failed "Preparation failure was not surfaced."
    Assert-Condition ($state.calls.Count -eq 2) "Preparation failure must not authenticate or create an agent."
    $state.preparationFails = $false

    $state.calls.Clear()
    & $helper -Agent prompt -Method AzCli
    Assert-Condition ($state.calls.Count -eq 3) "Prompt creation must not prepare a Search index."

    $state.calls.Clear()
    $failed = $false
    try {
        & $helper -Agent prompt -Method AzCli -SearchIndexMode create
    }
    catch {
        if ($_.Exception.Message -notmatch "apply only to the RAG Agent") {
            throw
        }
        $failed = $true
    }
    Assert-Condition $failed "Prompt must reject RAG-only options."
    Assert-Condition ($state.calls.Count -eq 0) "Invalid Prompt options must not execute commands."
    Write-Output "7 REST entrypoint scenarios passed."
}
finally {
    Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
}
$global:LASTEXITCODE = 0
