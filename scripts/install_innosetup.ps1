# Install Inno Setup 6 at a pinned version, per-user, without administrator
# rights. Used by both local development and the Windows CI runner so the
# installer compiler version is reproducible (M7-T23-INSTALL-001).
#
# The installer is downloaded from the official GitHub release URL, its SHA-256
# verified, then run with /CURRENTUSER into InstallDir. A timeout converts any
# unexpected elevation prompt into a loud failure instead of a silent hang.
#
# Usage:
#   pwsh -NoProfile -File scripts/install_innosetup.ps1 [-InstallDir <dir>] [-Version 6.7.3]

param(
    [string]$InstallDir = "",
    [string]$Version = "6.7.3"
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $InstallDir) {
    $InstallDir = Join-Path $repoRoot '.tools\innosetup'
}

# Verified against the winget-pkgs manifest for JRSoftware.InnoSetup 6.7.3
# (InstallerSha256) and the local download.
$expectedHash = '9c73c3bae7ed48d44112a0f48e66742c00090bdb5bef71d9d3c056c66e97b732'
$slug = ($Version -replace '\.', '_')
$url = "https://github.com/jrsoftware/issrc/releases/download/is-$slug/innosetup-$Version.exe"

$iscc = Join-Path $InstallDir 'ISCC.exe'
if (Test-Path -LiteralPath $iscc) {
    Write-Host "OK: Inno Setup already installed at $InstallDir"
    exit 0
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

$installer = Join-Path $env:TEMP "innosetup-$Version.exe"
if (-not (Test-Path -LiteralPath $installer)) {
    Write-Host "Downloading $url"
    Invoke-WebRequest -Uri $url -OutFile $installer
}
$actualHash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash
if ($actualHash.ToLower() -ne $expectedHash) {
    throw "Inno Setup installer hash mismatch: got $actualHash expected $expectedHash"
}

$args = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/CURRENTUSER', '/NORESTART', "/DIR=$InstallDir")
Write-Host "Installing Inno Setup $Version per-user into $InstallDir"
$process = Start-Process -FilePath $installer -ArgumentList $args -PassThru
if (-not $process.WaitForExit(240000)) {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    throw "Inno Setup installer timed out after 240s (elevation prompt?)"
}
if ($process.ExitCode -ne 0) {
    throw "Inno Setup installer failed with exit code $($process.ExitCode)"
}
if (-not (Test-Path -LiteralPath $iscc)) {
    throw "ISCC.exe missing after install at $InstallDir"
}
Write-Host "OK: Inno Setup $Version installed at $InstallDir"
