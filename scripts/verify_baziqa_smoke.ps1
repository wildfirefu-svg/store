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
    # auto-build a tiny jsonl from contest8 sample fixture
    $sampleJson = "tests/fixtures/baziqa/contest8_sample.json"
    if (-not (Test-Path $sampleJson)) {
        Write-Error "Dataset not found and no fixture available: $Dataset"
        exit 1
    }
    python benchmark/runners/import_baziqa_dataset.py --source-dir tests/fixtures/baziqa --output $Dataset
}

if (-not $env:DEEPSEEK_API_KEY -and -not $env:ANTHROPIC_API_KEY) {
    Write-Error "Smoke aborted: please set DEEPSEEK_API_KEY or ANTHROPIC_API_KEY before running."
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
