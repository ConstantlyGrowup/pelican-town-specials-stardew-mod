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

## 验证记录

- 实施子代理 TDD：RED 先行确认（`test_fourth_generation_rejected_busy_with_zero_side_effects` 在旧实现下 `KeyError: 'activeCount'`，API 层同型失败），GREEN 后 focused generation 测试 **30 passed**（6 个新增三路生命周期测试 + registry/cancellation 回归）；api/application/static 测试 **28 passed, 1 pre-existing skip**。
- 全量 backend：**674 passed / 2 skipped**（2 个均为既有 symlink 权限跳过）；2 warnings 为预存 zip 重复条目。
- 包工复跑：全量 backend 再跑 **674 passed / 2 skipped**；ruff **All checks passed**；mypy（2 个改动源文件）Success（实施期另跑全 src 87 文件亦 clean，Packet 记录的 exports.py/app.py 预存错误未复现）；`git diff --check` clean。
- 源码改动核验：`_busy_error(registry, draft_id)` details 恒定含 activeCount/maxConcurrent/draftId，消息文案、HTTP 409、retryable 不变；`app.py` activity 行改 `active_count() > 0`；`SlotOwner` 导入移除、`MAX_CONCURRENT_GENERATIONS` 导入新增；仅 6 个 allowed_files 变动，未越界。
- 人工核验（经新测试断言）：barrier 证明三路同一时刻都在 Provider 内（active_count==3）；第四请求零副作用（attempt 目录计数、草稿状态、Provider 调用计数均不变）；取消/失败/删除只释放对应槽（active_count 3→2，其余路仍 RUNNING，第四草稿立即可开始）；三路中断开只 detach（断开任务继续到 REVIEWABLE）；三槽占用时 idle monitor 不空闲退出。

## 审阅记录

- Codex（gpt-5.6-luna/max，新 thread，只读）：round 0 **PASS**，5/5 criterion（T28-001..T28-005），无 MUST_FIX，scope_delta none，planning_rulings R-01..R-03 全部检查通过。
- OPTIONAL_HARDENING（非阻塞）：① 只读环境无法复跑需写临时目录的 pytest/mypy，交接证据由包工复跑确认；② STATUS.md 已 active 但规划索引仍写 awaiting confirmation —— 已同步：AGENTS.md 当前工作模式段落与 M8 规划文档头部更新为 ACTIVE。
- 结论：auto_accepted → 本地 focused commit（不 push）。
