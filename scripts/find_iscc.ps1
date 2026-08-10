# Locate ISCC.exe (Inno Setup 6 command-line compiler) for installer builds.
#
# Checks, in order:
#   1. An explicit -SearchDir override (CI installs the pinned tool there).
#   2. A repo-local pinned install (.tools\innosetup) created by
#      scripts/install_innosetup.ps1.
#   3. A per-user Inno Setup 6 install (%LOCALAPPDATA%\Programs\Inno Setup 6).
#   4. The machine-wide Inno Setup 6 locations (preinstalled on GitHub
#      windows-latest runners).
#   5. iscc.exe on PATH.
#
# Prints the ISCC.exe path and exits 0, or prints an error and exits 1.
#
# Usage:
#   $iscc = (pwsh -NoProfile -File scripts/find_iscc.ps1).Trim()

param(
    [string]$SearchDir = ""
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot

$candidates = @()
if ($SearchDir) {
    $candidates += (Join-Path $SearchDir 'ISCC.exe')
}
$candidates += (Join-Path $repoRoot '.tools\innosetup\ISCC.exe')
$candidates += (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
$candidates += 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
$candidates += 'C:\Program Files\Inno Setup 6\ISCC.exe'

foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) {
        Write-Output $candidate
        exit 0
    }
}

$fromPath = Get-Command iscc.exe -ErrorAction SilentlyContinue
if ($fromPath) {
    Write-Output $fromPath.Source
    exit 0
}

Write-Error "ISCC.exe not found. Install Inno Setup 6 first: pwsh -NoProfile -File scripts/install_innosetup.ps1"
exit 1
