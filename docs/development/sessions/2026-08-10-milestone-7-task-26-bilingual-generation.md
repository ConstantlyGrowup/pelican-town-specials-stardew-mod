# Session｜Milestone 7 Task 26 Bilingual generation and image prompt

| 字段 | 值 |
|---|---|
| session_id | `2026-08-10-milestone-7-task-26-bilingual-generation` |
| session_type | `milestone-7-task-26-implementation` |
| status | `auto_accepted`（round-0 REVISE 4 项 MUST_FIX 已修复 → round-1 PASS，本地 focused commit `318e3cf` 已创建，未 push） |
| owner | Codex 主会话（Claude Code 主会话实施 + Codex 独立审阅） |
| started_at | `2026-08-10` |
| user_acceptance | `pending`（Milestone 7 全量验收时统一） |
| base_commit | `efd2e5b docs: record Task 25 bilingual UI implementation and review` |
| acceptance_contract_id | `mvp-m7-task-26-i18n-gen-v1` |

## 任务范围

按 `docs/plans/2026-08-10-milestone-7-refine.md` §10 Task 26：新建 en-US 草稿从结构化分析、
Ask Gus 展示字段、原料映射到最终图片 prompt 全部使用英文；继续保留 zh-CN 现有行为；把语言
和 prompt version 记录进可追溯 provenance。**不新增第二次翻译模型调用**（M7-T26-GEN-004）。

Context Packet：`docs/plans/2026-08-10-task-26-bilingual-generation-packet.md`（gitignored），
`planning_status: READY_FOR_IMPLEMENTATION`，4 条 planning_rulings，acceptance_ledger
M7-T26-GEN-001..005，`revise_round: 0`。不改变 API schema（请求已携带 `language`）。

## 规划裁决（包工冻结，实施时全部应用）

- **R-01（语言化 prompt 分支）**：gateway/视觉 prompt 忽略 `language`、固定中文 → 建立版本化
  语言分支：analysis/ask-gus 增加英文 prompt 与 JSON 指令，gateway 按 `request.language`
  选择；视觉 prompt（tooltip/visual brief/icon）增加 `language` 参数（默认 ZH_CN 兼容既有
  调用与测试），orchestrator/blueprint 传 `draft.source.language`。
- **R-02（显示名按目标语言输出）**：`GameIngredient.displayName` 固定英文 → `_map_gameplay`
  线程 language，`map_ingredient`/`ensure_main_protein`/fallback 按 language 选
  `display_name_zh`/`display_name_en`；`item_id` 保持权威（zh 由英文改中文是对 Task 25
  「不中英混杂」的一致化修复）。
- **R-03（provenance 语言版本）**：不新增 API/schema 字段；`prompt_versions` 用语言后缀
  版本字符串 `ask-gus-v3-zh`/`-en`、`visual-v3-multi-image-edit-zh`/`-en`（`_build_visual_spec`
  的 `promptVersion` 同步）。旧草稿保留历史字符串不变。
- **R-04（修复指令本地化）**：`_repair_prompt`/`_repair_prompt_plain` 与「菜品分析：」/
  「Dish analysis：」前缀按 language 本地化，避免 en-US 修复轮诱导中文输出。

## 实现（12 文件 +779/-52，未提交）

- **`providers/prompts/analysis_v1.py`**：新增 `ANALYSIS_PROMPT_V1_EN` + `ANALYSIS_JSON_INSTRUCTION_EN`
  + `analysis_prompt_for(language)` 选择函数。
- **`providers/prompts/ask_gus_v2.py` / `ask_gus_v3.py`**：新增英文全量 prompt
  `ASK_GUS_PROMPT_V2_EN`/`ASK_GUS_PROMPT_V3_EN`（含英文定价 block
  「ordinary dishes 80..250g, refined dishes 250..400g, clearly premium or complex
  dishes 400..500g」）+ `ask_gus_prompt_for(language)`；中文 v2/v3 原文保留。
- **`providers/openai_compatible.py`**：`analyze_dish`/`design_ask_gus` 按 `request.language`
  选 prompt/JSON 指令/「Dish analysis：」前缀；`_chat_structured` 新增 `language` 参数线程到
  `_repair_prompt`/`_repair_prompt_plain`（英文修复指令分支）。
