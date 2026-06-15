# BaZi Analysis API — One-shot launcher
# Usage:
#   .\start.ps1            # default: stop existing process on port 8000, start fresh
#   .\start.ps1 -Open      # also open browser preview
#   .\start.ps1 -NoStop    # do not kill existing listener; fail if port busy
#
# Behavior:
#   1. Resolve port (default 8000)
#   2. Stop any process currently listening on that port (unless -NoStop)
#   3. Start `python api_server.py` in foreground
#   4. (Optional) Open default browser to the local URL

[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$Open,
    [switch]$NoStop
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

# Stop existing listeners on the target port
if (-not $NoStop) {
    $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listeners) {
        Write-Host "Stopping existing process(es) on port $Port..." -ForegroundColor Yellow
        $listeners | ForEach-Object {
            try {
                Stop-Process -Id $_.OwningProcess -Force -ErrorAction Stop
                Write-Host "  stopped pid=$($_.OwningProcess)"
            } catch {
                Write-Warning "  could not stop pid=$($_.OwningProcess): $_"
            }
        }
        Start-Sleep -Milliseconds 800
    }
}

# Optional: open the default browser shortly after launch
if ($Open) {
    Start-Job -ScriptBlock {
        param($url)
        Start-Sleep -Seconds 3
        Start-Process $url
    } -ArgumentList "http://localhost:$Port/" | Out-Null
}

Write-Host "Starting BaZi Analysis API on port $Port..." -ForegroundColor Green
python api_server.py
