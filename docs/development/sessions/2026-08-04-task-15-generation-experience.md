# Session｜2026-08-04-task-15-generation-experience

| 字段 | 值 |
|---|---|
| `session_id` | `2026-08-04-task-15-generation-experience` |
| `session_type` | implementation |
| `state` | committed |
| `date` | 2026-08-04 |
| `task` | MVP Task 15：生成进度、Ask Gus 审核与 Blueprint 编辑体验 |
| `acceptance_contract_id` | `mvp-task-15-5df2352-20260804-final-v1` |
| `revise_round` | `1`（round 1 REVISE 1 项 MUST_FIX → 修复 → round 2 PASS） |
| `base_commit` | `5df2352` |

## 实际模型与 effort

```yaml
actual_models:
  main/coordinator: deepseek-v4-flash / effort: default
  implementer: 实施子代理（deepseek-v4-flash，干净上下文）
  review: Codex / GPT-5 / effort: max（独立新 thread）
```

## 目标

实现前端生成体验：NDJSON 流式解析与进度 UI（仅依据实际 stage events）、Ask Gus 审核页（接受/完整重新生成/拒绝/进入料理蓝图，无局部视觉操作，重生成期间显示旧结果）、Blueprint 编辑器更新预览与 STALE_PREVIEW 阻止接受，及 Playwright fake-flow E2E。

## 不包含

后端改动、OpenAPI/契约再导出、真实模型调用、Content Patcher、Cookbook 页功能扩展、Launcher/会话安全重构、后端 `RETRY_FAILED_GENERATION` 接线（延后单独 Task）。

## 实现证据

- `frontend/src/api/ndjson.ts`：分块 NDJSON 解析 + `streamGeneration`（原生 fetch + `ReadableStreamDefaultReader` + TextDecoder stream 模式 + CSRF + AbortSignal）+ `cancelGeneration`。
- `frontend/src/features/generation/useGeneration.ts`：阶段状态机 idle/streaming/success/error/cancelled，事件驱动阶段状态，begin 可重启、cancel 中止并 POST /cancel。
- `GenerationProgress.tsx` / `GenerationError.tsx`：阶段进度与错误/重试 UI。
- `AskGusReviewPage.tsx`：四操作；重生成期间旧结果 + 「正在准备整套新结果」；失败恢复旧结果；FAILED 草稿不暴露重试（round-1 修复）。
- `BlueprintEditorPage.tsx`：更新预览流 + STALE_PREVIEW 阻止接受。
- `app/router.tsx`：`DraftRoute` 按 mode 分发 ASK_GUS→AskGusReviewPage / BLUEPRINT→BlueprintEditorPage。
- `i18n/copy.ts`：生成体验与双模式文案（zh）；`playwright.config.ts` + `e2e/generation.spec.ts`（page.route 拦截全部 API 的 fake flow，无后端/模型调用）。
- scope delta：`frontend/vite.config.ts`（vitest test.exclude 加 e2e/**），Codex validated。

## 验证结果

- 红测：3 个测试文件因目标模块不存在 FAIL（符合预期）。
- 绿测：vitest **52 passed**（10 文件，含 +2 FAILED 回归）；Playwright E2E **7 passed**；`build`、`lint` 通过；backend 回归 **428 passed / 2 skipped**（无后端改动）；`git diff --check` clean。
- 前端 `test:run`/`build`/`lint`/`e2e` 全部由包工复跑确认。

## Review 结果

- Round 1（Codex 独立新 thread，GPT-5/max）：`REVISE`，1 项 MUST_FIX。
  - T15-004：AskGusReviewPage 对 FAILED 草稿暴露后端不支持的重试入口（`_resolve_kind` 对 FAILED 返回 409）。minimal_fix（前端）：`canGenerate` 排除 FAILED、GenerationError retry 门控 `draft.status === "REVIEWABLE"`。
  - `scope_delta`/`implementation_scope_delta` validated；copy.ts en 块、删除 Ask Gus 只读用例、vite.config e2e 排除均接受。
- Round 2（同 thread）：`PASS`，无 MUST_FIX。
- 非阻塞观察：后端 FAILED 重试（`RETRY_FAILED_GENERATION: FAILED→GENERATING` 已存在于状态机但 orchestrator/_resolve_kind 未接线）延后为单独后端 Task；当前 FAILED ask-gus 草稿无操作入口（round-1 修复后），属既有状态。

## 当前状态

- `state`: `committed`
- `next_action`: Task 15 Review PASS 后本地 focused commit `038635a`（不 push）。**Milestone 3（Task 11–15）全部完成**，进入 Milestone 3 全量验证与用户一次性验收。
