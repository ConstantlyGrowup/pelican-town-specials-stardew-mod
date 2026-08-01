Set-StrictMode -Version Latest
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDirectory

$secureKey = Read-Host '请输入一步 API Key' -AsSecureString
$env:PTS_OPENAI_API_KEY = [System.Net.NetworkCredential]::new('', $secureKey).Password

if (-not $env:PTS_OPENAI_BASE_URL) { $env:PTS_OPENAI_BASE_URL = 'https://yibuapi.com/v1' }
if (-not $env:PTS_TEXT_MODEL) { $env:PTS_TEXT_MODEL = 'gpt-5.6-luna' }
if (-not $env:PTS_TEXT_REASONING_EFFORT) { $env:PTS_TEXT_REASONING_EFFORT = 'high' }
if (-not $env:PTS_IMAGE_MODEL) { $env:PTS_IMAGE_MODEL = 'gpt-image-2-max' }
if (-not $env:PTS_IMAGE_SIZE_TIER) { $env:PTS_IMAGE_SIZE_TIER = '2K' }
if (-not $env:PTS_IMAGE_ASPECT_RATIO) { $env:PTS_IMAGE_ASPECT_RATIO = '1:1' }
if (-not $env:PTS_IMAGE_RESPONSE_FORMAT) { $env:PTS_IMAGE_RESPONSE_FORMAT = 'url' }
if (-not $env:PTS_IMAGE_QUALITY) { $env:PTS_IMAGE_QUALITY = 'high' }

try {
    & python .\server.py
}
finally {
    Remove-Item Env:PTS_OPENAI_API_KEY -ErrorAction SilentlyContinue
}
