$ErrorActionPreference = "Stop"
$state = @{
    scenario = ""
    calls = [Collections.Generic.List[string]]::new()
}
function az {
    $command = $args -join " "
    $state.calls.Add($command)
    $global:LASTEXITCODE = 0
    if ($command -like "webapp identity show*") {
        if ($state.scenario -eq "missing-mi") { return '{"type":"None"}' }
        return '{"type":"SystemAssigned","principalId":"11111111-1111-4111-8111-111111111111"}'
    }
    if ($command -like "*length(*") {
        if ($state.scenario -eq "missing-monitoring") { return "0" }
        return "1"
    }
    if ($command -like "webapp config appsettings list*") {
        $agentId = if ($state.scenario -eq "missing-agent-id") { "" } else { "22222222-2222-4222-8222-222222222222" }
        $enabled = if ($state.scenario -in @("a365-incomplete", "a365-ready")) { "true" } else { "false" }
        return (@(
            @{name="A365_BLUEPRINT_CLIENT_ID";value="11111111-1111-4111-8111-111111111111"},
            @{name="A365_AGENT_CLIENT_ID";value=$agentId},
            @{name="AGENT365_ENABLED";value=$enabled},
            @{name="AGENT365_AUTH_MODE";value="s2s"},
            @{name="AGENT365_MAF_AGENT_NAME";value="mock-maf"},
            @{name="ENABLE_A365_OBSERVABILITY_EXPORTER";value=($state.scenario -eq "a365-ready").ToString().ToLowerInvariant()},
            @{name="A365_USE_S2S_ENDPOINT";value="true"},
            @{name="A365_SUPPRESS_INVOKE_AGENT_INPUT";value="true"}
        ) | ConvertTo-Json)
    }
    if ($command -like "webapp deploy*") {
        if ($state.scenario -eq "deploy-failure") {
            $global:LASTEXITCODE = 1
        }
        return
    }
    throw "Unexpected Azure operation: $command"
}

foreach ($scenario in @("preview", "ready", "a365-ready", "missing-mi", "missing-agent-id", "missing-monitoring", "a365-incomplete", "deploy-failure")) {
    $state.scenario = $scenario
    $state.calls.Clear()
    $failure = $null
    try {
        & (Join-Path $PSScriptRoot "..\deploy-package.ps1") `
            -SubscriptionId "mock" -ResourceGroupName "mock" -WebAppName "mock" `
            -WhatIf:($scenario -eq "preview")
    }
    catch { $failure = $_ }
    $deployed = @($state.calls | Where-Object { $_ -like "webapp deploy*" }).Count -gt 0
    if ($scenario -eq "preview") {
        if ($failure -or $state.calls.Count -ne 0) { throw "Preview must remain offline." }
    }
    elseif ($scenario -in @("ready", "a365-ready")) {
        if ($failure) { throw $failure }
        if (-not $deployed) { throw "Ready platform must receive the package." }
    }
    elseif ($scenario -eq "deploy-failure") {
        if (-not $failure -or -not $deployed) { throw "Deployment errors must propagate." }
    }
    elseif (-not $failure -or $deployed) {
        throw "Missing platform prerequisite must block package deployment: $scenario"
    }
    if (@($state.calls | Where-Object { $_ -match " create | assign | set | auth update " }).Count) {
        throw "Package delivery must not mutate platform configuration."
    }
    Write-Output "PASS: package-$scenario"
}
$global:LASTEXITCODE = 0
