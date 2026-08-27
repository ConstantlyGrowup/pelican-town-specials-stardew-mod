# Build the Windows PyInstaller onedir release bundle (Task 19 Step 4).
#
# Flow:
#   1. Run backend tests, frontend tests/build, OpenAPI drift and repo ignore
#      policy checks (fail fast; nothing is built before these pass).
#   2. Run PyInstaller with packaging/pyinstaller/PelicanTownSpecials.spec.
#   3. Verify the bundle structure and gate the release content: no .env,
#      workspace, design docs, test fixtures or sample assets may land in it.
#
# Any step failing exits non-zero; a release ZIP is never produced/kept on
# failure. Run from anywhere; the script locates the repo root via $PSScriptRoot.

param(
    [string]$BundleDir = "",
    [string]$TelemetryHost = "",
    [string]$TelemetryProjectToken = "",
    [switch]$TelemetryEnabledForBuild
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not $BundleDir) {
    $BundleDir = Join-Path $repoRoot 'dist\PelicanTownSpecials-windows-x64'
}

function Assert-Zero {
    param([string]$Name)
    if ($LASTEXITCODE -ne 0) {
        throw "FAILED: $Name"
    }
}

Write-Host "==> prepare Release telemetry resource"
$telemetryWriter = Join-Path $PSScriptRoot 'write_telemetry_config.ps1'
$telemetryArguments = @(
    '-TelemetryHost', $TelemetryHost,
    '-TelemetryProjectToken', $TelemetryProjectToken
)
if ($TelemetryEnabledForBuild) {
    $telemetryArguments += '-EnabledForBuild'
}
& pwsh -NoProfile -File $telemetryWriter @telemetryArguments
Assert-Zero "Release telemetry resource"

Write-Host "==> backend tests"
python -m pytest backend/tests tests/integration -q
Assert-Zero "backend tests"

Write-Host "==> frontend tests"
pnpm --dir frontend test:run
Assert-Zero "frontend tests"

Write-Host "==> frontend build"
pnpm --dir frontend build
Assert-Zero "frontend build"

Write-Host "==> OpenAPI drift"
python scripts/export_openapi.py
Assert-Zero "OpenAPI export"
pnpm --dir frontend contract:generate
Assert-Zero "contract generate"
git diff --exit-code -- frontend/openapi.json frontend/src/api/generated/schema.d.ts
Assert-Zero "OpenAPI drift"

Write-Host "==> repo ignore policy"
pwsh -NoProfile -File scripts/verify_local_docs_ignored.ps1
Assert-Zero "repo ignore policy"

Write-Host "==> internal telemetry dashboard contract"
python scripts/validate_telemetry_dashboard.py
Assert-Zero "internal telemetry dashboard contract"

Write-Host "==> PyInstaller build"
python -m PyInstaller --clean --noconfirm packaging/pyinstaller/PelicanTownSpecials.spec
Assert-Zero "PyInstaller build"

Write-Host "==> EXE icon gate (Task 22)"
pwsh -NoProfile -File scripts/check_exe_icon.ps1 -BundleDir $BundleDir
if ($LASTEXITCODE -ne 0) {
    throw "FAILED: EXE icon gate"
}

Write-Host "==> copy release docs into bundle root"
$readmeSrc = Join-Path $repoRoot 'packaging\release\README.txt'
$noticesSrc = Join-Path $repoRoot 'packaging\release\THIRD_PARTY_NOTICES.txt'
$readmeDst = Join-Path $BundleDir 'README.txt'
$noticesDst = Join-Path $BundleDir 'THIRD_PARTY_NOTICES.txt'
if (-not (Test-Path -LiteralPath $readmeSrc)) {
    throw "Missing release README source: $readmeSrc"
}
if (-not (Test-Path -LiteralPath $noticesSrc)) {
    throw "Missing third-party notices source: $noticesSrc"
}
Copy-Item -LiteralPath $readmeSrc -Destination $readmeDst -Force
Copy-Item -LiteralPath $noticesSrc -Destination $noticesDst -Force

Write-Host "==> verify bundle structure"
$exePath = Join-Path $BundleDir 'PelicanTownSpecials.exe'
$indexPath = Join-Path $BundleDir 'frontend\dist\index.html'
$catalogPath = Join-Path $BundleDir 'resources\catalogs\stardew-1.6.15\vanilla-ingredients.json'
if (-not (Test-Path -LiteralPath $exePath)) {
    throw "Missing executable: $exePath"
}
if (-not (Test-Path -LiteralPath $indexPath)) {
    throw "Missing static homepage: $indexPath"
}
if (-not (Test-Path -LiteralPath $catalogPath)) {
    throw "Missing vanilla catalog: $catalogPath"
}
if (-not (Test-Path -LiteralPath $readmeDst)) {
    throw "Missing release README in bundle: $readmeDst"
}
if (-not (Test-Path -LiteralPath $noticesDst)) {
    throw "Missing third-party notices in bundle: $noticesDst"
}

Write-Host "==> release content gate"
. (Join-Path $PSScriptRoot 'release_content_gate.ps1')
$violations = @(Test-ReleaseContent -Root $BundleDir)
if ($violations.Count -gt 0) {
    throw "Release bundle contains forbidden content: $($violations -join ', ')"
}

Write-Host "OK: Windows bundle built at $BundleDir"
