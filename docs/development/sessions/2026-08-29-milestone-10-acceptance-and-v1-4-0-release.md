# Session｜Milestone 10 验收与 v1.4.0 Release

| 字段 | 值 |
|---|---|
| session_id | `2026-08-29-milestone-10-acceptance-and-v1-4-0-release` |
| status | `closed` |
| date | `2026-08-29` |
| scope | M10 用户联合验收、v1.4.0 版本提升、本地干净构建验证、branch/tag push 与 GitHub Release 核验 |
| base_commit | `c4c1bcf test: verify release telemetry end to end` |

## 用户授权与统计口径

- 用户明确授权推送 M10 代码、提升版本并发布新的 GitHub Release。
- 下一功能版本采用 `v1.4.0`，发布范围包含已推送但尚未进入正式 Release 的 M9、Task 36.1/36.2，以及本地 M10 Task 37–39。
- 用户接受首次人工验收数据作为普通 personless 匿名事件参与聚合，不要求 Cohort 或测试渠道排除；该选择不改变事件 schema、运行配置或隐私 allowlist。
- GitHub Repository Variables 已由用户配置；不需要也不得把 PostHog Personal API Key 注入 Release。

## 发布边界

- 版本链同步：PyInstaller/installer、FastAPI/diagnostics、workflow defaults、release README、下载旁证默认 tag、锁定测试和生成 OpenAPI。
- 用户随后明确接受 Canonical 阈值 `0.90 → 0.80` 的召回率/误命中权衡，并要求纳入发布；校准实现、边界测试与正式设计同步已通过 worker/main/detector 验收，focused commit 为 `23d16c3`。
- 本地发布候选必须从 committed HEAD 的干净 worktree 构建；本地 telemetry 使用 fake public config 验证包内容，不向真实 PostHog 发送事件。真实 Repository Variables 只由 GitHub Release workflow 注入。
- 发布产物必须包括 setup.exe、portable ZIP 和 SHA256SUMS.txt；workflow 与资产校验完成后再关闭本 Session。

## 本地发布候选验收

- v1.4.0 版本链提交：`11cb287`；OpenAPI 契约、PyInstaller/installer 版本身份、workflow defaults、release README 和锁定测试一致。
- 隔离 worktree 从 committed HEAD 构建，注入的 telemetry 仅为 `telemetry.example.com` + fake public token；真实 Repository Variables 未在本地读取或写入产物。
- backend/repo/integration 最终结果：`904 passed, 2 skipped`；Ruff PASS；mypy 96 source files PASS。
- frontend：Vitest `149 passed`、Playwright `34 passed`、ESLint/locale/build/OpenAPI drift PASS。
- Windows onedir：PyInstaller、内容 gate、Gus icon、ProductVersion/FileVersion 1.4.0 均 PASS；两次干净启动成功创建并复用非空 `registry.sqlite3`。
- installer：Inno Setup 6.7.3 编译 PASS；本地 setup SHA-256 `B117235D63737163BE9992AE803D571CF02DCCE712733FBCF9E61A770B58FF7A`；隔离 install → health → reinstall → uninstall PASS，未创建快捷方式且 workspace marker 保留。
- 完整套件发现旧 `test_installer.py` 仍要求脚本访问真实默认 workspace；仅更新该静态契约以验证临时 `/DIR`、`/NOICONS` 和隔离 workspace。`luna_worker` focused tests `9 passed`、Ruff PASS；detector `release-gate-r0` 最终 `PASS`，无 must-fix/optional/scope delta。

## 发布结果

- 发布门禁修订与候选验收记录提交：`0673221 test: align isolated installer release gate`；`feat/mvp-implementation` 已从 `8d30aae` 推送至 `0673221`。
- annotated tag `v1.4.0` 精确指向 `0673221ab05a2ba392fc8d53133d2c9bf29e2075` 并已推送。
- GitHub Actions run `33228870083`：`resolve-version`、`verify-and-build / verify-and-build`、`create-release` 全部 `success`；发布流程在 2026-08-29 02:39:05 UTC 完成。
- GitHub Release `Pelican Town Specials v1.4.0` 已发布，`isDraft=false`、`isPrerelease=false`。
- `PelicanTownSpecials-Setup-v1.4.0.exe`：43,497,036 B；SHA-256 `9e64b59b8b5ef25452d1533d242aea3c610d569b70ec7dcd9fc8b07cb39e3d15`。
- `PelicanTownSpecials-windows-x64-v1.4.0.zip`：48,525,527 B；SHA-256 `423aadc618ae51f8f31dc12cebc66f7a07d5cd78a12f9c41f0efdbf381ef07c6`。
- `SHA256SUMS.txt`：212 B；下载 setup/ZIP 后重新计算的 SHA-256 与该文件和 GitHub asset digest 均逐一一致。
- Session 关闭。发布后可选人工检查：安装 v1.4.0，确认 PostHog 首批 personless 事件、IP discard 和内部看板；这不是本次 Release 的阻塞项。
