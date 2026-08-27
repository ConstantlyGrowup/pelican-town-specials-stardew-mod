# Session｜M10 Task 38 核心业务事件接入

| 字段 | 值 |
|---|---|
| session_id | `2026-08-27-milestone-10-task-38-core-business-telemetry` |
| status | `committed` |
| session_type | `task-implementation` |
| owner | Codex 主 Agent（M10 全量接管） |
| started_at | `2026-08-27` |
| implementation_started | `true` |
| user_authorization | `2026-08-27 用户明确授权开始 M10 开发` |
| base_commit | `d198a3e feat: add lightweight release telemetry core` |
| acceptance_contract_id | `mvp-m10-task-38-core-business-telemetry-v1` |
| revise_round | `2` |
| context_packet | `docs/plans/2026-08-27-task-38-core-business-telemetry-packet.md`（gitignored） |

## 目标与边界

本 Session 只把 Task 37 类型化 recorder 接到生成、拒绝、首次正式存档和导出 terminal 业务事实。无 UI/API/OpenAPI 变化，不修改 Task 37 transport/state/schema，不修改 Canonical 召回或试用额度语义，不开始 Task 39。

用户既存 `backend/src/pelican_town_specials/domain/canonical.py` 阈值 `0.80` 继续隔离，不属于本 Task 或 focused commit。

## 当前进度

- Task 37 已经 worker/main/detector round 3 PASS，并创建本地 focused commit `d198a3e`；未 push。
- 已完成 Task 38 字段、接口、文件、测试和依赖闭包；Packet 状态 `READY_FOR_IMPLEMENTATION`。
- 已冻结 started/trial 时序、pre-attempt rejection、M9 memory mapping、粗错误分类和 archive/export replay 去重裁决。
- worker round 0 已实现 generation/archive/export wiring，focused generation/application `9 passed`、app wiring `7 passed`；主 Agent 独立 focused `16 passed`、Ruff/mypy PASS。
- 主 Agent代码审查进入 revise round 1：总耗时必须从 persisted attempt 开始；startup recovery 不得补造可能重复的 started；terminal 增加 once guard；补 trial true、失败/取消/settings/Provider 后 validation、M9 memory mapping 和 export bucket 边界测试。
- worker round 1：generation focused `20 passed`、application focused `9 passed`、app wiring `7 passed`，组合 focused `36 passed`；Ruff/mypy PASS。
- round 1 修复后：duration 从 persisted attempt 起算；recovery 零 telemetry；terminal once guard；trial true、失败、取消、settings、Provider 后 validation、M9 memory mapping 和所有 export bucket 均有测试。
- 主 Agent独立复跑：focused `36 passed`；application/generation/api 扩大回归排除一条由用户 0.80 阈值导致的旧 0.90 断言后 `359 passed / 1 skipped / 1 deselected`；Ruff、mypy 96 files、OpenAPI drift、frontend 零 diff、diff-check 均 PASS。
- detector round 1 `REVISE`：Provider 已开始后的 `PTS_PROVIDER_AUTH_FAILED` 仍被错误映射为 `generation rejected/settings`，违反“rejected 仅用于 Provider 前拒绝”的冻结口径；其余 T38-001、003–007 PASS，无 scope delta。
- worker revise round 2 已完成最小修复：所有 `provider_started=true` 路径在错误分类前直接返回无 rejection；settings rejection 测试改为 Provider 前 gateway/configuration 失败；新增 Provider 后鉴权失败只产生 started + finished 的回归测试。
- worker 证据：Task 38 focused `37 passed`、相关扩展回归 `106 passed`、Ruff/mypy/diff-check PASS。主 Agent复跑 focused 首次受 pytest 临时目录 ACL 阻塞，改用已批准的沙箱外测试执行后 `37 passed`；Ruff、mypy 96 files PASS。
- 当前等待 fresh `detector` round 2 独立只读审阅；尚未 auto_accept、commit 或开始 Task 39。
- detector round 2 `PASS`：M10-T38-001..007 全部通过，focused `37 passed`，无 must-fix、optional hardening、new design 或 scope delta；Provider 后鉴权失败只产生 started + finished，Provider 前 settings rejection 保持。
- Task 38 已按 Milestone 自动路径进入 `auto_accepted`；下一步只创建本地 focused commit，不 push。
- 本地 focused commit：`3600d09 feat: record anonymous product usage events`；未 push。Task 38 Session 关闭，后续控制面由 Task 39 Session 接管。
