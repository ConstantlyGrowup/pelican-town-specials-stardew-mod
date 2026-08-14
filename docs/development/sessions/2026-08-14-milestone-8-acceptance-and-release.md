# Session｜Milestone 8 验收与 v1.2.0 Release

| 字段 | 值 |
|---|---|
| session_id | `2026-08-14-milestone-8-acceptance-and-release` |
| status | `closed`（2026-08-14 v1.2.0 Release 已发布并核验） |
| date | 2026-08-14 |
| scope | Milestone 8 用户验收记录 + 「验收即发布」v1.2.0 版本提升、本地全量验证、推送与 GitHub Release |

## 用户验收（2026-08-14）

用户明确验收 Milestone 8 并通过，同时授权发布流程：

> 1. Milestone 8 验收通过
> 2. 我已经卸载成功了，你可以发布新的安装包，并同步发布新的 release 至我们的仓库

即：M8 正式进入 `accepted`；用户已卸载 v1.1.0 复验安装（此前阻塞 smoke_installer.ps1 的环境前置解除）；授权按「验收即发布」流程重建 installer 并发布 GitHub Release（push 分支、tag v1.2.0、push tag 触发 release.yml）。

## v1.2.0 版本提升

commit `3b6ea33`（11 文件 +16/-15）：按 `packaging/pyinstaller/version_info.txt` 为冻结版本源，同步全链路：

- `.github/workflows/build.yml`（inputs.version 描述与默认值）、`.github/workflows/release.yml`（注释、manual dispatch 默认值 `v1.2.0`）
- `backend/src/pelican_town_specials/api/app.py`（FastAPI `version="1.2.0"`）
- `backend/src/pelican_town_specials/observability/diagnostics.py`（`APP_VERSION = "1.2.0"`）
- `packaging/installer/PelicanTownSpecials.iss`（`PtsAppVersion "1.2.0"`）
- `packaging/pyinstaller/version_info.txt`（FileVersion/ProductVersion 1.2.0）
- `packaging/release/README.txt`（`PelicanTownSpecials-Setup-v1.2.0.exe`）
- `scripts/build_installer.ps1`（`-Version` 默认值）
- 锁定测试：`tests/repo/test_release.py`（`_frozen_version() == "1.2.0"`）、`tests/repo/test_app_icon.py`

OpenAPI 契约再生成：`scripts/export_openapi.py` 重写 `frontend/openapi.json`（`"version": "1.2.0"`），`pnpm --dir frontend contract:generate` 再生成 `schema.d.ts`。首次本地 build 的 drift 门失败为预期：门禁语义是「工作树契约与已提交源同步」，需先提交版本提升（CI 检出已提交状态的等价物），提交后重跑即通过。

## 本地全量验证

| 门禁 | 结果 |
|---|---|
| 版本锁定测试（test_release.py + test_app_icon.py） | 11 passed |
| backend + repo + integration 全量 | **724 passed / 2 skipped** |
| ruff | All checks passed |
| mypy（backend/src，87 文件） | Success: no issues found |
| build_windows.ps1 | exit 0：backend 690 passed/2 skipped → Vitest 122 passed → frontend build → OpenAPI drift OK → repo ignore policy OK → PyInstaller onedir → EXE icon gate（32px hash `3FE51DEB…`）→ EXE 版本身份 ProductVersion/FileVersion 1.2.0 → release content gate |
| smoke_windows_bundle.ps1 | Phase A OK（health + 静态首页）；Phase B OK（自检退出 0，无残留 runtime lock） |
| build_installer.ps1 | exit 0：setup exe icon gate（`3FE51DEB…`）→ ProductName/1.2.0 → SHA-256 `1A8CC5FB19E0908C2BF6CBDE420E104513FF6270AC126B9C6F30319FA59AD3F3` |
| smoke_installer.ps1 | **全流程通过**：silent install（程序 + 开始菜单快捷方式，桌面快捷方式正确缺席）→ 安装版 health OK → silent reinstall（升级路径，app 与 workspace 保留）→ silent uninstall（程序 + 快捷方式移除，workspace 保留）。M8 期间唯一遗留门禁已解除 |

## 发布（已完成，2026-08-14）

1. push `feat/mvp-implementation`（33dd204..3604713，11 提交：M8 全部 Task + `3b6ea33` 版本提升 + 控制面记录）——用户已授权。
2. `git tag -a v1.2.0` → push tag 触发 `release.yml`（run **31769766198 success**）：resolve-version → verify-and-build（build.yml 全门禁 + 漂移门）→ create-release（setup.exe + 便携 ZIP + SHA256SUMS + 中文 release notes）。
3. GitHub Release **v1.2.0** 已发布（2026-08-14 04:37 UTC，title「Pelican Town Specials v1.2.0」），产物：
   - `PelicanTownSpecials-Setup-v1.2.0.exe`（42,705,029 B）
   - `PelicanTownSpecials-windows-x64-v1.2.0.zip`（47,485,062 B）
   - `SHA256SUMS.txt`（212 B）
4. 产物核验：经 API `Accept: application/octet-stream` 下载三个资产（本机无 gh CLI、私有仓库、github.com 直链 404，改走 API 端点成功），`Get-FileHash` 与 SHA256SUMS.txt 比对 **两个产物均 OK**。
5. 分支 push 触发的 CI run 31769757384 亦 success。

Session 关闭。用户可选：从 GitHub Release v1.2.0 下载 fresh-install 复验（setup.exe，SHA256SUMS 已核验一致）。

## 范围

本 Session 只做版本提升、契约再生成、本地全量验证与发布；不新增产品功能、不改业务代码逻辑。M8 功能验收合同（Task 27–29 Acceptance Ledger）不变。
