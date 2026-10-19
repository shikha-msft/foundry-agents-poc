[CmdletBinding(SupportsShouldProcess)]
param(
    [string] $SubscriptionId = "c6a4ffe5-6f74-4846-b4e1-57386c4b7935",
    [string] $TenantId = "16b3c013-d300-468d-ac64-7eda0820b6d3",
    [string] $ResourceGroupName = "rg-foundry-demo",
    [string] $FoundryAccountName = "ss-aueast-foundry",
    [string] $Location = "australiaeast",
    [ValidateRange(30, 730)]
    [int] $RetentionDays = 90,
    [switch] $SkipRoleAssignments
)

$ErrorActionPreference = "Stop"

$projects = [ordered]@{
    "playground-projects" = @{
        DisplayName = "PlaygroundProjects"
        Description = "Project for NoCode Experimentation Agents."
    }
    "poc-project" = @{
        DisplayName = "POC Project"
        Description = "Project for Governed POC Agents development."
    }
}

$roleDefinitionIds = @{
    FoundryUser                    = "53ca6127-db72-4b80-b1b0-d745d6d5456d"
    LogAnalyticsReader             = "73c42c96-874c-492b-b04d-ab87d138a893"
    PrivilegedMonitoringDataReader = "dbc9c667-e97f-4491-aee6-90b9cf960190"
}

