<#
.SYNOPSIS
    Build spektralionkk: the one-folder app (PyInstaller) and the Windows installer (Inno Setup 6).

.DESCRIPTION
    Needs a Python 3.13 (64-bit) virtual environment with requirements.txt and requirements-build.txt
    installed (see README.md), and Inno Setup 6 for the installer step.

      dist\spektralionkk\                    the app (spektralionkk.exe + its files)
      release\spektralionkk-<ver>-setup.exe  the installer

.EXAMPLE
    .\build.ps1
.EXAMPLE
    .\build.ps1 -Python C:\envs\sprk\Scripts\python.exe -RepoUrl https://github.com/you/spektralionkk
#>
param(
    [string]$Python = ".venv\Scripts\python.exe",
    [string]$ISCC = "",
    [string]$RepoUrl = ""
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Invoke-Native([scriptblock]$Command) {
    # Tools such as PyInstaller log to stderr; judge them by their exit code, not by stderr output.
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $Command } finally { $ErrorActionPreference = $old }
}

if (-not (Test-Path $Python)) { throw "Python not found at $Python - create the venv first (see README.md)." }
$sf = Invoke-Native { & $Python -c "import os, spektrafilm; print(os.path.dirname(spektrafilm.__file__))" }
if ($LASTEXITCODE) { throw "spektrafilm is not installed in this environment (pip install -r requirements.txt)." }

# Stale numba caches from development runs must not be bundled: the app compiles its own on first start.
Get-ChildItem app, $sf -Recurse -Include *.nbi, *.nbc -ErrorAction SilentlyContinue | Remove-Item -Force

Write-Host "Building the app with PyInstaller..."
Invoke-Native { & $Python -m PyInstaller app\spektralionkk_app.spec --noconfirm --distpath dist --workpath build }
if ($LASTEXITCODE) { throw "PyInstaller failed." }

# Licences and notes shipped next to the exe (the installer shows LICENSE).
Copy-Item LICENSE, THIRD_PARTY_NOTICES.md, app\README-spektralionkk.txt dist\spektralionkk\ -Force
Copy-Item (Join-Path $sf "data\license\SPEKTRAFILM_LICENSE.txt") dist\spektralionkk\ -Force

if (-not $ISCC) {
    foreach ($c in "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
                   "$env:ProgramFiles\Inno Setup 6\ISCC.exe") {
        if (Test-Path $c) { $ISCC = $c; break }
    }
}
if (-not $ISCC) {
    Write-Warning "Inno Setup 6 not found: the app is in dist\spektralionkk, the installer step was skipped."
    return
}
Write-Host "Building the installer with Inno Setup..."
$isccArgs = @("/Q")
if ($RepoUrl) { $isccArgs += "/DAppURL=$RepoUrl" }
Invoke-Native { & $ISCC @isccArgs installer\spektralionkk.iss }
if ($LASTEXITCODE) { throw "Inno Setup failed." }
Get-ChildItem release\*.exe | ForEach-Object { "{0}  {1:N1} MB" -f $_.FullName, ($_.Length / 1MB) }
