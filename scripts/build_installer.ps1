# Build the Windows per-user installer from the validated onedir bundle
# (Milestone 7 Task 23).
#
# Flow:
#   1. Assert the onedir bundle + executable exist.
#   2. Content gate (M7-T23-INSTALL-005): the shared Test-ReleaseContent policy
#      must reject secrets, .env, tests, samples, design docs, workspace and
#      source maps before anything is compiled.
#   3. Locate ISCC.exe (scripts/find_iscc.ps1, or -IsccPath override).
#   4. Compile packaging/installer/PelicanTownSpecials.iss with PtsAppVersion,
#      PtsBundleDir and PtsOutputDir defines.
#   5. Gate the built setup exe: it must embed the Gus icon (32px pixel hash vs
#      the reference .ico) and carry the frozen product version identity.
#   6. Print the SHA-256 for downstream release checksumming.
#
# Run from anywhere; the script locates the repo root via $PSScriptRoot.

param(
    [string]$BundleDir = "",
    [string]$IsccPath = "",
    [string]$OutputDir = "",
    [string]$Version = "1.4.0"
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not $BundleDir) {
    $BundleDir = 'dist\PelicanTownSpecials-windows-x64'
}
if (-not $OutputDir) {
    $OutputDir = 'dist\installer'
}

$bundleFull = (Resolve-Path -LiteralPath $BundleDir -ErrorAction Stop).Path
$exePath = Join-Path $bundleFull 'PelicanTownSpecials.exe'
if (-not (Test-Path -LiteralPath $exePath)) {
    throw "Missing built executable: $exePath"
}

Write-Host "==> installer content gate (M7-T23-INSTALL-005)"
. (Join-Path $PSScriptRoot 'release_content_gate.ps1')
$violations = @(Test-ReleaseContent -Root $bundleFull)
if ($violations.Count -gt 0) {
    throw "Installer bundle contains forbidden content: $($violations -join ', ')"
}

Write-Host "==> locate ISCC.exe"
if (-not $IsccPath) {
    $IsccPath = (pwsh -NoProfile -File (Join-Path $PSScriptRoot 'find_iscc.ps1')).Trim()
}
if (-not (Test-Path -LiteralPath $IsccPath)) {
    throw "ISCC.exe not found at: $IsccPath"
}
Write-Host "ISCC: $IsccPath"

Write-Host "==> compile installer (Inno Setup)"
$outFull = Join-Path $repoRoot $OutputDir
New-Item -ItemType Directory -Force -Path $outFull | Out-Null
$issPath = Join-Path $repoRoot 'packaging\installer\PelicanTownSpecials.iss'
& $IsccPath "/DPtsAppVersion=$Version" "/DPtsBundleDir=$bundleFull" "/DPtsOutputDir=$outFull" $issPath
if ($LASTEXITCODE -ne 0) {
    throw "ISCC compile failed (exit $LASTEXITCODE)"
}

$setupExe = Join-Path $outFull "PelicanTownSpecials-Setup-v$Version.exe"
if (-not (Test-Path -LiteralPath $setupExe)) {
    throw "Missing built installer: $setupExe"
}

Write-Host "==> setup exe icon gate (Gus icon)"
$icoPath = Join-Path $repoRoot 'packaging\assets\pelican-town-specials.ico'
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

$referenceIcon = [System.Drawing.Icon]::new($icoPath, 32, 32)
$referenceHash = Get-IconHash $referenceIcon 32
$referenceIcon.Dispose()

$setupIcon = [System.Drawing.Icon]::ExtractAssociatedIcon($setupExe)
if ($null -eq $setupIcon) {
    throw "Could not extract an icon from $setupExe"
}
$setupHash = Get-IconHash $setupIcon 32
$setupIcon.Dispose()

Write-Host "reference 32px hash: $referenceHash"
Write-Host "setup 32px hash:     $setupHash"
if ($setupHash -ne $referenceHash) {
    throw "Installer icon does not match the Gus portrait reference"
}

Write-Host "==> setup exe version identity"
$info = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($setupExe)
Write-Host "ProductName:   $($info.ProductName)"
Write-Host "ProductVersion:$($info.ProductVersion)"
# Inno Setup pads version-resource strings to a fixed width; trim before comparing.
if ($info.ProductName.Trim() -ne 'Pelican Town Specials') {
    throw "Unexpected ProductName in installer: $($info.ProductName)"
}

Write-Host "==> checksum"
$sha256 = (Get-FileHash -LiteralPath $setupExe -Algorithm SHA256).Hash
Write-Host "SHA-256: $sha256"

Write-Host "OK: installer built at $setupExe"
