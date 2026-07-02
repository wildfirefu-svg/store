param(
    [string]$Dataset = "tests/fixtures/baziqa/contest8_sample.jsonl",
    [int]$MaxCases = 3,
    [string]$Provider = "deepseek",
    [string]$Model = "",
    [string]$Method = "direct_choice",
    [string]$Output = "benchmark/outputs"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not (Test-Path $Dataset)) {
    $sampleJson = "tests/fixtures/baziqa/contest8_sample.json"
    if (-not (Test-Path $sampleJson)) {
        Write-Error "Dataset not found and no fixture available: $Dataset"
        exit 1
    }

    $tmpSource = ".tmp/baziqa_smoke_source"
    New-Item -ItemType Directory -Force $tmpSource | Out-Null
    Copy-Item $sampleJson "$tmpSource/contest8_2025.json" -Force
    python benchmark/runners/import_baziqa_dataset.py --source-dir $tmpSource --output $Dataset

    $lineCount = (Get-Content $Dataset -Encoding UTF8 | Measure-Object -Line).Lines
    if ($lineCount -lt 1) {
        Write-Error "Smoke dataset generation produced 0 rows: $Dataset"
        exit 3
    }
}

if (-not $env:DEEPSEEK_API_KEY -and (Test-Path ".deepseek_key")) {
    $env:DEEPSEEK_API_KEY = (Get-Content ".deepseek_key" -Raw).Trim()
}
if (-not $env:ANTHROPIC_API_KEY -and (Test-Path ".anthropic_key")) {
    $env:ANTHROPIC_API_KEY = (Get-Content ".anthropic_key" -Raw).Trim()
}
if (-not $env:DEEPSEEK_API_KEY -and -not $env:ANTHROPIC_API_KEY) {
    Write-Error "Smoke aborted: please set DEEPSEEK_API_KEY or ANTHROPIC_API_KEY before running, or place .deepseek_key/.anthropic_key in the project root."
    exit 2
}

$args = @(
    "benchmark/runners/run_benchmark.py",
    "--dataset", $Dataset,
    "--model-runner",
    "--provider", $Provider,
    "--method", $Method,
    "--max-cases", $MaxCases,
    "--output-dir", $Output
)
if ($Model) { $args += @("--model", $Model) }

python @args
if ($LASTEXITCODE -ne 0) {
    Write-Error "Real-model smoke failed (exit $LASTEXITCODE)."
    exit $LASTEXITCODE
}

Write-Host "Real-model smoke run finished. Latest report saved under $Output."
