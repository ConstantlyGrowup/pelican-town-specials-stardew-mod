# Task 4 Domain Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立严格、可序列化、可测试的领域模型、错误/验证协议和 Draft 状态机，为后续 Repository、生成流程、API 和前端提供稳定契约。

**Architecture:** 领域模型按职责拆分为共享基类与错误协议、资产与菜品结构、草稿/尝试/存档/导出记录、以及独立状态机。所有模型只依赖 Pydantic 与同层领域模块；状态转换只返回内存中的新记录，不访问 API、文件系统、供应商或真实模型。

**Tech Stack:** Python 3.13、Pydantic v2、pytest、Ruff、mypy strict。

## Global Constraints

- 所有 Task 4 领域模型继承 `StrictModel`，其配置必须为 `ConfigDict(extra="forbid", strict=True, populate_by_name=True, alias_generator=to_camel)`。
- Python 内部字段使用 `snake_case`，`model_dump(by_alias=True)` 使用 `camelCase`；未知字段、未知枚举、宽松数字/字符串转换必须拒绝。
- UUID 必须是 v4；时间必须 timezone-aware UTC；SHA-256 必须是 64 位小写十六进制；持久化相对路径不能进入公共 DTO。
- `RecoverySpec` 只接受 `edibility` 事实输入，并派生 `energyRestore=floor(edibility*2.5)`、`healthRestore=floor(edibility*1.125)`、`calculationVersion="stardew-1.6"`。
- `FieldAuthority` 不得接受 `COPIED_FROM_SIMPLE`；该字符串只能出现在拒绝它的负向测试中。
- `Blueprint` 不允许 `START_FULL_REGENERATION`，`Ask Gus` 不允许 `MODIFY_FIELDS`；完整重生成失败或取消必须保留旧结果与旧 revision。
- `transition(draft, action, now=None)` 必须不修改输入、不产生 I/O 或供应商副作用；非法转换抛出 `PTS_STATE_ILLEGAL_TRANSITION`、HTTP 建议状态 409，并携带 `currentState` 与 `allowedActions`。
- Task 4 不实现 FastAPI、Repository、工作区、供应商调用、前端、Mod 编译、真实模型调用或自动发布；不新增 Python lockfile、虚拟环境或 `uv` 前置依赖。
- 每个实现行为都先由目标失败测试证明，再写最小实现；验证使用当前 Python 环境的 `python -m ...` 入口。
- 用户验收前不创建 commit；整个 Task 4 最终只创建一个 focused commit，推送另行授权。

---

## 文件结构与执行顺序

实现顺序固定为：共享基础 → 菜品与游戏字段 → 草稿/存档/导出与组合验证 → 状态机。这样后续模块只依赖已经存在的基础类型，且 `validation.py` 不在模块加载时反向导入 `draft.py`，避免循环依赖。

测试夹具约定：Task 3 创建 `backend/tests/domain/factories.py`，集中提供后续测试使用的真实 Pydantic 对象，而不是 mock。`make_draft(*, mode, status, revision=1, visual_source_revision=None)` 使用固定的 UUID、UTC 时间、`SourceInput`、完整 `Provenance`、`PresentationSpec`、`GameplaySpec` 和 `VisualSpec` 构造草稿；`visual_source_revision` 为 `None` 时使用 `revision`。它另外导出 `ask_gus_reviewable_fixture(revision=1)`、`blueprint_reviewable_fixture()`、`blueprint_draft_fixture(revision=1, visual_source_revision=None)`、`initial_attempt_fixture(candidate_record_path=None)` 和 `archived_dish_fixture(mode="ASK_GUS", source_draft_id=None)`，分别调用 `make_draft` 或对应模型构造器，并只通过参数覆盖测试需要的字段。Task 4 的 `test_state_machine.py` 从该文件导入这些函数；这样每个测试中的状态、revision、来源和时间值都是明确且可重现的。

### Task 1: 共享严格模型、错误协议与资产输入

**Files:**
- Modify: `backend/src/pelican_town_specials/domain/common.py`
- Create: `backend/src/pelican_town_specials/domain/errors.py`
- Create: `backend/src/pelican_town_specials/domain/validation.py`
- Create: `backend/src/pelican_town_specials/domain/assets.py`
- Create: `backend/tests/domain/__init__.py`
- Create: `backend/tests/domain/test_models.py`

