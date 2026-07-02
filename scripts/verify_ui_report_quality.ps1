param(
    [int]$Port = 8770,
    [string]$OutDir = ".tmp/ui-report-quality"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not $env:DEEPSEEK_API_KEY -and (Test-Path ".deepseek_key")) {
    $env:DEEPSEEK_API_KEY = (Get-Content ".deepseek_key" -Raw).Trim()
}
if (-not $env:ANTHROPIC_API_KEY -and (Test-Path ".anthropic_key")) {
    $env:ANTHROPIC_API_KEY = (Get-Content ".anthropic_key" -Raw).Trim()
}
if (-not $env:DEEPSEEK_API_KEY -and -not $env:ANTHROPIC_API_KEY) {
    Write-Error "UI quality check requires DEEPSEEK_API_KEY or ANTHROPIC_API_KEY."
    exit 2
}

New-Item -ItemType Directory -Force ".tmp" | Out-Null
$dbPath = Join-Path (Get-Location) ".tmp\ui-report-quality.db"
$stdout = ".tmp\ui-report-quality-uvicorn.out.log"
$stderr = ".tmp\ui-report-quality-uvicorn.err.log"
Remove-Item $dbPath -Force -ErrorAction SilentlyContinue

$env:BAZI_API_RETRIES = "0"
$env:BAZI_DB_PATH = $dbPath
$proc = Start-Process -FilePath python `
    -ArgumentList @("-m", "uvicorn", "api_server:app", "--host", "127.0.0.1", "--port", [string]$Port) `
    -WorkingDirectory (Get-Location) `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -WindowStyle Hidden `
    -PassThru

try {
    $base = "http://127.0.0.1:$Port"
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        try {
            $resp = Invoke-WebRequest -UseBasicParsing "$base/api/health" -TimeoutSec 2
            if ($resp.StatusCode -eq 200) {
                $ready = $true
                break
            }
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    if (-not $ready) {
        Write-Error "Server did not become ready. See $stderr"
        exit 3
    }

    python scripts/run_ui_report_quality.py --base-url $base --out-dir $OutDir
    if ($LASTEXITCODE -ne 0) {
        Write-Error "UI report quality check failed."
        exit $LASTEXITCODE
    }
} finally {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}
