# Session｜2026-08-05-preview-pipeline-r6

| 字段 | 值 |
|---|---|
| `session_id` | `2026-08-05-preview-pipeline-r6` |
| `session_type` | milestone-acceptance-fix |
| `state` | committed |
| `date` | 2026-08-05 |
| `task` | Milestone 3 验收修复（R6）：按新 SKILL 重做预览管线——最终词条卡由图像模型双图 EDIT 生成 |
| `acceptance_contract_id` | `preview-pipeline-r6-8e5aaee-20260805-v1` |
| `revise_round` | 0（REVISE 2 项 MUST_FIX）→ 1（PASS） |
| `base_commit` | `8e5aaee` → `fb40992` |

## 实际模型与 effort

```yaml
actual_models:
  main/coordinator: deepseek-v4-flash / effort: max（用户本 Session 设置）
  implementer: 实施子代理（deepseek-v4-flash，干净上下文；round-1 修复复用同一子代理）
  review: Codex gpt-5.6-luna / xhigh（经 codex-mcp 独立新 thread，round 0/1 各一个）
```

## 背景

用户 2026-08-05 更新了 SKILL（`samples/image-edit/skills/stardew-dish-card-overlay-SKILL (1).md`），核心变化：**最终词条卡必须由图像模型生成**——一次双图 EDIT（`source_images=[原图, 同一轮像素图标]`，图标优先 `iconSourceAssetId` 清晰源）；本地模板/Pillow/Canvas/前端组件程序化排版被明确列为**错误做法**；Provider 不支持双图编辑时停止并报告能力不满足，不得回退本地合成。

R5（`8e5aaee`）的本地合成方案被用户确认推翻重做。同日用户澄清协作规则：codex-mcp 只是主 agent 与 codex 的**通信桥接**（交接/审阅），codex 担任执行者仅限视觉/多模态 Task；审阅强度为 **GPT 5.6 Luna (xHigh)**（`gpt-5.6-luna` + `model_reasoning_effort: xhigh`）。已同步更新 memory 三文件。

## 实现（commit `fb40992`，22 文件 +571/-767）

- **orchestrator PREVIEW 阶段重构**：读原图 → `downscale_for_vision`（≤2048、LANCZOS、JPEG，R1 先例）→ `source_images[0]`；读 ICON_SOURCE asset → `source_images[1]`；单次 `gateway.generate_image(EDIT, prompt=完整词条卡 prompt, size=原图尺寸)` → 结果注册 PREVIEW asset（实际输出尺寸）。`compose_preview`/`PreviewSnapshot` 从 images 导出移除，`PNGBytes` 由 icon_pipeline 再导出。`_VISUAL_PROMPT_VERSION → visual-v3-multi-image-edit`。
- **能力门**：`_ensure_image_edit_capability`（`image_edits_supported=False` 或 `capabilities.image_edits.supported=False` → `PTS_PROVIDER_IMAGE_EDIT_UNSUPPORTED` 502 retryable=False），无本地合成回退。
- **prompt 重建**：ask-gus `_preview_prompt`（orchestrator）+ `blueprint_preview_prompt`（blueprint.py，新增 gameplay 参数）：包含已验证 displayName/categoryLabel/description/体力/生命/售价 + SKILL 视觉语言（饱和暖橙羊皮纸渐变、多层深棕像素边框、像素装饰角、分隔线、统一像素符号、图标置于卡上方）；Blueprint 逐字使用 draft.presentation/gameplay；`clip_visual_brief`（200 字符，仅"氛围参考"非业务字段）。
- **合成器清理**：preview_compositor.py、test_preview_compositor.py、test_preview_resources.py、golden/preview_v1.sha256、scripts/build_preview_resources.py、resources/templates/preview-v1/、NotoSansSC-VF.ttf 删除；scope_delta（§10 合法）：`resources/provenance.json`（登记被删资源）与 `THIRD_PARTY_NOTICES.txt`（唯一内容为被删字体许可）一并删除。
- **round-1 修复（Codex 2 个 MUST_FIX）**：最大合法字段（含 BuffSpec）下 prompt 超 1500 冻结契约 → ValidationError。新增共享校验器 `enforce_preview_prompt_budget(prompt)`（blueprint.py，`_PROMPT_MAX_CHARS=1500`），orchestrator PREVIEW 中 Provider 调用前统一执行（Ask Gus/Blueprint 共用）；超限抛受控 `PTS_PREVIEW_PROMPT_TOO_LONG`（422 retryable=False，details 仅 promptLimit）；业务字段逐字保留；TDD 红（PTS_GEN_UNEXPECTED）→ 绿。
- **generatedArtAssetId** 对新运行保持不设置（R5 决定，字段保留兼容旧归档）。

## 验证结果

- round 1 修复后：focused images+generation **43 passed**；全量 backend **462 passed / 2 skipped**；frontend **71 passed**；E2E **7 passed**；ruff、mypy（69 源文件）、build、lint、`git diff --check` 全 clean。
- Codex 第二轮审阅 **PASS**（revise_round: 1，must_fix 空）；回归确认：双图 EDIT 顺序、iconSourceAssetId、能力门、STALE_PREVIEW、失败/取消保护、合成器清理。
- 无 OpenAPI/契约/前端/持久化变化（R6-CONTRACT-001）；前端在 R5 已交付渲染，本 Task 未触碰。
- 已创建本地 focused commit `fb40992`（22 文件 +571/-767），未 push。

## 非阻塞观察

- 真实 Provider 端到端双图 EDIT 未验证（out_of_scope）；用户下次真实验收时确认模型渲染的词条卡视觉效果、中文准确性与图标复用。
- `build_blueprint_visual_brief` 存储文本仍含「菜品插画」措辞，但在 prompt 中降级为「视觉氛围参考（不可作为额外卡片文字）」并截断至 200 字符；修改存储文本会改变 API 可见字段，留作 optional hardening。
- `enforce_preview_prompt_budget` 超限（极端合法字段）走受控 422；产品侧如需支持超长描述可后续扩大契约或缩短描述渲染。
