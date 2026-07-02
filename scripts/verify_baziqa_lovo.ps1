param(
    [string]$Source = "benchmark/datasets/baziqa_contest8_2021_2025.jsonl",
    [string]$Years = "2021,2022,2023,2024,2025",
    [int]$MaxCases = 40,
    [string]$Provider = "deepseek",
    [string]$Model = "deepseek-v4-pro",
    [string]$Output = "docs/BAZIQA_LOVO_REPORT.md"
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
    Write-Error "LOVO evaluation requires DEEPSEEK_API_KEY or ANTHROPIC_API_KEY."
    exit 2
}

$allRows = @()
foreach ($year in $Years.Split(",")) {
    $year = $year.Trim()
    if (-not $year) { continue }
    $corpus = "benchmark/datasets/baziqa_contest8_except_$year`_corpus.jsonl"
    $holdout = "benchmark/datasets/baziqa_contest8_$year`_holdout.jsonl"
    python benchmark/runners/split_baziqa_by_year.py --source $Source --holdout-year $year --corpus-out $corpus --holdout-out $holdout

    $env:BAZI_RAG_CORPUS = $corpus
    $captured = & python benchmark/runners/run_benchmark.py `
        --dataset $holdout `
        --model-runner `
        --provider $Provider `
        --model $Model `
        --max-cases $MaxCases `
        --method structured_reasoning `
        --temperature 0 `
        --rag 2>&1
    $captured | Write-Host
    $exactLine = $captured | Select-String -Pattern 'AccuracyExact:\s*(\d+)/(\d+)=(\d+(?:\.\d+)?)'
    if (-not $exactLine) { throw "Cannot parse exact accuracy for $year" }
    $idLine = $captured | Select-String -Pattern 'id=([a-f0-9]{8})'
    if ($idLine) { $rid = $idLine.Matches[0].Groups[1].Value } else { $rid = "" }
    $allRows += [pscustomobject]@{
        Year = $year
        Correct = [int]$exactLine.Matches[0].Groups[1].Value
        Total = [int]$exactLine.Matches[0].Groups[2].Value
        Accuracy = [double]$exactLine.Matches[0].Groups[3].Value
        RunId = $rid
    }
}

# Persist raw rows for downstream rendering.
$rowsJson = ".tmp/baziqa_lovo_rows.json"
$null = New-Item -ItemType Directory -Force ".tmp" -ErrorAction SilentlyContinue
$allRows | ConvertTo-Json -Depth 4 | Set-Content -Path $rowsJson -Encoding UTF8

$env:BAZIQA_LOVO_ROWS = $rowsJson
$env:BAZIQA_LOVO_OUTPUT = $Output
$env:BAZIQA_LOVO_SOURCE = $Source
$env:BAZIQA_LOVO_MAX = [string]$MaxCases
python scripts/render_baziqa_lovo_report.py

$mean = ($allRows | Measure-Object -Property Accuracy -Average).Average
$min = ($allRows | Measure-Object -Property Accuracy -Minimum).Minimum
Write-Host ("LOVO mean={0:P1}, min={1:P1}" -f $mean, $min)

if ($mean -lt 0.40) {
    Write-Error "LOVO mean accuracy below 40%."
    exit 1
}
if ($min -lt 0.30) {
    Write-Error "At least one yearly holdout is below 30%."
    exit 1
}
