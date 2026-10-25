[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $projectRoot

Write-Host 'Creating the experimental Python 3.14 environment...'
& py -3.14 -m venv .venv
if ($LASTEXITCODE -ne 0) {
    throw 'Python 3.14 was not found by the Windows Python launcher. Confirm it appears in: py -0p'
}

$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
& $pythonPath -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'Failed to upgrade pip.' }

Write-Host 'Installing the PyTorch CPU wheel first...'
& $pythonPath -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.14.1
if ($LASTEXITCODE -ne 0) { throw 'PyTorch CPU installation failed. See the pip error above.' }

Write-Host 'Installing the experimental Python 3.14 dependency set...'
& $pythonPath -m pip install -r requirements-py314.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. See the pip error above.' }

& $pythonPath -m pip check
if ($LASTEXITCODE -ne 0) { throw 'pip check found dependency conflicts.' }

Write-Host ''
Write-Host 'Environment setup finished. Next run: .\scripts\start.ps1'
Write-Host 'This setup is experimental; run tests and smoke checks before relying on it.'