- **`generation/blueprint.py`**：`_BUFF_ATTRIBUTE_LABELS_ZH/EN` + `_buff_attribute_labels(language)`
  选择器；`build_blueprint_visual_brief`/`blueprint_icon_prompt`/`build_full_tooltip_prompt`
  增加 `language: Language = Language.ZH_CN` 参数与英文变体；`blueprint_preview_prompt` 透传。
- **`generation/orchestrator.py`**：`_map_gameplay` 线程 language；`_icon_prompt`/`_preview_prompt`
  英文变体；INVISUAL_BRIEF/ICON/PREVIEW 各分支传 `draft.source.language`；`_generated_provenance`
  与 `_build_visual_spec` 使用 `_language_suffix()` 语言后缀版本。
- **`catalog/mapping.py`**：`_display_name(item, language)` 选择器（EN_US→`display_name_en`，
  否则 `display_name_zh`）；`map_ingredient`/`ensure_main_protein`/`_fallback_ingredient`
  增加 `language` kwarg；`item_id` 权威不变。

## 验证

- RED→GREEN 已确认：实施前 focused 20 failed / 71 passed；实施后 focused 全部通过。
- focused（generation/providers/catalog）：**165 passed**。
- 全量 backend + repo + integration：**705 passed / 2 skipped**
  （`python -m pytest backend/tests tests/repo tests/integration -q -p no:cacheprovider`，
  含 round-1 新增 2 个回归测试）。
- ruff：**All checks passed!**（`python -m ruff check src tests`）。
- mypy：仅 3 处 HEAD 预存错误（`application/exports.py:194,226` no-untyped-def、
  `api/app.py:356` unused-ignore）——`git stash` 基线确认与 Task 26 无关，属 out_of_scope
  未越界修复。
- 无 OpenAPI/契约/前端变化；无真实 provider 调用（测试全部 fake）。

## 审阅

### round 0（Codex gpt-5.6-luna / max，新 thread）→ REVISE

**REVISE**，4 项 MUST_FIX：

- **M7-T26-GEN-002**：英文最长 tooltip prompt 超 1500 冻结契约（实测 2178）→ 压缩英文静态
  模板（最大字段 buff 1463 / no-buff 1258 ≤ 1500，硬锚点语义保留）+ 新增
  `test_blueprint_preview_prompt_en_stays_within_provider_limit`。
- **M7-T26-GEN-003**：`ensure_main_protein` 只匹配中文海鲜词，英文菜名（"Pan-seared Salmon"）
  落入 R15 护栏 → `_SEAFOOD_KEYWORDS` 增英文词表 + `casefold` 不区分大小写匹配 + 新增
  `test_en_dish_text_triggers_fish_insert_with_english_display_name`。
- **M7-T26-GEN-005（analysis）**：provenance 未记录分析 prompt version → 新增
  `_ANALYSIS_PROMPT_VERSION`，`prompt_versions["analysis"] = "analysis-v1-zh|en"`。
- **M7-T26-GEN-005（blueprint）**：蓝图 provenance 原样保留、visual 版本不可追溯 →
  `_finalize_candidate` BLUEPRINT 分支经 `model_copy` 合并
  `prompt_versions["visual"] = "visual-v3-multi-image-edit-zh|en"`，保留用户字段权威与
  `cache_eligibility=False`。

### round 1（Codex gpt-5.6-luna / max，新 thread）→ PASS

- **PASS**，`revise_round: 1`；checked M7-T26-GEN-002/003/005；must_fix 空；
  optional_hardening none；new_design none；scope_delta none；implementation_scope_delta none；
  planning_rulings_checked R-01..R-04。
- 修复后复验：focused **165 passed**；全量 **705 passed / 2 skipped**；ruff **All checks passed!**；
  mypy 仍仅 3 处 HEAD 预存错误（与修复无关，未越界）。

## 范围说明

- 未实现 Task 26 之外的导出语言（`ExportSpec.language` 保持 zh-CN）。
- 未翻译已有草稿/归档记录/历史生成结果。
- 未新增服务端用户偏好 API / 前端契约变化。
- 未修改 mod compiler、持久化 schema、OpenAPI。
- 未调用真实 provider；失败/取消/重生成沿用现有状态机与费用边界，无第二次翻译调用。
