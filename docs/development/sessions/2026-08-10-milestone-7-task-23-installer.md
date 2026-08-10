# Session｜Milestone 7 Task 23 per-user installer

| 字段 | 值 |
|---|---|
| session_id | `2026-08-10-milestone-7-task-23-installer` |
| session_type | `milestone-7-task-23-implementation` |
| status | `in_progress` |
| owner | Codex 主会话（Claude Code 主会话实施 + Codex 独立审阅） |
| started_at | `2026-08-10` |
| user_acceptance | `pending` |
| base_commit | `7286c74 feat: add Gus portrait app icon and EXE identity gate` |

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

- [ ] 生成 Context Packet `mvp-task-23-installer-v1`（planning_status: READY_FOR_IMPLEMENTATION）。
- [ ] 评估并锁定 installer 方案（Inno Setup 或等效，可版本化 CI 安装）。
- [ ] 实现：installer 脚本/配置、per-user 安装目录、快捷方式（Gus icon）、卸载保留
      workspace、内容 gate。
- [ ] 验证：安装/启动/health/卸载/重复安装、release 内容 gate。
- [ ] Codex 独立审阅（gpt-5.6-luna/max，新 thread）→ PASS → auto_accepted → 本地 focused commit。
- [ ] 更新本 Session 记录与 STATUS.md。

## 范围说明

- Task 24（GitHub Release）、Task 25/26（双语）不实施。
- 不运行真实 Provider；不创建 GitHub Release。