**Interfaces:**
- Produces `StrictModel`, `DraftMode`, `Language`, `utc_now()`, `ensure_utc()`。
- Produces `AppError`, `ErrorSummary`、`ValidationIssue`、`ValidationReport`。
- Produces `AssetKind`、`MediaType`、`AssetRef`、`SourceInput`。
- `ValidationReport` 在有 `ERROR` issue 时必须为 `valid=False`；Task 3 再向同一模块增加 `validate_draft`，本 Task 不加载 `DraftRecord`。

- [ ] **Step 1: 写共享与资产的失败测试**

```python
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from pelican_town_specials.domain.assets import AssetKind, AssetRef, MediaType, SourceInput
from pelican_town_specials.domain.common import DraftMode, Language
from pelican_town_specials.domain.errors import AppError, ErrorSummary
from pelican_town_specials.domain.validation import ValidationIssue, ValidationReport, ValidationSeverity


def test_strict_models_reject_unknown_fields_and_coercion() -> None:
    with pytest.raises(ValidationError):
        SourceInput(originalImageAssetId=uuid4(), language="zh-CN", unexpected=True)
    with pytest.raises(ValidationError):
        AssetRef(
            assetId=uuid4(), kind="ORIGINAL_IMAGE", mediaType="image/png",
            relativePath="assets/a.png", sha256="a" * 64, byteSize="10",
            createdAt=datetime.now(timezone.utc), width=1, height=1,
        )


def test_asset_ref_requires_lowercase_sha_and_image_dimensions() -> None:
    values = dict(
        assetId=uuid4(), kind=AssetKind.ORIGINAL_IMAGE, mediaType=MediaType.PNG,
        relativePath="assets/original.png", byteSize=10,
        createdAt=datetime.now(timezone.utc), width=1, height=1,
    )
    with pytest.raises(ValidationError):
        AssetRef(**values, sha256="A" * 64)


def test_validation_report_cannot_be_valid_with_error() -> None:
    issue = ValidationIssue(code="PTS_INPUT_BAD", severity=ValidationSeverity.ERROR,
                            path="source", message="invalid", details={})
    with pytest.raises(ValidationError):
        ValidationReport(valid=True, issues=[issue],
                         validatedAt=datetime.now(timezone.utc), validatorVersion="v1")


def test_error_summary_is_serializable_without_provider_payload() -> None:
    summary = ErrorSummary(code="PTS_STATE_ILLEGAL_TRANSITION", message="not allowed",
                           retryable=False, requestId=uuid4(),
                           occurredAt=datetime.now(timezone.utc))
    assert summary.model_dump(by_alias=True)["requestId"]
    assert "stack" not in summary.model_dump()
    with pytest.raises(AppError):
        raise AppError(code="PTS_STATE_ILLEGAL_TRANSITION", message="not allowed",
                       http_status=409, details={"currentState": "DRAFT"}, retryable=False)


def test_source_input_trims_context_and_accepts_only_supported_language() -> None:
    source = SourceInput(originalImageAssetId=uuid4(), contextText="  ramen  ", language=Language.ZH_CN)
    assert source.context_text == "ramen"
    with pytest.raises(ValidationError):
        SourceInput(originalImageAssetId=uuid4(), contextText="x", language="ja-JP")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest backend/tests/domain/test_models.py -q`

Expected: FAIL，因为 `StrictModel`、资产模型、错误模型和验证模型尚未定义；先修正测试自身的导入/语法问题，再保留由缺少生产类型造成的失败。

- [ ] **Step 3: 实现最小共享基础与协议**

在 `common.py` 保留 `ApiModel` 原样兼容边界，并增加：

```python
class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, populate_by_name=True, alias_generator=to_camel,
    )


class DraftMode(str, Enum):
    ASK_GUS = "ASK_GUS"
    BLUEPRINT = "BLUEPRINT"


class Language(str, Enum):
    ZH_CN = "zh-CN"
    EN_US = "en-US"


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
```

