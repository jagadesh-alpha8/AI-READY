# Starts the local background services extraction needs, in the right order,
# skipping anything already running:
#   0. A hidden WSL keep-alive, so WSL doesn't shut down when idle
#   1. Redis on port 6380 inside WSL (Celery's queue -- stops whenever WSL stops)
#   2. In multi_router mode: the 9routers listed in AI_ROUTER_URLS (WSL routers.sh)
#   3. The Celery worker (its own window; closing that window stops processing)
#   4. `manage.py ai_mode_status`: the active mode and endpoint / router health
# The mode is read from AI_PROCESSING_MODE in backend\.env (single | multi_router).
# To CHANGE the mode use switch-ai-mode.ps1 -- it also stops the old worker.
# Django (runserver) and the frontend (npm run dev) are started as usual.
#
# Usage, from the project folder:   powershell -ExecutionPolicy Bypass -File .\start-dev.ps1
#   -With9Router   also start the Windows 9router on port 20128 (only needed
#                  while backend\.env points AI_BASE_URL at localhost:20128)

param([switch]$With9Router)

$ErrorActionPreference = 'Stop'
$backend = Join-Path $PSScriptRoot 'backend'

function Get-EnvValue([string]$name) {
    $line = Get-Content (Join-Path $backend '.env') | Where-Object { $_ -match "^\s*$name\s*=" } | Select-Object -Last 1
    if ($line) { return ($line -split '=', 2)[1].Trim() } else { return '' }
}

function Test-Port([int]$port) {
    $client = New-Object Net.Sockets.TcpClient
    try { return $client.ConnectAsync('127.0.0.1', $port).Wait(1500) } catch { return $false } finally { $client.Close() }
}

$mode = (Get-EnvValue 'AI_PROCESSING_MODE').ToLower()
if (-not $mode) { $mode = 'single' }
if ($mode -notin @('single', 'multi_router')) {
    throw "AI_PROCESSING_MODE='$mode' in backend\.env is not valid. Use single or multi_router."
}
Write-Host "[mode]  AI_PROCESSING_MODE = $mode"

# 0. Keep WSL alive -------------------------------------------------------------
# WSL shuts itself down shortly after its last terminal closes, taking Redis
# (and the 9routers) with it -- which leaves every new job stuck at "Queued".
# One hidden, idle WSL process prevents that until you log off or run
# `wsl --shutdown`.
$keepAlive = @(Get-CimInstance Win32_Process -Filter "Name='wsl.exe'" | Where-Object { $_.CommandLine -match 'sleep infinity' })
if ($keepAlive.Count -gt 0) {
    Write-Host '[ok]    WSL keep-alive already running'
} else {
    Start-Process wsl.exe -WindowStyle Hidden -ArgumentList '-e', 'sleep', 'infinity'
    Write-Host '[start] WSL keep-alive (hidden)'
}

# 1. Redis 6380 in WSL ----------------------------------------------------------
if (Test-Port 6380) {
    Write-Host '[ok]    Redis 6380 already running'
} else {
    Write-Host '[start] Redis 6380 in WSL...'
    wsl -e sh -c 'redis-server --bind 0.0.0.0 --port 6380 --daemonize yes >/dev/null'
    $deadline = (Get-Date).AddSeconds(20)
    while (-not (Test-Port 6380) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
    if (-not (Test-Port 6380)) { throw 'Redis on port 6380 did not come up. Check WSL: wsl -e redis-server --version' }
    Write-Host '[ok]    Redis 6380 started'
}

# 2. Optional: Windows 9router on 20128 ------------------------------------------
if ($With9Router) {
    if (Test-Port 20128) {
        Write-Host '[ok]    9router 20128 already running'
    } else {
        Write-Host '[start] 9router 20128 (tray mode)...'
        Start-Process powershell -WindowStyle Minimized -ArgumentList '-NoExit', '-Command',
            "`$host.UI.RawUI.WindowTitle = '9router 20128'; 9router --tray --no-browser --skip-update"
    }
}

# 2b. multi_router: the 9routers in WSL -------------------------------------------
if ($mode -eq 'multi_router') {
    $ports = @((Get-EnvValue 'AI_ROUTER_URLS') -split ',' | ForEach-Object {
        if ($_ -match ':(\d+)') { [int]$Matches[1] } })
    $down = @($ports | Where-Object { -not (Test-Port $_) })
    if ($ports.Count -eq 0) {
        throw 'AI_PROCESSING_MODE=multi_router but AI_ROUTER_URLS has no router ports.'
    } elseif ($down.Count -eq 0) {
        Write-Host "[ok]    $($ports.Count) routers already running ($($ports -join ', '))"
    } else {
        Write-Host "[start] 9routers in WSL (down: $($down -join ', '))..."
        wsl -e bash -lc '~/9router/routers.sh start' | Out-Host
        $stillDown = @($ports | Where-Object { -not (Test-Port $_) })
        if ($stillDown.Count -gt 0) {
            Write-Host "[warn]  routers still down: $($stillDown -join ', ') -- jobs will use the others."
        }
    }
}

# 3. Celery worker ------------------------------------------------------------------
$workers = @(Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -match 'celery.*worker' -and $_.Name -ne 'powershell.exe'
})
if ($workers.Count -gt 0) {
    Write-Host "[ok]    Celery worker already running (to change mode use switch-ai-mode.ps1)"
} else {
    Write-Host "[start] Celery worker, $mode mode (new window)..."
    Start-Process powershell -WorkingDirectory $backend -ArgumentList '-NoExit', '-Command',
        "`$host.UI.RawUI.WindowTitle = 'Celery worker ($mode)'; celery -A config worker -l info"
}

# 3b. Health check --------------------------------------------------------------------
Write-Host '[check] AI processing mode:'
Push-Location $backend
# 'Continue' + -W ignore: in PowerShell 5.1 any stderr line from a native
# program (even a harmless Python warning) is fatal under 'Stop'.
$ErrorActionPreference = 'Continue'
try { python -W ignore manage.py ai_mode_status 2>$null | Out-Host } finally { Pop-Location; $ErrorActionPreference = 'Stop' }
if ($LASTEXITCODE -ne 0) { Write-Host '[warn]  Health check found a problem (see above). Jobs may fail until it is fixed.' }

# 4. Reminders for what this script doesn't start ----------------------------------
if (-not (Test-Port 8000)) { Write-Host '[todo]  Django is not running:   cd backend; python manage.py runserver' }
if (-not ((Test-Port 3000) -or (Test-Port 5173))) { Write-Host '[todo]  Frontend is not running: cd frontend; npm run dev' }
Write-Host 'Ready. Extraction jobs will be picked up as soon as the worker window shows "ready".'
