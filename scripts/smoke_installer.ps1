# Smoke-test the built per-user installer in an isolated temporary run root
# (Milestone 7 Task 23 and M10 Task 39).
#
# The installer is deliberately exercised with an explicit /DIR value generated
# for this run and /NOICONS. Nothing is installed into the user's normal product
# directory, no shortcut/group is created, and no real default workspace is
# resolved or touched:
#
#   1. Silent install into a unique temporary app directory.
#   2. Assert the executable exists; /NOICONS prevents default or smoke
#      shortcuts/groups from being created.
#   3. Health smoke of the installed app using an isolated temporary workspace.
#   4. Create a preservation marker in a separate isolated workspace.
#   5. Silent reinstall with the exact same /DIR and /NOICONS values.
#   6. Silent uninstall and assert the temporary app is gone while the isolated
#      workspace marker still exists.
#   7. Remove only the validated unique run root.
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

$telemetryDisabledWasSet = Test-Path Env:PTS_TELEMETRY_DISABLED
$telemetryDisabledPreviousValue = $env:PTS_TELEMETRY_DISABLED
# The installer, its uninstaller, and every app process launched through the
# unique smoke application process inherit this safety gate. Keep it process-local
# and restore the invoking PowerShell environment at the end.
$env:PTS_TELEMETRY_DISABLED = '1'
try {
    $tempRoot = $null
    $tempRootPrefix = $null
    $runId = $null
    $runRoot = $null
    $runRootPrefix = $null
    $runRootCreated = $false

    # Inno uses this exact production AppId for its per-user uninstall entry.
    # Registry checks are read-only and target only the exact key in both views;
    # this smoke never enumerates, modifies, or deletes registry data directly.
    $innoAppId = '{F3A6C7E2-4B91-4E0D-9C6A-8D5F2B1A7C43}'
    $innoUninstallSubKey = "Software\Microsoft\Windows\CurrentVersion\Uninstall\$($innoAppId)_is1"
    $registryViews = @(
        [Microsoft.Win32.RegistryView]::Registry64,
        [Microsoft.Win32.RegistryView]::Registry32
    )

    function Test-ExactInnoUninstallRegistration(
        [Microsoft.Win32.RegistryView]$view
    ) {
        $baseKey = $null
        $registrationKey = $null
        try {
            $baseKey = [Microsoft.Win32.RegistryKey]::OpenBaseKey(
                [Microsoft.Win32.RegistryHive]::CurrentUser,
                $view
            )
            $registrationKey = $baseKey.OpenSubKey($innoUninstallSubKey, $false)
            return $null -ne $registrationKey
        }
        finally {
            if ($registrationKey) {
                $registrationKey.Dispose()
            }
            if ($baseKey) {
                $baseKey.Dispose()
            }
        }
    }

    function Get-ExactInnoUninstallRegistrationViews {
        $foundViews = @()
        foreach ($view in $registryViews) {
            if (Test-ExactInnoUninstallRegistration $view) {
                $foundViews += $view
            }
        }
        return @($foundViews)
    }

    function Assert-SmokeRunRoot([string]$path) {
        if ([string]::IsNullOrWhiteSpace($path)) {
            throw 'Installer smoke run root must not be empty.'
        }
        $resolved = [System.IO.Path]::GetFullPath($path)
        if (-not $resolved.StartsWith($tempRootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to use a run root outside the system temp root: $resolved"
        }
        if ([System.IO.Path]::GetFileName($resolved) -notmatch '^pts-installer-smoke-[0-9a-f]{32}$') {
            throw "Refusing to use an unrecognized installer smoke run root: $resolved"
        }
        if ($resolved -ne $runRoot) {
            throw "Refusing to use a run root different from the generated root: $resolved"
        }
    }

    function Assert-SmokeRunChild([string]$path) {
        if ([string]::IsNullOrWhiteSpace($path)) {
            throw 'Installer smoke run child path must not be empty.'
        }
        Assert-SmokeRunRoot $runRoot
        $resolved = [System.IO.Path]::GetFullPath($path)
        if (-not $resolved.StartsWith($runRootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to use a path outside the validated installer smoke run root: $resolved"
        }
        if ($resolved -eq $runRoot) {
            throw 'Installer smoke child path must not be the run root itself.'
        }
    }

    function Remove-SmokeRunRoot([string]$path) {
        Assert-SmokeRunRoot $path
        if (-not (Test-Path -LiteralPath $path)) {
            return
        }
        $item = Get-Item -LiteralPath $path -Force -ErrorAction Stop
        if (-not $item.PSIsContainer) {
            throw "Refusing to recursively delete a non-directory run root: $path"
        }
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Refusing to recursively delete a reparse-point run root: $path"
        }
        Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction Stop
    }

    # Refuse before creating a run root or starting setup when the production
    # AppId is already registered. A pre-existing entry is never changed or
    # removed by this smoke.
    $preExistingRegistrationViews = @(Get-ExactInnoUninstallRegistrationViews)
    if ($preExistingRegistrationViews.Count -gt 0) {
        $viewNames = ($preExistingRegistrationViews | ForEach-Object { $_.ToString() }) -join ', '
        throw "Refusing to run installer smoke: production AppId $innoAppId is already registered for CurrentUser in registry view(s): $viewNames. No setup process was started and the existing registration was not modified."
    }

    # Reserve a fresh, name-validated root before any installer process starts.
    $tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
    $tempRootPrefix = $tempRoot.TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    ) + [System.IO.Path]::DirectorySeparatorChar
    $runId = [guid]::NewGuid().ToString('N')
    $runRoot = [System.IO.Path]::GetFullPath(
        (Join-Path $tempRoot ("pts-installer-smoke-$runId"))
    )
    $runRootPrefix = $runRoot.TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    ) + [System.IO.Path]::DirectorySeparatorChar
    Assert-SmokeRunRoot $runRoot
    if (Test-Path -LiteralPath $runRoot) {
        throw "Generated installer smoke run root already exists: $runRoot"
    }
    New-Item -ItemType Directory -Path $runRoot -Force -ErrorAction Stop | Out-Null
    $runRootCreated = $true

    $appDir = [System.IO.Path]::GetFullPath((Join-Path $runRoot 'app'))
    $appExe = Join-Path $appDir 'PelicanTownSpecials.exe'
    $healthWorkspace = [System.IO.Path]::GetFullPath((Join-Path $runRoot 'health-workspace'))
    $workspaceDir = [System.IO.Path]::GetFullPath((Join-Path $runRoot 'preserved-workspace'))
    $marker = Join-Path $workspaceDir 'pts-smoke-preservation-marker.txt'
    $setupLog = Join-Path $runRoot 'pts-setup.log'
    Assert-SmokeRunChild $appDir
    Assert-SmokeRunChild $healthWorkspace
    Assert-SmokeRunChild $workspaceDir
    Assert-SmokeRunChild $marker
    Assert-SmokeRunChild $setupLog

    # These exact arguments are reused for install and reinstall. Quotes keep
    # the explicit app path safe if a Windows profile path contains spaces.
    # /NOICONS is intentional: this M10 smoke must not create or remove any
    # default or smoke shortcut/group artifacts.
    $innoInstallArguments = @(
        "/DIR=`"$appDir`"",
        '/NOICONS'
    )

    function Invoke-Silent(
        [string]$exe,
        [string[]]$extraArgs,
        [switch]$UseInstallLocation
    ) {
        $args = @(
            '/VERYSILENT',
            '/SUPPRESSMSGBOXES',
            '/CURRENTUSER',
            '/NORESTART',
            '/SP-'
        )
        if ($UseInstallLocation) {
            $args += $innoInstallArguments
        }
        $args += $extraArgs
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

    # 1. Silent install into the validated temporary app directory without icons.
    Write-Host "==> silent isolated install"
    $code = Invoke-Silent $setupFull @("/LOG=`"$setupLog`"") -UseInstallLocation
    if ($code -ne 0) {
        throw "Installer exited with code $code; log: $setupLog"
    }
    $installedRegistrationViews = @(Get-ExactInnoUninstallRegistrationViews)
    if ($installedRegistrationViews.Count -eq 0) {
        throw (
            "Isolated installer did not create the expected CurrentUser uninstall " +
            "registration for production AppId $innoAppId in Registry64 or Registry32."
        )
    }
    if (-not (Test-Path -LiteralPath $appExe)) {
        throw "Install did not create $appExe"
    }
    $sqliteExtension = @(
        Get-ChildItem -LiteralPath $appDir -Recurse -File -Filter '_sqlite3*.pyd' -ErrorAction Stop
    )
    if ($sqliteExtension.Count -eq 0) {
        throw "Installed app is missing the recursive _sqlite3 extension: $appDir"
    }
    Write-Host "OK: isolated installed app includes recursive SQLite extension at $($sqliteExtension[0].FullName)."
    Write-Host "OK: isolated install created program without default or smoke shortcuts/groups."

    # 2. Two clean launches of the installed app against one isolated health
    # workspace. The second launch proves the packaged SQLite registry can be
    # reopened without changing user data.
    Write-Host "==> installed app health + persistent registry"
    $port = 43141
    $secondPort = 43142
    $proc = $null
    $secondProc = $null
    $client = $null
    try {
        $arguments = @('--no-browser', '--workspace', $healthWorkspace, '--port', $port.ToString())
        # Launch the validated temporary executable directly. This M10 smoke
        # intentionally has no shortcut dependency or mutation.
        $proc = Start-Process -FilePath $appExe -ArgumentList $arguments -PassThru
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

        if ($client) {
            $client.Dispose()
            $client = $null
        }
        if ($proc -and -not $proc.HasExited) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            Wait-Process -Id $proc.Id -Timeout 10 -ErrorAction SilentlyContinue
        }
        $registryPath = Join-Path $healthWorkspace 'canonical\registry.sqlite3'
        if (-not (Test-Path -LiteralPath $registryPath -PathType Leaf)) {
            throw "Installed app did not create the Canonical registry: $registryPath"
        }
        $registryBytesAfterFirstLaunch = (Get-Item -LiteralPath $registryPath).Length
        if ($registryBytesAfterFirstLaunch -le 0) {
            throw "Installed app created an empty Canonical registry: $registryPath"
        }
        Write-Host "OK: first clean launch created non-empty registry.sqlite3 ($registryBytesAfterFirstLaunch bytes)."

        $secondArguments = @(
            '--no-browser',
            '--workspace', $healthWorkspace,
            '--port', $secondPort.ToString(),
            '--exit-after-health-check'
        )
        $secondProc = Start-Process -FilePath $appExe -ArgumentList $secondArguments -PassThru
        Wait-Process -Id $secondProc.Id -Timeout 60 -ErrorAction Stop
        $secondProc.Refresh()
        if ($secondProc.ExitCode -ne 0) {
            throw "Second installed app launch exited with code $($secondProc.ExitCode)."
        }
        $registryBytesAfterSecondLaunch = (Get-Item -LiteralPath $registryPath -ErrorAction Stop).Length
        if ($registryBytesAfterSecondLaunch -le 0) {
            throw "Second installed app launch left an empty Canonical registry: $registryPath"
        }
        $runtimeJson = Join-Path $healthWorkspace 'app-state\runtime.json'
        if (Test-Path -LiteralPath $runtimeJson) {
            throw "Second installed app launch left a runtime record: $runtimeJson"
        }
        Write-Host "OK: second clean launch reopened the same non-empty registry and exited 0."
    }
    finally {
        if ($client) {
            $client.Dispose()
        }
        if ($proc -and -not $proc.HasExited) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
        if ($secondProc -and -not $secondProc.HasExited) {
            Stop-Process -Id $secondProc.Id -Force -ErrorAction SilentlyContinue
        }
    }

    # 3. Isolated workspace preservation marker. It remains under the
    # validated run root until the outer final cleanup after uninstall checks.
    Write-Host "==> create isolated workspace preservation marker"
    New-Item -ItemType Directory -Force -Path $workspaceDir -ErrorAction Stop | Out-Null
    Set-Content -LiteralPath $marker -Value 'pts-smoke-marker' -Encoding ascii
    if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) {
        throw "Failed to create isolated workspace marker: $marker"
    }

    # 4. Upgrade/reinstall path: use exactly the same /DIR and /NOICONS and
    # never delete the isolated workspace marker.
    Write-Host "==> silent isolated reinstall (upgrade path)"
    $code = Invoke-Silent $setupFull @("/LOG=`"$setupLog`"") -UseInstallLocation
    if ($code -ne 0) {
        throw "Reinstall exited with code $code; log: $setupLog"
    }
    if (-not (Test-Path -LiteralPath $appExe)) {
        throw "Reinstall removed the isolated app executable"
    }
    if (-not (Test-Path -LiteralPath $marker)) {
        throw "Reinstall deleted the isolated workspace marker"
    }
    Write-Host "OK: reinstall kept isolated app and workspace marker intact."

    # 5. Silent uninstall: isolated program gone, isolated workspace preserved
    # until final run-root cleanup. /NOICONS means no shortcut/group cleanup is
    # needed or permitted here.
    Write-Host "==> silent isolated uninstall"
    $uninstaller = Join-Path $appDir 'unins000.exe'
    if (-not (Test-Path -LiteralPath $uninstaller)) {
        throw "Missing uninstaller: $uninstaller"
    }
    $code = Invoke-Silent $uninstaller @()
    if ($code -ne 0) {
        throw "Uninstaller exited with code $code"
    }
    $remainingRegistrationViews = @(Get-ExactInnoUninstallRegistrationViews)
    if ($remainingRegistrationViews.Count -gt 0) {
        $viewNames = ($remainingRegistrationViews | ForEach-Object { $_.ToString() }) -join ', '
        throw (
            "Isolated uninstaller left the exact production AppId $innoAppId registered " +
            "for CurrentUser in registry view(s): $viewNames."
        )
    }
    if (Test-Path -LiteralPath $appDir) {
        throw "Uninstall did not remove the isolated program directory"
    }
    if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) {
        throw "Uninstall deleted the isolated workspace marker (user data must be preserved)"
    }
    Write-Host "OK: uninstall removed the isolated program and preserved the isolated workspace."

    Write-Host "OK: isolated installer smoke passed (install / health / reinstall / uninstall; workspace preserved)."
}
finally {
    $cleanupFailures = @()
    if ($runRootCreated -and $runRoot) {
        try {
            # This guard permits recursive deletion only of this run's generated
            # temp root; the preserved marker is removed as part of this final
            # cleanup and no default/user-computed path is touched.
            Remove-SmokeRunRoot $runRoot
        }
        catch {
            $cleanupFailures += $_.Exception.Message
        }
    }

    if ($telemetryDisabledWasSet) {
        $env:PTS_TELEMETRY_DISABLED = $telemetryDisabledPreviousValue
    }
    else {
        Remove-Item Env:PTS_TELEMETRY_DISABLED -ErrorAction SilentlyContinue
    }

    if ($cleanupFailures.Count -gt 0) {
        throw "Installer smoke cleanup failed: $($cleanupFailures -join '; ')"
    }
}