`errors.py` 定义 `ErrorSummary(StrictModel)` 的 `code/message/retryable/stage?/request_id/occurred_at`，以及不继承 Pydantic 模型的 `AppError(Exception)`；`AppError` 暴露 `code`、`message`、`http_status`、`details`、`retryable`，不保存堆栈、密钥、完整 prompt 或供应商响应。`validation.py` 定义 `ValidationSeverity`、`ValidationIssue`、`ValidationReport`，并在模型验证器中强制 `valid == not any(issue.severity is ERROR)`。`assets.py` 定义白名单枚举、sha256/路径/尺寸/UTC 校验和 `SourceInput.context_text` 的去首尾空白逻辑。

- [ ] **Step 4: 运行局部测试确认通过**

Run: `python -m pytest backend/tests/domain/test_models.py -q`

Expected: 新增共享与资产测试全部 PASS；失败输入必须由实际 Pydantic 校验触发，而非测试中的 mock。

- [ ] **Step 5: 运行局部静态检查**

Run:

```powershell
python -m ruff check backend/src/pelican_town_specials/domain backend/tests/domain
python -m mypy backend/src/pelican_town_specials/domain
```

Expected: 两项均退出码 0；没有引入 `uv.lock`、`.venv` 或其他环境文件。

### Task 2: 菜品分析、展示、游戏字段与来源权属

**Files:**
- Create: `backend/src/pelican_town_specials/domain/dish.py`
- Modify: `backend/tests/domain/test_models.py`

**Interfaces:**
- Consumes `StrictModel`、`DraftMode`、`Language`、`AssetRef` 的共享规则。
- Produces `DishAnalysis`、`SemanticIngredient`、`GameIngredient`、`PresentationSpec`、`RecoverySpec`、`BuffAttributes`、`BuffSpec`、`GameplaySpec`、`VisualSpec`、`Provenance`。
- `RecoverySpec(edibility=80)` 生成 `energy_restore=200`、`health_restore=90`、`calculation_version="stardew-1.6"`。

- [ ] **Step 1: 写菜品模型失败测试**

```python
from pelican_town_specials.domain.dish import (
    BuffAttributes, BuffSpec, FieldAuthority, GameIngredient, GameplaySpec,
    Provenance, RecoverySpec,
)


def test_recovery_values_are_derived_and_not_overridable() -> None:
    recovery = RecoverySpec(edibility=80)
    assert (recovery.energy_restore, recovery.health_restore) == (200, 90)
    assert recovery.calculation_version == "stardew-1.6"
    with pytest.raises(ValidationError):
        RecoverySpec(edibility=80, energyRestore=1)


def test_field_authority_rejects_removed_legacy_value() -> None:
    with pytest.raises(ValueError):
        FieldAuthority("COPIED_FROM_SIMPLE")


def test_gameplay_requires_unique_one_to_eight_ingredients() -> None:
    ingredient = GameIngredient(itemId="24", displayName="Egg", quantity=1,
                                mappingReason="catalog match", catalogVersion="stardew-1.6.15-v1")
    base = dict(ingredients=[ingredient], recovery=RecoverySpec(edibility=80),
                sellPrice=100, isDrink=False, recipeUnlock="DEFAULT")
    GameplaySpec(**base)
    with pytest.raises(ValidationError):
        GameplaySpec(**{**base, "ingredients": [ingredient, ingredient]})


def test_buff_requires_ten_minute_multiple_and_nonzero_attribute() -> None:
    with pytest.raises(ValidationError):
        BuffSpec(id="food", durationMinutes=15, attributes=BuffAttributes(speed=1))
    with pytest.raises(ValidationError):
        BuffSpec(id="food", durationMinutes=20, attributes=BuffAttributes())


def test_blueprint_provenance_cannot_reuse_cache() -> None:
    with pytest.raises(ValidationError):
        Provenance(mode="BLUEPRINT", authorityByField={}, promptVersions={},
                   generationSource="USER_AUTHORED", cacheEligibility=True)
```

- [ ] **Step 2: 运行失败测试**

Run: `python -m pytest backend/tests/domain/test_models.py -q`

Expected: 新增测试因 `dish.py` 和领域类型不存在而 FAIL；保留该失败证据后再实现。

