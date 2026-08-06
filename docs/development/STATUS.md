# Pelican Town Specials｜开发状态

> 本文件是开发状态唯一真源。设计内容回查正式技术设计，文档索引回查项目设计源索引；本文件只回答“当前哪个 Session、做到哪里、下一步是什么”。

## 当前状态

| 字段 | 值 |
|---|---|
| overall_state | awaiting_user_verification |
| project_phase | milestone-4-content-patcher-compiler |
| product_implementation_started | true |
| active_session_id | 无 |
| active_session_state | 无 |
| active_session_type | 无 |
| current_task | Milestone 4 游戏内复验 R12–R17；随后 Task 19（PyInstaller 发布包） |
| blocker | 无 |
| next_action | 用户重新生成菜品，验证 R16 Buff 分布与 R17 售价分布；之后进入 Task 19 |
| collaboration_model | 包工-子代理-Codex 审阅（2026-08-04 采用；包工生成 Packet，实施子代理执行，Codex luna/max 经 codex-mcp 新 thread 审阅） |

## 当前 Git 状态事实

| 项目 | 当前值 |
|---|---|
| 仓库 | 已在当前目录初始化 |
| 当前分支 | feat/mvp-implementation（Task8 focused commit 已推送；Task 9–15 与验收修复已本地提交，未推送） |
| origin | https://github.com/ConstantlyGrowup/pelican-town-specials-stardew-mod.git |
| 初始提交 | 517f844 chore: add serial agent handoff control plane |
| 最新提交 | 5905360（fix: constrain ask gus gameplay pricing，R17） |
| 远端操作 | 已推送：Task5–Task10、自治规则控制面与 Milestone 2 全部修复（2301daa..4b58be0）；Milestone 3 全量（Task 11–15 + R1–R11）已按用户授权统一 push（4b58be0..916e3da → origin/feat/mvp-implementation）；Task 16–18 与后续验收修复（1730578/be6eb1b/fa34d5e、2056658/7623e43、fa64a91/e426b2c、886de32/8589a3e/5761e92/b7fa672/9d06e41/5905360）已本地提交未 push（Milestone 4 门） |
| 当前工作树范围 | 工作树核验干净；仅预存未跟踪 `samples/image-edit/`、`samples/牛肉0.jpg`、`.pytest_tmp/`（非本 Session 产物） |

## 当前 Milestone 3 验收 Session（accepted）

- `2026-08-05-milestone3-acceptance`：用户 2026-08-05 宣布 Milestone 3 验收通过（R1–R11 全部修复已本地提交）。验收范围：Task 11–15（OpenAI-compatible generation）+ 验收修复 R1–R11（含 provider 入参约束 16 倍数/最小像素、Stardew tooltip prompt 硬锚点、双图 EDIT 管线、Buff 逐行中文展示）。
- 本地 commits 等待用户授权统一 push 至 origin/feat/mvp-implementation。

## 当前 R17 Session（committed）

- `2026-08-06-r17-gus-gameplay-pricing`：按 Stardew 1.6.15 原版烹饪物价格分布约束 Ask Gus gameplay prompt；生图 prompt 保持不变。
- 实现（commit `5905360`）：新增版本化 `ask_gus_v3` 并保留 v1/v2；普通菜 80..250g、精致菜 250..400g、高档/复杂菜 400..500g，多数结果 100..400g；普通或无 Buff 菜不得超过 500g，不得用高价补偿无 Buff；超过 500g 仅限明确传奇/特殊功能性物品并须在 `gusComment` 解释玩法理由。
- 价格依据覆盖原料价值/稀有度、制作复杂度、恢复量、Buff 强度/持续时间和定位；Oil of Garlic 1000g 与 Magic Rock Candy 5000g 只作极少数原版例外校准。
- 验证：TDD RED→GREEN focused 49 passed；全量 backend 553 passed/2 skipped；Ruff、Mypy（15 源文件）、diff-check clean；独立只读 Review PASS，无 MUST_FIX。
- 无 schema/validator/compiler/API/frontend/图像链路变化，未调用真实 Provider；已有草稿不自动改价，等待用户重新生成观察。

## 当前 Task 16 Session（committed）

- `2026-08-05-task-16-mod-compiler`：Milestone 4 首个 Task（deterministic Content Patcher compiler）。Context Packet：`mvp-task-16-mod-compiler-v1`。实施子代理 TDD（红→绿 60 passed、回归 208 passed、全量 528 passed/2 skipped），Codex 审阅 **PASS**（round 0，14/14 criterion），本地 focused commit `1730578`（feat）+ `be6eb1b`/`fa34d5e`（docs），未 push。
- 闭包裁决 R16-1..6：author_name 注入编译器构造；`validate_export` 增 catalog 参数；Buff→Data/Objects.Buffs（Task 18 Spike 冻结）；i18n default/zh 一致；ExportArtifact/compile_to_bytes；staging 为调用方目录。

## 当前 R16 Session（committed）

