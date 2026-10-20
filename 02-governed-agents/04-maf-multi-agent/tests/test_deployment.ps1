$ErrorActionPreference = "Stop"
$source = Join-Path $PSScriptRoot "..\deploy.ps1"
$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) "maf-auth-tests-$([guid]::NewGuid())"
$scriptPath = Join-Path $testRoot "isolated\maf\deploy.ps1"

function Assert-True {
    param([bool] $Condition, [string] $Message)
    if (-not $Condition) {
        throw $Message
    }
}

try {
    New-Item -ItemType Directory -Path (Split-Path $scriptPath) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $scriptPath

    foreach ($scenario in @("disabled", "enabled", "missing-client", "invalid-client", "preview-disabled", "preview-enabled", "auth-failure")) {
        & {
            param($scenario, $scriptPath)
            $calls = [System.Collections.Generic.List[object]]::new()
            function az {
                $arguments = @($args)
                $calls.Add($arguments)
                $global:LASTEXITCODE = 0
                $command = $arguments -join " "
                if ($command -like "webapp auth update*" -and $scenario -eq "auth-failure") {
                    $global:LASTEXITCODE = 1
                    return "Mock authentication update failure"
                }
                if ($command -like "cognitiveservices account show*") { return "/mock/foundry" }
                if ($command -like "monitor app-insights component show*") { return "mock-monitoring-configuration" }
                if ($command -like "webapp identity assign*") { return "mock-managed-identity" }
                if ($command -like "role assignment list*") { return "mock-existing-role" }
                if ($command -like "webapp show*defaultHostName*") { return "mock.azurewebsites.net" }
            }

            $options = @{
                SubscriptionId = "test-subscription"
                TenantId = "test-tenant"
                ResourceGroupName = "test-rg"
                Location = "test-region"
                AppServicePlanName = "test-plan"
                WebAppName = "test-app"
                Sku = "B1"
                FoundryAccountName = "test-foundry"
                ProjectEndpoint = "https://mock.services.ai.azure.com/api/projects/test"
                ModelDeploymentName = "test-model"
                PromptAgentName = "test-prompt"
                RagAgentName = "test-rag"
                ApplicationInsightsName = "test-insights"
                SkipPackageDeploy = $true
            }
            $enabled = $scenario -in @("enabled", "missing-client", "invalid-client", "preview-enabled")
            if ($enabled) { $options.EnableEasyAuth = $true }
            if ($scenario -ne "missing-client") {
                $options.EntraClientId = if ($scenario -eq "invalid-client") { "<placeholder>" } else { "11111111-1111-4111-8111-111111111111" }
            }
            if ($scenario -like "preview-*") { $options.WhatIf = $true }

            $previousClientId = $env:ENTRA_CLIENT_ID
            try {
                $env:ENTRA_CLIENT_ID = ""
                $failure = $null
                $output = $null
                try { $output = & $scriptPath @options } catch { $failure = $_ }
                if ($scenario -in @("missing-client", "invalid-client")) {
                    Assert-True ($null -ne $failure) "$scenario must fail"
                    Assert-True ($calls.Count -eq 0) "$scenario must fail before Azure calls"
                }
                elseif ($scenario -eq "auth-failure") {
                    Assert-True ($null -ne $failure) "Native auth failure must propagate"
                    Assert-True ($failure.ToString() -like "*Mock authentication update failure*") "Expected native auth error"
                }
                else {
                    if ($failure) { throw $failure }
                    $result = ($output -join "`n") | ConvertFrom-Json
                    Assert-True ($result.entraAuthenticationEnabled -eq $enabled) "Reported auth mode mismatch"
                    $authCalls = @($calls | Where-Object { ($_ -join " ") -like "webapp auth update*" })
                    $settingsCalls = @($calls | Where-Object { ($_ -join " ") -like "webapp config appsettings set*" })
                    if ($scenario -like "preview-*") {
                        Assert-True ($authCalls.Count -eq 0 -and $settingsCalls.Count -eq 0) "Preview must not mutate auth/settings"
                    }
                    else {
                        Assert-True ($authCalls.Count -eq 1) "Exactly one platform auth update expected"
                        $expected = $enabled.ToString().ToLowerInvariant()
                        Assert-True (($authCalls[0] -join " ") -like "*--enabled $expected*") "Platform auth mode mismatch"
                        Assert-True (($settingsCalls[0] -join " ") -like "*REQUIRE_APP_SERVICE_AUTH=$expected*") "App auth mode mismatch"
                        if ($enabled) {
                            Assert-True (($authCalls[0] -join " ") -like "*--aad-client-id $($options.EntraClientId)*") "Enabled mode must configure selected client"
                            Assert-True (($authCalls[0] -join " ") -like "*--aad-token-issuer-url https://sts.windows.net/test-tenant/*") "Enabled mode must configure tenant issuer"
                        }
                        else {
                            Assert-True (($authCalls[0] -join " ") -notlike "*--aad-client-id*") "Disabled mode must ignore supplied client"
                        }
                    }
                }
            }
            finally {
                $env:ENTRA_CLIENT_ID = $previousClientId
            }
            Write-Output "PASS: $scenario"
        } $scenario $scriptPath
    }
}
finally {
    if (Test-Path -LiteralPath $testRoot) {
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}
$global:LASTEXITCODE = 0