- [ ] **Step 3: 实现最小菜品与游戏模型**

使用 `Field` 明确字符串长度、整数范围和列表长度；用 `model_validator(mode="after")` 检查列表内 `item_id`/`tags` 唯一、BuffAttributes 至少一个非零字段、Blueprint 的 `cache_eligibility=False`。`RecoverySpec` 只接受 `edibility`，在 `mode="before"` validator 中拒绝 `energy_restore/energyRestore`、`health_restore/healthRestore`、`calculation_version/calculationVersion` 输入，再由 `mode="after"` validator 使用 `math.floor` 生成派生字段。`FieldAuthority` 的正式值只有 `AGENT_ASSIGNED`、`USER_ASSIGNED`、`SYSTEM_GENERATED`、`TEMPLATE_DEFAULT`、`CACHE_REUSED`。

- [ ] **Step 4: 运行测试和静态检查**

Run:

```powershell
python -m pytest backend/tests/domain/test_models.py -q
python -m ruff check backend/src/pelican_town_specials/domain backend/tests/domain
python -m mypy backend/src/pelican_town_specials/domain
```

Expected: Task 1 与 Task 2 测试全部 PASS，生产代码中搜索不到可接受的 `COPIED_FROM_SIMPLE` 枚举/常量，strict mypy 通过。

### Task 3: 草稿、生成尝试、存档、Cookbook DTO、导出与组合验证

**Files:**
- Modify: `backend/src/pelican_town_specials/domain/validation.py`
- Create: `backend/src/pelican_town_specials/domain/draft.py`
- Create: `backend/src/pelican_town_specials/domain/archive.py`
- Create: `backend/src/pelican_town_specials/domain/export.py`
- Create: `backend/tests/domain/factories.py`
- Modify: `backend/tests/domain/test_models.py`

**Interfaces:**
- Produces `DraftStatus`、`GenerationStage`、`StageAttempt`、`DraftRecord`、`GenerationAttempt`、`GenerationAttemptPublic`。
- Produces `ArchivedDish`、`CookbookDishSummary`、`CookbookDishDetail`、`ExportSpec`。
- Produces `validate_draft(draft: DraftRecord) -> ValidationReport`；`validation.py` 只通过字符串注解和函数内属性访问依赖 DraftRecord，避免反向模块导入。
- `GenerationAttemptPublic` 和 Cookbook DTO 的公开序列化不包含 `candidate_record_path`、`mode`、`source_draft_id`、`gus_comment` 或 provider/model 字段。

- [ ] **Step 1: 写记录、DTO 与组合验证失败测试**

```python
def test_generation_attempt_public_dto_hides_staging_path() -> None:
    attempt = initial_attempt_fixture(candidate_record_path="staging/candidate.json")
    public = GenerationAttemptPublic.from_attempt(attempt)
    assert "candidateRecordPath" not in public.model_dump(by_alias=True)


def test_cookbook_dto_hides_source_mode_and_private_fields() -> None:
    archive = archived_dish_fixture(mode="ASK_GUS", source_draft_id=uuid4())
    detail = CookbookDishDetail.from_archived_dish(archive)
    payload = detail.model_dump(by_alias=True)
    serialized = json.dumps(payload)
    for private_name in ("mode", "sourceDraftId", "gusComment", "visionModel", "textModel", "imageModel"):
        assert private_name not in serialized


def test_validate_draft_reports_stale_visual_revision_as_error() -> None:
    draft = blueprint_draft_fixture(revision=3, visual_source_revision=2)
    report = validate_draft(draft)
    assert report.valid is False
    assert any(issue.code == "PTS_VALIDATION_SOURCE_REVISION_MISMATCH" for issue in report.issues)


def test_export_spec_rejects_duplicate_dishes_and_invalid_slug() -> None:
    dish_id = uuid4()
    with pytest.raises(ValidationError):
        ExportSpec(dishIds=[dish_id, dish_id], packDisplayName="Pack",
                   packSlug="bad-slug", version="1.0.0", description="x", language="zh-CN")
```

- [ ] **Step 2: 运行失败测试**

Run: `python -m pytest backend/tests/domain/test_models.py -q`

