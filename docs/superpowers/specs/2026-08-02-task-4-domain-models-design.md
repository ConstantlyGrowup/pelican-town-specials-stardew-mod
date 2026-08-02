# MVP Task 4 设计说明：领域模型、错误协议与状态机

> 状态：approved design，Task 4 implementation and verification committed
> Session：2026-08-02-task-4-domain-models
> 日期：2026-08-02
> 本文是 Task 4 的书面设计闸门；实现代码与验证证据记录在当前工作树和 Session 记录中。

## 0. 设计闸门与依据

用户已明确要求以 docs/development/STATUS.md 为当前状态真源，并已审阅通过本设计，授权继续 MVP Task 4 开发。当前 Session 已进入 committed；本设计说明与正式实施计划共同约束实现，领域业务代码已按计划落地、验证并提交。

设计依据按项目规则排序：

1. 用户当前确认的范围与开发工具边界；
2. docs/architecture/MVP_TECHNICAL_DESIGN.md §9 数据模型、§11.6 状态机；
3. docs/plans/MVP_IMPLEMENTATION_PLAN.md 的 Task 4 文件和测试边界；
4. AGENTS.md、docs/development/CONSTRAINTS.md 与 STATUS.md 的 Session/Git 规则。

如果后续实施计划与本文或正式技术设计冲突，必须先报告冲突；不得为了让测试通过而静默放宽模型约束。

## 1. 目标

Task 4 只建立后续 API、生成流程、Repository 和前端可以共同依赖的领域契约：

- 严格、可序列化、拒绝未知字段的 Pydantic v2 领域模型；
- 统一的业务错误摘要、验证问题和验证报告；
- 资产引用、原始输入、菜品分析、游戏化字段、草稿、生成尝试、不可变存档和导出规格；
- 由显式转换表驱动的 Draft 状态机；
- 可被单元测试证明的跨字段约束和失败恢复语义。

Task 4 的完成标志是：领域模型和状态机的接口、拒绝规则、状态转换与测试全部落成，且不依赖 API、文件系统、供应商或真实模型调用。

## 2. 非目标与边界

本 Task 不做：

- FastAPI 路由、OpenAPI 新接口、HTTP 异常映射；
- Repository、JSON 聚合文件、资产目录、垃圾箱或 Cookbook 索引；
- OpenAI 兼容适配层、真实模型请求、缓存、异步任务队列；
- 草稿/收集品页面、前端类型生成、Mod 编译和游戏内验证；
- 业务之外的环境管理、Python lockfile、虚拟环境或自动化发布流程；uv 不作为 Task 4 前置。

Task 4 可以定义 Repository 后续需要的不可变数据结构，但不实现 Repository 的读写、删除和事务。ArchivedDish 只提供冻结模型，不提供更新方法；CookbookTombstone 的落盘动作属于后续持久化 Task。

## 3. 文件边界与模块依赖

计划文件范围如下：

- 修改 backend/src/pelican_town_specials/domain/common.py：增加供领域模型使用的 StrictModel；保留现有 API 专用 ApiModel 的兼容边界。
- 新建 domain/errors.py：AppError、ErrorSummary 和错误码/错误细节类型。
- 新建 domain/validation.py：ValidationIssue、ValidationReport，以及不属于单字段的验证组合。
- 新建 domain/assets.py：AssetRef、AssetKind、MediaType、SourceInput。
- 新建 domain/dish.py：DishAnalysis、SemanticIngredient、GameIngredient、PresentationSpec、RecoverySpec、BuffAttributes、BuffSpec、GameplaySpec、VisualSpec、Provenance。
- 新建 domain/draft.py：DraftMode、DraftStatus、DraftRecord、GenerationAttempt、GenerationStage、StageAttempt 及相关枚举。
- 新建 domain/archive.py：ArchivedDish 和只读 Cookbook DTO。
- 新建 domain/export.py：ExportSpec。
- 新建 state_machine.py：DraftAction、ALLOWED_TRANSITIONS、transition。
- 新建 backend/tests/domain/test_models.py 和 backend/tests/domain/test_state_machine.py。

