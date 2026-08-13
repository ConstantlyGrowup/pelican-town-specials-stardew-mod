# Session｜Milestone 8 三路并发生成规划

| 字段 | 值 |
|---|---|
| session_id | `2026-08-13-milestone-8-generation-concurrency-planning` |
| session_type | `milestone-8-planning` |
| status | `planned / awaiting_user_confirmation` |
| owner | Codex 主会话 |
| started_at | `2026-08-13` |
| implementation_started | `false` |
| user_acceptance | `pending` |
| base_commit | `33dd204 docs: record Milestone 7 closure` |

## 用户最终方向

用户说明多次生成均通过 API，链路本质上可以按 attempt/draft 隔离；不希望为当前本地小项目引入中大型队列重构。Milestone 8 改为：最多同时运行 3 个任务，第 4 个请求立即提示并中断发起；完整排队机制留到未来分布式消息队列等高级后端架构。

此前同 Session 中形成的“5 槽 + 持久化 FIFO + QUEUED”草案未获确认，已整体撤回，不作为项目设计或实施依据。

## 可行性结论

可行，属于小到中等改造。现有 `AttemptRegistry` 已具备按 attemptId 归属、task/cancel 跟踪和持久化终态对账，只需将单 owner 扩展为最多 3 个 owner，并系统验证 orchestrator、取消、删除、进度与空闲退出在多 owner 下相互隔离。

不新增 Draft/Attempt 状态、不迁移 JSON、不建立队列 API、不增加 Dashboard 队列中心。

## Task 拆分

| Task | 主题 | 依赖 | 状态 |
|---|---|---|---|
| 27 | 三槽 AttemptRegistry | M7 | planned |
| 28 | 生成生命周期与 API 上限提示 | 27 | planned |
| 29 | 前端提示与完整并发验收 | 28 | planned |

详细范围见 `docs/plans/2026-08-13-milestone-8-generation-concurrency.md`。

## 验证边界

- 第 1–3 个任务可并行，第 4 个在创建 attempt、改变草稿状态和调用 Provider 前被拒绝。
- 完成、失败、取消、删除和迟到 cleanup 按 attemptId 隔离释放。
- 三草稿进度、刷新恢复和取消不串线；busy 提示中英文清楚。
- 不运行真实 Provider；最终以 fake provider barrier、全量回归和 Windows smoke 验证。

## 当前状态

只更新规划与控制面，没有产品源码改动、Context Packet、stage、commit 或 push。等待用户确认后再创建 Task 27 实施 Session。
