# Milestone 7 Task 24: version-drift gate.
#
# The requested release version (from a v* tag or manual dispatch, without the
# leading v) must match the frozen FileVersion in packaging/pyinstaller/version_info.txt.
# If they drift, the pipeline fails loudly instead of publishing a mislabeled
# artifact; bump version_info.txt before tagging a new release.
#
# Run from anywhere; the script locates the repo root via $PSScriptRoot.
#   pwsh -NoProfile -File scripts/check_release_version.ps1 -Version 1.0.0

param(
    [string]$Version = ""
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$versionInfo = Join-Path $repoRoot 'packaging\pyinstaller\version_info.txt'

if (-not $Version.Trim()) {
    throw "Missing -Version parameter (release version without a leading v)."
}
$normalized = $Version.Trim().TrimStart('v')

$text = Get-Content -LiteralPath $versionInfo -Raw -ErrorAction Stop
if ($text -notmatch "StringStruct\('FileVersion', '([^']+)'\)") {
    throw "version_info.txt must declare a FileVersion; cannot run the drift gate."
}
$frozen = $Matches[1]

if ($normalized -ne $frozen) {
    throw "Release version '$($Version.Trim())' (normalized '$normalized') does not match " +
        "version_info.txt FileVersion '$frozen'. Bump packaging/pyinstaller/version_info.txt " +
        "first (version drift gate)."
}

Write-Host "OK: release version $normalized matches version_info.txt ($frozen)."