- `2026-08-06-r16-gus-buff-latitude`：用户确认生图 prompt 已满意，仅要求适度放宽 Ask Gus gameplay prompt 的 Buff 推荐标准。
- 实现（commit `9d06e41`）：新增版本化 `ask_gus_v2` 并保留 v1；普通但有可信玩法关联的菜通常可获得 1 个温和 Buff，特征明确时最多 2 个互补属性；仅非常朴素且无可信关联时为 null；禁止无关或夸张 Buff。新调用路由 v2，provenance 记录 `ask-gus-v2`。
- 验证：TDD RED 2 个预期失败→GREEN focused 48 passed；全量 backend 552 passed/2 skipped；Ruff、Mypy（14 源文件）、diff-check clean；独立只读 Review PASS，无 MUST_FIX。
- 生图 prompt、双图 EDIT、图标与预览管线均无改动；未调用真实 Provider。技术设计已更新至 v1.3；等待用户重新生成验证模型分布。

## 当前 R12–R15 Session（committed）

- `2026-08-06-r12-r15-game-acceptance-fixes`：用户游戏内验收发现四项细节问题并授权修复——R12 图标黑底（确定性 Pillow 洪泛抠图 + 洋红背景 prompt，`5761e92`）、R13 Buff 游戏内不显示（Buff 内嵌 Data/Objects 条目、对齐官方 1.6.15 结构、Duration 游戏分钟，`886de32`）、R14 Edibility 偏高（prompt 原版取值带 + 官方换算公式 ceil/floor，`8589a3e`）、R15 材料不准（双 prompt 约束 + `ensure_main_protein` 主食材护栏，`8589a3e`）。
- 验证：全量 backend + 集成 565 passed/2 skipped；Ruff clean；mypy 仅剩 3 处 HEAD 预存错误（exports.py/app.py，stash 基线确认与本次无关）；diff-check clean；无契约/前端变化。
- 独立只读 Review Subagent **PASS**（无 MUST_FIX；本环境无 codex-mcp 通道，按回退路径执行，未冒充 Luna 路由）。auto_accepted，三个本地 focused commits（未 push）。
- Spike 结论已回写设计 §18.3 与变更记录 v1.2；待用户重新生成菜品并游戏内复验四项效果。

## 当前 Task 18 Session（game-acceptance-passed）

- `2026-08-05-task-18-game-validation`：Milestone 4 第三个 Task（真实 Stardew Valley 验证与 Spike 冻结）。Context Packet：`mvp-task-18-game-validation-v1`（R18-1..5，gitignored）。自动范围完成：`scripts/validate_mod_zip.py`、`scripts/deploy_local_mod.ps1`、`tests/integration/test_release_mod.py`（16 passed）、根级 `pytest.ini`（importlib 模式，Codex 验证接受的 scope_delta）。
- Codex：round 0 REVISE（T18-VALIDATOR-002 根孤儿未拒）→ round 1 修复 → round 2 **PASS**。包工复跑：集成 16 passed、combined 76 passed、全量 backend 538 passed/2 skipped、ruff/mypy/diff-check clean。auto_accepted，本地 focused commit（未 push）。
- **游戏验收（用户 2026-08-06 确认）**：打包验收成功，解压后游戏内找到对应物品。核心验收通过；8 项细节中的四项 API 调用问题已由 R12–R15 修复（见上方 Session），Spike 结论已回写设计 §18.3。

## 当前 Task 17 Session（committed）

- `2026-08-05-task-17-export`：Milestone 4 第二个 Task（Export API、Pack the Menu 与 Bring It In-Game）。Context Packet：`mvp-task-17-export-v1`（R17-1..7）。实施子代理 TDD 完成；Codex round 0 REVISE（T17-OPENFOLDER-001 生产装配未注入 os.startfile）→ round 1 修复（app.py `_default_open_folder()` win32→os.startfile + 新测试）→ round 2 BLOCKED（环境性：只读环境无法跑 pytest，无 criterion 失败）。
- 包工复跑闭合：全量 backend **538 passed/2 skipped**、前端 77 passed、E2E 8 passed、lint/build/ruff/mypy（79 源文件）/diff-check clean、契约已重生成。判定 auto_accepted。
- 实现：`ExportRecord`/`ExportStatus`/`ExportRecordView` + `ExportRepository`（幂等 add_or_get）；`ExportService` 同步状态机 VALIDATING→BUILDING→SUCCEEDED/FAILED（staging ZIP 永不可下载）；5 端点；前端 PackMenuPage/ValidationIssues/BringInGamePage + CookbookPage 打包入口 + 路由 + E2E。
- 非阻塞：download OpenAPI 声明 application/json（运行时 application/zip）、Idempotency-Key 标可选 —— 后续加固。
## 当前 Task 13 Session（committed）

