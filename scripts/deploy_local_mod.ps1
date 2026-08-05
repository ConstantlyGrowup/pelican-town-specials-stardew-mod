# Deploy a validated Pelican Town Specials export ZIP into a Stardew Valley
# Mods directory with recovery and safety guards (Task 18).
#
# Flow:
#   1. Validate the ZIP with scripts/validate_mod_zip.py first (fail fast;
#      nothing is written before validation passes).
#   2. Resolve the Mods root and the pack target with Resolve-Path /
#      GetFullPath and refuse any target outside the Mods root.
#   3. Default refuses to overwrite an existing pack. With -Replace the old
#      pack directory is moved (never recursively deleted) to
#      <ModsRoot>/_pts_backup/<yyyyMMdd_HHmmss>/.
#   4. With -WhatIf only the resolved pack target and (when applicable) the
#      backup target are printed; no directory is written.
#   5. Otherwise the ZIP is expanded into a temporary staging directory and the
#      extracted content pack root is moved into place (atomic-ish).
#
# Run from anywhere; the script locates itself and the validator via $PSScriptRoot.

param(
    [Parameter(Mandatory = $true)]
    [string]$PackZip,
    [Parameter(Mandatory = $true)]
    [string]$ModsDir,
    [switch]$Replace,
    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'

$validator = Join-Path $PSScriptRoot 'validate_mod_zip.py'

# 1. Resolve the pack ZIP and validate it before touching the Mods directory.
$packZipFull = (Resolve-Path -LiteralPath $PackZip -ErrorAction Stop).Path
$rootName = (& python $validator --zip $packZipFull --print-root | Out-String).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "ZIP validation failed for '$packZipFull'."
}
if (-not $rootName) {
    throw "ZIP validation returned no content pack root folder for '$packZipFull'."
}

# 2. Resolve the Mods root and the pack target, and enforce containment.
$modsRootFull = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $ModsDir -ErrorAction Stop).Path)
$packTarget = [System.IO.Path]::GetFullPath((Join-Path $modsRootFull $rootName))
$modsRootPrefix = $modsRootFull.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
if (-not $packTarget.StartsWith($modsRootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to deploy: target '$packTarget' is outside the Mods root '$modsRootFull'."
}

# 3. Default refuses to overwrite an existing pack.
$targetExists = Test-Path -LiteralPath $packTarget
if ($targetExists -and -not $Replace) {
    throw "Refusing to overwrite existing pack '$packTarget'. Pass -Replace to back it up and deploy."
}

# 4. Compute the backup target when replacing.
$backupTarget = $null
if ($targetExists -and $Replace) {
    $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $backupRoot = Join-Path $modsRootFull (Join-Path '_pts_backup' $timestamp)
    $backupTarget = Join-Path $backupRoot $rootName
}

# 5. WhatIf: print resolved targets and stop without writing anything.
if ($WhatIf) {
    Write-Output "WhatIf: pack target: $packTarget"
    if ($backupTarget) {
        Write-Output "WhatIf: backup target: $backupTarget"
    }
    return
}

# 6. Move the old pack to the backup location (whole directory, no recursive delete).
if ($backupTarget) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $backupTarget) -Force | Out-Null
    Move-Item -LiteralPath $packTarget -Destination $backupTarget
}

# 7. Expand into a temporary staging directory, then move the content pack root
#    into place. The ZIP was validated above, so Expand-Archive only ever sees
#    safe, single-root archives.
$staging = Join-Path ([System.IO.Path]::GetTempPath()) ("pts-deploy-" + [guid]::NewGuid().ToString('N'))
try {
    New-Item -ItemType Directory -Path $staging -Force | Out-Null
    Expand-Archive -LiteralPath $packZipFull -DestinationPath $staging -Force
    $extractedRoot = Join-Path $staging $rootName
    if (-not (Test-Path -LiteralPath $extractedRoot)) {
        throw "Staged pack root not found: $extractedRoot"
    }
    Move-Item -LiteralPath $extractedRoot -Destination $packTarget
}
finally {
    if (Test-Path -LiteralPath $staging) {
        Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Output "Deployed pack to: $packTarget"
