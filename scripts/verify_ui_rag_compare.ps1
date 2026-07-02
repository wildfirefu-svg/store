param(
    [int]$Port = 8775,
    [string]$OutDir = ".tmp/ui-rag-compare"
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
Set-Location $PSScriptRoot\..

if (-not $env:DEEPSEEK_API_KEY -and (Test-Path ".deepseek_key")) {
    $env:DEEPSEEK_API_KEY = (Get-Content ".deepseek_key" -Raw).Trim()
}
if (-not $env:ANTHROPIC_API_KEY -and (Test-Path ".anthropic_key")) {
    $env:ANTHROPIC_API_KEY = (Get-Content ".anthropic_key" -Raw).Trim()
}
if (-not $env:DEEPSEEK_API_KEY -and -not $env:ANTHROPIC_API_KEY) {
    Write-Error "需要 DEEPSEEK_API_KEY 或 ANTHROPIC_API_KEY"
    exit 2
}

New-Item -ItemType Directory -Force ".tmp" | Out-Null
New-Item -ItemType Directory -Force $OutDir | Out-Null

function Run-Variant {
    param([string]$Tag, [string]$RagFlag)

    $dbPath = Join-Path (Get-Location) ".tmp/ui-rag-compare-$Tag.db"
    Remove-Item $dbPath -Force -ErrorAction SilentlyContinue

    $stdout = ".tmp/ui-rag-compare-$Tag.out.log"
    $stderr = ".tmp/ui-rag-compare-$Tag.err.log"
    $env:BAZI_API_RETRIES = "0"
    $env:BAZI_DB_PATH = $dbPath
    $env:BAZI_RAG = $RagFlag

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
                if ($resp.StatusCode -eq 200) { $ready = $true; break }
            } catch {
                Start-Sleep -Seconds 1
            }
        }
        if (-not $ready) { throw "Server $Tag did not become ready" }

        $variantDir = Join-Path $OutDir $Tag
        New-Item -ItemType Directory -Force $variantDir | Out-Null
        python scripts/run_ui_report_quality.py --base-url $base --out-dir $variantDir
    } finally {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
}

Run-Variant -Tag "baseline" -RagFlag "0"
Run-Variant -Tag "rag" -RagFlag "1"

python scripts/render_ui_rag_compare.py
