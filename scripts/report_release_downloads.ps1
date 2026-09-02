# Read-only GitHub Release download report for M10 telemetry reach evidence.
#
# By default this performs one anonymous GET against the public GitHub Releases
# API.  ``-FixturePath`` replaces the request for offline/reproducible tests.
# The installer and portable ZIP totals intentionally remain separate: GitHub
# may reset an asset's count when the asset is replaced or re-uploaded.
# v1.5.3 (2026-09-02): report the current patch release tag by default.

param(
    [string]$Repository = "ConstantlyGrowup/pelican-town-specials-stardew-mod",
    [string]$Tag = "v1.5.3",
    [string]$FixturePath = ""
)

$ErrorActionPreference = 'Stop'

if ($FixturePath) {
    $release = Get-Content -LiteralPath $FixturePath -Raw | ConvertFrom-Json
    $source = 'fixture'
} else {
    $encodedTag = [System.Uri]::EscapeDataString($Tag)
    $uri = "https://api.github.com/repos/$Repository/releases/tags/$encodedTag"
    $release = Invoke-RestMethod -Method Get -Uri $uri -Headers @{
        Accept = 'application/vnd.github+json'
        'X-GitHub-Api-Version' = '2022-11-28'
    }
    $source = 'github-release-api'
}

if ($null -eq $release -or $null -eq $release.assets) {
    throw 'Release response did not contain an assets collection.'
}

function Get-AssetsByPattern {
    param([string]$Pattern)
    return @(
        $release.assets | Where-Object {
            $_.name -is [string] -and $_.name -match $Pattern
        }
    )
}

function Sum-DownloadCounts {
    param(
        [Parameter(Mandatory = $true)][object[]]$Assets,
        [Parameter(Mandatory = $true)][string]$Label
    )
    if ($Assets.Count -eq 0) {
        throw "Release is missing the $Label asset."
    }
    [int64]$total = 0
    foreach ($asset in $Assets) {
        if ($null -eq $asset.download_count) {
            throw "$Label asset $($asset.name) has no download_count."
        }
        [int64]$total += [int64]$asset.download_count
    }
    return $total
}

$installerAssets = Get-AssetsByPattern '^PelicanTownSpecials-Setup-v[^/]+\.exe$'
$portableAssets = Get-AssetsByPattern '^PelicanTownSpecials-windows-x64-v[^/]+\.zip$'
$installerTotal = Sum-DownloadCounts -Assets $installerAssets -Label 'installer'
$portableTotal = Sum-DownloadCounts -Assets $portableAssets -Label 'portable ZIP'

$report = [ordered]@{
    releaseTag = if ($release.tag_name) { [string]$release.tag_name } else { $Tag }
    source = $source
    installerDownloadCount = $installerTotal
    portableDownloadCount = $portableTotal
    installerAssets = @($installerAssets | ForEach-Object {
        [ordered]@{ name = [string]$_.name; downloadCount = [int64]$_.download_count }
    })
    portableAssets = @($portableAssets | ForEach-Object {
        [ordered]@{ name = [string]$_.name; downloadCount = [int64]$_.download_count }
    })
    caveat = 'GitHub may reset download_count when a Release asset is replaced or re-uploaded; treat this as reach evidence only.'
}

$report | ConvertTo-Json -Depth 5 -Compress
