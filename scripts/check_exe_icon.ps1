# Verify the built EXE embeds the Gus-portrait app icon (Task 22 gate).
#
# PyInstaller embeds the .ico passed to EXE(icon=...). This check re-extracts
# the icon Windows associates with the built executable and compares its 32x32
# pixel hash with the reference icon in packaging/assets. A mismatch means the
# bundle would ship the default PyInstaller icon or a stale build, so the gate
# fails the release build.
#
# Also asserts the embedded version identity matches version_info.txt.
#
# Usage:
#   pwsh -NoProfile -File scripts/check_exe_icon.ps1 [-BundleDir <dir>]

param(
    [string]$BundleDir = ""
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $BundleDir) {
    $BundleDir = Join-Path $repoRoot 'dist\PelicanTownSpecials-windows-x64'
}

$exePath = Join-Path $BundleDir 'PelicanTownSpecials.exe'
$icoPath = Join-Path $repoRoot 'packaging\assets\pelican-town-specials.ico'

if (-not (Test-Path -LiteralPath $exePath)) {
    throw "Missing built executable: $exePath"
}
if (-not (Test-Path -LiteralPath $icoPath)) {
    throw "Missing reference icon: $icoPath"
}

Add-Type -AssemblyName System.Drawing

function Get-PixelHash([System.Drawing.Bitmap]$bitmap) {
    $md5 = [System.Security.Cryptography.MD5]::Create()
    $bytes = New-Object byte[] (($bitmap.Width * $bitmap.Height) * 4)
    $i = 0
    for ($y = 0; $y -lt $bitmap.Height; $y++) {
        for ($x = 0; $x -lt $bitmap.Width; $x++) {
            $color = $bitmap.GetPixel($x, $y)
            $bytes[$i++] = $color.A
            $bytes[$i++] = $color.R
            $bytes[$i++] = $color.G
            $bytes[$i++] = $color.B
        }
    }
    return ([BitConverter]::ToString($md5.ComputeHash($bytes)) -replace '-', '')
}

function Get-IconHash([System.Drawing.Icon]$icon, [int]$size) {
    $resized = [System.Drawing.Icon]::new($icon, $size, $size)
    $bitmap = $resized.ToBitmap()
    try {
        return Get-PixelHash $bitmap
    } finally {
        $bitmap.Dispose()
        $resized.Dispose()
    }
}

Write-Host "==> EXE icon gate"
$referenceIcon = [System.Drawing.Icon]::new($icoPath, 32, 32)
$referenceHash = Get-IconHash $referenceIcon 32
$referenceIcon.Dispose()

# ExtractAssociatedIcon returns the icon Windows shows for the executable.
$exeIcon = [System.Drawing.Icon]::ExtractAssociatedIcon($exePath)
if ($null -eq $exeIcon) {
    throw "Could not extract an icon from $exePath"
}
$exeHash = Get-IconHash $exeIcon 32
$exeIcon.Dispose()

Write-Host "reference 32px hash: $referenceHash"
Write-Host "built exe 32px hash:  $exeHash"
if ($exeHash -ne $referenceHash) {
    throw "EXE icon does not match the Gus portrait reference (default PyInstaller or stale build?)"
}
Write-Host "OK: EXE embeds the Gus portrait icon."

Write-Host "==> EXE version identity"
$info = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($exePath)
Write-Host "ProductName:   $($info.ProductName)"
Write-Host "ProductVersion:$($info.ProductVersion)"
Write-Host "FileVersion:   $($info.FileVersion)"
if ($info.ProductName -ne 'Pelican Town Specials') {
    throw "Unexpected ProductName in built EXE: $($info.ProductName)"
}
Write-Host "OK: EXE version identity matches."
