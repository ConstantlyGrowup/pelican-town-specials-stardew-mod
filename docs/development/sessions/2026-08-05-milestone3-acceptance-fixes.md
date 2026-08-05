# Session｜2026-08-05-milestone3-acceptance-fixes

| 字段 | 值 |
|---|---|
| `session_id` | `2026-08-05-milestone3-acceptance-fixes` |
| `session_type` | milestone-acceptance-fix |
| `state` | committed |
| `date` | 2026-08-05 |
| `task` | Milestone 3 验收反馈修复（两轮） |
| `acceptance_contract_ids` | `mvp-acceptance-fixes-eafdeb2-20260804-v1`、`mvp-acceptance-fixes-r2-20260805-v1` |
| `revise_round` | R1：round 1（截断 off-by-one）→ round 2 PASS；R2：round 1（蓝图 REVIEWABLE 重试门控）→ round 2 PASS |
| `base_commit` | `eafdeb2` → `07652f6` → `949b762` |

## 实际模型与 effort

```yaml
actual_models:
  main/coordinator: deepseek-v4-flash / effort: default
  implementer: 实施子代理（deepseek-v4-flash，干净上下文）
  review: Codex / GPT-5 / effort: max（独立新 thread）
```

## 背景

用户对 Milestone 3 做真实验证，反馈多类缺陷，分两轮修复：

### R1（commit `07652f6`）
- Provider 视觉调用 400：源图 10.8MP 未降采样直发视觉模型。新增 `images/vision_input.py` `downscale_for_vision`（LANCZOS、长边 ≤2048、JPEG），orchestrator DISH_ANALYSIS 降采样后调用；`_provider_error` 增加脱敏 providerError 摘要便于诊断。
- Blueprint 新鲜草稿无生成入口（按钮只在 STALE_PREVIEW）：`canGenerate` 覆盖 DRAFT/READY/STALE_PREVIEW。
- 无草稿列表：首页变为草稿仪表盘（GET /api/v1/drafts，空态引导创建），用户确认「首页草稿区」。
- scope delta：frontend/vite.config.ts（e2e 排除 vitest）、App.test.tsx（HomePage 需 AppProviders）。Codex validated。

### R2（commit `949b762`）
- 模型默认值：`_ProviderSettingsFields` 默认 vision/text=gpt-5.6-luna、image=gpt-image-2-max（用户确认「默认使用我们那一套配置」）；`_require_model` 空模型守卫 PTS_PROVIDER_NOT_CONFIGURED。
- FAILED 重试：`_resolve_kind` FAILED→INITIAL（两种模式）、orchestrator `RETRY_FAILED_GENERATION` 分支；前端重试门控恢复 FAILED。
- 草稿删除：BlueprintEditorPage 与 HomePage discard 入口（POST /discard）。
- recovery schema：`_model_schema` 在 `_strictify_schema` 前用 `_strip_frozen_fields` 剔除 `Field(frozen=True)` 派生字段（RecoverySpec 的 energyRestore/healthRestore/calculationVersion），解决 `recovery:value_error`（Issue 6 根因）。
- round-1 修复：Blueprint REVIEWABLE 从 GenerationError 重试门控移除（后端不映射 BLUEPRINT REVIEWABLE）。

## 验证结果

- R1：backend 441、frontend 58、E2E 7、ruff/mypy（70 文件）/build/lint/diff-check clean。
- R2：backend **450 passed / 2 skipped**、frontend **64 passed**、E2E 7、ruff/mypy/build/lint/diff-check clean；无 OpenAPI/契约变化。
- 包工全程复跑确认；全部本地 committed（`07652f6`、`949b762`），未 push。

## 非阻塞观察

- HomePage 删除草稿后 `list_drafts` 仍含 DISCARDED 记录；如产品要求丢弃后完全隐藏需另行过滤终态（待用户确认）。
- `_strip_frozen_fields` 按 schema `title` 匹配模型类名；未来可用显式 ref/模型映射避免同名或泛型冲突（Codex 非阻塞观察）。
- `providers/structured_output.py` docstring「one repair」已过时（现为 2 次修复），非阻塞。

## R3（commit `1996d85`）

- INGREDIENT_MAPPING 兜底：`map_ingredient` 空候选/无可用项返回确定性 fallback（Egg 176，按 `used_item_ids` 去重选未用项），mappingReason 标记 catalog fallback；`orchestrator._map_gameplay` 维护 used_item_ids 避免重复 itemId（GameplaySpec 唯一性）。
- 结构化输出修复轮次 1→2：`_chat_structured` MAX_REPAIRS=2（最多 3 次尝试）；`_extract_chat_text` 移入 repair try，envelope 错误（无 choices/非法 JSON/非 object）也进入修复计数。
- round-1 修复：fallback 去重（Codex R3-ING-001/002）+ extract 入 repair（R3-REPAIR-001）。
- 验证：backend **461 passed / 2 skipped**、frontend 64、E2E 7、ruff/mypy/build/lint/diff-check clean；无 OpenAPI/契约变化。

## 当前状态

- `state`: `committed`
- `next_action`: 交还 Milestone 3 验收——用户重测 Ask Gus 完整流程（INGREDIENT_MAPPING 未匹配原料走 fallback 不再失败）、Blueprint 重试与删除、首页草稿区；通过后进入 Milestone 3 全量验收与统一 push。
