# Session｜Milestone 8 Task 27 三槽 AttemptRegistry

| 字段 | 值 |
|---|---|
| session_id | `2026-08-14-milestone-8-task-27-slot-registry` |
| session_type | `milestone-8-task-27-implementation` |
| status | `active` |
| owner | Claude Code 主会话（包工）+ 实施子代理 + Codex 审阅 |
| started_at | `2026-08-14` |
| base_commit | `33dd204 docs: record Milestone 7 closure` |
| acceptance_contract_id | `mvp-m8-task-27-slot-registry-v1` |

## 范围与边界

本 Session 只处理 Task 27：把 `AttemptRegistry` 从单一可归属 `SlotOwner` 扩展为最多 3 个、以 `attemptId` 为键、彼此隔离的 owner 集合。不修改领域 schema、orchestrator、service、API、前端或持久化。

Task 28 承接 orchestrator/删除/activity/API 上限提示接线；Task 29 承接前端提示与完整并发验收。

## 验收项（来自 Context Packet `mvp-m8-task-27-slot-registry-v1`）

- T27-001 前三个不同 attempt 均能成功保留槽；第四个被拒绝，且 active count 不超过 3。
- T27-002 owner、task、cancellation 按 attemptId 隔离；`release_slot(attemptId)` 只释放匹配 owner。
- T27-003 释放、重复释放、迟到释放不会误伤其他 owner。
- T27-004 陈旧持久化 owner（终态或记录缺失）可逐项对账回收；仍 RUNNING 的 owner 不被扫除。
- T27-005 同一草稿仍最多一个 active attempt；重复请求不能绕过并发限制。
- T27-006 进程级 `asyncio.Semaphore` 容量提升为 3，支持三路生成阶段循环真实重叠。
- T27-007 既有 backend 全量回归保持通过（same-draft busy 语义不变）。

## 验证记录

（由包工在 PASS 后填写 focused 测试、全量回归、ruff/mypy、diff-check 结果）

## 审阅记录

（round 0 / round 1 PASS 结论与 MUST_FIX 处理由包工填写）