function Invoke-AzCli {
    param(
        [Parameter(Mandatory)]
        [string[]] $Arguments
    )

    $output = & az @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI command failed: az $($Arguments -join ' ')`n$output"
    }

    return $output
}

function Invoke-AzRest {
    param(
        [Parameter(Mandatory)]
        [ValidateSet("GET", "PUT")]
        [string] $Method,
        [Parameter(Mandatory)]
        [string] $Url,
        [hashtable] $Body
    )

    $bodyFile = $null
    try {
        $arguments = @("rest", "--method", $Method, "--url", $Url, "--output", "json")
        if ($Body) {
            $bodyFile = [System.IO.Path]::GetTempFileName()
            [System.IO.File]::WriteAllText(
                $bodyFile,
                ($Body | ConvertTo-Json -Depth 10 -Compress),
                [System.Text.UTF8Encoding]::new($false)
            )
            $arguments += @(
                "--headers", "Content-Type=application/json",
                "--body", "@$bodyFile"
            )
        }

        $result = Invoke-AzCli -Arguments $arguments
        return ($result | ConvertFrom-Json)
    }
    finally {
        if ($bodyFile -and (Test-Path -LiteralPath $bodyFile)) {
            Remove-Item -LiteralPath $bodyFile -Force
        }
    }
}

function Ensure-ProviderRegistration {
    param(
        [Parameter(Mandatory)]
        [string] $Namespace
    )

    $state = Invoke-AzCli -Arguments @(
        "provider", "show",
        "--namespace", $Namespace,
        "--query", "registrationState",
        "--output", "tsv"
    )

    if ($state.Trim() -eq "Registered") {
        return
    }

    if ($PSCmdlet.ShouldProcess($Namespace, "Register Azure resource provider")) {
        Invoke-AzCli -Arguments @(
            "provider", "register",
            "--namespace", $Namespace,
            "--wait",
            "--output", "none"
        ) | Out-Null
    }
}

function Ensure-RoleAssignment {
    param(
        [Parameter(Mandatory)]
        [string] $PrincipalId,
        [Parameter(Mandatory)]
        [string] $RoleDefinitionId,
        [Parameter(Mandatory)]
        [string] $Scope
    )

    $existing = Invoke-AzCli -Arguments @(
        "role", "assignment", "list",
        "--assignee-object-id", $PrincipalId,
        "--scope", $Scope,
        "--query", "[?roleDefinitionId=='$RoleDefinitionId'].id | [0]",
        "--output", "tsv"
    )

    if (-not [string]::IsNullOrWhiteSpace([string] $existing)) {
        return
    }

    if ($PSCmdlet.ShouldProcess($Scope, "Assign role $RoleDefinitionId to $PrincipalId")) {
        Invoke-AzCli -Arguments @(
            "role", "assignment", "create",
            "--assignee-object-id", $PrincipalId,
            "--assignee-principal-type", "ServicePrincipal",
            "--role", $RoleDefinitionId,
            "--scope", $Scope,
            "--output", "none"
        ) | Out-Null
    }
}

if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    throw "Azure CLI is required. Install it from https://aka.ms/installazurecli."
}

$account = Invoke-AzCli -Arguments @(
    "account", "show",
    "--query", "{subscriptionId:id,tenantId:tenantId,state:state}",
    "--output", "json"
) | ConvertFrom-Json

if ($account.state -ne "Enabled") {
    throw "The active Azure subscription is not enabled."
}

if ($account.tenantId -ne $TenantId -or $account.subscriptionId -ne $SubscriptionId) {
    Invoke-AzCli -Arguments @(
        "account", "set",
        "--subscription", $SubscriptionId
    ) | Out-Null

    $account = Invoke-AzCli -Arguments @(
        "account", "show",
        "--query", "{subscriptionId:id,tenantId:tenantId,state:state}",
        "--output", "json"
    ) | ConvertFrom-Json
}

if ($account.tenantId -ne $TenantId) {
    throw "Subscription $SubscriptionId is not in the expected tenant $TenantId."
}

foreach ($namespace in @(
    "Microsoft.CognitiveServices",
    "Microsoft.Insights",
    "Microsoft.OperationalInsights",
    "Microsoft.Authorization"
)) {
    Ensure-ProviderRegistration -Namespace $namespace
}

$foundryAccountId = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroupName/providers/Microsoft.CognitiveServices/accounts/$FoundryAccountName"
$foundryApiUrl = "https://management.azure.com${foundryAccountId}?api-version=2025-06-01"
$foundry = Invoke-AzRest -Method GET -Url $foundryApiUrl

if ($foundry.kind -ne "AIServices") {
    throw "The existing account must have kind AIServices. Actual kind: $($foundry.kind)"
}

if ($foundry.location -ne $Location) {
    throw "The existing account is in $($foundry.location), not $Location."
}

if (-not $foundry.properties.allowProjectManagement) {
    throw "The existing account does not have Foundry project management enabled."
}

$deploymentOutput = [ordered]@{
    subscriptionId = $SubscriptionId
    resourceGroup  = $ResourceGroupName
    foundryAccount = $foundryAccountId
    projects       = [ordered]@{}
}

foreach ($projectName in $projects.Keys) {
    $projectConfiguration = $projects[$projectName]
    $workspaceName = "log-agents-poc-aue-$projectName"
    $appInsightsName = "appi-agents-poc-aue-$projectName"

    $projectId = "$foundryAccountId/projects/$projectName"
    $workspaceId = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroupName/providers/Microsoft.OperationalInsights/workspaces/$workspaceName"
    $appInsightsId = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroupName/providers/Microsoft.Insights/components/$appInsightsName"

    if ($PSCmdlet.ShouldProcess($projectId, "Create or update Foundry V2 project")) {
        $project = Invoke-AzRest -Method PUT `
            -Url "https://management.azure.com${projectId}?api-version=2025-06-01" `
            -Body @{
                location = $Location
                identity = @{ type = "SystemAssigned" }
                properties = @{
                    displayName = $projectConfiguration.DisplayName
                    description = $projectConfiguration.Description
                }
            }
    }
    else {
        continue
    }

    if ($PSCmdlet.ShouldProcess($workspaceId, "Create or update Log Analytics workspace")) {
        $workspace = Invoke-AzRest -Method PUT `
            -Url "https://management.azure.com${workspaceId}?api-version=2023-09-01" `
            -Body @{
                location = $Location
                tags = @{
                    environment      = "poc"
                    workload         = "ai-agents"
                    "managed-by"     = "azure-cli"
                    "foundry-project" = $projectName
                }
                properties = @{
                    retentionInDays = $RetentionDays
                    features = @{
                        enableLogAccessUsingOnlyResourcePermissions = $true
                    }
                    publicNetworkAccessForIngestion = "Enabled"
                    publicNetworkAccessForQuery     = "Enabled"
                }
                sku = @{ name = "PerGB2018" }
            }
    }

    if ($PSCmdlet.ShouldProcess($appInsightsId, "Create or update Application Insights")) {
        $appInsights = Invoke-AzRest -Method PUT `
            -Url "https://management.azure.com${appInsightsId}?api-version=2020-02-02" `
            -Body @{
                location = $Location
                kind = "web"
                tags = @{
                    environment      = "poc"
                    workload         = "ai-agents"
                    "managed-by"     = "azure-cli"
                    "foundry-project" = $projectName
                }
                properties = @{
                    Application_Type             = "web"
                    WorkspaceResourceId           = $workspaceId
                    RetentionInDays               = $RetentionDays
                    DisableLocalAuth              = $false
                    publicNetworkAccessForIngestion = "Enabled"
                    publicNetworkAccessForQuery     = "Enabled"
                }
            }
    }

    $connectionId = "$projectId/connections/$appInsightsName"
    if ($PSCmdlet.ShouldProcess($connectionId, "Create or update Foundry Application Insights connection")) {
        Invoke-AzRest -Method PUT `
            -Url "https://management.azure.com${connectionId}?api-version=2025-06-01" `
            -Body @{
                properties = @{
                    category      = "AppInsights"
                    target        = $appInsightsId
                    authType      = "ApiKey"
                    isSharedToAll = $true
                    credentials   = @{ key = $appInsights.properties.ConnectionString }
                    metadata      = @{
                        ApiType    = "Azure"
                        ResourceId = $appInsightsId
                    }
                }
            } | Out-Null
    }

    if (-not $SkipRoleAssignments) {
        $projectPrincipalId = $project.identity.principalId
        if (-not $projectPrincipalId) {
            throw "The system-assigned identity was not returned for project $projectName."
        }

        Ensure-RoleAssignment `
            -PrincipalId $projectPrincipalId `
            -RoleDefinitionId "/subscriptions/$SubscriptionId/providers/Microsoft.Authorization/roleDefinitions/$($roleDefinitionIds.FoundryUser)" `
            -Scope $foundryAccountId

        Ensure-RoleAssignment `
            -PrincipalId $projectPrincipalId `
            -RoleDefinitionId "/subscriptions/$SubscriptionId/providers/Microsoft.Authorization/roleDefinitions/$($roleDefinitionIds.LogAnalyticsReader)" `
            -Scope $appInsightsId

        Ensure-RoleAssignment `
            -PrincipalId $projectPrincipalId `
            -RoleDefinitionId "/subscriptions/$SubscriptionId/providers/Microsoft.Authorization/roleDefinitions/$($roleDefinitionIds.PrivilegedMonitoringDataReader)" `
            -Scope $appInsightsId
    }

    $deploymentOutput.projects[$projectName] = [ordered]@{
        id                       = $projectId
        displayName              = $projectConfiguration.DisplayName
        principalId              = $project.identity.principalId
        logAnalyticsWorkspaceId  = $workspaceId
        applicationInsightsId    = $appInsightsId
        applicationInsightsConnectionId = $connectionId
    }
}

if (-not $WhatIfPreference) {
    $outputPath = Join-Path $PSScriptRoot "deployment-output.json"
    $deploymentOutput | ConvertTo-Json -Depth 8 | Set-Content -Path $outputPath -Encoding utf8
    Write-Host "Deployment completed. Resource identifiers: $outputPath"
}
