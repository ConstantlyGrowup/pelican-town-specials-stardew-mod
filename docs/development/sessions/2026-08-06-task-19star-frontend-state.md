# Session｜2026-08-06-task-19star-frontend-state

| 字段 | 值 |
|---|---|
| `session_id` | `2026-08-06-task-19star-frontend-state` |
| `session_type` | milestone-task |
| `state` | auto_accepted（待用户 Milestone 验收与统一 push） |
| `date` | 2026-08-06 |
| `task` | Task 19*：5 个前端状态/草稿同步问题 |
| `acceptance_contract_id` | `mvp-task-19star-frontend-state-v1` |
| `revise_round` | 1（round 0 REVISE 2 项 → 修复 → round 1 PASS；全局两轮上限内） |
| `base_commit` | `3492650`（Task 19 提交之后实施） |

## 任务范围

Milestone 5 第二个 Task，修复用户报告的 5 项问题：1) 取消生成后状态未同步、再次生成仍提示「生成中」；2) 生成中切页再回草稿丢失进行中状态；3) 移除 Ask Gus 产出页「进入料理蓝图」入口；4) 移除 Gus 生成页「尚未填写玩法字段。」无效提示；5) 收集品已删除菜品在首页草稿仍滞留且不可删除。Context Packet：`docs/plans/2026-08-06-task-19star-frontend-state-packet.md`（gitignored）。

## 实施

- **F19-1（取消同步）**：后端 `/cancel` 从 fire-and-forget 改为等待回滚——`AttemptRegistry.await_task`（`asyncio.wait_for(asyncio.shield(task), 5s)` best-effort）、`GenerationOrchestrator.await_cancelled`、`GenerationService.cancel` 改 async、`/cancel` 路由 async 且 202 只在回滚完成后返回；`orchestrator._generate` 持内部 `_run` generator，`finally` 中 `inner.aclose()` 使客户端断流的 GeneratorExit 同步传播到 `_run` 的 `except GeneratorExit` 分支执行 `_rollback_cancelled`（从 `_finish_cancelled` 抽取的同步 side-effect），修复取消/断流后草稿卡 GENERATING。前端 `generationStore.cancelStream` 先 `await` 后端 `/cancel` 再 abort + 置终态；实现 per-draft 取消 single-flight（`pendingCancels` map）并在 finally 中仅在 `current.controller === 取消开始时捕获的 controller` 时才 abort/写终态，防止过期取消杀死新一轮生成。
- **F19-2（跨页状态继承）**：`generationStore.ts` 模块级 per-draftId state + listener set + `_snapshot`（useSyncExternalStore 稳定引用）；页面卸载不 abort，导航期间流在 store 中继续；重挂载从 store 恢复进度。`useGeneration` 改薄封装；`AskGusReviewPage` 从 store 恢复。
- **F19-3/F19-4（UI 移除）**：`AskGusReviewPage` 删除 convert-to-blueprint 按钮与 `onConvertToBlueprint` handler、删除 `noGameplayYet` 渲染块；`i18n/copy.ts` 移除 `convertToBlueprint`/`noGameplayYet` 键；`POST /drafts/{id}/convert-to-blueprint` 端点保留（契约不变）。
- **F19-5（草稿/收集品一致性）**：`CookbookService.delete` tombstone 后级联 `DraftService.delete_archived_by_dish(dish_id)`（可选 `draft_service` 关键词注入，app.py 装配）；`DraftService` 抽取共享 `_delete_draft_record`（复用 discard 的引用资产保护 + attempt/记录删除），新增 `delete_archived_by_dish`；`list_drafts` 过滤「archived_dish_id 不在活跃收集品」的 ARCHIVED 草稿（自愈既有孤儿）；活跃收集品的 ARCHIVED 草稿仍显示已归档且 /discard 仍拒绝（DEL-003 不变）。
- 前端 `api/ndjson.ts`：`GenerationRequestError`/`GenerationCancelError` + `parseErrorEnvelope`（F19-1-003 结构化错误呈现）。

## 审阅

- round 0 → **REVISE**（2 项 MUST_FIX，均 F19-1-001）：① `/cancel` 202 未等待回滚（`request_cancel` 仅 `task.cancel()` fire-and-forget，回滚在 202 之后异步完成，立即重新生成命中 409）→ 修复（async cancel 路由 await `await_cancelled`，best-effort timeout）+ API 集成回归测试「cancel 202 → 立即 regenerate 成功」；② `cancelStream` finally 读取 finally 时刻 controller、无 single-flight，过期取消会 abort 新一轮 → 修复（pendingCancels 单飞 + 捕获原 controller 守卫）+ 前端竞态与单飞回归测试。
- round 1 → 闭包验证 **PASS**（仅检查两处修复与回归；实施期观察「send 边界 CancelledError 可能不经回滚」经核对由 `_generate` finally 的 `inner.aclose()` → `_run` GeneratorExit 回滚覆盖，判非缺陷、非回归）。

## 验证证据

- 全量 backend：**616 passed / 2 skipped**（含新增 `test_cancel_awaits_rollback_then_immediate_regenerate_succeeds`）；前端：**86 passed**（84 + 2 新用例）；E2E：**9 passed**（spec 未改，新增断言仅「进入料理蓝图」count 0）。
- Ruff、Mypy（87 源文件）、前端 lint、`tsc --noEmit`+vite build、`git diff --check` 全 clean。
- 无 OpenAPI/契约变化。

## 验收与遗留

- 按 Milestone 自动路径进入 `auto_accepted`，创建本地 focused commit，未 push。
- 非阻塞观察：`await_task` 的 shield+5s timeout 为 best-effort（任务实际超过 timeout 时 202 可能先于最终回滚返回；当前 Ledger 未要求超时/故障注入矩阵）；预存孤儿草稿磁盘记录/素材清扫仅列表过滤隐藏、记录仍留盘（out_of_scope）。
- 真实用户交互复验（取消→立即重新生成、切页恢复进度、删除菜品后首页草稿消失）留待 Milestone 5 全量验收。
