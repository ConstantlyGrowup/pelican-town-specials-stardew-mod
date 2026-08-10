# Session｜Milestone 7 Task 24 GitHub Release auto-publish

| 字段 | 值 |
|---|---|
| session_id | `2026-08-10-milestone-7-task-24-release` |
| session_type | `milestone-7-task-24-implementation` |
| status | `in_progress` |
| owner | Codex 主会话（Claude Code 主会话实施 + Codex 独立审阅） |
| started_at | `2026-08-10` |
| user_acceptance | `pending` |
| base_commit | `5f54516 feat: add Windows per-user installer wrapping the validated onedir` |

## 任务范围

按 `docs/plans/2026-08-10-milestone-7-refine.md` Task 24：为 GitHub Release 提供
自动发布入口（tag/manual 触发），生成 checksum、release notes，使用最小写权限。
**不实现 Task 23 的 installer 逻辑变更、Task 25/26 双语。**

## 协作模式

用户 2026-08-10 确认：主会话（Claude Code）直接实施 + 自动验证；完成后拉起
Codex MCP 独立审阅（`gpt-5.6-luna` / max effort，新 thread）；PASS → auto_accepted
→ 本地 focused commit；里程碑粒度不打断用户。

## 实施进度

- [ ] 生成 Context Packet（planning_status: READY_FOR_IMPLEMENTATION）。
- [ ] 实现：Release workflow（tag/manual 触发）、checksum、release notes、最小写权限。
- [ ] 验证：workflow 语法、权限/产物检查、本地 checksum 与 release notes 生成。
- [ ] Codex 独立审阅（gpt-5.6-luna/max，新 thread）→ PASS → auto_accepted → 本地 focused commit。
- [ ] 更新本 Session 记录与 STATUS.md。

## 范围说明

- Task 25/26（双语）不实施；不创建真实 GitHub Release（仅 workflow 就绪 + 本地验证）。
- 不运行真实 Provider。
