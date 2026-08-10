# Smoke-test the built per-user installer (Milestone 7 Task 23).
#
# Real silent install/uninstall cycle against the default per-user locations:
#
#   1. Silent install (/VERYSILENT /CURRENTUSER) to
#      %LOCALAPPDATA%\Programs\PelicanTownSpecials.
#   2. Assert the executable and the required start-menu shortcut exist and the
#      optional desktop shortcut was NOT created by default.
#   3. Health smoke of the installed app (isolated temp workspace).
#   4. Create a marker file in the app's real default workspace (resolved from
#      the app's own config) to represent user data.
#   5. Silent reinstall over the existing install (upgrade path) and assert the
#      app and the workspace marker survive (M7-T23-INSTALL-004).
#   6. Silent uninstall (unins000.exe) and assert program files and shortcuts are
#      gone while the workspace marker survives (M7-T23-INSTALL-003).
#
# The machine returns to its pre-smoke state: the marker is removed and any
# workspace directory this script created is cleaned up only if it did not
# pre-exist (user data is never deleted).
#
# Run from anywhere; the script locates the repo root via $PSScriptRoot.

param(
    [string]$SetupExe = ""
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not $SetupExe) {
    $SetupExe = 'dist\installer\PelicanTownSpecials-Setup-v1.0.0.exe'
}
$setupFull = (Resolve-Path -LiteralPath $SetupExe -ErrorAction Stop).Path

$appDir = Join-Path $env:LOCALAPPDATA 'Programs\PelicanTownSpecials'
$appExe = Join-Path $appDir 'PelicanTownSpecials.exe'
$startMenuDir = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Pelican Town Specials'
$startLnk = Join-Path $startMenuDir 'Pelican Town Specials.lnk'
$desktopLnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Pelican Town Specials.lnk'

