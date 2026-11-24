<#
.SYNOPSIS
  Start or stop the whole dev stack: the API (8000), the worker placeholder and the frontend (5173).

.DESCRIPTION
  Default: warns and exits if the ports are busy, runs `uv run gtm db upgrade` once that command exists
  (S05), opens one window each for gtm-api, gtm-worker and gtm-web, waits until they answer, and prints
  the URLs.
  -Stop: stops the windows this script opened, plus whatever still listens on 8000 or 5173 (with its
  child processes).

  Keep the ports in step with frontend/vite.config.ts and frontend/playwright.config.ts.

.EXAMPLE
  powershell -File scripts/dev.ps1
  powershell -File scripts/dev.ps1 -Stop
#>
[CmdletBinding()]
param(
    [switch]$Stop
)

$Root = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $Root 'backend'
$FrontendDir = Join-Path $Root 'frontend'
$PidFile = Join-Path $Root 'storage\dev-pids.json'   # storage/ is git-ignored runtime data
$ApiPort = 8000
$WebPort = 5173

function Get-ListenerPids([int]$Port) {
    $connections = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    if (-not $connections) { return @() }
    return @($connections | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -gt 4 })
}

# Children first, so a parent that respawns its children (a reloader) can't outlive them.
function Stop-ProcessTree([int]$ProcessId) {
    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue
    foreach ($child in $children) { Stop-ProcessTree $child.ProcessId }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function Stop-DevStack {
    $stopped = 0

    # 1. The windows this script opened. The recorded start time guards against a reused PID.
    if (Test-Path $PidFile) {
        # Windows PowerShell 5.1 returns a JSON array as ONE object. Piping it unrolls it (PowerShell 7 too).
        $recorded = Get-Content $PidFile -Raw | ConvertFrom-Json
        foreach ($entry in @($recorded | ForEach-Object { $_ })) {
            $process = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
            if ($process -and $process.StartTime.ToString('o') -eq $entry.started) {
                Write-Host "Stopping $($entry.name) (pid $($entry.pid))"
                Stop-ProcessTree $entry.pid
                $stopped++
            }
        }
        Remove-Item $PidFile -Force
    }

    # 2. Anything still listening on the dev ports (started by hand, or orphaned).
    foreach ($port in @($ApiPort, $WebPort)) {
        foreach ($listenerPid in (Get-ListenerPids $port)) {
            $name = (Get-Process -Id $listenerPid -ErrorAction SilentlyContinue).ProcessName
            Write-Host "Stopping $name (pid $listenerPid), which listens on port $port"
            Stop-ProcessTree $listenerPid
            $stopped++
        }
    }

    if ($stopped -eq 0) { Write-Host 'Nothing was running.' } else { Write-Host 'Stopped.' }
}

# `uv` is installed with `py -m pip install --user uv`, and its Scripts folder may not be on PATH.
function Add-UvToPath {
    if (Get-Command uv -ErrorAction SilentlyContinue) { return $true }
    $scripts = Get-ChildItem (Join-Path $env:APPDATA 'Python\Python3*\Scripts\uv.exe') -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1
    if (-not $scripts) { return $false }
    $env:Path = "$($scripts.DirectoryName);$env:Path"   # child windows inherit it
    return $true
}

function Start-DevWindow([string]$Name, [string]$WorkDir, [string]$Command) {
    # -EncodedCommand sidesteps quoting: Start-Process does not quote array arguments on Windows PowerShell.
    $script = "`$Host.UI.RawUI.WindowTitle = '$Name'; $Command"
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($script))
    $process = Start-Process -FilePath 'powershell.exe' -WorkingDirectory $WorkDir -PassThru `
        -ArgumentList @('-NoExit', '-NoProfile', '-EncodedCommand', $encoded)
    Write-Host "Started $Name (pid $($process.Id))"
    return [pscustomobject]@{ name = $Name; pid = $process.Id; started = $process.StartTime.ToString('o') }
}

function Wait-ForUrl([string]$Url, [int]$TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) { return $true }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

if ($Stop) {
    Stop-DevStack
    exit 0
}

# --- start -----------------------------------------------------------------------------------------
$busy = @()
foreach ($port in @($ApiPort, $WebPort)) {
    foreach ($listenerPid in (Get-ListenerPids $port)) {
        $name = (Get-Process -Id $listenerPid -ErrorAction SilentlyContinue).ProcessName
        $busy += "port $port is in use by $name (pid $listenerPid)"
    }
}
if ($busy.Count -gt 0) {
    $busy | ForEach-Object { Write-Warning $_ }
    Write-Warning 'Not starting. Run `powershell -File scripts/dev.ps1 -Stop` first.'
    exit 1
}

if (-not (Add-UvToPath)) {
    Write-Error 'uv was not found. Install it with `py -m pip install --user uv` (see README.md).'
    exit 1
}

# `gtm db upgrade` arrives in S05. Until the command exists there is nothing to migrate.
Push-Location $BackendDir
try {
    & uv run gtm db upgrade --help *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Upgrading the database...'
        & uv run gtm db upgrade
        if ($LASTEXITCODE -ne 0) {
            Write-Error 'gtm db upgrade failed. Nothing was started.'
            exit 1
        }
    }
} finally {
    Pop-Location
}

$windows = @(
    Start-DevWindow 'gtm-api' $BackendDir "uv run uvicorn gtm_studio.api.app:create_app --factory --reload --port $ApiPort"
    Start-DevWindow 'gtm-worker' $BackendDir 'uv run gtm worker'
    Start-DevWindow 'gtm-web' $FrontendDir 'npm run dev'
)
New-Item -ItemType Directory -Force -Path (Split-Path $PidFile) | Out-Null
ConvertTo-Json -InputObject $windows | Set-Content -Path $PidFile -Encoding ASCII

Write-Host 'Waiting for the API and the frontend (the first start can take a while)...'
$apiUp = Wait-ForUrl "http://127.0.0.1:$ApiPort/api/health" 90
# Through the Vite proxy, so this also proves the frontend can reach the API.
$webUp = Wait-ForUrl "http://localhost:$WebPort/api/health" 30

Write-Host ''
Write-Host "  Web       http://localhost:$WebPort"
Write-Host "  API       http://127.0.0.1:$ApiPort/api/health"
Write-Host "  API docs  http://localhost:$WebPort/api/docs"
Write-Host '  Stop      powershell -File scripts/dev.ps1 -Stop'
if (-not ($apiUp -and $webUp)) {
    Write-Warning 'Not everything answered in time. Check the gtm-api and gtm-web windows.'
    exit 1
}
