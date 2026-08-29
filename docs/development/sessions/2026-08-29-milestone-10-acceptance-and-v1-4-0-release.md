# Session｜Milestone 10 验收与 v1.4.0 Release

| 字段 | 值 |
|---|---|
| session_id | `2026-08-29-milestone-10-acceptance-and-v1-4-0-release` |
| status | `release_in_progress` |
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

## 待执行

- 提交发布门禁修订与本验收记录。
- push `feat/mvp-implementation`，创建并 push `v1.4.0` tag。
- 等待 `release.yml`，核验 setup.exe、portable ZIP、SHA256SUMS.txt 和 Release 状态后关闭 Session。
