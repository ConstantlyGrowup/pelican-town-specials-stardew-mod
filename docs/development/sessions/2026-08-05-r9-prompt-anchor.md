# Session｜2026-08-05-r9-prompt-anchor

| 字段 | 值 |
|---|---|
| `session_id` | `2026-08-05-r9-prompt-anchor` |
| `session_type` | milestone-acceptance-fix |
| `state` | committed |
| `date` | 2026-08-05 |
| `task` | Milestone 3 验收修复（R9）：EDIT prompt 精简为「硬锚点 + 少量版式约束 + 字段内容」 |
| `acceptance_contract_id` | `milestone3-acceptance-fix-r9-prompt-anchor` |
| `revise_round` | 0（PASS） |
| `base_commit` | `787b82c` → `a727a8f` |

## 实际模型与 effort

```yaml
actual_models:
  main/coordinator: deepseek-v4-flash / effort: max
  implementer: 包工直接实施（参照 R7/R8 先例，改动 4 文件）
  review: Codex gpt-5.6-luna / xhigh（经 codex-mcp 独立新 thread）
```

## 背景

用户（产品负责人）反馈 R8 的 EDIT prompt 存在**过强细节引导**（羊皮纸、渐变、装饰角等设计学形容词），词条卡视觉偏离 Stardew 游戏内 item hover tooltip。用户给出两条原则与参考写法：

- **原则 1**：少描述"材质"，多描述"类型"——删羊皮纸/渐变/装饰角/复古纸卡，改为《星露谷物语》物品悬浮词条框、像素游戏 UI、平面硬边低材质感、非海报/非菜单/非说明书。
- **原则 2**：「星露谷词条框」最高优先级——必须是 Stardew 游戏内 item hover tooltip 的视觉语言，而非泛 RPG 菜单卡、菜单海报、说明书卡片或羊皮纸公告板。
- 结构：硬锚点 + 少量版式约束 + 字段内容；字段格式：标题：/类别：/描述：/能量：+N/生命：+N/售价：Ng/无 Buff：不要生成增益行。

## 实现（commit `a727a8f`，4 文件 +123/-252）

- **`blueprint.py`**：新增公共 `build_full_tooltip_prompt(presentation, gameplay)`——Ask Gus 与 Blueprint 共用同一 prompt（硬锚点「Stardew Valley item hover tooltip」、非海报/菜单/网页卡片/PPT 文本框/说明书卡片/羊皮纸公告板；负空间区域、图标卡上方/轻压边框；字段逐字格式 标题：/类别：/描述：/能量：+N/生命：+N/售价：Ng/Buff：…或无 Buff）。`blueprint_preview_prompt` 变薄别名。删除 `clip_visual_brief` 与 `_VISUAL_BRIEF_CAP`（visual_brief 不再进 prompt，但仍持久化于 `VisualSpec.visualBrief`，领域无变化）。
- **`orchestrator.py`**：`_preview_prompt(presentation, gameplay)` 薄封装调用 `build_full_tooltip_prompt`；删除 `_buff_prompt`；PREVIEW 阶段两处调用点去掉 visual_brief 参数；`enforce_preview_prompt_budget`（1500）保留为安全网。
- **测试（TDD）**：stage_order 断言改新格式（能量：+200/生命：+90/售价：220g/item hover tooltip/不是海报/无 Buff：不要生成增益行，删除旧视觉措辞断言）；within-limit 测试去 visual_brief 参数并加最大 BuffSpec；两个 over-budget 端到端测试改为 `enforce_preview_prompt_budget` 单元测试（新 prompt 最大合法字段约 1190 字符，不再触发超限，安全网以单元测试覆盖）。

## 验证结果

- focused generation **19 passed**；全量 backend **464 passed/2 skipped**；ruff、mypy（69 源文件）、`git diff --check` clean。
- Codex 独立审阅 **PASS**（round 0，must_fix 空；R9-PROMPT-ANCHOR/R9-SHARED-PROMPT/R9-VISUAL-BRIEF-CLOSURE/R9-BUDGET-GATE/R9-REGRESSION-SCOPE 全过）。
- 无 OpenAPI/契约/前端变化；双图 EDIT、quality=high、能力门、STALE_PREVIEW 语义不变。
- 已创建本地 focused commit `a727a8f`，未 push。

## 非阻塞观察

- 词条卡视觉是否达成「游戏内悬浮词条」效果依赖图像模型行为；用户重测确认。若仍有偏差，可继续按「类型优先」原则微调锚点措辞。
