# Session｜2026-08-04-task-14-blueprint-preview

| 字段 | 值 |
|---|---|
| `session_id` | `2026-08-04-task-14-blueprint-preview` |
| `session_type` | implementation |
| `state` | committed |
| `date` | 2026-08-04 |
| `task` | MVP Task 14：Blueprint 视觉更新与用户字段保护 |
| `acceptance_contract_id` | `mvp-task-14-28db7a8-20260804-final-v1` |
| `revise_round` | `1`（round 1 REVISE 1 项 MUST_FIX → 修复 → round 2 PASS） |
| `base_commit` | `28db7a8`（包工-子代理-Codex 审阅协作模型控制面提交） |

## 实际模型与 effort

```yaml
actual_models:
  main/coordinator: deepseek-v4-flash / effort: default
  implementer: 实施子代理（deepseek-v4-flash，干净上下文）
  review: Codex / GPT-5 / effort: max（独立新 thread）
```

> 本 Session 是「包工-子代理-Codex 审阅」新协作模式的首次完整跑通：包工闭包检查并生成 Context Packet，实施子代理执行，包工桥接 Codex（新 thread）独立只读审阅，round 1 REVISE 后实施子代理修复，round 2 PASS，包工创建本地 focused commit。

## 目标

实现 BLUEPRINT 草稿的视觉更新与用户字段保护：STALE_PREVIEW → BLUEPRINT_PREVIEW → REVIEWABLE；预览只重生成视觉资产，绝不改写 USER_ASSIGNED 字段；PATCH 后 revision +1 进入 STALE_PREVIEW；失败/取消保持 STALE_PREVIEW。

## 不包含

前端页面（Task 15）、真实模型调用、Provider/网关变更、Content Patcher、OpenAPI/前端契约再导出、新增状态机过渡或持久化字段、预览运行期间 PATCH 并发竞争加固。

## 实现证据

- `generation/blueprint.py`（新）：`BLUEPRINT_STAGE_ORDER`（6 阶段）、`build_blueprint_visual_brief`（确定性构造）、蓝图 icon/preview prompt、`run_blueprint_preview(orchestrator, command)` 入口。
- `generation/orchestrator.py`：`BLUEPRINT_PREVIEW` 分支（要求 STALE_PREVIEW，运行期不转换状态）、按 mode 选阶段序列、蓝图 VISUAL_BRIEF/ICON/PREVIEW 分支（模型只生成图像）、`_finalize_candidate` 按 kind 选 action（BLUEPRINT_PREVIEW→PREVIEW_UPDATED）且 BLUEPRINT 保留 provenance、`_finish_failed`/`_finish_cancelled` BLUEPRINT 保持 STALE_PREVIEW 并记录 last_error。
- `application/generation.py`：`_resolve_kind` 支持 BLUEPRINT（DRAFT/READY→INITIAL、STALE_PREVIEW→BLUEPRINT_PREVIEW、REVIEWABLE→非法）；`begin_generation` 对 BLUEPRINT_PREVIEW 走 `run_blueprint_preview`。
- `domain/validation.py`（implementation_scope_delta）：`validate_draft` 对 BLUEPRINT 模式不再要求 analysis 非空（Blueprint 草稿按设计 analysis 恒为 None）；`user_visible_delta: none`，Codex 已验证。
- 测试：`tests/generation/test_blueprint.py`（6）+ `tests/api/test_blueprint_generation.py`（2）；conftest 增 `blueprint_stale` fixture 与 `blueprint_preview_command`。
- `application/drafts.py` 无需改动：既有 `patch_draft` + `save()` 已满足 PATCH→STALE_PREVIEW + revision+1（T14-004 测试证实）。

## 验证结果

- 红测：`ModuleNotFoundError: No module named 'pelican_town_specials.generation.blueprint'`（符合预期）。
- 绿测：蓝图测试 8 passed；`backend/tests/generation` 13 passed；全量 `backend/tests` **428 passed / 2 skipped**（包工复跑确认）。
- 静态：ruff clean；mypy 69 源文件 clean；`git diff --check` clean；OpenAPI/前端契约无变化。
- 人工验证：无（全自动；工作树核验干净后提交）。

## Review 结果

- Round 1（Codex 独立新 thread，GPT-5/max）：`REVISE`，1 项 MUST_FIX。
  - T14-006：Blueprint 取消路径未记录 `last_error`。minimal_fix：`_finish_cancelled` 蓝图分支补 `_to_summary(_cancelled_error())`，取消测试断言 `last_error`。
  - `scope_delta: validated`、`implementation_scope_delta: validated`（validation.py 放宽与 `run_blueprint_preview` 签名两点均接受）。
- Round 2（同 thread）：`PASS`，无 MUST_FIX。
- 非阻塞观察：审阅期间 Codex 在仓库根生成的 `.review-runtime-workspace/` 已清理。

## 当前状态

- `state`: `committed`
- `next_action`: Task 14 Review PASS 后 auto_accepted + 本地 focused commit `daeacfd`（不 push）；按里程碑粒度继续 Task 15（生成进度、Ask Gus 审核与 Blueprint 编辑体验）。
