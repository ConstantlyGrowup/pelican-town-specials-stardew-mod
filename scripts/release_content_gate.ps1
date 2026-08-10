# Shared release content gate (Milestone 7 Task 23).
#
# Both the onedir bundle build (scripts/build_windows.ps1) and the installer
# build (scripts/build_installer.ps1) run the same policy so a secret, workspace
# file, design document, test fixture, sample asset or source map can never
# reach a release artifact through either path (M7-T23-INSTALL-005).
#
# Usage:
#   . .\scripts\release_content_gate.ps1
#   $violations = @(Test-ReleaseContent -Root <dir>)

function Test-ReleaseContent {
    param(
        [Parameter(Mandatory = $true)][string]$Root
    )

    # Normalize to an absolute path so segment math below is correct even when
    # a caller passes a relative path (e.g. build_windows.ps1 default bundle dir).
    $Root = (Resolve-Path -LiteralPath $Root -ErrorAction Stop).Path

    $forbiddenTop = @('workspace', 'design docs', 'docs', 'tests', 'samples', '最初设计功能清点')
    $violations = @()
    Get-ChildItem -LiteralPath $Root -Recurse -Force -File | ForEach-Object {
        $rel = $_.FullName.Substring($Root.Length).TrimStart('\', '/')
        $name = $_.Name
        $topSegment = ($rel -split '[\\/]')[0]
        $forbidden = $false
        # Project-level leakage appears at the bundle root or as named files;
        # Python library internals (e.g. jedi/.../samples/) are not project content.
        if ($name -like '.env*') { $forbidden = $true }
        if ($name -like 'StarValleyCook*') { $forbidden = $true }
        if ($name -eq 'launcher-error.log') { $forbidden = $true }
        if ($name -like '*.map') { $forbidden = $true }
        if ($forbiddenTop -contains $topSegment) { $forbidden = $true }
        if ($rel -match '(^|[\\/])docs[\\/](architecture|plans)([\\/]|$)') { $forbidden = $true }
        if ($forbidden) {
            $violations += $rel
        }
    }
    return $violations
}
