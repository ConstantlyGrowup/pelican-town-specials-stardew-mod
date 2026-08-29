# Session｜M10 Task 39 Release 注入、看板、全链路与打包验收

| 字段 | 值 |
|---|---|
| session_id | `2026-08-27-milestone-10-task-39-release-telemetry-e2e` |
| status | `committed / milestone accepted` |
| session_type | `task-implementation` |
| owner | Codex 主 Agent（M10 全量接管） |
| started_at | `2026-08-27` |
| implementation_started | `true` |
| user_authorization | `2026-08-27 用户明确授权开始 M10 开发并要求继续` |
| base_commit | `3600d09 feat: record anonymous product usage events` |
| acceptance_contract_id | `mvp-m10-task-39-release-telemetry-e2e-v1` |
| revise_round | `4` |
| context_packet | `docs/plans/2026-08-27-task-39-release-telemetry-e2e-packet.md`（gitignored） |

## 目标与边界

本 Session 只完成 Task 39：Release Repository Variables 到 gitignored telemetry resource 的可复现注入、CI/smoke 零生产污染、fake collector 全链路、包内容门禁、PostHog 看板契约/人工核验入口和 GitHub Release 下载量旁证。不得修改前端、OpenAPI、用户文档或版本号，不得 push、tag、创建 GitHub Release，也不得把 PostHog 管理 API key 放入仓库、workflow 或 EXE。

外部 PostHog project、IP discard、实际 dashboard、Repository Variables 和标记测试安装需要项目维护者账号与管理权限；本 Task 实现并自动验证所有本地契约，但不伪造外部证据。它们保留为 M10 联合人工验收项。

用户既存 `backend/src/pelican_town_specials/domain/canonical.py` 阈值 `0.80` 继续隔离，不属于本 Task 或 focused commit。

## 当前进度

- Task 37 commit：`d198a3e feat: add lightweight release telemetry core`，未 push。
- Task 38 detector round 2 PASS，commit：`3600d09 feat: record anonymous product usage events`，未 push。
- Task 39 字段、构建接口、文件、测试和外部验收边界已闭包；Packet 状态 `READY_FOR_IMPLEMENTATION`。
- 下一步：派 fresh `luna_worker`（gpt-5.6-luna/max）实施 round 0；worker 不提交、不 push。
- worker round 0 已完成本地 patch；主 focused `16 passed`，全量后端/仓库/集成排除两条 canonical 旧阈值断言后 `899 passed / 2 skipped / 2 deselected`，frontend `149 passed`，lint/build/OpenAPI、onedir build 与 bundle smoke、installer build 均通过。
- 主 Agent在 installer smoke 前发现安全缺口：脚本会覆盖并卸载真实默认安装目录，权限审查因此拒绝执行。进入 revise round 1：改用显式 `/DIR` 与唯一 `/GROUP` 的验证后临时安装根、隔离 workspace 和严格清理，再复跑 smoke。
- revise round 1 focused `17 passed`；live smoke 证明 `/DIR` 已安全落入验证后的临时根，但带空格并内嵌引号的 `/GROUP` 未被 Inno 按预期采用，唯一组快捷方式缺失。脚本安全退出并清理隔离目录；进入 round 2，改用无空格唯一 group 参数并复跑。
- revise round 2 focused `17 passed`；无空格 `/GROUP` 在同一 AppId 下仍未产生预期唯一组。为杜绝开始菜单副作用，round 3 改为 `/NOICONS` + 临时 `/DIR` + 直接启动隔离 EXE；M7 已验收的快捷方式契约保留在既有静态测试/历史证据，本 Task 不再重复写真实开始菜单。
- revise round 3 focused `17 passed`；live installer smoke PASS：临时 `/DIR` 安装、无 shortcut/group、两次健康启动与持久 SQLite、同目录重装、卸载、隔离 workspace marker 保留和最终严格清理全部通过。
- 主 Agent完整证据：全量 backend/repo/integration `899 passed / 2 skipped / 2 deselected`（仅排除用户 canonical 0.80 对应两条旧 0.90 断言）；frontend `149 passed`、lint/build、OpenAPI drift、Ruff/mypy、dashboard validator、onedir build/content gate、bundle smoke、installer build/smoke 均 PASS。当前等待 fresh detector round 3。
- detector round 3 `REVISE`：T39-001..008 与 R01..R10 PASS；唯一 must-fix 是 production AppId 可能复用既有当前用户卸载注册，即使 `/DIR + /NOICONS` 已隔离文件。进入 round 4：setup 前精确检查该 AppId 的 HKCU 32/64 位卸载项，存在即拒绝且绝不删除；隔离卸载后断言两视图均无残留。
- round 4 focused `18 passed`；主 Agent live installer smoke PASS：exact AppId Registry32/64 preflight 无既有注册后才启动，隔离安装注册存在，卸载后两视图零残留；其余临时安装/重装/SQLite/workspace/telemetry/清理门禁继续通过。等待 fresh detector round 4。
- detector round 4 `PASS`：M10-T39-001..009 与 T39-R01..R10 全部通过，must-fix/optional hardening/new design/scope delta 均为空；独立 focused `18 passed`，并确认 AppId 两视图最终均无注册残留。
- Task 39 已进入 `auto_accepted`；创建本地 focused commit 后，M10 进入 `awaiting_milestone_acceptance`。外部 PostHog project/IP discard/dashboard、Repository Variables 和标记测试事件仍为联合人工验收项。

## Milestone 验收（2026-08-29）

- 用户已完成三个 GitHub Repository Variables 配置，并明确接受 personless 验收事件直接进入聚合统计；初期测试安装和少量测试操作可能短暂影响 DAU/成功率，但无需 Cohort 或额外 `test_channel` 协议。
- 用户明确授权 M10 统一 push、版本提升和发布新的 GitHub Release；该授权同时覆盖 branch push、`v1.4.0` tag 与由 tag 触发的 Release workflow。
- Task 39 focused commit 已存在：`c4c1bcf test: verify release telemetry end to end`。M10 Task 37–39 至此全部通过独立审阅并获用户联合验收。
- PostHog 管理 Personal API Key 不属于运行或发布依赖，不进入 Repository Variables、workflow 或 EXE。实际事件、IP discard 和看板显示在 v1.4.0 安装运行后核验。
