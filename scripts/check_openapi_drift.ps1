# Verifies the generated OpenAPI contract and frontend types are in sync with
# the backend. Regenerates both, then fails if git sees any diff.
# Run from anywhere; the script locates the repo root via $PSScriptRoot.

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

Write-Host '==> export OpenAPI schema'
python scripts/export_openapi.py
if ($LASTEXITCODE -ne 0) {
    throw 'OpenAPI export failed'
}

Write-Host '==> regenerate frontend types'
pnpm --dir frontend contract:generate
if ($LASTEXITCODE -ne 0) {
    throw 'frontend contract:generate failed'
}

Write-Host '==> check drift'
git diff --exit-code -- frontend/openapi.json frontend/src/api/generated/schema.d.ts
if ($LASTEXITCODE -ne 0) {
    throw 'OpenAPI drift detected: frontend/openapi.json or schema.d.ts is out of sync with the backend.'
}

Write-Host 'OK: OpenAPI contract and frontend types are in sync.'
exit 0
