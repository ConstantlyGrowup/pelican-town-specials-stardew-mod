# Milestone 7 Task 24: generate the concise, version-consistent release notes.
#
# Produces a Markdown body for the GitHub Release: download links (installer,
# portable ZIP, SHA-256 checksum), the per-user install steps, and the note that
# uninstall preserves the user workspace. The version is stamped at build time so
# the notes always match the artifacts they describe.
#
# Run from anywhere; the script locates the repo root via $PSScriptRoot.
#   pwsh -NoProfile -File scripts/generate_release_notes.ps1 -Version 1.5.2 -OutputFile RELEASE_NOTES.md

param(
    [string]$Version = "1.5.2",
    [string]$OutputFile = ""
)

$ErrorActionPreference = 'Stop'

$normalized = $Version.Trim().TrimStart('v')

$body = @"
# Pelican Town Specials v$normalized

感谢使用「鹈鹕镇新菜单」！这是一个本地运行、为《星露谷物语》生成自定义食谱
内容包的桌面工具。

## v$normalized / 报错信息本地化补丁

- 英文界面的生成报错信息（蓝图、问问 Gus 与系统级生成错误）现在会显示英文提示。
- 中文界面保持原有提示内容不变。

## 下载

- 安装程序（推荐）：`PelicanTownSpecials-Setup-v$normalized.exe`
- 便携版：`PelicanTownSpecials-windows-x64-v$normalized.zip`（解压后双击 `PelicanTownSpecials.exe`）
- 校验文件：`SHA256SUMS.txt`（使用 `Get-FileHash -Algorithm SHA256` 或 `sha256sum` 校验以上文件）

## 安装

1. 双击安装程序，应用安装到 `%LOCALAPPDATA%\Programs\PelicanTownSpecials`，
   无需管理员权限，不需要 Python、Node.js 或 Git。
2. 安装会创建开始菜单快捷方式「Pelican Town Specials」（可选择创建桌面快捷方式）。
3. 可以先使用公共试用，也可以在「设置」页配置个人服务；然后上传菜品照片即可开始生成食谱。

卸载会删除程序文件和快捷方式，但**保留**你的工作区与用户数据
（`%LOCALAPPDATA%\PelicanTownSpecials`），重新安装后数据仍在。

完整说明见发布包内 `README.txt`。
"@

if ($OutputFile) {
    Set-Content -LiteralPath $OutputFile -Value $body -Encoding utf8
    Write-Host "OK: release notes written to $OutputFile"
} else {
    Write-Output $body
}
