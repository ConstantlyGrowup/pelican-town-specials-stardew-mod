# Session｜2026-08-05-r8-prompt-quality

| 字段 | 值 |
|---|---|
| `session_id` | `2026-08-05-r8-prompt-quality` |
| `session_type` | milestone-acceptance-fix |
| `state` | committed |
| `date` | 2026-08-05 |
| `task` | Milestone 3 验收修复（R8）：预览 prompt 自适应卡片位置 + EDIT quality=high |
| `acceptance_contract_id` | `milestone3-acceptance-fix-r8-prompt-quality` |
| `revise_round` | 0（PASS） |
| `base_commit` | `90700b6` → `787b82c` |

## 实际模型与 effort

```yaml
actual_models:
  main/coordinator: deepseek-v4-flash / effort: max
  implementer: 包工直接实施（参照 R7 先例，改动 4 文件）
  review: Codex gpt-5.6-luna / xhigh（经 codex-mcp 独立新 thread）
```

## 背景

用户真实环境观察（R6 双图 EDIT 预览）：词条卡稳定出现在食物居中上方。产品要求**模型自主判断最佳放置位置**（SKILL §3：优先背景留白/墙面/桌面/窗景；主体中下→放上方或上侧；主体一侧→放相反一侧；不固定位置、不遮挡主体）。同时要求预览 EDIT 请求指定 `quality="high"`。

## 实现（commit `787b82c`，4 文件 +13/-2）

- **两处 prompt 自适应位置指令**（ask-gus `_preview_prompt` in orchestrator.py、blueprint `blueprint_preview_prompt` in blueprint.py）：把「只在不遮挡主体的负空间叠加 UI」替换为「词条卡放置位置由你根据照片构图自主判断：优先背景留白、墙面、桌面或窗景等负空间；主体位于中下方时放上方或上侧，主体位于一侧时放相反一侧；不要固定在食物正上方或居中，不得遮挡主体。」（净增约 75 字符；`enforce_preview_prompt_budget` 1500 契约仍在 Provider 调用前兜底）。
- **EDIT quality="high"**：orchestrator PREVIEW 阶段 `ImageGenerationRequest` 新增 `quality="high"`（字段已存在于 contracts.py，`_generate_edit` 已支持传递，无 provider 改动）；icon GENERATION 不加，保持已验收行为。
- 测试（TDD 红→绿）：test_ask_gus.py / test_blueprint.py 增加 `preview_request.quality == "high"` 与 prompt 含「自主判断」「背景留白」断言。

## 验证结果

- focused generation **19 passed**；全量 backend **464 passed/2 skipped**；ruff、mypy（69 源文件）、`git diff --check` clean。
- Codex 独立审阅 **PASS**（round 0，must_fix 空；R8-PROMPT/R8-BUDGET/R8-QUALITY/R8-REGRESSION/R8-SCOPE 全过）。
- 无 OpenAPI/契约/前端变化；双图 EDIT 顺序、能力门、STALE_PREVIEW 语义不变。
- 已创建本地 focused commit `787b82c`，未 push。

## 非阻塞观察

- 卡片位置是否真正自适应依赖图像模型行为；用户重测确认。若模型仍倾向固定位置，可在 prompt 中加强负空间示例或后续调参。
