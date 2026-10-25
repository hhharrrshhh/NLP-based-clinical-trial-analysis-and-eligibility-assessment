[CmdletBinding()]
param(
    [string]$ApiUrl = 'http://127.0.0.1:8000',
    [string]$UiUrl = 'http://127.0.0.1:8501',
    [switch]$Full
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$checks = [System.Collections.Generic.List[object]]::new()
function Test-Endpoint([string]$Name, [string]$Uri) {
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 30
    $watch.Stop()
    if ($response.StatusCode -ne 200) { throw "$Name returned HTTP $($response.StatusCode)." }
    $checks.Add([ordered]@{ name = $Name; url = $Uri; http_status = $response.StatusCode; latency_ms = [Math]::Round($watch.Elapsed.TotalMilliseconds, 2) })
    return $response
}
$ApiUrl = $ApiUrl.TrimEnd('/')
$UiUrl = $UiUrl.TrimEnd('/')
$health = (Test-Endpoint 'backend_health' "$ApiUrl/health").Content | ConvertFrom-Json
if ($health.status -ne 'ok' -or $health.study_count -lt 1) { throw 'Backend has no loaded study corpus.' }
$studies = (Test-Endpoint 'studies' "$ApiUrl/studies").Content | ConvertFrom-Json
if ($studies.count -ne $health.study_count) { throw 'Study count differs between API endpoints.' }
$null = Test-Endpoint 'dashboard' "$ApiUrl/dashboard"
$null = Test-Endpoint 'openapi' "$ApiUrl/openapi.json"
$uiHealth = Test-Endpoint 'frontend_health' "$UiUrl/_stcore/health"
if ($uiHealth.Content.Trim() -ne 'ok') { throw 'Frontend health body was not ok.' }
$null = Test-Endpoint 'frontend_page' $UiUrl
if ($Full) {
    if ($UiUrl -ne 'http://127.0.0.1:8501') { throw 'The full integration script currently checks frontend port 8501. Use the default UiUrl.' }
    $pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
    Push-Location $projectRoot
    try {
        & $pythonPath -m scripts.integration_smoke --api $ApiUrl
        if ($LASTEXITCODE -ne 0) { throw "Full integration smoke exited with $LASTEXITCODE." }
    } finally { Pop-Location }
}
$report = [ordered]@{ run_at_utc = [DateTime]::UtcNow.ToString('o'); status = 'passed'; full_integration = [bool]$Full; study_count = $health.study_count; checks = $checks }
$reportPath = Join-Path $projectRoot 'reports\deployment_smoke.json'
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding utf8
$report | ConvertTo-Json -Depth 8