- `2026-08-04-task-13-generation-orchestrator` 已从上下文溢出后的部分工作树恢复，完成 Ask Gus 生成 Orchestrator、NDJSON 流式事件与完整重生成，独立只读 Review Subagent 首轮 `PASS`（无 MUST_FIX），auto_accepted 后创建本地 focused commit `5949516`（不 push）。
- 实现：`generation/orchestrator.py`（阶段循环、候选构建、原子 promote、取消/失败回滚、`_SlotGuardedAsyncIterator` 槽位释放）、`application/generation.py`、`api/routes/generation.py`、app.py 装配与 lifespan 启动恢复；依赖闭包含 repositories `control_write`/`promote`/attempt 仓库、domain errors/state_machine、providers ModelGateway Protocol、catalog mapping Protocol、error_handlers 共享 ErrorEnvelope。
- 验证：生成测试 10 passed；全量后端 420 passed/2 skipped；Ruff、mypy（68 源文件）、前端 contract:generate/build/lint/test（36 passed）、`git diff --check` 全部通过。
- 已消费 Task 11 建立的 `ModelGateway` 协议；测试全部使用 FakeGateway，不产生模型费用。

## 当前 Task 14 Session（committed）

- `2026-08-04-task-14-blueprint-preview` 采用「包工-子代理-Codex 审阅」新模式首次完整跑通：包工生成 Context Packet（`mvp-task-14-28db7a8-20260804-final-v1`），实施子代理 TDD 实现，包工桥接 Codex 独立审阅（round 1 REVISE 1 项 MUST_FIX → 修复 → round 2 PASS），本地 focused commit `daeacfd`（不 push）。
- 实现：`generation/blueprint.py`（6 阶段序列、确定性 brief、`run_blueprint_preview`）、orchestrator 的 BLUEPRINT_PREVIEW 分支（用户字段保护、provenance 保留、失败/取消保持 STALE_PREVIEW）、`application/generation.py` kind 解析、`domain/validation.py` scope delta（BLUEPRINT analysis 可选）。
- 验证：蓝图测试 8 passed；全量后端 428 passed/2 skipped；Ruff、mypy（69 源文件）clean；OpenAPI/前端契约无变化；`git diff --check` 通过。
- Task 14 不包含前端（Task 15）、真实模型调用；测试全部使用 FakeGateway。

## 当前 Task 15 Session（committed）

- `2026-08-04-task-15-generation-experience` 采用「包工-子代理-Codex 审阅」模式完成 Milestone 3 收尾：包工生成 Context Packet（`mvp-task-15-5df2352-20260804-final-v1`），实施子代理实现前端生成体验，Codex 独立审阅（round 1 REVISE 1 项 MUST_FIX → 修复 → round 2 PASS），本地 focused commit `038635a`（不 push）。
- 实现：`api/ndjson.ts`（NDJSON 流式解析 + streamGeneration）、`features/generation/`（useGeneration/GenerationProgress/GenerationError）、`AskGusReviewPage.tsx`（四操作）、`BlueprintEditorPage.tsx`（更新预览 + STALE_PREVIEW 阻止接受）、router 模式分发、`playwright.config.ts` + E2E fake flow。
- 验证：vitest 52 passed；Playwright E2E 7 passed；build/lint 通过；后端 428 passed/2 skipped（无后端改动）。
- 已知限制：后端 FAILED 重试未接线（`RETRY_FAILED_GENERATION` 已存在于状态机），FAILED ask-gus 草稿无操作入口；延后为单独后端 Task。
- **Milestone 3（Task 11–15）全部完成**：本地 commits（10aa141/9555a55/145e164、5949516/aca590b、daeacfd/5df2352、038635a）均已本地提交、未 push。

## 当前 R11 Session（committed）

- `2026-08-05-r11-min-pixels`：用户真实环境 Ask Gus 双图 EDIT 报 `total pixels must not be less than 655360 (got "752x672")`。方案选定：LANCZOS 放大为主、极端比例受控拦截兜底。修复（commit `8f36b6d`，4 文件 +107/-10）：`downscale_for_vision` 新增 `min_pixels`（默认 655,360）——缩放+16 倍数对齐后不足则 `_ceil_align_edge` 两轴放大到满足下限的最小尺寸（752x672→864x768=663,552、640x480→944x704=664,576）；放大后长边将超 2048（如 16x2048）抛 ValueError；orchestrator `_prepare_vision_input` 将 ValueError 转受控 `PTS_IMAGE_INPUT_UNSUPPORTED`（422 非重试），DISH_ANALYSIS 与 PREVIEW 统一使用。
- 验证：focused 32 passed、全量 backend **468 passed/2 skipped**、ruff/mypy/diff-check clean；Codex 审阅 **PASS**（round 0）；无契约变化。未 push。

## 当前 R10 Session（committed）

