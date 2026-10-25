[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)][int]$BackendPort = 8000,
    [ValidateRange(1024, 65535)][int]$FrontendPort = 8501,
    [ValidateRange(10, 300)][int]$TimeoutSeconds = 90
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$reportsPath = Join-Path $projectRoot 'reports'
$statePath = Join-Path $reportsPath 'server_state.json'
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Missing $pythonPath. Create the Python 3.11 virtual environment and install requirements.txt first."
}
New-Item -ItemType Directory -Path $reportsPath -Force | Out-Null

function Test-ServiceHealth([string]$Uri, [string]$Kind) {
    try {
        $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 3
        if ($response.StatusCode -ne 200) { return $false }
        if ($Kind -eq 'backend') { return (($response.Content | ConvertFrom-Json).status -eq 'ok') }
        return ($response.Content.Trim() -eq 'ok')
    } catch { return $false }
}

function Get-ProcessIdentity([int]$ProcessId) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    if (-not $process) { return $null }
    return [ordered]@{
        pid = [int]$process.ProcessId
        created_at_utc = $process.CreationDate.ToUniversalTime().ToString('o')
        executable = $process.ExecutablePath
        command_line = $process.CommandLine
    }
}

function Test-OwnedIdentity($Identity) {
    if (-not $Identity -or -not $Identity.pid) { return $false }
    $actual = Get-ProcessIdentity $Identity.pid
    return ($actual -and ([DateTime]$actual.created_at_utc).ToUniversalTime().Ticks -eq ([DateTime]$Identity.created_at_utc).ToUniversalTime().Ticks -and
        $actual.command_line -eq $Identity.command_line -and
        $actual.executable -eq $pythonPath)
}

$previous = $null
if (Test-Path -LiteralPath $statePath) {
    try { $previous = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json } catch { Write-Warning 'Ignoring unreadable prior process state.' }
}
$state = [ordered]@{ version = 1; project_root = $projectRoot; updated_at_utc = [DateTime]::UtcNow.ToString('o'); services = [ordered]@{} }
$definitions = @(
    @{ name = 'backend'; port = $BackendPort; url = "http://127.0.0.1:$BackendPort/health";
       arguments = @('-m', 'uvicorn', 'backend.app.main:app', '--host', '127.0.0.1', '--port', "$BackendPort") },
    @{ name = 'frontend'; port = $FrontendPort; url = "http://127.0.0.1:$FrontendPort/_stcore/health";
       arguments = @('-m', 'streamlit', 'run', ('"' + (Join-Path $projectRoot 'frontend\app.py') + '"'), '--server.address', '127.0.0.1', '--server.port', "$FrontendPort", '--server.headless', 'true') }
)
if ($previous -and $previous.project_root -eq $projectRoot) {
    foreach ($definition in $definitions) {
        $oldEntry = $previous.services.($definition.name)
        if ($oldEntry -and $oldEntry.owned -and (Test-OwnedIdentity $oldEntry.process) -and $oldEntry.url -ne $definition.url) {
            throw "A tracked $($definition.name) process uses $($oldEntry.url). Run scripts/stop.ps1 before changing ports."
        }
    }
}
$savedEnvironment = @{}
foreach ($key in @('DATA_DIR', 'TRIALOPS_MODEL_CACHE', 'API_BASE_URL')) { $savedEnvironment[$key] = [Environment]::GetEnvironmentVariable($key, 'Process') }
try {
    $env:DATA_DIR = Join-Path $projectRoot 'data'
    $env:TRIALOPS_MODEL_CACHE = Join-Path $projectRoot 'models\hf'
    $env:API_BASE_URL = "http://127.0.0.1:$BackendPort"
    foreach ($definition in $definitions) {
        $name = $definition.name
        $entry = [ordered]@{ url = $definition.url; mode = 'reused'; owned = $false; process = $null; log_stdout = $null; log_stderr = $null }
        if (Test-ServiceHealth $definition.url $name) {
            if ($previous -and $previous.project_root -eq $projectRoot) {
                $oldEntry = $previous.services.$name
                if ($oldEntry -and $oldEntry.owned -and (Test-OwnedIdentity $oldEntry.process)) {
                    $entry.owned = $true
                    $entry.process = $oldEntry.process
                    $entry.log_stdout = $oldEntry.log_stdout
                    $entry.log_stderr = $oldEntry.log_stderr
                }
            }
            Write-Host "Reusing healthy $name at $($definition.url)"
        } else {
            if ($previous -and $previous.project_root -eq $projectRoot) {
                $oldEntry = $previous.services.$name
                if ($oldEntry -and $oldEntry.owned -and (Test-OwnedIdentity $oldEntry.process)) {
                    throw "Tracked $name process is unhealthy. Run scripts/stop.ps1 and inspect $($oldEntry.log_stderr) before retrying."
                }
            }
            $listener = Get-NetTCPConnection -State Listen -LocalPort $definition.port -ErrorAction SilentlyContinue
            if ($listener) { throw "Port $($definition.port) is occupied by a service that failed its health check. No processes were stopped." }
            $logStamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ')
            $entry.log_stdout = Join-Path $reportsPath "$name-$logStamp.out.log"
            $entry.log_stderr = Join-Path $reportsPath "$name-$logStamp.err.log"
            $started = Start-Process -FilePath $pythonPath -ArgumentList $definition.arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
                -RedirectStandardOutput $entry.log_stdout -RedirectStandardError $entry.log_stderr
            $entry.mode = 'started'
            $entry.owned = $true
            $entry.process = Get-ProcessIdentity $started.Id
            if (-not $entry.process) { throw "$name exited at launch. See $($entry.log_stderr)." }
            # Persist ownership immediately so a failed readiness check remains stoppable.
            $state.services[$name] = $entry
            $state | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $statePath -Encoding utf8
            $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
            while (-not (Test-ServiceHealth $definition.url $name)) {
                if ($started.HasExited) { throw "$name exited. See $($entry.log_stderr)." }
                if ([DateTime]::UtcNow -ge $deadline) { throw "$name did not become healthy in $TimeoutSeconds seconds. See $($entry.log_stderr)." }
                Start-Sleep -Milliseconds 500
                $started.Refresh()
            }
            Write-Host "Started healthy $name at $($definition.url)"
        }
        $state.services[$name] = $entry
        $state | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $statePath -Encoding utf8
    }
} finally {
    foreach ($key in $savedEnvironment.Keys) { [Environment]::SetEnvironmentVariable($key, $savedEnvironment[$key], 'Process') }
}
Write-Host "TrialOps: http://127.0.0.1:$FrontendPort | API: http://127.0.0.1:$BackendPort/docs"
Write-Host "Process state: $statePath"