依赖方向固定为：

~~~text
common
  ├─ errors
  ├─ validation
  ├─ assets
  ├─ dish
  ├─ draft
  ├─ archive
  └─ export
draft + errors + validation
  └─ state_machine
~~~

领域模块不得反向导入 api、config、Repository、FastAPI 或供应商客户端。为了避免循环依赖，跨模型校验放在 validation.py，状态机只依赖 DraftRecord、枚举和 AppError。

## 4. 统一模型基类与序列化策略

在 domain/common.py 增加 StrictModel：

~~~python
class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )
~~~

具体约束：

- 所有 Task 4 领域模型继承 StrictModel；未知字段一律拒绝，不做静默丢弃。
- Python 内部使用 snake_case；API/JSON 序列化通过 to_camel 产生 camelCase；测试同时覆盖字段名和序列化结果。
- ID 使用 UUID v4；时间要求 timezone-aware UTC；对外序列化为结尾为 Z 的 ISO 8601。
- schemaVersion、revision、数量、金额均为正整数或技术设计规定的非负范围；枚举只接受正式文档定义值。
- SHA-256 必须是 64 位小写十六进制；相对路径只作为持久化内部字段，不进入 API DTO。
- StrictModel 只负责结构和局部约束；目录存在性、资产引用存在性、跨对象一致性由 validation.py 处理。

RecoverySpec 不接受调用方直接覆盖派生字段。输入事实只有 edibility；model validator 确定性派生：

~~~text
energyRestore = floor(edibility × 2.5)
healthRestore = floor(edibility × 1.125)
calculationVersion = stardew-1.6
~~~

## 5. 错误协议与验证报告

### 5.1 AppError

AppError 是领域层内部可预期业务错误，不携带堆栈、密钥、完整 prompt 或供应商原始正文。最小字段：

- code：稳定机器可读代码，例如 PTS_STATE_ILLEGAL_TRANSITION、PTS_VALIDATION_FAILED；
- message：面向日志/上层的安全摘要；
- http_status：供后续 API 映射的建议状态码；Task 4 不实现 HTTP 映射；
- details：可序列化的结构化细节；
- retryable：是否允许上层按相同操作重试。

非法转换必须抛出 code 为 PTS_STATE_ILLEGAL_TRANSITION、http_status 为 409 的 AppError，并在 details 中包含 currentState 和 allowedActions。

### 5.2 ErrorSummary

ErrorSummary 是 DraftRecord/GenerationAttempt 可持久化的安全错误摘要，包含 code、message、retryable、可选 stage、requestId 和 occurredAt。它与 AppError 分开：前者是记录，后者是控制流异常。

### 5.3 ValidationIssue 与 ValidationReport

ValidationIssue 字段为 code、severity、path、message、details；severity 只允许 ERROR 或 WARNING。ValidationReport 字段为 valid、issues、validatedAt、validatorVersion。

- 存在 ERROR 时 valid 必须为 false；
- 只有 ERROR 阻止生成、预览更新或接受；WARNING 仅供 UI/后续平衡提示；
- Pydantic 单字段错误转换成报告属于上层适配，不在 Task 4 伪造 HTTP 422；
- validation.py 提供 validate_draft(draft) -> ValidationReport，负责草稿字段联动、模式权属、sourceRevision 和资产引用规则。

## 6. 领域对象设计

### 6.1 资产和原始输入

AssetRef 按技术设计 §9.5 实现：

- assetId、kind、mediaType、sha256、byteSize、createdAt；
- 图片的 width/height；派生资产的 sourceRevision 和 attemptId；
- relativePath 仅持久化内部使用；
- AssetKind 只允许 ORIGINAL_IMAGE、GENERATED_ART、PREVIEW、ICON_SOURCE、ICON_16、MOD_SPRITESHEET、EXPORT_ZIP；
- mediaType 只允许技术设计规定的 PNG/JPEG/WebP/ZIP 白名单。