- `2026-08-05-r10-buff-tooltip-prompt`：按用户参考图将 Buff 从内部摘要改为逐行中文展示，持续时间改为 `H:MM`，并补充状态/时钟/金币像素图标与分隔线的最小布局要求；保持 R9 的 Stardew item hover tooltip 硬锚点。
- 实现（commit `732b3ac`）：12 个非零 Buff 属性固定中文映射与显式正负号；隐藏 Buff ID/内部键名；420→`7:00`、490→`8:10`；无 Buff 时省略 Buff 与持续时间；售价固定末行；Ask Gus/Blueprint 共用 builder。
- 验证：TDD RED 2 failed→GREEN focused 20 passed；全量 backend 465 passed/2 skipped；Ruff、Mypy、diff-check clean；独立只读 Review PASS，无 MUST_FIX。
- 实际 Review 为 `gpt-5.6-sol/max`；项目指定的 gpt-Luna 路由在当前工具面不可用，未静默冒充。真实模型视觉效果等待用户重测；未 push。

## 当前 R9 Session（committed）

- `2026-08-05-r9-prompt-anchor`：用户反馈 EDIT prompt 过强细节引导（羊皮纸/渐变/装饰角），要求按「硬锚点 + 少量版式约束 + 字段内容」重构，星露谷 item hover tooltip 为最高优先级。修复（commit `a727a8f`，4 文件 +123/-252）：新增公共 `build_full_tooltip_prompt`（Ask Gus/Blueprint 共用；锚点「Stardew Valley item hover tooltip」、非海报/菜单/网页卡/PPT/说明书/羊皮纸公告板；字段格式 标题：/类别：/描述：/能量：+N/生命：+N/售价：Ng）；删除 `clip_visual_brief`（visual_brief 不再进 prompt，`VisualSpec.visualBrief` 持久化不变）；`enforce_preview_prompt_budget` 保留为安全网；over-budget 端到端测试改为 budget 门单元测试（新 prompt 最大字段约 1190 < 1500）。
- 验证：focused 19 passed、全量 backend **464 passed/2 skipped**、ruff/mypy/diff-check clean；Codex 审阅 **PASS**（round 0）；无契约变化。

## 当前 R8 Session（committed）

- `2026-08-05-r8-prompt-quality`：用户观察词条卡稳定出现在食物居中上方，要求模型自主判断最佳位置（SKILL §3 自适应规则）+ 预览 EDIT 指定 `quality="high"`。修复（commit `787b82c`，4 文件 +13/-2）：两处 prompt（ask-gus/blueprint）加入自适应位置指令（优先背景留白/墙面/桌面/窗景，主体中下放上方、一侧放相反侧，不固定居中、不遮挡主体）；EDIT 请求加 `quality="high"`（icon 生成不加，保持已验收行为）；测试加 quality 与措辞断言（TDD 红→绿）。
- 验证：focused 19 passed、全量 backend **464 passed/2 skipped**、ruff/mypy/diff-check clean；Codex 审阅 **PASS**（round 0）；无契约变化。

## 当前 R7 Session（committed）

- `2026-08-05-r7-edit-edge-alignment`：用户真实环境 Ask Gus 超时，Provider 报 `invalid image size: edges must be multiples of 16 (got "990x1051")`。根因：`downscale_for_vision` 只保证长边 ≤2048，未对齐 16 倍数（缩放与不缩放两条路径）。修复（commit `90700b6`）：新增 `_align_edge`（向下取整 16 倍数、min 16 保护），缩放/不缩放路径统一对齐；新增 2 个红→绿测试（4032x2689→2048x1360、990x1051→976x1040）。同一函数服务 DISH_ANALYSIS，对齐无害且更合规。
- 验证：focused 9 passed、全量 backend **464 passed/2 skipped**、ruff/mypy/diff-check clean；Codex 审阅 **PASS**（round 0）；无契约变化。

## 当前 R6 Session（committed）

- `2026-08-05-preview-pipeline-r6`：用户更新 SKILL——最终词条卡**必须由图像模型双图 EDIT 生成**（`source_images=[原图, 同一轮像素图标]`，图标优先 `iconSourceAssetId`），本地合成器/Pillow/Canvas/前端组件排版被明确列为错误做法；R5 本地合成方案推翻重做。同日用户澄清协作规则：codex-mcp 为通信桥接（非执行通道），codex 担任执行者仅限视觉/多模态 Task；审阅强度 GPT 5.6 Luna (xHigh)（`gpt-5.6-luna` + xhigh），memory 已同步。
- Packet：`docs/plans/2026-08-05-preview-pipeline-r6-packet.md`（`preview-pipeline-r6-8e5aaee-20260805-v1`）。
- 实现（commit `fb40992`，22 文件 +571/-767）：orchestrator PREVIEW 单次双图 EDIT（原图 `downscale_for_vision` ≤2048 + ICON_SOURCE，`size=原图尺寸`）；能力门 `_ensure_image_edit_capability`（不支持 → `PTS_PROVIDER_IMAGE_EDIT_UNSUPPORTED` 502 非重试，无回退）；prompt 重建（ask-gus `_preview_prompt` + `blueprint_preview_prompt` 含 gameplay 参数，字段逐字 + SKILL 视觉语言，`clip_visual_brief` 200 字符）；合成器及其独占资源/测试/golden/脚本/字体删除（scope_delta：`resources/provenance.json`、`THIRD_PARTY_NOTICES.txt` 一并清理）。
- round-1 修复（Codex REVISE 2 项 MUST_FIX）：最大合法字段下 prompt 超 1500 冻结契约 → 共享 `enforce_preview_prompt_budget`（Provider 调用前统一执行，超限受控 `PTS_PREVIEW_PROMPT_TOO_LONG` 422 非重试），TDD 红→绿；round 2 审阅 **PASS**。
- 验证：backend **462 passed/2 skipped**、frontend **71 passed**、E2E **7 passed**、ruff/mypy/build/lint/diff-check clean；无 OpenAPI/契约/前端变化。
- 非阻塞：真实 Provider 双图 EDIT 端到端未验证（下次用户验收确认模型渲染词条卡效果）；`build_blueprint_visual_brief` 措辞「菜品插画」已降级为氛围参考，改存储文本会变 API 可见字段留作加固。

