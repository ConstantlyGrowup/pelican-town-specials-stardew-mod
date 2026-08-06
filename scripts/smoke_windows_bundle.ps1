# Smoke-test a built Windows onedir bundle (Task 19 Step 5).
#
# Two launch phases exercise the two launcher paths:
#
#   Phase A (normal launch)  -- --no-browser --workspace <temp> --port <p>
#       The server stays up, so we can externally poll /api/v1/health and
#       fetch the static homepage. This proves the bundle really serves HTTP.
#
#   Phase B (self-check exit) -- --no-browser --workspace <temp> --port 43132
#       --exit-after-health-check
#       The launcher itself waits for health and exits 0 only if it passed
#       (launcher/main.py), so exit code 0 IS the health evidence. We wait for
#       that exit, assert code 0, and assert no runtime lock is left behind.
#
# The on-dir structure check (exe + frontend/dist/index.html) runs first.
#
# Run from anywhere; the script locates the repo root via $PSScriptRoot.

param(
    [string]$BundleDir = "dist\PelicanTownSpecials-windows-x64"
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not $BundleDir) {
    $BundleDir = Join-Path $repoRoot 'dist\PelicanTownSpecials-windows-x64'
}
$bundleFull = (Resolve-Path -LiteralPath $BundleDir -ErrorAction Stop).Path

# 1. Default directory structure on disk.
$exePath = Join-Path $bundleFull 'PelicanTownSpecials.exe'
$indexPath = Join-Path $bundleFull 'frontend\dist\index.html'
if (-not (Test-Path -LiteralPath $exePath)) {
    throw "Missing executable: $exePath"
}
if (-not (Test-Path -LiteralPath $indexPath)) {
    throw "Missing static homepage: $indexPath"
}

function New-TempWorkspace {
    return Join-Path ([System.IO.Path]::GetTempPath()) ('pts-smoke-' + [guid]::NewGuid().ToString('N'))
}

function Remove-TempWorkspace([string]$workspace) {
    if (Test-Path -LiteralPath $workspace) {
        Remove-Item -LiteralPath $workspace -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# Fast local HTTP client for health/homepage probes.
function New-FastHttpClient {
    $handler = [System.Net.Http.HttpClientHandler]::new()
    $handler.UseProxy = $false
    $client = [System.Net.Http.HttpClient]::new($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(2)
    return $client
}

# ---- Phase A: normal launch, real HTTP health + homepage ----
$workspaceA = New-TempWorkspace
$portA = 43133
$procA = $null
$clientA = $null
try {
    $argumentsA = @('--no-browser', '--workspace', $workspaceA, '--port', $portA.ToString())
    $procA = Start-Process -FilePath $exePath -ArgumentList $argumentsA -PassThru
    $clientA = New-FastHttpClient
    $healthUrl = "http://127.0.0.1:$portA/api/v1/health"
    $homeUrl = "http://127.0.0.1:$portA/"

    $healthy = $false
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        if ($procA.HasExited) {
            throw "Phase A launcher exited with code $($procA.ExitCode) before health was ready."
        }
        try {
            $response = $clientA.GetAsync($healthUrl).GetAwaiter().GetResult()
            if ($response.StatusCode -eq [System.Net.HttpStatusCode]::OK) {
                $healthy = $true
                break
            }
        } catch {
            # server not ready yet
        }
        Start-Sleep -Milliseconds 50
    }
    if (-not $healthy) {
        throw "Phase A health check did not become ready within 30s at $healthUrl"
    }

    $homeResponse = $clientA.GetAsync($homeUrl).GetAwaiter().GetResult()
    $homeBody = $homeResponse.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    if ($homeResponse.StatusCode -ne 200 -or $homeBody -notmatch 'Pelican Town Specials') {
        throw "Phase A static homepage did not serve expected content (status=$($homeResponse.StatusCode))."
    }
    Write-Host "Phase A OK: health + static homepage served."
}
finally {
    if ($clientA) {
        $clientA.Dispose()
    }
    if ($procA -and -not $procA.HasExited) {
        Stop-Process -Id $procA.Id -Force -ErrorAction SilentlyContinue
    }
    Remove-TempWorkspace $workspaceA
}

# ---- Phase B: --exit-after-health-check self-check exit + no residual lock ----
$workspaceB = New-TempWorkspace
$portB = 43132
$procB = $null
try {
    $argumentsB = @(
        '--no-browser',
        '--workspace', $workspaceB,
        '--port', $portB.ToString(),
        '--exit-after-health-check'
    )
    $procB = Start-Process -FilePath $exePath -ArgumentList $argumentsB -PassThru
    # The launcher self-verifies health and exits 0 only on success.
    Wait-Process -Id $procB.Id -Timeout 60 -ErrorAction Stop
    if ($procB.ExitCode -ne 0) {
        throw "Phase B launcher exited with non-zero code $($procB.ExitCode)."
    }

    $runtimeJson = Join-Path $workspaceB 'app-state\runtime.json'
    if (Test-Path -LiteralPath $runtimeJson) {
        throw "Phase B residual runtime record left behind: $runtimeJson"
    }
    Write-Host "Phase B OK: self-check exit 0, no residual runtime lock."
}
finally {
    if ($procB -and -not $procB.HasExited) {
        Stop-Process -Id $procB.Id -Force -ErrorAction SilentlyContinue
    }
    Remove-TempWorkspace $workspaceB
}

Write-Host "OK: bundle smoke passed (exe + static homepage + health + clean self-check exit)."