Expected: FAIL，因为 Draft/Archive/Export 类型、DTO 转换和组合验证尚未实现。

- [ ] **Step 3: 实现 Draft 与生成记录**

定义正式状态/阶段/attempt 枚举；`DraftRecord` 包含技术设计 §9.14 的字段，所有 revision/schemaVersion 使用严格正整数，`mode`、`source`、`provenance` 和时间必填。`StageAttempt.retry_count` 为 0–3，`GenerationAttempt.source_revision` 为正整数，`candidate_record_path` 仅作为内部字段。提供：

```python
class GenerationAttemptPublic(StrictModel):
    attempt_id: UUID
    draft_id: UUID
    kind: GenerationAttemptKind
    source_revision: int
    status: AttemptStatus
    current_stage: GenerationStage | None
    stages: list[StageAttempt]
    started_at: datetime
    finished_at: datetime | None
    error: ErrorSummary | None

    @classmethod
    def from_attempt(cls, attempt: GenerationAttempt) -> "GenerationAttemptPublic":
        return cls.model_validate(attempt.model_dump(exclude={"candidate_record_path"}))
```

- [ ] **Step 4: 实现冻结存档、Cookbook DTO 和 ExportSpec**

`ArchivedDish` 使用 `archive_revision=1`、完整的 presentation/gameplay/visuals、64 位 sha256、internal provenance 与 source draft ID；不增加更新/PATCH 方法。`CookbookDishSummary` 与 `CookbookDishDetail` 只复制展示和游戏事实的公开字段，使用 `from_archived_dish()` 构造，不接收 Provenance 或 `gus_comment`。`ExportSpec` 验证 1–100 个去重 UUID、pack slug `^[A-Za-z][A-Za-z0-9_]{2,47}$`、SemVer `MAJOR.MINOR.PATCH`、1–80/200 字符长度和语言枚举。

同时在 `tests/domain/factories.py` 写入前述夹具的完整构造逻辑：固定 `uuid4()` 结果只在每次夹具调用内生成，所有 `created_at/updated_at/archived_at/started_at` 使用 `utc_now()`，所有必填嵌套字段使用 Task 2 的合法值，`archived_dish_fixture` 的 `content_hash` 使用 `"a" * 64`，`initial_attempt_fixture` 的 `stages` 至少包含一个 `StageAttempt`，并把传入的 `candidate_record_path` 原样写入内部字段。夹具不读取文件、不访问网络、不使用 pytest monkeypatch。

- [ ] **Step 5: 实现 `validate_draft` 的最小跨字段规则**

不加载文件系统或目录。至少检查：Blueprint 的 `cache_eligibility` 为 false；存在 `visuals` 时 `visuals.source_revision == draft.revision`；进入 READY/GENERATING/REGENERATING/REVIEWABLE/STALE_PREVIEW/ARCHIVED 的记录必须有相应的结构化输入；所有问题使用 `ValidationIssue`，错误码为稳定的 `PTS_VALIDATION_*`，WARNING 不使报告失效。函数返回带 UTC `validated_at` 和固定 `validator_version` 的 `ValidationReport`。

- [ ] **Step 6: 运行 Task 1–3 测试与静态检查**

Run:

```powershell
python -m pytest backend/tests/domain -q
python -m ruff check backend/src/pelican_town_specials/domain backend/tests/domain
python -m mypy backend/src/pelican_town_specials/domain
```

Expected: 所有领域模型、DTO、组合验证测试通过，严格检查通过，公共 payload 不出现内部路径和来源信息。

### Task 4: 显式 Draft 状态机

**Files:**
- Create: `backend/src/pelican_town_specials/domain/state_machine.py`
- Create: `backend/tests/domain/test_state_machine.py`

**Interfaces:**
- Produces `DraftAction`、`ALLOWED_TRANSITIONS`、`transition(draft: DraftRecord, action: DraftAction, now: datetime | None = None) -> DraftRecord`。
- `ALLOWED_TRANSITIONS` 是所有状态/动作合法目标的唯一表；模式专属规则在 `transition` 中以明确检查实现。

- [ ] **Step 1: 写状态转换失败测试**