## 当前 Preview Pipeline Session（committed）

- `2026-08-05-preview-pipeline-refactor`（R5）：用户反馈两问题——（1）三页只显示文案不渲染预览/图标（schema 有字段、端点已存在但无 `<img>`）；（2）orchestrator 预览阶段用 `ImageOperation.GENERATION` 生成整幅像素画，违反用户 skill `stardew-dish-card-overlay` 的「原图不可替换、只叠加词条卡」核心判定。
- 用户确认正确范式（`samples/image-edit/case/`）并要求实现走 codex-mcp（`gpt-5.6-luna`/xhigh）、主会话负责通信与验收。Context Packet：`docs/plans/2026-08-06-preview-pipeline-packet.md`（gitignored，`preview-pipeline-refactor-fd79f6a-20260805-v1`）。
- 实现（commit `8e5aaee`，17 文件 +363/-130）：合成器 `PreviewSnapshot` 改 `original_image + icon_16`、以原图为画布（保留尺寸/构图）、卡片自适应右上角、NEAREST 图标缩放、确定性文字；orchestrator PREVIEW 阶段删除模型调用，直接读原图 + icon_16 本地合成，`generatedArtAssetId` 新记录不再设置；前端三页（AskGusReviewPage/CookbookDetailPage/BlueprintEditorPage）经 `assetUrl()` 渲染 preview + icon，`imageRendering: pixelated`。
- 验证：backend **466 passed/2 skipped**、frontend **71 passed**、E2E **7 passed**、ruff/mypy/build/lint/资源检查/diff-check clean；无 OpenAPI/契约变化；包工人工核查 PREVIEW 阶段零 `ImageOperation.GENERATION`、`_read_source_image` 读 `original_image_asset_id`（skill 硬约束满足）。
- 非阻塞：真实 Provider 端到端预览视觉未验证（下次用户验收时确认）；卡片几何为确定性算法，产品侧如需微调可另立 Task。

## 当前 Milestone 3 验收修复 Session（committed）

- `2026-08-05-milestone3-acceptance-fixes` 两轮修复用户真实验证反馈：R1 `07652f6`（视觉降采样 ≤2048 + provider 错误脱敏摘要、Blueprint 生成入口覆盖 DRAFT/READY、首页草稿仪表盘）、R2 `949b762`（模型默认值 sample 配置 + 空模型守卫、FAILED 重试、草稿删除、recovery 派生字段 schema 剔除、Blueprint REVIEWABLE 重试门控）。
- 验证：R2 全量 backend **450 passed/2 skipped**、frontend **64 passed**、E2E 7 passed、ruff/mypy/build/lint/diff-check clean；无 OpenAPI/契约变化。
- 关键根因修复：`_model_schema` 剔除 `Field(frozen=True)` 派生字段解决 `recovery:value_error`（schema 曾强制模型返回只读派生字段）；`_resolve_kind` FAILED→INITIAL 解决 FAILED 重试 409。
- 非阻塞：HomePage 删除后 `list_drafts` 仍含 DISCARDED（过滤终态待用户确认）；`_strip_frozen_fields` 用 title 匹配可后续加固。

## 当前 Task 9 Session（committed）

- `2026-08-04-task-9-draft-cookbook-api` 已按最终 Context Packet（`mvp-task-9-rerun-15405d0-20260804-final-v1`）完成实现、自动验证与两轮 Review（第一轮 REVISE 4 项 MUST_FIX 已修复，第二轮 PASS），用户确认实验成功后创建本地 focused commit；工作树核验干净。
- domain 增加 `baseTemplateVersion`；persistence 扩展 asset UUID 查找与 Archive 幂等查询；application 新增 `AssetService`/`DraftService`/`CookbookService`/`Page`；api 新增 assets/drafts/cookbook 路由与 `dependencies.py` 装配。
- 验证：focused 125 passed、全量 334 passed/2 skipped、Ruff、mypy、前端 test/lint/build、`git diff --check` 与本地文档忽略检查全部通过。
- 用户已确认双 Agent 协作实验成功，后续采用里程碑粒度验收：普通 Task 的 PASS 自动进入 `auto_accepted` 并创建本地 focused commit，不在单个 Task 打断用户；Milestone 全量验证后统一验收与 push。

