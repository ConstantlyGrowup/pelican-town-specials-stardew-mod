# Session｜M10 Task 37 匿名统计核心、状态与 PostHog sink

| 字段 | 值 |
|---|---|
| session_id | `2026-08-27-milestone-10-task-37-telemetry-core` |
| status | `auto_accepted / committed` |
| session_type | `task-implementation` |
| owner | Codex 主 Agent（M10 全量接管） |
| started_at | `2026-08-27` |
| implementation_started | `true` |
| user_authorization | `2026-08-27 用户明确授权开始 M10 开发` |
| base_commit | `8d30aae docs: close endpoint compatibility tasks` |
| acceptance_contract_id | `mvp-m10-task-37-telemetry-core-v1` |
| revise_round | `3` |
| context_packet | `docs/plans/2026-08-27-task-37-telemetry-core-packet.md`（gitignored） |
| focused_commit | `feat: add lightweight release telemetry core`（本 Session focused commit） |

## 目标与边界

本 Session 只实现 Task 37 的匿名统计核心、安装状态、daily-open、PostHog personless batch sink 和 app lifespan 接线。Task 38 的业务事件接入、Task 39 的 Release 注入/看板/E2E、任何前端/API/OpenAPI/用户文档/发布行为均不在本 Session。

现有 `backend/src/pelican_town_specials/domain/canonical.py` 中用户将阈值从 `0.90` 调为 `0.80` 的未提交改动继续隔离，不属于本 Task，也不得覆盖或提交。

## 当前进度

- 已复核 AGENTS、STATUS、约束、Review Protocol、Context Packet Schema、M10 正式技术设计与实施计划。
- 已核对 PostHog 官方 Capture API 当前 `/batch/`、Cloud host、项目 token 和 `$process_person_profile=false` 契约。
- Context Packet 已完成字段、接口、文件、测试和依赖闭包，状态 `READY_FOR_IMPLEMENTATION`。
- `luna_worker` round 0 完成统计核心与 focused `22 passed`；主 Agent mypy 发现 4 个新代码类型错误，round 1 修复后 mypy 96 files PASS。
- 主 Agent round 1 代码审查发现两项冻结契约缺口：无持久化 installation ID 时可能生成临时发送 ID；state sidecar lock 最多等待 5 秒。round 2 已改为无持久化 ID 即 Noop、锁竞争非阻塞 fail-open，并补两条针对性回归。
- 主 Agent round 2：focused `24 passed`；全后端排除两条由用户既存 Canonical 阈值 `0.80` 直接导致的冻结 `0.90` 测试后 `800 passed / 2 skipped / 2 deselected`；完整 Ruff、mypy 96 files、OpenAPI drift、frontend 零 diff、diff-check 均 PASS。
- `detector` round 2 返回 REVISE：队列容量测试未注入 fake transport，shutdown 会使用 fake token 尝试真实 PostHog host；唯一 must-fix 为该测试改用 `httpx.MockTransport`，确保自动测试零外网。
- worker round 3 仅修改该测试：5 个 batch 全由 `httpx.MockTransport` 截获，并断言保留事件为 `duration 1..100`；主 Agent focused `24 passed`。
- `detector` round 3：`PASS`；M10-T37-001..007 全部 PASS，`must_fix: []`、`optional_hardening: []`、`new_design: []`、`scope_delta: none`。
- Task 37 按 Milestone 自动路径进入 `auto_accepted` 并创建本地 focused commit；不 push、不提升版本、不 tag、不发布。