SourceInput 包含 originalImageAssetId、可选 contextText 和 language。contextText 去首尾空白且最多 500 字符；language 只允许 zh-CN 或 en-US。模型只验证形状，原图 kind 的存在性由组合验证处理。

### 6.2 菜品与游戏字段

DishAnalysis 和 SemanticIngredient 完整遵循技术设计 §9.7：识别名称、摘要、烹饪方式、风味、1–12 个语义原料、0–1 置信度和安全提示。

GameIngredient 的 itemId 必须由目录校验层确认；数量为 1–99；displayName 必须来自目录事实源；mappingReason 为 1–200 字符；catalogVersion 必填。Task 4 不加载真实目录，但保留版本字段和验证入口。

PresentationSpec：

- displayName 1–60；
- internalName 匹配 ^[A-Za-z][A-Za-z0-9_]{2,47}$；
- categoryLabel 1–40；
- description 1–400；
- 可选 gusComment；
- tags 0–12，单项最多 30 字符且去重。

RecoverySpec、BuffAttributes、BuffSpec 和 GameplaySpec 按技术设计 §9.10–§9.11 实现：

- edibility 0–500，能量/生命/计算版本只能由验证器派生；
- Buff durationMinutes 为 10–1440 的 10 的倍数；
- BuffAttributes 至少一个非零字段；一个菜最多一个 BuffSpec；
- ingredients 数量为 1–8，itemId 唯一；
- sellPrice 为 0–50000；
- recipeUnlock 只接受 DEFAULT。

VisualSpec 包含 visualBrief、生成/预览/图标资产 ID、sourceRevision 和 promptVersion。它不把结构化字段或权威文字交给图像资产作为事实源。

Provenance：

- mode 只允许 ASK_GUS 或 BLUEPRINT；
- authorityByField 的值只允许 AGENT_ASSIGNED、USER_ASSIGNED、SYSTEM_GENERATED、TEMPLATE_DEFAULT、CACHE_REUSED；
- generationSource 只允许 FRESH_GENERATION 或 USER_AUTHORED；
- Blueprint 的 cacheEligibility 必须为 false；
- canonicalDishSignature 可为空并只作为后续第三期元数据。

允许的 FieldAuthority 不包含 COPIED_FROM_SIMPLE。负向测试可以传入这个字符串验证 Pydantic/枚举拒绝，但实现中的枚举、映射和业务常量不得把它作为可接受字段值。

### 6.3 草稿与生成尝试

DraftRecord 完整遵循技术设计 §9.14，至少包含 schemaVersion、draftId、mode、status、revision、source、可选 analysis/presentation/gameplay/visuals、provenance、activeAttemptId、lastAttemptId、lastError、createdAt、updatedAt 和 archivedDishId。

- mode 创建后不可变；
- revision 为正整数；成功写入新的可变草稿快照时递增；
- DraftRecord 的字段组合完整性由 validate_draft 处理；
- 状态变化不进行 I/O，不偷偷创建 attempt 或资产。

GenerationAttempt 遵循 §9.15，包含 attemptId、draftId、kind、sourceRevision、status、currentStage、stages、可选 candidateRecordPath、时间和错误。candidateRecordPath 只是持久化层内部字段，不能出现在公共 DTO。

GenerationStage 允许技术设计 §11.1 的 INPUT_VALIDATION、DISH_ANALYSIS、GAMEPLAY_DESIGN、INGREDIENT_MAPPING、VISUAL_BRIEF、ICON_GENERATION_AND_NORMALIZATION、PREVIEW_ART_GENERATION_AND_COMPOSITION、RESULT_VALIDATION、ATOMIC_PROMOTION。StageAttempt 记录阶段状态、0–3 次重试、时间和 ErrorSummary。

### 6.4 不可变存档与导出规格

ArchivedDish 是冻结快照：

- schemaVersion、dishId、archiveRevision=1、archivedAt；
- presentation、gameplay、visuals；
- contentHash、internalProvenance、sourceDraftId。

