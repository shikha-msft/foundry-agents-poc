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
    monitoringFails = $false
    identityFails = $false
}

function python {
    $input | Out-Null
    $state.calls.Add("python $($args -join ' ')")
    if ($args[1] -eq "render") {
        $position = [array]::IndexOf($args, "--output")
        [System.IO.File]::WriteAllText($args[$position + 1], '{"definition":{}}')
    }
    if (
        ($args[1] -eq "prepare-index" -and $state.preparationFails) -or
        ($args[1] -eq "monitoring" -and $state.monitoringFails) -or
        ($args[1] -eq "identity" -and $state.identityFails)
    ) {
        $global:LASTEXITCODE = 1
    }
    else {
        $global:LASTEXITCODE = 0
        if ($args[1] -eq "identity") {
            '{"blueprint":{},"instance_identity":{}}'
        }
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
    $state.calls.Add("rest:$Method")
    if ($Uri -match "/connections") {
        return @{ value = @() }
    }
    [pscustomobject]@{ version = "offline" }
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
        Assert-Condition ($state.calls.Count -eq 8) "Expected render, authentication, monitoring, preparation, creation and identity verification."
        Assert-Condition ($state.calls[4] -match "prepare-index --index-mode $mode --index-name selected-index") "Index mode/name not forwarded."
        Assert-Condition ($state.calls[1] -eq "az" -and $state.calls[5] -eq "rest:Post") "Preparation must precede REST creation."
    }

    $state.calls.Clear()
    & $helper -Agent rag -Method Azd -SearchIndexMode existing
    Assert-Condition ($state.calls[4] -match "prepare-index --index-mode existing") "Azd path skipped index preparation."
    Assert-Condition ($state.calls[1] -eq "azd" -and $state.calls[5] -eq "rest:Post") "Azd authentication path changed."

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
    Assert-Condition ($state.calls.Count -eq 5) "Preparation failure must not create an agent."
    $state.preparationFails = $false

    $state.calls.Clear()
    & $helper -Agent prompt -Method AzCli
    Assert-Condition ($state.calls.Count -eq 7) "Prompt creation must not prepare a Search index."

    $state.calls.Clear()
    $state.monitoringFails = $true
    $failed = $false
    try {
        & $helper -Agent rag -Method AzCli -SearchIndexMode create
    }
    catch {
        if ($_.Exception.Message -notmatch "Project monitoring validation failed") { throw }
        $failed = $true
    }
    Assert-Condition $failed "Missing monitoring must fail."
    Assert-Condition ($state.calls.Count -eq 4) "Missing monitoring must not prepare an index or create an agent."
    $state.monitoringFails = $false

    $state.calls.Clear()
    $state.identityFails = $true
    $failed = $false
    try {
        & $helper -Agent prompt -Method AzCli
    }
    catch {
        if ($_.Exception.Message -notmatch "Agent Identity validation failed") { throw }
        $failed = $true
    }
    Assert-Condition $failed "Missing identity must fail after creation."
    Assert-Condition ($state.calls -contains "rest:Post") "Identity check should run after creation."
    $state.identityFails = $false

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
    Write-Output "9 REST entrypoint scenarios passed."
}
finally {
    Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
}
$global:LASTEXITCODE = 0