## 已关闭自治规则 Session（committed）

- `2026-08-04-dual-agent-autonomy-rules` 已完成规则落地、协议静态验证和旧 Task 9 产物清点；未修改 backend、frontend 或生成产品契约。
- Context Packet Schema、动态依赖闭包、技术冲突自治裁决、`BLOCKED` 边界、全局两轮 `REVISE` 上限、模型路由、Task 9 实验门和 Milestone push 门已写入控制面。
- Task 9 重做只可从新的最终 Context Packet 开始；Task 9 旧 Context Packet fixture 已移除，当前 schema 内的 rerun fixture 仅用于验证协议，不授权产品实现。

## 上一 Task 8 Session（committed）

- 2026-08-03-task-8-vanilla-catalog 已完成用户验收、focused commit 和推送。
- Task8 目标是把真实 Stardew 1.6.15 Data/Objects 变成可审计、可重复构建的原版目录，并提供安全映射与 Gameplay 校验。
- 计划文件为 docs/superpowers/plans/2026-08-03-task-8-vanilla-catalog.md；已保留用户提供的 Objects.json 与 Objects.zh-CN.json，并由构建脚本生成真实 vanilla-ingredients.json 与 provenance.json；不创建伪造的 objects-source.json。
- 已收到 Objects.json（SHA-256 6CBC66CAECFED0AAC884958E21834D572014DBF4E41E64A0AF1B190E8390FF90）和 Objects.zh-CN.json（SHA-256 E51B2EF545E519E268A793BDB9EC0905B9ED6A3F7E1BFD7EEA84D5EE79051F07）；中文名称通过 Name_Name 本地化 Key 合并。
- 最终验证已完成：真实重建与生产目录 identical；目录 808 条、85 个 named IDs，256 为 Tomato、-5 为 category；catalog 测试 51 passed，全后端 254 passed/2 skipped。两个 skipped 仅因 Windows 无 symlink 权限。

## 已关闭 Task 7 Session（committed）

- `2026-08-03-task-7-launcher-security` 已完成实现、全量验证和独立只读复审，用户已明确验收通过并创建 focused commit；Task7 设计补充和实施计划已写入并通过用户确认。
- 本 Session 只处理 Launcher 单实例启动、loopback 安全边界、一次性 launch token、HttpOnly 会话、Origin/CSRF 校验、同源静态托管、前端 bootstrap、心跳和 10 分钟空闲退出。
- Task7 不处理真实模型调用、Provider Gateway、业务草稿/菜品 API、登录账户、数据库、机器级环境变量或发布流水线。
- 设计说明：`docs/superpowers/specs/2026-08-03-task-7-launcher-security-design.md`；详细计划：`docs/superpowers/plans/2026-08-03-task-7-launcher-security.md`。
- Task1 已完成：安全测试先红后绿；当前主工作区最终安全回归 21 passed，Ruff、mypy、git diff --check 和独立只读复审均通过。修复了 health Host 校验、错误 CSRF 不续期、过期 token 清理和当前端口精确匹配。
- Task2 已完成：锁、运行记录、loopback URL、端口选择、浏览器打开和 health 探针已通过 15 项测试、Ruff、mypy、差异检查和独立只读复审；修复了总超时边界与端口 0。
- Task3 已完成：同源静态托管、SPA fallback、缺失资源安全错误、heartbeat、主动 shutdown 和生命周期 idle monitor 已通过 30 passed/1 skipped 的回归、Ruff、mypy、差异检查和独立只读复审；symlink 测试因当前 Windows 权限跳过，路径边界逻辑已覆盖。
- Task4 已完成：Launcher 主流程、CLI、动态端口、安全注入、单实例复用、health 等待、浏览器 fragment、no-browser/exit-after-health-check 和失败清理已通过 42 passed/2 skipped、Ruff、mypy、差异检查和独立只读复审；修复了站外 index symlink 预检旁路。
- Task5 已完成：前端 launch bootstrap、`X-PTS-CSRF` 内存 middleware、成功后 fragment 清除、30 秒 heartbeat 与 pagehide 清理已通过 9 项前端测试、lint、TypeScript/Vite build、差异检查和独立只读复审；实现过程中前端现有文件使用受控编辑完成，未创建提交。
- Task7 最终复验已完成：后端 201 passed, 2 skipped；前端 9 passed；Ruff、mypy、前端 lint/build、git diff --check 和本地文档忽略检查均通过；真实 no-browser Launcher smoke 在 127.0.0.1:43132 启动并完成 health 后正常退出，运行记录已清理。
- 独立只读总审阅已通过：端口预留竞态、可读失败反馈、异常清理覆盖缺口和 SPA fallback 文档路径边界均已修复并通过回归；剩余 P2 复用边界已记录为验收限制。Windows 无 symlink 权限的 2 项路径边界测试保留为 skipped；真实浏览器视觉流程仍需用户在本机确认。
- 当前下一步：完成最终验证证据、同步文档并进入用户验收准备。
## 已关闭 Task 3 Session（committed）

