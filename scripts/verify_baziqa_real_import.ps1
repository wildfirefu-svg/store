param(
    [Parameter(Mandatory=$true)]
    [string]$SourceDir,
    [string]$Output = "benchmark/datasets/baziqa_contest8_2021_2025.jsonl",
    [int]$ExpectedQuestions = 200,
    [int]$ExpectedYears = 5
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

python benchmark/runners/import_baziqa_dataset.py --source-dir $SourceDir --output $Output --include-celebrity

if (-not (Test-Path $Output)) {
    Write-Error "Import failed: $Output not found"
    exit 1
}

$lines = Get-Content $Output -Encoding UTF8
$count = $lines.Count
Write-Host "Imported rows: $count"

if ($count -lt 100) {
    Write-Error "Imported rows look too small (<100). Aborting."
    exit 2
}

$years = New-Object 'System.Collections.Generic.HashSet[string]'
foreach ($line in $lines | Select-Object -First 200) {
    $obj = $line | ConvertFrom-Json
    if ($obj.source_year) {
        $null = $years.Add([string]$obj.source_year)
    }
}
Write-Host ("Distinct years sampled: {0}" -f ($years -join ', '))

if ($years.Count -lt 1) {
    Write-Error "No source_year detected in imported rows."
    exit 3
}

Write-Host "Real BaziQA import passed."
