param(
    [string]$Holdout = "benchmark/datasets/baziqa_contest8_2025_holdout.jsonl",
    [int]$MaxCases = 40,
    [string]$Provider = "deepseek",
    [string]$Model = "deepseek-v4-pro",
    [string]$Output = "docs/BAZIQA_RAG_REPORT.md",
    [string]$RagCorpus = ""
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
    Write-Error "RAG lift evaluation requires DEEPSEEK_API_KEY or ANTHROPIC_API_KEY."
    exit 2
}

if (-not (Test-Path $Holdout)) {
    Write-Error "Holdout dataset not found: $Holdout"
    exit 3
}

$resultsJson = ".tmp/baziqa_rag_lift_results.json"
$null = New-Item -ItemType Directory -Force ".tmp" -ErrorAction SilentlyContinue

function Invoke-Bench {
    param([string]$Label, [bool]$Rag, [string]$Method)
    Write-Host "=== Running $Label / $Method / rag=$Rag ==="
    $argsList = @(
        "benchmark/runners/run_benchmark.py",
        "--dataset", $Holdout,
        "--model-runner",
        "--provider", $Provider,
        "--model", $Model,
        "--max-cases", [string]$MaxCases,
        "--method", $Method
    )
    if ($Rag) { $argsList += "--rag" }
    if ($Rag -and $RagCorpus) { $argsList += @("--rag-corpus", $RagCorpus) }
    $captured = & python @argsList 2>&1
    $captured | Write-Host
    $exactLine = $captured | Select-String -Pattern 'AccuracyExact:\s*(\d+)/(\d+)=(\d+(?:\.\d+)?)'
    if (-not $exactLine) {
        throw "Cannot parse exact accuracy for $Label"
    }
    $correct = [int]$exactLine.Matches[0].Groups[1].Value
    $total = [int]$exactLine.Matches[0].Groups[2].Value
    $acc = [double]$exactLine.Matches[0].Groups[3].Value
    $idLine = $captured | Select-String -Pattern 'id=([a-f0-9]{8})'
    if ($idLine) { $rid = $idLine.Matches[0].Groups[1].Value } else { $rid = '?' }
    return [pscustomobject]@{ Label = $Label; Method = $Method; Rag = $Rag; Accuracy = $acc; Correct = $correct; Total = $total; RunId = $rid }
}

$results = @()
$results += Invoke-Bench -Label "baseline-direct" -Rag $false -Method "direct_choice"
$results += Invoke-Bench -Label "rag-direct"      -Rag $true  -Method "direct_choice"
$results += Invoke-Bench -Label "rag-structured"  -Rag $true  -Method "structured_reasoning"

$results | ConvertTo-Json -Depth 4 | Set-Content -Path $resultsJson -Encoding UTF8

$baseline = ($results | Where-Object { $_.Label -eq "baseline-direct" } | Select-Object -First 1).Accuracy
$ragDirect = ($results | Where-Object { $_.Label -eq "rag-direct" } | Select-Object -First 1).Accuracy
$ragStructured = ($results | Where-Object { $_.Label -eq "rag-structured" } | Select-Object -First 1).Accuracy
$threshold = $baseline + 0.08
$pass = ($ragDirect -ge $threshold) -and ($ragStructured -ge $threshold)
if ($pass) { $status = 'PASS' } else { $status = 'BLOCKED' }

# Build the markdown via Python helper to avoid PowerShell parser pitfalls with pipe characters.
$env:BAZIQA_RAG_LIFT_RESULTS = $resultsJson
$env:BAZIQA_RAG_LIFT_OUTPUT = $Output
$env:BAZIQA_RAG_LIFT_HOLDOUT = $Holdout
$env:BAZIQA_RAG_LIFT_PROVIDER = $Provider
$env:BAZIQA_RAG_LIFT_MODEL = $Model
$env:BAZIQA_RAG_LIFT_MAX = [string]$MaxCases
$env:BAZIQA_RAG_LIFT_STATUS = $status
python scripts/render_baziqa_rag_report.py
Write-Host "RAG lift report written to $Output"
if ($pass) { exit 0 } else { exit 1 }
