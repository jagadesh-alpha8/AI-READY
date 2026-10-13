# Switches the AI processing mode and restarts the Celery worker in it.
#
#   powershell -ExecutionPolicy Bypass -File .\switch-ai-mode.ps1 -Mode single -With9Router
#   powershell -ExecutionPolicy Bypass -File .\switch-ai-mode.ps1 -Mode multi_router
#
# Steps:
#   1. Set AI_PROCESSING_MODE in backend\.env (the only line it edits).
#   2. Ask the running Celery worker(s) to shut down WARMLY: jobs already running
#      finish first, queued jobs stay in Redis. Only after -WaitSeconds (default
#      600) is a worker force-stopped; any job it was running then shows as
#      "running" until you Stop + Process it again.
#   3. Run start-dev.ps1: starts what the new mode needs (routers in
#      multi_router mode), one new worker, and the health check.
# Only the worker needs restarting: Django just queues jobs and is the same in both modes.

param(
    [Parameter(Mandatory = $true)][ValidateSet('single', 'multi_router')][string]$Mode,
    [int]$WaitSeconds = 600,
    [switch]$With9Router  # also start the Windows 9router on 20128 (single mode on localhost:20128)
)

$ErrorActionPreference = 'Stop'
$backend = Join-Path $PSScriptRoot 'backend'
$envFile = Join-Path $backend '.env'

# 1. Set the mode ---------------------------------------------------------------------
$lines = @(Get-Content $envFile)
if ($lines -match '^\s*AI_PROCESSING_MODE\s*=') {
    $lines = $lines -replace '^\s*AI_PROCESSING_MODE\s*=.*$', "AI_PROCESSING_MODE=$Mode"
} else {
    $lines += "AI_PROCESSING_MODE=$Mode"
}
# UTF-8 without a BOM: PowerShell 5.1's "-Encoding utf8" adds one, which would
# corrupt the first variable name when Python reads .env.
[IO.File]::WriteAllLines($envFile, [string[]]$lines, (New-Object Text.UTF8Encoding($false)))
Write-Host "[mode]  backend\.env -> AI_PROCESSING_MODE=$Mode"

# 2. Stop the old worker(s) gracefully -------------------------------------------------
function Get-Workers {
    @(Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -match 'celery.*worker' -and $_.Name -ne 'powershell.exe'
    })
}
if ((Get-Workers).Count -gt 0) {
    Write-Host '[stop]  Asking the Celery worker to finish running jobs and shut down...'
    Push-Location $backend
    $ErrorActionPreference = 'Continue'  # stderr from a native program is fatal under 'Stop' in PowerShell 5.1
    try { celery -A config control shutdown 2>$null | Out-Host } finally { Pop-Location; $ErrorActionPreference = 'Stop' }
    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    while ((Get-Workers).Count -gt 0 -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 3 }
    $left = Get-Workers
    if ($left.Count -gt 0) {
        Write-Host "[warn]  Worker still busy after $WaitSeconds s - force-stopping it. A job it was running will show"
        Write-Host '        as "running": Stop it and click Process again in the AI Processing Monitor.'
        $left | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    }
    # Close the old worker's leftover window(s)
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
        Where-Object { $_.CommandLine -match 'Celery worker' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Write-Host '[ok]    Old worker stopped'
} else {
    Write-Host '[ok]    No worker was running'
}

# 3. Start everything for the new mode ---------------------------------------------------
& (Join-Path $PSScriptRoot 'start-dev.ps1') -With9Router:$With9Router
