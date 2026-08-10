# Session｜Milestone 7 Task 23 per-user installer

| 字段 | 值 |
|---|---|
| session_id | `2026-08-10-milestone-7-task-23-installer` |
| session_type | `milestone-7-task-23-implementation` |
| status | `auto_accepted` |
| owner | Codex 主会话（Claude Code 主会话实施 + Codex 独立审阅） |
| started_at | `2026-08-10` |
| user_acceptance | `auto_accepted`（里程碑粒度；用户一次性验收在 M7 全量验证时） |
| base_commit | `7286c74 feat: add Gus portrait app icon and EXE identity gate` |
| accepted_at | `2026-08-10`（Codex round 1 PASS） |

## 任务范围

按 `docs/plans/2026-08-10-milestone-7-refine.md` Task 23：把已验证的
`PelicanTownSpecials-windows-x64` onedir bundle 包装为单个 Windows per-user
installer。**不实现 GitHub Release（Task 24）、双语（Task 25/26）。**

验收条件（Acceptance Ledger，见 Context Packet `mvp-task-23-installer-v1`）：
- `M7-T23-INSTALL-001`：干净 Windows 10/11 x64 用户无需 Python/Node/Git 或
  管理员权限完成安装。
- `M7-T23-INSTALL-002`：安装后快捷方式启动 app/browser，health smoke 通过，
  工作区默认位置正确。
- `M7-T23-INSTALL-003`：卸载后程序文件和快捷方式消失，用户 workspace 保留。
- `M7-T23-INSTALL-004`：升级/重复安装不会把 workspace 当作安装目录删除；
  安装失败不留半成品快捷方式。
- `M7-T23-INSTALL-005`：installer 内容 gate 拒绝 secrets、`.env`、tests、
  samples、设计资料、workspace 和 source maps。

规划裁决 M7-D01/D02：installer 包裹现有 onedir；默认 per-user 安装到
`%LOCALAPPDATA%\Programs\PelicanTownSpecials`，无管理员权限；卸载保留
workspace。推荐评估 Inno Setup；工具不作为用户运行时依赖。

## 协作模式

用户 2026-08-10 确认：主会话（Claude Code）直接实施 + 自动验证；完成后拉起
Codex MCP 独立审阅（`gpt-5.6-luna` / max effort，新 thread）；PASS → auto_accepted
→ 本地 focused commit；里程碑粒度不打断用户。

## 实施进度

- [x] 生成 Context Packet `mvp-task-23-installer-v1`（planning_status: READY_FOR_IMPLEMENTATION，base_commit `4333267`）。
- [x] 评估并锁定 installer 方案（Inno Setup 6.7.3，官方 GitHub release URL + SHA-256 `9c73c3ba…` 固定，`/CURRENTUSER` 静默安装到 tools 目录）。
- [x] 实现：`packaging/installer/PelicanTownSpecials.iss`（`PrivilegesRequired=lowest`、`{localappdata}\Programs\PelicanTownSpecials`、`x64os`、`MinVersion=10.0`、Gus icon、start-menu 必建/desktop 可选、无 `[UninstallDelete]`）；`scripts/release_content_gate.ps1`（共享 `Test-ReleaseContent`，新增 `*.map` 拒绝、Root 绝对化）；`scripts/install_innosetup.ps1` / `find_iscc.ps1` / `build_installer.ps1` / `smoke_installer.ps1`；`build_windows.ps1` 改接共享 gate；`tests/repo/test_installer.py`（8+1 条合同门禁）；`ci.yml` 增加 Inno Setup 安装、installer 构建/冒烟与产物上传；`packaging/release/README.txt` 安装/卸载说明。
- [x] 验证：`tests/repo` 22 passed；全量 backend+repo+integration **680 passed / 2 skipped**；ruff/mypy clean；`smoke_installer.ps1` 全流程通过（静默安装 → 快捷方式解析校验 + 经快捷方式启动 health → GUID marker 唯一化 → 静默重装保持 app+marker → `unins000.exe` 卸载移除程序/快捷方式并保留真实 workspace），机器返回干净状态（无残留 marker、install 目录/快捷方式消失、真实用户 workspace 保留）。
- [x] Codex 独立审阅（gpt-5.6-luna/max，新 thread）：round 0 REVISE（2 项 MUST_FIX）→ 修复 → round 1 **PASS**（5/5 criterion，无 MUST_FIX）→ auto_accepted。
- [x] 更新本 Session 记录与 STATUS.md。

## 审阅记录

- round 0 REVISE（revise_round 0）MUST_FIX：
  1. `M7-T23-INSTALL-002`：smoke 直接启动 exe，未真正演练快捷方式 → 修复为 `WScript.Shell` 解析并校验快捷方式（`TargetPath` == 安装 exe、`WorkingDirectory` == 安装目录，`FinalReleaseComObject` 释放），health 探针**经快捷方式**启动。
  2. `M7-T23-INSTALL-003`：固定 marker 路径可能覆盖/删除真实用户文件 → 修复为每轮唯一 marker（`.pts-smoke-marker-<Guid>.txt`）；`finally` 只删除本轮创建且清空的目录（预存目录集合追踪，`%LOCALAPPDATA%\PelicanTownSpecials` 下预存目录绝不删除）。
- round 1 PASS：`checked_criteria` 001–005 全过；`planning_rulings_checked` R-01..R-06；`scope_delta: none`；`implementation_scope_delta: none`。
- OPTIONAL_HARDENING（非阻塞，未纳入本 Task）：① `%TEMP%\pts-setup.log` 固定路径可后续唯一化/守卫；② README 隐私措辞可进一步明确生成请求会传输图片。
- 规划裁决 `R-06`（workspace 路径准确性）：实测 platformdirs 4.10.0 在 Windows 上将 `user_data_dir("PelicanTownSpecials")` 展开为**双重**路径 `%LOCALAPPDATA%\PelicanTownSpecials\PelicanTownSpecials\workspace`（appauthor 默认取 appname），即 app 冻结的真实默认 workspace；Task 23 不改变 app 路径（R-01）。smoke 改为经 `_default_workspace_path()` 探测真实路径放置 marker，README 改引用 app 数据目录 `%LOCALAPPDATA%\PelicanTownSpecials` 而非错误的单一子路径。双重路径本身记录为候选后续项（产品级，可能未来 Task 显式传 `appauthor`），M7 验收时向用户呈现。

## 范围说明

- Task 24（GitHub Release）、Task 25/26（双语）不实施。
- 不运行真实 Provider；不创建 GitHub Release。
- 安装器不改变 app 运行时、workspace 逻辑、domain/persistence/API/Mod 协议。