```python
def test_failed_full_regeneration_returns_to_reviewable_without_revision_change() -> None:
    draft = ask_gus_reviewable_fixture(revision=3)
    regenerating = transition(draft, DraftAction.START_FULL_REGENERATION)
    restored = transition(regenerating, DraftAction.REGENERATION_FAILED)
    assert restored.status is DraftStatus.REVIEWABLE
    assert restored.revision == 3
    assert draft.status is DraftStatus.REVIEWABLE


def test_successful_full_regeneration_increments_revision() -> None:
    draft = ask_gus_reviewable_fixture(revision=3)
    result = transition(
        transition(draft, DraftAction.START_FULL_REGENERATION),
        DraftAction.REGENERATION_SUCCEEDED,
        now=datetime(2026, 8, 2, tzinfo=timezone.utc),
    )
    assert result.status is DraftStatus.REVIEWABLE
    assert result.revision == 4


def test_blueprint_cannot_start_full_regeneration() -> None:
    with pytest.raises(AppError) as exc_info:
        transition(blueprint_reviewable_fixture(), DraftAction.START_FULL_REGENERATION)
    assert exc_info.value.code == "PTS_STATE_ILLEGAL_TRANSITION"
    assert exc_info.value.http_status == 409
    assert "currentState" in exc_info.value.details
    assert "allowedActions" in exc_info.value.details
```

覆盖 DRAFT→READY→GENERATING→REVIEWABLE、初次失败/重试、Blueprint 修改与预览更新、接受/放弃、ARCHIVED/终止状态和 Ask Gus/Blueprint 模式限制。

- [ ] **Step 2: 运行失败测试**

Run: `python -m pytest backend/tests/domain/test_state_machine.py -q`

Expected: FAIL，因为状态动作枚举、转换表和转换函数尚未定义。

- [ ] **Step 3: 实现显式转换表和纯内存转换**

将以下动作全部列入 `DraftAction`：`FIELDS_READY`、`START_INITIAL_GENERATION`、`GENERATION_SUCCEEDED`、`GENERATION_FAILED`、`RETRY_FAILED_GENERATION`、`START_FULL_REGENERATION`、`REGENERATION_SUCCEEDED`、`REGENERATION_FAILED`、`REGENERATION_CANCELLED`、`MODIFY_FIELDS`、`PREVIEW_UPDATED`、`ACCEPT`、`DISCARD`。`ALLOWED_TRANSITIONS` 覆盖技术设计 §11.6 的每一行；缺失 key 或模式不匹配都由同一个 `_illegal_transition` 抛出 `AppError`，details 至少包含当前状态和按当前模式过滤后的允许动作名。

`transition` 使用 `draft.model_copy(update={"status": target, "updated_at": ensure_utc(now or utc_now())})` 返回新对象；仅在 `REGENERATION_SUCCEEDED` 时把 revision 加一，失败/取消回 REVIEWABLE 时保留原 revision，绝不修改传入对象或创建 attempt/UUID。

- [ ] **Step 4: 运行状态机测试与全领域检查**

Run:

```powershell
python -m pytest backend/tests/domain -q
python -m ruff check backend/src/pelican_town_specials/domain backend/tests/domain
python -m mypy backend/src/pelican_town_specials/domain
```

Expected: 全部通过；所有非法转换的错误码/HTTP 状态/details 正确，输入对象保持不变。

## 最终验收（由主 Agent 执行）

- [ ] 读取本计划与已批准设计逐项核对，确认没有 API、Repository、供应商、前端或环境配置越界。
- [ ] 运行 `python -m pytest backend/tests -q`，确认 Task 3 健康检查回归仍通过。
- [ ] 运行 `python -m ruff check backend`、`python -m mypy backend/src`、`git diff --check`。
- [ ] 搜索生产领域代码，确认 `COPIED_FROM_SIMPLE` 只存在于负向测试而不在可接受枚举/常量中。
- [ ] 确认没有新增 `uv.lock`、`.venv`、Python lockfile 或虚拟环境目录；uv 不进入启动、部署或 Task4 命令。
- [ ] 更新 `STATUS.md` 和当前 Session 到 `verification`，记录测试证据、范围外限制和建议 focused commit；等待用户明确验收后才创建 commit。