# Resolve the workspace the installed app actually uses by default, so the
# preservation marker proves uninstall leaves the real user-data location intact
# (M7-T23-INSTALL-003/004). The probe calls the app's own config so the smoke
# tracks the true platformdirs app-data layout instead of hardcoding a path.
$workspaceDir = (& python -c "from pelican_town_specials.config import _default_workspace_path; print(_default_workspace_path())" 2>$null).Trim()
if (-not $workspaceDir) {
    throw "Failed to resolve the app default workspace path (is the backend importable by 'python'?)."
}
$workspaceDir = [System.IO.Path]::GetFullPath($workspaceDir)
# Install dir and workspace must be disjoint so uninstall can never touch user
# data (M7-T23-INSTALL-003).
if ($workspaceDir.StartsWith($appDir, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Workspace ($workspaceDir) must not live inside the install dir ($appDir)."
}
# Unique per-run marker: never overwrites and never deletes a pre-existing file
# that might belong to the user (M7-T23-INSTALL-003).
$marker = Join-Path $workspaceDir ('.pts-smoke-marker-' + [guid]::NewGuid().ToString('N') + '.txt')

# Capture which ancestor dirs already exist so the finally cleanup never removes
# a pre-existing directory (user data is never deleted).
$preExistingDirs = New-Object 'System.Collections.Generic.HashSet[string]'
$localAppDataPrefix = $env:LOCALAPPDATA + [System.IO.Path]::DirectorySeparatorChar
$d = $workspaceDir
while ($d -and $d.StartsWith($localAppDataPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    if ([System.IO.Directory]::Exists($d)) {
        [void]$preExistingDirs.Add([System.IO.Path]::GetFullPath($d))
    }
    $d = [System.IO.Path]::GetDirectoryName($d)
}

function Invoke-Silent([string]$exe, [string[]]$extraArgs) {
    $args = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/CURRENTUSER', '/NORESTART', '/SP-') + $extraArgs
    $p = Start-Process -FilePath $exe -ArgumentList $args -Wait -PassThru
    return $p.ExitCode
}

# Fast local HTTP client for the health probe.
function New-FastHttpClient {
    $handler = [System.Net.Http.HttpClientHandler]::new()
    $handler.UseProxy = $false
    $client = [System.Net.Http.HttpClient]::new($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(2)
    return $client
}

try {
    # 0. A fresh machine must have no half shortcuts before install.
    if (Test-Path -LiteralPath $startLnk) {
        throw "Pre-existing start-menu shortcut found; refusing to continue on a dirty machine."
    }

    # 1. Silent install.
    Write-Host "==> silent install"
    $setupLog = Join-Path $env:TEMP 'pts-setup.log'
    Remove-Item -LiteralPath $setupLog -ErrorAction SilentlyContinue
    $code = Invoke-Silent $setupFull @("/LOG=$setupLog")
    if ($code -ne 0) {
        throw "Installer exited with code $code; log: $setupLog"
    }
    if (-not (Test-Path -LiteralPath $appExe)) {
        throw "Install did not create $appExe"
    }
    if (-not (Test-Path -LiteralPath $startLnk)) {
        throw "Required start-menu shortcut missing: $startLnk"
    }
    if (Test-Path -LiteralPath $desktopLnk) {
        throw "Desktop shortcut created although the task is unchecked by default"
    }
    # Resolve the shortcut and validate it points at the installed app with the
    # correct working directory (M7-T23-INSTALL-002).
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($startLnk)
    if ($shortcut.TargetPath -ne $appExe) {
        throw "Start-menu shortcut target mismatch: got $($shortcut.TargetPath) expected $appExe"
    }
    if ($shortcut.WorkingDirectory -ne $appDir) {
        throw "Start-menu shortcut working dir mismatch: got $($shortcut.WorkingDirectory) expected $appDir"
    }
    [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell) | Out-Null
    Write-Host "OK: install created program + start-menu shortcut (target=$appExe); desktop shortcut correctly absent."

    # 2. Health smoke of the installed app (isolated temp workspace).
    Write-Host "==> installed app health"
    $workspace = Join-Path ([System.IO.Path]::GetTempPath()) ('pts-inst-' + [guid]::NewGuid().ToString('N'))
    $port = 43141
    $proc = $null
    $client = $null
    try {
        $arguments = @('--no-browser', '--workspace', $workspace, '--port', $port.ToString())
        # Launch THROUGH the validated start-menu shortcut so the smoke exercises
        # the exact path a user takes (M7-T23-INSTALL-002).
        $proc = Start-Process -FilePath $startLnk -ArgumentList $arguments -PassThru
        $client = New-FastHttpClient
        $healthUrl = "http://127.0.0.1:$port/api/v1/health"

        $healthy = $false
        $deadline = (Get-Date).AddSeconds(30)
        while ((Get-Date) -lt $deadline) {
            if ($proc.HasExited) {
                throw "Installed app exited with code $($proc.ExitCode) before health was ready."
            }
            try {
                $response = $client.GetAsync($healthUrl).GetAwaiter().GetResult()
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
            throw "Installed app health check did not become ready within 30s at $healthUrl"
        }
        Write-Host "OK: installed app served /api/v1/health."
    }
    finally {
        if ($client) {
            $client.Dispose()
        }
        if ($proc -and -not $proc.HasExited) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
        Remove-Item -LiteralPath $workspace -Recurse -Force -ErrorAction SilentlyContinue
    }

    # 3. Workspace preservation marker (represents user data).
    New-Item -ItemType Directory -Force -Path $workspaceDir | Out-Null
    Set-Content -LiteralPath $marker -Value 'pts-smoke-marker' -Encoding ascii

    # 4. Upgrade/reinstall path: never deletes the workspace.
    Write-Host "==> silent reinstall (upgrade path)"
    $code = Invoke-Silent $setupFull @()
    if ($code -ne 0) {
        throw "Reinstall exited with code $code"
    }
    if (-not (Test-Path -LiteralPath $appExe)) {
        throw "Reinstall removed the app executable"
    }
    if (-not (Test-Path -LiteralPath $marker)) {
        throw "Reinstall deleted the workspace marker"
    }
    Write-Host "OK: reinstall kept app and workspace intact."

    # 5. Silent uninstall: program + shortcuts gone, workspace preserved.
    Write-Host "==> silent uninstall"
    $uninstaller = Join-Path $appDir 'unins000.exe'
    if (-not (Test-Path -LiteralPath $uninstaller)) {
        throw "Missing uninstaller: $uninstaller"
    }
    $code = Invoke-Silent $uninstaller @()
    if ($code -ne 0) {
        throw "Uninstaller exited with code $code"
    }
    if (Test-Path -LiteralPath $appDir) {
        throw "Uninstall did not remove the program directory"
    }
    if (Test-Path -LiteralPath $startLnk) {
        throw "Uninstall left the start-menu shortcut"
    }
    if (-not (Test-Path -LiteralPath $marker)) {
        throw "Uninstall deleted the workspace marker (user data must be preserved)"
    }
    Write-Host "OK: uninstall removed program + shortcuts and preserved the workspace."

    Write-Host "OK: installer smoke passed (install / health / reinstall / uninstall; workspace preserved)."
}
finally {
    Remove-Item -LiteralPath $marker -Force -ErrorAction SilentlyContinue
    # Remove only directories this run created and left empty; never delete a
    # pre-existing directory or anything under it.
    $d = $workspaceDir
    while ($d -and $d.StartsWith($localAppDataPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        if (-not ([System.IO.Directory]::Exists($d))) { break }
        if ($preExistingDirs.Contains([System.IO.Path]::GetFullPath($d))) { break }
        $leftovers = @(Get-ChildItem -LiteralPath $d -Force -ErrorAction SilentlyContinue)
        if ($leftovers.Count -gt 0) { break }
        Remove-Item -LiteralPath $d -Force -ErrorAction SilentlyContinue
        $d = [System.IO.Path]::GetDirectoryName($d)
    }
}