- `2026-08-02-task-3-frontend-shell` 已完成 verification 并通过用户验收，范围严格限定为 MVP Task 3：React/Vite/TypeScript 前端骨架、OpenAPI 生成类型、same-origin typed client、正式产品首屏和启动健康检查。
- 用户明确反馈已手动启动 Vite 与后端，首页显示正常，Network 中 health 请求返回 200，并确认“task3可以验收通过了”。
- 本 Session 的 focused commit amend 边界包含前端壳层、标准 Uvicorn `app` 入口、开发依赖兼容性调整和启动回归测试；不改变 API 路由、不调用真实模型、不实现 Task 4 或后续领域页面。
- Task 3 未把 uv 作为启动前置，也未提交 Python lockfile 或虚拟环境；前端依赖使用 pnpm workspace 与根 pnpm-lock.yaml。

## 已完成 Task 4 Session（committed）

- 2026-08-02-task-4-domain-models 已获用户设计审阅通过，正式实施计划已写入 `docs/superpowers/plans/2026-08-02-task-4-domain-models.md`，实现、独立复审和最终验证已完成，并已创建 focused commit。
- 目标是实现技术设计 §9 的严格领域模型、错误协议、验证报告和 §11 的显式状态机；实现顺序为共享基础、菜品字段、草稿/存档/导出与组合验证、状态机。
- 本阶段不实现 API、Repository、工作区持久化、模型调用、前端页面或 Mod 导出；uv 不是 Task 4 前置，不提交 Python lockfile 或虚拟环境。
- 已完成证据：Task 1–4 implementer/reviewer 串行执行；全量 `python -m pytest backend/tests -q -p no:cacheprovider` 通过；Ruff、mypy、`git diff --check`、生产旧枚举扫描和文档忽略检查通过。Task4 已验收并创建 focused commit；推送结果以 Git 核验为准。

- uv 是否必需已完成本地评估：uv 不在 PATH，但现有 Python/FastAPI 依赖、pytest（2 passed）、ruff、mypy 和直接 Python/Uvicorn health 均通过；因此 uv 不属于产品运行或发布媒介。

## 当前 Task 5 Session（committed）

- 2026-08-02-task-5-persistence 已获用户授权启动，当前状态为 committed；实现、两轮独立复审和自动验证已完成，focused commit 已创建，当前等待下一 Task 授权。本 Session 只处理本地工作区、原子 JSON 写入、领域 Repository、Asset Store 与短期回收站。
- Task5 消费 Task4 的领域记录，建立 %LOCALAPPDATA%\\PelicanTownSpecials\\workspace 的可恢复持久化边界；实体记录与资产内容是真实来源，索引只作为可重建加速层。
- 本 Session 不实现 API、Secret Store、模型调用、前端页面、Launcher、数据库或 Mod 编译；uv 不作为前置工具，不提交 Python lockfile 或虚拟环境。
- 设计说明与实施计划：docs/superpowers/specs/2026-08-02-task-5-persistence-design.md、docs/superpowers/plans/2026-08-02-task-5-persistence.md。
- 范围边界：本 Session 按 Task5 实施计划完成；正式技术设计中更完整的 WorkspaceRecord 字段、应用根 bootstrap、进程锁、更强迁移恢复和统一异常层未在本 Task 扩展，若要求纳入需另行收敛设计和实现。
- 验收证据：持久化测试 21 passed；领域+持久化回归 107 passed；完整后端回归 109 passed；Ruff、mypy、git diff --check 均通过。默认 pytest 临时目录曾出现 WinError 5，使用全新 C:\tmp basetemp 后测试通过。
- focused commit 已创建并推送到 origin/feat/mvp-implementation；Task5 已关闭.

## 已完成 Task 6 Session（committed）

- 2026-08-02-task-6-provider-settings 已获用户授权启动，设计说明和实施计划均已通过，自动验证已完成并通过用户验收，focused commit 已创建；本 Session 只处理用户级环境变量 Key、非机密 Provider Settings 和统一 ErrorEnvelope。
- 用户明确选择易用优先：应用直接新增、更新和删除当前 Windows 用户级 PTS_OPENAI_API_KEY，不要求用户手动配置环境变量；不写机器级变量，不实现 Credential Locker 作为默认持久化路径。
- Task6 设计说明：docs/superpowers/specs/2026-08-02-task-6-provider-settings-design.md；实施计划：docs/superpowers/plans/2026-08-02-task-6-provider-settings.md。
- 已实现文件：backend/src/pelican_town_specials/persistence/secret_store.py、application/settings.py、api/routes/settings.py、api/error_handlers.py，以及 api/app.py/config.py；对应 persistence/application/api 测试已补齐。
- 本 Session 不实现真实模型调用、Launcher、会话安全、CSRF、前端设置页面、数据库或 Mod 编译。
- 验收证据：全量 backend/tests 通过（152 passed）；Ruff、mypy、git diff --check 通过；依赖与敏感配置扫描无 keyring、setx、机器级环境变量或 Credential Locker 实现；生产 create_app 装配与 API 脱敏集成测试通过。
- focused commit：feat: configure provider settings and environment secrets；已推送到 origin/feat/mvp-implementation。

