# Verifies that local design/planning documents are ignored by git.
# Run from anywhere; the script locates the repo root via $PSScriptRoot.
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

# Directory entries carry a trailing slash so `git check-ignore` treats them as
# directories even when the path is absent from the working tree (e.g. a fresh CI
# checkout that never materialises these ignored design sources). Without the
# slash, the `/<dir>/` ignore pattern cannot match a non-existent path and the
# gate would fail on CI only. The file entry keeps no slash.
$paths = @(
    'design docs/',
    '最初设计功能清点/',
    'docs/architecture/',
    'docs/plans/',
    'StarValleyCook_项目设计源索引与状态快照.md'
)

$notIgnored = @()
foreach ($path in $paths) {
    git check-ignore --quiet -- $path
    if ($LASTEXITCODE -ne 0) {
        $notIgnored += $path
    }
}

if ($notIgnored.Count -gt 0) {
    Write-Host "FAIL: the following paths are NOT ignored by git:"
    foreach ($p in $notIgnored) {
        Write-Host "  - $p"
    }
    exit 1
}

Write-Host "OK: all local design/planning paths are ignored by git."
exit 0
