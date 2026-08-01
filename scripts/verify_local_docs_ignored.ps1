# Verifies that local design/planning documents are ignored by git.
# Run from anywhere; the script locates the repo root via $PSScriptRoot.
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$paths = @(
    'design docs',
    '最初设计功能清点',
    'docs/architecture',
    'docs/plans',
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