Task 4 不暴露更新方法；不通过 model_copy 或 Repository 伪造 PATCH 语义。Cookbook DTO 单独定义，明确排除 mode、sourceDraftId、gusComment 和供应商模型信息，确保收集品不泄露来源模式。

ExportSpec 包含 1–100 个去重 dishIds、packDisplayName、packSlug、semver version、description 和 language。packSlug 使用技术设计规定的正则。ExportRecord 属于后续导出流程，Task 4 不实现。

## 7. 状态机设计

DraftAction 采用明确的业务动作值：

- FIELDS_READY；
- START_INITIAL_GENERATION；
- GENERATION_SUCCEEDED；
- GENERATION_FAILED；
- RETRY_FAILED_GENERATION；
- START_FULL_REGENERATION；
- REGENERATION_SUCCEEDED；
- REGENERATION_FAILED；
- REGENERATION_CANCELLED；
- MODIFY_FIELDS；
- PREVIEW_UPDATED；
- ACCEPT；
- DISCARD。

ALLOWED_TRANSITIONS 是唯一状态真源，键为 (DraftStatus, DraftAction)，值为目标 DraftStatus。transition(draft, action, optional now) 只执行内存状态转换，不能调用外部服务。

| 当前状态 | 动作 | 目标状态 | 额外规则 |
|---|---|---|---|
| DRAFT | FIELDS_READY | READY | 输入/字段组合是否完整由 validation.py 判断 |
| READY | START_INITIAL_GENERATION | GENERATING | 初次 attempt 由后续生成流程创建 |
| GENERATING | GENERATION_SUCCEEDED | REVIEWABLE | 保持当前 revision |
| GENERATING | GENERATION_FAILED | FAILED | 保留安全错误记录位置 |
| FAILED | RETRY_FAILED_GENERATION | GENERATING | 只允许重试失败的初次生成 |
| REVIEWABLE + ASK_GUS | START_FULL_REGENERATION | REGENERATING | 旧结果继续作为安全回退 |
| REGENERATING | REGENERATION_SUCCEEDED | REVIEWABLE | 整套替换；revision 递增 1 |
| REGENERATING | REGENERATION_FAILED | REVIEWABLE | 保留旧结果和原 revision |
| REGENERATING | REGENERATION_CANCELLED | REVIEWABLE | 保留旧结果和原 revision |
| REVIEWABLE + BLUEPRINT | MODIFY_FIELDS | STALE_PREVIEW | 合法用户字段改变后预览失效 |
| STALE_PREVIEW | PREVIEW_UPDATED | REVIEWABLE | sourceRevision 必须由上层确认 |
| REVIEWABLE | ACCEPT | ARCHIVED | 接受前的完整性由 validation.py 判断 |
| DRAFT/READY/GENERATING/REGENERATING/FAILED/REVIEWABLE/STALE_PREVIEW | DISCARD | DISCARDED | ARCHIVED 和 DISCARDED 为终止状态 |

模式不符合时，即使状态相同也视为非法转换。例如 BLUEPRINT 不能 START_FULL_REGENERATION，ASK_GUS 不能 MODIFY_FIELDS。非法转换统一抛出 PTS_STATE_ILLEGAL_TRANSITION/409，并返回当前状态和允许动作列表。

transition 必须保持输入不可变：返回新的 DraftRecord；不修改原对象、不写文件、不创建 UUID 之外的外部副作用。时间由 UTC helper 提供；测试可以传入固定 now 以避免时钟不稳定。

## 8. TDD 测试设计

先写失败测试，再实现最小模型和状态机。测试文件只覆盖 Task 4 允许的领域边界：

### test_models.py

至少包括：