## 上一已关闭维护 Session 范围

- 更新 AGENTS.md，纠正已完成 Task 2 与当前无活动产品 Session 的状态，并明确开发工具不等于产品功能。
- 同步 README.md 与 docs/development/README.md 的当前状态说明。
- 移除仓库中的 uv 专属依赖 lockfile backend/uv.lock；保留 backend/pyproject.toml 的依赖/构建声明与 .gitignore 的通用 .venv/保护规则。
- 不修改业务实现、不启动 Task 3、不做真实模型调用；该 Session 已在 c4cedf0 提交并推送。

## 已完成 Task 2 的验收证据

- [x] uv sync --project backend --all-groups 成功，生成 backend/uv.lock 无冲突（CPython 3.13.14）。
- [x] health 测试先确认失败（红：ModuleNotFoundError），实现后通过（绿：1 passed）。
- [x] ruff check backend 与 mypy backend/src 通过（0 issues，strict 亦验证通过）。
- [x] frontend/openapi.json 含 /api/v1/health 与 HealthResponse（camelCase apiVersion）。
- [x] Review Subagent 规格符合性与代码质量检查通过（PASS）。
- [x] 用户已验收 verification 结果，并允许创建 focused commit。
- [x] 已创建一个 focused commit（feat: add FastAPI application shell）并推送 feat/mvp-implementation。

## 上一轮控制面维护检查

- [x] 未发现 backend/.venv、backend/venv 或 backend/virtualenv 目录。
- [x] 保留 backend/pyproject.toml 的后端依赖、构建和工具声明；未删除运行所需的 FastAPI/Uvicorn 等依赖。
- [x] 未修改业务源代码、测试或 OpenAPI 契约。
- [x] 已保留 Task 2 的 uv 历史执行证据；当前文档已将 uv 定位为可选开发便利，不作为产品运行、用户部署或产品 Task 前置。
- [x] 用户已明确验收本次控制面维护，并授权随后推送。
- [x] Task 3 与后端启动闭环已验收，统一纳入 `feat: add React application shell` 的 amend/push。

## Task 3 与本地启动闭环设计与验收边界

- 输入：现有 frontend/openapi.json，其中已冻结 GET /api/v1/health 与 HealthResponse。
- 产出：frontend/package.json、Vite/TypeScript 配置、React 入口与 Providers、apiClient、生成的 schema.d.ts、PRODUCT_COPY 和首屏测试；同时提供标准 Uvicorn `app` 入口、开发依赖兼容性配置和启动回归测试；构建产物为 frontend/dist。
- 首屏只显示正式中文产品名“鹈鹕镇新菜单”和主宣传语“把你做的菜，写进鹈鹕镇的下一张菜单。”；启动入口通过 typed client 发起 same-origin health probe。
- 不包含领域页面、草稿/收集品生命周期、真实模型调用、Mod 导出、认证会话或 Task 4+ 接口。
- [x] `pnpm install --frozen-lockfile`、`pnpm --dir frontend contract:generate`、`pnpm --dir frontend test:run`（1 file / 1 test）、`pnpm --dir frontend lint` 和 `pnpm --dir frontend build` 均通过。
- [x] `python -m pytest backend/tests -q` 通过（2 passed）；`pwsh -File scripts/verify_local_docs_ignored.ps1` 和 `git diff --check` 通过。
- [x] `python -m ruff check backend`、`python -m mypy backend/src`、Uvicorn 直连 health 和 Vite 代理 health 均通过；两端返回 `status=ok`、`app=PelicanTownSpecials`、`apiVersion=v1`。
- [x] 用户手动启动 Vite 与后端，确认首页显示以及 Network 中 `/api/v1/health` 返回 200；这补充了真实运行时联调证据。
- [x] amend 范围为前端文件、pnpm workspace/lockfile、后端标准 ASGI 启动入口、开发依赖、回归测试和两份 Task 3/启动控制面记录；不包含 Python lockfile 或虚拟环境。
- 已知限制：受限执行器曾对 Node 子进程报告 `spawn EPERM`；在真实 Windows 权限下的用户手动启动与浏览器联调已通过，不影响 Task 3 验收。

## 状态规则

修改型 Session 只能按以下顺序推进：

    planned → active → verification → awaiting_user_acceptance → accepted → committed

任何状态冲突、脏工作树、重复活动 Session 或缺失下一步都必须停下并报告。Session 历史见 docs/development/sessions/，不能用历史记录覆盖本文件的当前结论。
