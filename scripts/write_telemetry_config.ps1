# Write the Release-only telemetry resource next to the application bundle.
#
# A complete configuration is deliberately required before this script writes
# anything.  Incomplete local/CI inputs remove a stale generated resource so a
# previous Release build can never silently turn an ordinary build into a
# production-enabled build.  The replacement is written beside the target and
# moved into place in one filesystem operation.

param(
    [string]$OutputPath = "resources\telemetry\telemetry.json",
    [string]$TelemetryHost = "",
    [string]$TelemetryProjectToken = "",
    [switch]$EnabledForBuild
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if ([System.IO.Path]::IsPathRooted($OutputPath)) {
    $outputFull = [System.IO.Path]::GetFullPath($OutputPath)
} else {
    $outputFull = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $OutputPath))
}

function Remove-GeneratedResource {
    if (Test-Path -LiteralPath $outputFull -PathType Leaf) {
        Remove-Item -LiteralPath $outputFull -Force
    }
}

function Stop-InvalidConfiguration {
    param([Parameter(Mandatory = $true)][string]$Message)
    # A failed Release invocation must not leave a previous public config in
    # place for a later packaging step to consume accidentally.
    Remove-GeneratedResource
    throw $Message
}

if (-not $EnabledForBuild -or
    [string]::IsNullOrWhiteSpace($TelemetryHost) -or
    [string]::IsNullOrWhiteSpace($TelemetryProjectToken)) {
    Remove-GeneratedResource
    Write-Host 'Telemetry resource disabled; no production configuration generated.'
    return
}

$candidateHost = $TelemetryHost.Trim()
[System.Uri]$parsedHost = $null
if (-not [System.Uri]::TryCreate(
        $candidateHost,
        [System.UriKind]::Absolute,
        [ref]$parsedHost
    )) {
    Stop-InvalidConfiguration 'Telemetry host must be a valid HTTPS origin.'
}
if ($parsedHost.Scheme -cne 'https' -or
    [string]::IsNullOrWhiteSpace($parsedHost.Host) -or
    -not [string]::IsNullOrEmpty($parsedHost.UserInfo) -or
    -not [string]::IsNullOrEmpty($parsedHost.Query) -or
    -not [string]::IsNullOrEmpty($parsedHost.Fragment) -or
    $parsedHost.AbsolutePath -notin @('', '/')) {
    Stop-InvalidConfiguration 'Telemetry host must be an HTTPS origin without a path, query, fragment, or credentials.'
}

# Accessing Port forces malformed values such as ``:not-a-port`` to fail.
try {
    $null = $parsedHost.Port
} catch {
    Stop-InvalidConfiguration 'Telemetry host must have a valid port.'
}

$projectToken = $TelemetryProjectToken.Trim()
if ([string]::IsNullOrWhiteSpace($projectToken) -or
    $projectToken -match '[\r\n]' -or
    $projectToken -match '(?i)^phx_') {
    Stop-InvalidConfiguration 'Telemetry project token must be a single-line public capture value.'
}

$config = [ordered]@{
    schemaVersion = 1
    host = $candidateHost.TrimEnd('/')
    projectToken = $projectToken
    enabledForBuild = $true
}
$json = $config | ConvertTo-Json -Compress
$temporaryPath = "$outputFull.$([guid]::NewGuid().ToString('N')).tmp"

try {
    $parent = Split-Path -Parent $outputFull
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $utf8 = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($temporaryPath, $json, $utf8)
    [System.IO.File]::Move($temporaryPath, $outputFull, $true)
    Write-Host 'Telemetry resource generated for the configured Release build.'
} finally {
    if (Test-Path -LiteralPath $temporaryPath -PathType Leaf) {
        Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue
    }
}