1. RecoverySpec(edibility=80) 得到 energyRestore=200、healthRestore=90、calculationVersion=stardew-1.6；
2. FieldAuthority 传入 COPIED_FROM_SIMPLE 被拒绝；该字符串只出现在负向测试中，不出现在允许枚举/生产常量中；
3. unknown field、宽松数字/字符串转换、未知枚举值均失败；
4. UUID v4、UTC 时间、revision/schemaVersion、sha256、相对路径和 ID 正则；
5. ingredients 只能为 1–8 项，itemId 去重；
6. 目录外枚举、Buff 时长/属性上限、PackSlug 正则失败；
7. Blueprint provenance 的 cacheEligibility 必须为 false；
8. Cookbook DTO 序列化结果不含 mode、sourceDraftId、gusComment 和 provider/model 字段；
9. GenerationAttempt 的 candidateRecordPath 不进入公共 DTO；
10. ValidationReport 在 ERROR 存在时 valid=false。

### test_state_machine.py

至少包括：

- DRAFT 到 READY、READY 到 GENERATING、初次成功到 REVIEWABLE；
- 初次失败到 FAILED，失败重试回 GENERATING；
- 以 revision=3 构造 Ask Gus REVIEWABLE 草稿，完整重生成失败/取消后回 REVIEWABLE 且 revision 仍为 3；
- 完整重生成成功回 REVIEWABLE 且 revision 递增；
- Blueprint 字段修改进入 STALE_PREVIEW，预览更新回 REVIEWABLE；
- 接受进入 ARCHIVED，非 ARCHIVED 草稿可 DISCARD；
- ARCHIVED 和不匹配模式动作抛出 PTS_STATE_ILLEGAL_TRANSITION/409；
- 非法转换的 details 含 currentState 和 allowedActions。

不调用 FastAPI TestClient、不创建临时工作区、不请求模型。测试命令使用当前 Python 环境的模块入口；uv 可选但不是前置，不提交 Python lockfile 或本地虚拟环境。

## 9. 验证与交付边界

实现阶段计划运行：

~~~powershell
python -m pytest backend/tests/domain -q
python -m ruff check backend/src/pelican_town_specials/domain backend/tests/domain
python -m mypy backend/src/pelican_town_specials/domain
~~~

随后复跑与已有 Task 3 的回归检查：

~~~powershell
python -m pytest backend/tests -q
python -m ruff check backend
python -m mypy backend/src
git diff --check
~~~

预期结果：

- 所有领域测试通过；
- ruff 和 strict mypy 通过；
- 不产生或提交 Python lockfile、任何 .venv 或其他虚拟环境文件；
- 不改变 /api/v1/health、frontend/openapi.json 或 Task 3 首页行为；
- 领域模块中不把 COPIED_FROM_SIMPLE 作为可接受 FieldAuthority；
- 任何设计/规格冲突先回报，不通过放宽模型来消解。

## 10. Session 与提交边界

本设计说明和实施计划属于 Task 4 控制面；当前 Session 已进入 committed，业务代码已按计划实现、完成 verification 并创建 focused commit；推送结果以 Git 核验为准。

实现 Session 的建议 focused commit 包含：

- domain/common.py 及 Task 4 领域实现文件；
- backend/tests/domain/；
- Task 4 设计说明、实施计划和必要的当前 Session/STATUS 控制面同步。

项目规则仍然是：完成 verification、用户明确验收后，创建一个 focused commit；推送需另行授权。项目设计源索引保持 ignored，只在本地同步，不纳入该 commit。

## 11. 已确认的关键决定

以下边界已由用户审阅确认，实施计划必须保持一致：

1. 是否同意在现有 domain/common.py 增加 StrictModel，而不是改变 API 专用 ApiModel；
2. 是否同意状态机以显式 ALLOWED_TRANSITIONS 表为唯一转换源，并由 transition 返回不可变副本；
3. 是否同意 Blueprint/Ask Gus 的模式动作限制，以及完整重生成失败保留旧 revision；
4. 是否同意 Cookbook DTO 与内部 ArchivedDish 分离，并在 DTO 中隐藏来源模式和供应商信息；
5. 是否同意 Task 4 使用当前 Python 环境执行验证；uv 可作为个人开发可选工具，但不属于产品或 Task 前置，也不提交 Python lockfile 或虚拟环境配置。

用户已确认上述边界；当前按正式实施计划拆成 implementer 可直接执行的逐步任务。