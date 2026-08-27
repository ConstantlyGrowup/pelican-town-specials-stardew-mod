# Shared release content gate (Milestone 7 Task 23).
#
# Both the onedir bundle build (scripts/build_windows.ps1) and the installer
# build (scripts/build_installer.ps1) run the same policy so a secret, workspace
# file, design document, test fixture, sample asset or source map can never
# reach a release artifact through either path (M7-T23-INSTALL-005). The M10
# public telemetry resource is the only generated JSON explicitly validated by
# this gate; private state and captured event fixtures remain forbidden.
#
# Usage:
#   . .\scripts\release_content_gate.ps1
#   $violations = @(Test-ReleaseContent -Root <dir>)

function Test-ReleaseContent {
    param(
        [Parameter(Mandatory = $true)][string]$Root
    )

    function Test-TelemetryResource {
        param([Parameter(Mandatory = $true)][string]$Path)

        $issues = @()
        try {
            $json = Get-Content -LiteralPath $Path -Raw -ErrorAction Stop | ConvertFrom-Json
        } catch {
            return @("${Path}: invalid telemetry JSON")
        }

        if ($null -eq $json -or
            $json -is [System.Array] -or
            $json -isnot [pscustomobject]) {
            return @("${Path}: telemetry JSON must be an object")
        }

        $expectedKeys = @('schemaVersion', 'host', 'projectToken', 'enabledForBuild')
        $actualKeys = @($json.PSObject.Properties.Name)
        foreach ($key in $expectedKeys) {
            if ($actualKeys -notcontains $key) {
                $issues += "${Path}: missing $key"
            }
        }
        foreach ($key in $actualKeys) {
            if ($expectedKeys -notcontains $key) {
                $issues += "${Path}: unexpected key $key"
            }
        }
        if (($json.schemaVersion -is [bool]) -or
            ($json.schemaVersion -isnot [int] -and
                $json.schemaVersion -isnot [long]) -or
            $json.schemaVersion -ne 1) {
            $issues += "${Path}: schemaVersion must be integer 1"
        }
        if ($json.enabledForBuild -isnot [bool] -or $json.enabledForBuild -ne $true) {
            $issues += "${Path}: enabledForBuild must be true"
        }

        if ($json.host -isnot [string]) {
            $issues += "${Path}: host must be a string"
        } else {
            [System.Uri]$parsedHost = $null
            $hostValue = $json.host
            if (-not [System.Uri]::TryCreate(
                    $hostValue,
                    [System.UriKind]::Absolute,
                    [ref]$parsedHost
                ) -or
                $parsedHost.Scheme -cne 'https' -or
                [string]::IsNullOrWhiteSpace($parsedHost.Host) -or
                -not [string]::IsNullOrEmpty($parsedHost.UserInfo) -or
                -not [string]::IsNullOrEmpty($parsedHost.Query) -or
                -not [string]::IsNullOrEmpty($parsedHost.Fragment) -or
                $parsedHost.AbsolutePath -notin @('', '/')) {
                $issues += "${Path}: host must be an HTTPS origin"
            }
        }
        if ($json.projectToken -isnot [string] -or
            [string]::IsNullOrWhiteSpace($json.projectToken)) {
            $issues += "${Path}: projectToken must be a non-empty string"
        } elseif ($json.projectToken -match '[\r\n]') {
            $issues += "${Path}: projectToken must be a single-line string"
        } elseif ($json.projectToken -match '(?i)^phx_') {
            $issues += "${Path}: projectToken must be a public capture token"
        }
        return $issues
    }

    # Normalize to an absolute path so segment math below is correct even when
    # a caller passes a relative path (e.g. build_windows.ps1 default bundle dir).
    $Root = (Resolve-Path -LiteralPath $Root -ErrorAction Stop).Path

    $forbiddenTop = @('workspace', 'design docs', 'docs', 'tests', 'samples', '最初设计功能清点')
    $allowedTelemetryPath = 'resources/telemetry/telemetry.json'
    $textExtensions = @(
        '.txt', '.json', '.jsonl', '.ndjson', '.csv', '.xml', '.yaml', '.yml',
        '.ini', '.toml', '.md', '.py', '.ps1', '.bat', '.cmd', '.cfg'
    )
    $violations = @()
    Get-ChildItem -LiteralPath $Root -Recurse -Force -File | ForEach-Object {
        $rel = $_.FullName.Substring($Root.Length).TrimStart('\', '/').Replace('\', '/')
        $name = $_.Name
        $topSegment = ($rel -split '/')[0]
        $forbidden = $false
        $reasons = @()

        if ($rel -eq $allowedTelemetryPath) {
            $reasons += @(Test-TelemetryResource -Path $_.FullName)
        } elseif ($rel -match '^resources/telemetry/') {
            $reasons += 'unexpected telemetry resource'
        }
        if ($name -ieq 'telemetry.json' -and $rel -ine $allowedTelemetryPath) {
            $reasons += 'telemetry resource at unexpected path'
        }

        # Project-level leakage appears at the bundle root or as named files;
        # Python library internals (e.g. jedi/.../samples/) are not project content.
        if ($name -like '.env*') { $reasons += 'environment file' }
        if ($name -like 'StarValleyCook*') { $reasons += 'project design file' }
        if ($name -eq 'launcher-error.log') { $reasons += 'launcher log' }
        if ($name -like '*.map') { $reasons += 'source map' }
        if ($forbiddenTop -contains $topSegment) { $reasons += 'project-only directory' }
        if ($rel -match '(^|/)docs/(architecture|plans)(/|$)') { $reasons += 'design directory' }
        # The frontend's five tiny Stardew-derived screenshot fixtures are
        # versioned product assets, not user uploads. Keep only those exact
        # pre-existing names while rejecting every other fixture path.
        $isKnownProductFixture = $rel -match '^frontend/dist/assets/game/fixtures/dish-[1-5]\.png$'
        if ((-not $isKnownProductFixture) -and
            $rel -match '(^|/)(fixtures?|test-data|user-content)(/|$)') {
            $reasons += 'test or user-content fixture'
        }
        if ($name -match '(?i)(telemetry[-_]?state|telemetry[-_]?events?|^events?(?:[-_.]|$)|^payload(?:[-_.]|$))' -or
            $name -match '(?i)\.(?:db|sqlite\d*)$') {
            $reasons += 'captured event state'
        }

        # Third-party wheel metadata/SBOMs can contain build paths, UUIDs and
        # ordinary JSON ``properties`` keys; they are not application state.
        # The gate still checks their filenames and project-level directories.
        $isThirdPartyMetadata = $rel -match '\.dist-info/'
        if ((-not $isThirdPartyMetadata) -and
            $textExtensions -contains $_.Extension.ToLowerInvariant()) {
            try {
                $content = [System.IO.File]::ReadAllText($_.FullName)
                if ($content -match '(?i)"(event|events|distinct_id|installationId|properties|batch)"\s*:') {
                    $reasons += 'serialized telemetry event'
                }
                if ($content -match '(?i)generation\s+(started|finished)|app\s+opened') {
                    $reasons += 'event detail'
                }
                if ($content -match '(?i)(posthog[_ -]?(management|admin)|(?:management|admin|personal)[_ -]?api[_ -]?key|phx_[A-Za-z0-9_-]{8,})') {
                    $reasons += 'private or management key marker'
                }
                if ($content -match '(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b') {
                    $reasons += 'installation UUID'
                }
                if ($content -match '(?i)\b[A-Z]:[\\/](?:Users|Documents and Settings)[\\/][^\r\n"'']+|\\\\[^\r\n"'']+[\\/]') {
                    $reasons += 'absolute path'
                }
            } catch {
                $reasons += 'unreadable text file'
            }
        }

        if ($reasons.Count -gt 0) { $forbidden = $true }
        if ($forbidden) {
            $violations += "${rel}: $($reasons -join ', ')"
        }
    }
    return $violations
}
