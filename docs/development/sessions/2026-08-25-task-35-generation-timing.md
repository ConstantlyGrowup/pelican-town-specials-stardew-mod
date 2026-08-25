# Session｜Milestone 9 Task 35 Generation Timing and Gus Storytelling

| 字段 | 值 |
|---|---|
| session_id | `2026-08-25-task-35-generation-timing` |
| status | `auto_accepted` |
| session_type | `milestone-9-task-implementation` |
| owner | Codex 主 Agent（M9 临时全量接管） |
| started_at | `2026-08-25` |
| implementation_started | `true` |
| user_acceptance | `milestone authorization granted; task auto-accept path` |
| base_commit | `0cda23d feat: reuse canonical dishes in Ask Gus generation` |
| acceptance_contract_id | `m9-task-35-generation-timing-v1` |
| revise_round | `1` |
| context_packet | `docs/plans/2026-08-25-task-35-generation-timing-packet.md`（gitignored） |

## 目标

从既有 generation progress 的 terminal attempt 恢复总耗时，在 Ask Gus 和 Blueprint 成功结果上显示紧凑双语卡片；仅 Ask Gus `CANONICAL_REUSED` 使用已冻结 Gus 叙事，不暴露技术细节。

## 冻结范围

- Acceptance Ledger：M9-T35-001..008；planning rulings：R01..R08。
- 不修改后端、OpenAPI、Registry、Provider、生成动作或页面操作。
- 使用 `vercel:react-best-practices` 做多 TSX 组件的最终质量检查。

## 实施结果

- 新增共享 `GenerationTimingBadge`，总耗时只由 generation progress terminal `SUCCEEDED` attempt 的 `finishedAt-startedAt` 得出；小于 10 秒保留一位，其余四舍五入整数秒，无效/非成功数据不展示。
- generation store/hook 支持页面挂载、刷新、切页和本地 NDJSON 成功后的只读恢复；新 attempt、active、失败和取消均清除旧 timing，不发起新生成。
- Ask Gus 仅在当前 DraftView `generationSource=CANONICAL_REUSED` 时显示冻结 Gus 叙事；fresh/miss/full regenerate 与所有 Blueprint 结果只显示中性计时。
- 中文/英文 copy、非颜色 marker、aria label 和窄屏换行完整；Ask Gus 三操作及 Blueprint 编辑/预览/存档行为未改变。
- `vercel:react-best-practices` 检查落实：直接导入、无 inline component、无 derived-state effect、稳定 hooks 依赖、瞬态请求状态使用 refs、无新数据依赖或无意义 memoization。

## 审阅与返工

- detector round 0：`REVISE`。两项 MUST_FIX 均为异步一致性：重叠 progress GET 可乱序覆盖新 attempt；route/mount 恢复可把新 timing 与旧 provenance 配对。
- 同一 `luna_worker` round 1：增加单调 progress 请求序号；begin/cancel/effect cleanup 使旧读取失效；本地 terminal refresh 校验事件/响应/store attemptId；mount/poll 成功恢复先等待 DraftView refetch，再应用 timing。
- 新增延迟 active A、延迟 terminal A、错误 terminal ID、旧 CANONICAL_REUSED cache + 新 FULL_REGENERATE success/refetch 延迟回归。
- 同一 detector round 1：`PASS`；M9-T35-001..008 与 R01..R08 全部通过，`must_fix: []`、`optional_hardening: none`、`scope_delta: none`。

## 主 Agent 验证

- focused Vitest：`65 passed`。
- frontend full Vitest：`149 passed`。
- `pnpm --dir frontend build`、ESLint、`scripts/check_frontend_locale.py`、`git diff --check`：全部 PASS。
- `implementation_scope_delta: none`。

## 验收与提交

- Task 35 依 Milestone 自治协议进入 `auto_accepted`。
- focused commit：`feat: show generation timing and Gus memory feedback`；仅本地，不 push。
- 下一步：创建 Task 36 Context Packet，完成 M9 全链路、Windows 打包与指标验收。
