# Session｜Milestone 8 Task 28 生成生命周期与 API 上限提示

| 字段 | 值 |
|---|---|
| session_id | `2026-08-14-milestone-8-task-28-generation-lifecycle` |
| session_type | `milestone-8-task-28-implementation` |
| status | `active` |
| owner | Claude Code 主会话（包工）+ 实施子代理 + Codex 审阅 |
| started_at | `2026-08-14` |
| base_commit | `cdef3e6 docs: record M8 Task 27 auto_accepted` |
| acceptance_contract_id | `mvp-m8-task-28-generation-lifecycle-v1` |

## 范围与边界

本 Session 只处理 Task 28：把 orchestrator、activity monitor 与 API 错误细节接入三槽 AttemptRegistry。源码改动仅两处（`orchestrator.py` 的 `_busy_error` 及调用点、`api/app.py` 的 activity 行）；其余生命周期接线（按 attemptId 键控的 cancel/task/对账/删除/服务端 task finally）由 Task 27 预留，经验证无需改动。前端提示与完整并发验收属 Task 29。

## 验收项（来自 Context Packet `mvp-m8-task-28-generation-lifecycle-v1`）

- T28-001 三个 fake Provider 生成链路真实重叠（barrier）；阶段与终态分别落到对应草稿。
- T28-002 第 4 个请求返回稳定 PTS_GEN_BUSY（409），details 含 activeCount/maxConcurrent，不创建 attempt、不改草稿、不调 Provider。
- T28-003 完成、失败、取消和删除只释放对应槽；释放后新的手动请求立即开始。
- T28-004 三任务中客户端断开仍只 detach；存在任意 active attempt 时应用不空闲退出。
- T28-005 既有 backend 全量回归保持通过。

## 规划裁决

- R-01 busy details 形状：`_busy_error(registry, draft_id)` 恒定输出 activeCount（active_count()）、maxConcurrent（MAX_CONCURRENT_GENERATIONS）与 draftId（被拒请求草稿）；同草稿场景值与 Task 27 断言一致。
- R-02 activity monitor：`app.py:407` 从 `owner() is not None` 改为 `active_count() > 0`。
- R-03 最小改动：其余接线已满足 M8-D02/D05/D06，不改动。

## 验证记录（实施后填写）

## 审阅记录（实施后填写）

## 结论（实施后填写）
