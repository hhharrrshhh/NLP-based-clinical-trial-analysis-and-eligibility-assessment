[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$statePath = Join-Path $projectRoot 'reports\server_state.json'
if (-not (Test-Path -LiteralPath $statePath)) { Write-Host 'No processes tracked by scripts/start.ps1.'; exit 0 }
$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
if ($state.version -ne 1 -or $state.project_root -ne $projectRoot) { throw 'Process state does not belong to this project.' }

function Find-Process([int]$ProcessId) {
    return Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
}
function Test-SameProcess($Actual, $Identity) {
    return ($Actual -and $Actual.CreationDate.ToUniversalTime().Ticks -eq ([DateTime]$Identity.created_at_utc).ToUniversalTime().Ticks -and
        $Actual.CommandLine -eq $Identity.command_line -and $Actual.ExecutablePath -eq $Identity.executable)
}

foreach ($name in @('frontend', 'backend')) {
    $entry = $state.services.$name
    if (-not $entry -or -not $entry.owned) { Write-Host "Leaving reused $name running; it was not launched by scripts/start.ps1."; continue }
    $identity = $entry.process
    $actual = Find-Process $identity.pid
    $marker = if ($name -eq 'backend') { '-m uvicorn backend.app.main:app ' } else { '-m streamlit run ' }
    if (-not (Test-SameProcess $actual $identity) -or $identity.executable -ne $pythonPath -or
        -not $identity.command_line.Contains($marker) -or -not $identity.command_line.Contains($projectRoot)) {
        Write-Warning "Skipping ${name}: saved PID no longer matches the exact project-owned process."
        continue
    }
    # Snapshot descendants while the verified parent is alive. Each child must run
    # the same service command, and each identity is rechecked just before stopping.
    $snapshot = @(Get-CimInstance Win32_Process)
    $queue = [System.Collections.Generic.Queue[int]]::new()
    $queue.Enqueue([int]$actual.ProcessId)
    $children = @()
    while ($queue.Count -gt 0) {
        $parentId = $queue.Dequeue()
        foreach ($child in $snapshot | Where-Object { $_.ParentProcessId -eq $parentId }) {
            if ($child.CommandLine -and $child.CommandLine.Contains($marker) -and
                $child.CreationDate -ge $actual.CreationDate -and $child.Name -eq 'python.exe') {
                $children += [pscustomobject]@{ pid = [int]$child.ProcessId; created_at_utc = $child.CreationDate.ToUniversalTime().ToString('o'); command_line = $child.CommandLine; executable = $child.ExecutablePath }
                $queue.Enqueue([int]$child.ProcessId)
            }
        }
    }
    [array]::Reverse($children)
    foreach ($childIdentity in $children) {
        if (Test-SameProcess (Find-Process $childIdentity.pid) $childIdentity) {
            Stop-Process -Id $childIdentity.pid -ErrorAction SilentlyContinue
        }
    }
    if (Test-SameProcess (Find-Process $identity.pid) $identity) { Stop-Process -Id $identity.pid -ErrorAction SilentlyContinue }
    $entry.owned = $false
    $entry.mode = 'stopped'
    Write-Host "Stopped tracked $name process $($identity.pid)."
}
$state.updated_at_utc = [DateTime]::UtcNow.ToString('o')
$state | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $statePath -Encoding utf8
