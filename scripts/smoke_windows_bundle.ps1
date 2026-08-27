# Smoke-test a built Windows onedir bundle (Task 19 Step 5).
#
# Two clean launches exercise both launcher paths against the same verified
# temporary workspace:
#
#   Phase A (normal launch)  -- --no-browser --workspace <temp> --port <p>
#       The server stays up, so we can externally poll /api/v1/health and
#       fetch the static homepage. This proves the bundle really serves HTTP.
#
#   Phase B (self-check exit) -- --no-browser --workspace <same-temp> --port 43132
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

# PyInstaller must carry the stdlib SQLite extension in the onedir tree. Do
# this recursively because the extension may live below an architecture- or
# Python-version-specific subdirectory.
$sqliteExtension = @(
    Get-ChildItem -LiteralPath $bundleFull -Recurse -File -Filter '_sqlite3*.pyd' -ErrorAction Stop
)
if ($sqliteExtension.Count -eq 0) {
    throw "Missing recursive _sqlite3 extension in bundle: $bundleFull"
}
Write-Host "OK: recursive SQLite extension found at $($sqliteExtension[0].FullName)."

$tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$tempRootPrefix = $tempRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar

function New-TempWorkspace {
    return Join-Path ([System.IO.Path]::GetTempPath()) ('pts-smoke-' + [guid]::NewGuid().ToString('N'))
}

function Assert-TempWorkspacePath([string]$workspace) {
    if ([string]::IsNullOrWhiteSpace($workspace)) {
        throw 'Temporary workspace path must not be empty.'
    }
    $resolved = [System.IO.Path]::GetFullPath($workspace)
    if (-not $resolved.StartsWith($tempRootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to use a workspace outside the temp root: $resolved"
    }
    if ([System.IO.Path]::GetFileName($resolved) -notmatch '^pts-smoke-[0-9a-f]{32}$') {
        throw "Refusing to use an unrecognized smoke workspace: $resolved"
    }
}

function Remove-TempWorkspace([string]$workspace) {
    Assert-TempWorkspacePath $workspace
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

# ---- Phase A + B: two clean launches against one persistent workspace ----
$workspace = New-TempWorkspace
Assert-TempWorkspacePath $workspace
$portA = 43133
$portB = 43132
$procA = $null
$clientA = $null
$procB = $null
$clientB = $null
$telemetryDisabledWasSet = Test-Path Env:PTS_TELEMETRY_DISABLED
$telemetryDisabledPreviousValue = $env:PTS_TELEMETRY_DISABLED
# Every product process launched by this smoke, including both clean app
# launches, inherits this gate so a configured Release resource cannot pollute
# the production project. The original parent value is restored in finally.
$env:PTS_TELEMETRY_DISABLED = '1'
try {
    $argumentsA = @('--no-browser', '--workspace', $workspace, '--port', $portA.ToString())
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

    if ($clientA) {
        $clientA.Dispose()
        $clientA = $null
    }
    if ($procA -and -not $procA.HasExited) {
        Stop-Process -Id $procA.Id -Force -ErrorAction SilentlyContinue
        Wait-Process -Id $procA.Id -Timeout 10 -ErrorAction SilentlyContinue
    }
    $registryPath = Join-Path $workspace 'canonical\registry.sqlite3'
    if (-not (Test-Path -LiteralPath $registryPath -PathType Leaf)) {
        throw "Phase A did not create the Canonical registry: $registryPath"
    }
    $registryBytesAfterFirstLaunch = (Get-Item -LiteralPath $registryPath).Length
    if ($registryBytesAfterFirstLaunch -le 0) {
        throw "Phase A created an empty Canonical registry: $registryPath"
    }
    Write-Host "Phase A OK: non-empty registry.sqlite3 created ($registryBytesAfterFirstLaunch bytes)."

    $argumentsB = @(
        '--no-browser',
        '--workspace', $workspace,
        '--port', $portB.ToString(),
        '--exit-after-health-check'
    )
    $procB = Start-Process -FilePath $exePath -ArgumentList $argumentsB -PassThru
    Wait-Process -Id $procB.Id -Timeout 60 -ErrorAction Stop
    $procB.Refresh()
    if ($procB.ExitCode -ne 0) {
        throw "Phase B launcher exited with non-zero code $($procB.ExitCode)."
    }
    $registryBytesAfterSecondLaunch = (Get-Item -LiteralPath $registryPath -ErrorAction Stop).Length
    if ($registryBytesAfterSecondLaunch -le 0) {
        throw "Phase B left an empty Canonical registry: $registryPath"
    }
    $runtimeJson = Join-Path $workspace 'app-state\runtime.json'
    if (Test-Path -LiteralPath $runtimeJson) {
        throw "Phase B residual runtime record left behind: $runtimeJson"
    }
    Write-Host "Phase B OK: second clean launch reopened the same non-empty registry and exited 0."
}
finally {
    if ($clientA) {
        $clientA.Dispose()
    }
    if ($procA -and -not $procA.HasExited) {
        Stop-Process -Id $procA.Id -Force -ErrorAction SilentlyContinue
    }
    if ($clientB) {
        $clientB.Dispose()
    }
    if ($procB -and -not $procB.HasExited) {
        Stop-Process -Id $procB.Id -Force -ErrorAction SilentlyContinue
    }
    Remove-TempWorkspace $workspace
    if ($telemetryDisabledWasSet) {
        $env:PTS_TELEMETRY_DISABLED = $telemetryDisabledPreviousValue
    } else {
        Remove-Item Env:PTS_TELEMETRY_DISABLED -ErrorAction SilentlyContinue
    }
}

Write-Host "OK: bundle smoke passed (exe + recursive _sqlite3 + static homepage + two clean launches + persistent registry)."
