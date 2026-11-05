<#
.SYNOPSIS
    Run all spektralionkk test suites (headless) and print a summary.

.DESCRIPTION
    test_engine runs first: it writes app\tests\out\test_input.jpg, which the other suites use.
    test_rawformats needs sample RAW files in rawsamples\<format>\ (or in $env:SPRK_RAWSAMPLES) and is
    skipped without them. test_raw runs only when -RawFile points to one of your own RAW photos.

.EXAMPLE
    .\scripts\run_tests.ps1
.EXAMPLE
    .\scripts\run_tests.ps1 -RawFile D:\photos\DSC01234.ARW
#>
param(
    [string]$Python = ".venv\Scripts\python.exe",
    [string]$RawFile = ""
)
$ErrorActionPreference = "Continue"
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path $Python)) { throw "Python not found at $Python" }
$env:SPRK_LANG = "en"          # the suites check English texts (test_i18n switches to Chinese itself)
$tests = "test_engine", "test_fastprint", "test_features", "test_live", "test_controls", "test_ui", "test_ui_live",
         "test_i18n", "test_platform", "test_rawformats"
if ($RawFile) { $tests += "test_raw" }
$results = @()
foreach ($t in $tests) {
    if ($t -like "test_ui*" -or $t -in "test_controls", "test_i18n", "test_platform") { $env:QT_QPA_PLATFORM = "offscreen" }
    else { Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue }
    $a = @("-I", "-X", "utf8", "-W", "ignore", "app\tests\$t.py")
    if ($t -eq "test_raw") { $a += $RawFile }
    $sw = [Diagnostics.Stopwatch]::StartNew()
    & $Python @a 2>&1 | ForEach-Object { "$_" } | Where-Object { $_ -match "^(FAIL|SKIP)|Traceback|Error" } |
        ForEach-Object { Write-Host "    $_" }
    $code = $LASTEXITCODE
    $results += "{0,-16} {1,-6} {2,5} s" -f $t, ($(if ($code -eq 0) { "PASS" } else { "FAIL" })), [int]$sw.Elapsed.TotalSeconds
    Write-Host $results[-1]
}
Write-Host ""
$results
if ($results -match "FAIL") { exit 1 }
