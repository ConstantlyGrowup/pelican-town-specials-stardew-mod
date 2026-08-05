# Session｜2026-08-05-preview-pipeline-refactor

| 字段 | 值 |
|---|---|
| `session_id` | `2026-08-05-preview-pipeline-refactor` |
| `session_type` | milestone-acceptance-fix |
| `state` | committed |
| `date` | 2026-08-05 |
| `task` | Milestone 3 验收修复（R5）：预览管线按 skill 以原图为底重构 + 前端渲染 |
| `acceptance_contract_id` | `preview-pipeline-refactor-fd79f6a-20260805-v1` |
| `revise_round` | 0（codex 自审 + 包工复跑验收一次通过） |
| `base_commit` | `fd79f6a` → `8e5aaee` |

## 实际模型与 effort

```yaml
actual_models:
  main/coordinator: deepseek-v4-flash / effort: max（用户本 Session 设置）
  implementer: Codex gpt-5.6-luna / xhigh（经 codex-mcp 独立 thread）
  review: Codex 自审（同一实施 thread）+ 包工复跑验收
```

## 背景

用户真实验证 Milestone 3 时反馈两个问题：

1. **前端不渲染图片**：Ask Gus Review 页 / 收集品详情页 / Blueprint 编辑页只显示文案，预览图与图标不显示。根因：schema 已有 `previewAssetId`/`icon16AssetId`，素材端点 `GET /api/v1/assets/{id}` 已存在，但三个页面无 `<img>` 标签。
2. **预览生成违反 skill**：orchestrator `PREVIEW_ART_GENERATION_AND_COMPOSITION` 用 `ImageOperation.GENERATION` 让模型生成整幅像素画预览，违反用户提供的 skill `stardew-dish-card-overlay` 的「输入照片是不可替换的底图，只在负空间叠加词条卡 + 像素图标」核心判定。

用户确认正确范式为 `samples/image-edit/case/{1.jpg,2.png}`（真实食物照片 + 右上角暖橙词条卡 + 卡内像素图标），并要求实现走 codex-mcp（`gpt-5.6-luna`/xhigh），主会话（包工）负责通信与验收。

## 实现（commit `8e5aaee`）

- **合成器重构**：`images/preview_compositor.py` 的 `PreviewSnapshot` 从 `generated_art` 改为 `original_image + icon_16`；`compose_preview` 以原图为唯一画布（保持原始尺寸/宽高比/构图），卡片几何自适应（宽 30%、右上角、3% 边距），图标 NEAREST 缩放（像素保留），文字确定性绘制（displayName/category/description/体力/生命/售价）；删除 `_cover_crop` 与全幅 frame 层。
- **Orchestrator 预览本地化**：PREVIEW 阶段删除 `gateway.generate_image` 调用（含 `_preview_prompt`/`blueprint_preview_prompt`）；直接读 `draft.source.original_image_asset_id` 原图 + icon_16 asset → 本地 `compose_preview`；PREVIEW asset 使用实际输出尺寸；新运行不再设置 `generatedArtAssetId`（字段保留兼容旧记录）；`_VISUAL_PROMPT_VERSION` → `visual-v2-local-composite`。模型调用仅保留 icon_16 生成。
- **前端渲染**：`api/client.ts` 新增 `assetUrl()` helper（同源 `/api/v1/assets/{id}`，不改 OpenAPI 契约）；AskGusReviewPage、CookbookDetailPage、BlueprintEditorPage 三页条件渲染 preview（maxWidth 100%）+ icon（32×32, `imageRendering: pixelated`），asset 存在时才显示，STALE_PREVIEW 编辑门控不变。
- **测试**：合成器 focused 测试改为原图输入 + golden hash 更新（`backend/tests/golden/preview_v1.sha256`）；Ask Gus/Blueprint/regeneration/API 流式测试断言「无 preview 模型调用、仅一次 icon 调用」；前端三页测试断言 `<img>` 使用 asset 端点。

## 验证结果

- backend **466 passed / 2 skipped**、frontend **71 passed**、E2E **7 passed**。
- ruff、mypy（70 源文件）、build、lint、`scripts/build_preview_resources.py --check`、`git diff --check` 全部通过。
- **无 OpenAPI/契约变化**（PP-CONTRACT-001）。
- 包工人工核查：orchestrator PREVIEW 阶段无 `ImageOperation.GENERATION`；`_read_source_image` 读 `draft.source.original_image_asset_id`（skill 硬约束）；合成器保留原图尺寸与构图，仅叠加卡片/图标（PP-COMP-001/002、PP-ORCH-001/002 证据）。
- 已创建本地 focused commit `8e5aaee`（17 文件，+363/-130），未 push。

## 非阻塞观察

- 真实 Provider 端到端预览验证未执行（本 Task out_of_scope）；用户下次真实验收时可在真实模型下走 Ask Gus / Blueprint 全流程，确认合成预览视觉效果。
- 预览合成使用本地字体与羊皮纸模板，尺寸/位置为确定性算法；若产品侧对卡片位置或比例有进一步要求，可作为独立加固 Task。
- `generatedArtAssetId` 字段保留但新记录不再产生该 asset；旧归档记录不受影响。
