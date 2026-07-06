# Phase 3 Full Experiment Pipeline
# Run from project root: f:/project/agent
# Usage: pwsh -File scripts/run_phase3_all.ps1
#
# This script runs all 4 stages sequentially:
#   Step 1: link8  (18 cmds)
#   Step 2: dev20  (36 cmds)
#   Step 3: MingLi20 (18 cmds)
#   Step 4: formal40 (18 cmds)
#
# Each stage uses: python scripts/run_phase3_ablation.py --stage <S> --execute
# The --execute flag runs commands via subprocess directly (NO shell quoting issues)

$ErrorActionPreference = "Continue"
$projectRoot = "f:/project/agent"
Set-Location $projectRoot

$stages = @("link8", "dev20", "MingLi20", "formal40")
$globalSuccess = 0
$globalFailures = 0
$totalStart = [System.Diagnostics.Stopwatch]::StartNew()

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Phase 3 Full Experiment Pipeline" -ForegroundColor Cyan
Write-Host "  Started at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

foreach ($stage in $stages) {
    Write-Host ">>> STAGE: $stage <<<" -ForegroundColor Yellow
    $stageStart = [System.Diagnostics.Stopwatch]::StartNew()

    $exitCode = 0
    $output = & python scripts/run_phase3_ablation.py --stage $stage --execute 2>&1
    $exitCode = $LASTEXITCODE

    # Print output
    foreach ($line in $output) {
        Write-Host $line
    }

    $elapsed = [math]::Round($stageStart.Elapsed.TotalSeconds, 0)

    if ($exitCode -eq 0) {
        Write-Host ">>> $stage DONE: ALL OK (${elapsed}s) <<<" -ForegroundColor Green
        $globalSuccess++
    } else {
        Write-Host ">>> $stage DONE: FAILURES (rc=$exitCode, ${elapsed}s) <<<" -ForegroundColor Red
        $globalFailures++
    }
    Write-Host ""
}

$totalElapsed = [math]::Round($totalStart.Elapsed.TotalSeconds, 0)
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Pipeline Complete: $globalSuccess/$($stages.Count) stages OK" -ForegroundColor Cyan
Write-Host "  Total time: ${totalElapsed}s" -ForegroundColor Cyan
Write-Host "  Output dir: .tmp/phase3_ablation/" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

if ($globalFailures -gt 0) {
    exit 2
}
exit 0
