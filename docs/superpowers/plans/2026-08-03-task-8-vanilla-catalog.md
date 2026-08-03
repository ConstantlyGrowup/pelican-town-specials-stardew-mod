# Task 8：Stardew 原版目录、恢复值与 Gameplay 校验 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 建立版本化的 Stardew Valley 1.6.15 原版物品目录，让语义食材只能映射到真实原版 item ID，并为料理恢复值、Buff、数量和售价提供可重复的 Gameplay 校验。

**Architecture:** 以真实的 Data/Objects 导出文件为事实源，使用独立构建脚本生成稳定排序的 vanilla-ingredients.json；VanillaCatalog 只从已构建目录读取；mapping 层验证模型返回的候选 ID 并从目录复制展示名；gameplay_rules 层组合目录成员关系、既有领域模型的硬约束和版本化的软警告规则。现有 domain/dish.py 仍是 RecoverySpec 的结构真值，不在目录层重新实现恢复公式。

**Tech Stack:** Python 3.13, Pydantic, pytest, pathlib, hashlib, json, Ruff, mypy。

## Scope boundary

- 本 Task 只建立原版目录、候选搜索/安全映射和 Gameplay 校验。
- 本 Task 不实现真实模型调用、Provider Gateway、业务 API、前端选择器、数据库、Mod 编译或游戏内发布。
- 不伪造完整的 Stardew 数据，不从网络下载未审核的数据，不把用户数据写进 resources。
- uv 仍然只是可选的开发便利工具；所有命令使用当前 Python 环境的模块入口。
- Task7 已完成的 Launcher、会话安全和同源静态托管不在本 Task 修改范围。

## External prerequisites and freeze points

实施 Step 1 前必须满足以下条件：

1. 用户已提供真实的 Stardew Valley 1.6.15 + SMAPI + Content Patcher 导出文件 resources/catalogs/stardew-1.6.15/Objects.json。实现时将保留该原始文件，并以它作为 Data/Objects 源；不把文件名差异当作数据缺失。
2. 中文导出文件 resources/catalogs/stardew-1.6.15/Objects.zh-CN.json 已提供；英文名称来自 Objects.json 的 Name，中文名称通过对象 Name_Name key 从中文导出合并。不得静默把英文复制成中文。
3. 正式设计只冻结了 Gameplay 硬范围，没有冻结软警告的数值阈值。计划采用一个显式、版本化的 GameplayRuleSet；默认使用真实原版目录可观察到的 edibility/sellPrice 范围作为 warning-only 参考；Buff duration 使用独立、版本化的 Stardew gameplay reference，不改变硬错误边界。如果用户希望产品自定义范围，应在编码前确认并写入规则版本。

中文本地化输入已解决；edibility 与 sellPrice 软警告采用真实原版目录观察范围，Buff duration 使用独立、版本化的 Stardew gameplay reference；所有软规则均为 warning-only，不改变硬错误边界。

## Files and interfaces

### Production files

- Source: resources/catalogs/stardew-1.6.15/Objects.json（用户提供的英文 Data/Objects 导出）
- Source: resources/catalogs/stardew-1.6.15/Objects.zh-CN.json（用户提供的中文 Strings/Objects 导出）
- Create: resources/catalogs/stardew-1.6.15/vanilla-ingredients.json
- Create: resources/catalogs/stardew-1.6.15/provenance.json
- Create: scripts/build_vanilla_catalog.py
- Create: backend/src/pelican_town_specials/catalog/models.py
- Create: backend/src/pelican_town_specials/catalog/repository.py
- Create: backend/src/pelican_town_specials/catalog/mapping.py
- Create: backend/src/pelican_town_specials/catalog/gameplay_rules.py
- Create: backend/tests/catalog/test_catalog.py
- Create: backend/tests/catalog/test_mapping.py
- Create: backend/tests/catalog/test_gameplay_rules.py
- Create if needed after the localization decision: a separately documented Chinese localization input; it is not silently added to the frozen file list.

### Public Python interfaces

Use snake_case internally and keep the API small:

    @dataclass(frozen=True)
    class CatalogItem:
        item_id: str
        display_name_en: str
        display_name_zh: str
        aliases: tuple[str, ...]
        category: str
        type: str
        usable_as_ingredient: bool
        is_category: bool
        edibility: int | None
        sell_price: int | None

    @dataclass(frozen=True)
    class CatalogCandidate:
        item_id: str
        score: float

    class VanillaCatalog:
        @classmethod
        def from_json(cls, path: Path) -> "VanillaCatalog": ...
        def require(self, item_id: str) -> CatalogItem: ...
        def search(self, query: str, limit: int = 20) -> list[CatalogItem]: ...

    def map_ingredient(
        semantic: SemanticIngredient,
        candidates: Sequence[CatalogCandidate],
        catalog: VanillaCatalog,
    ) -> GameIngredient: ...

    def validate_gameplay(
        spec: GameplaySpec,
        catalog: VanillaCatalog,
        *,
        rules: GameplayRuleSet | None = None,
    ) -> ValidationReport: ...

The exact raw Data/Objects adapter is decided only after inspecting the supplied export. The parser must reject an unknown shape with a safe, stable error rather than guessing field positions.

## Implementation sequence

### Task 1: Register the real source and define deterministic build output

Files:

- Use the supplied Objects.json as the raw Data/Objects source and Objects.zh-CN.json as the localization source; preserve both raw files unchanged.
- Create resources/catalogs/stardew-1.6.15/provenance.json.
- Create scripts/build_vanilla_catalog.py.
- Add focused builder tests under backend/tests/catalog/test_catalog.py.

- [x] Confirm the source file is an actual 1.6.15 Data/Objects export and inspect its schema.
- [x] Add a small test fixture that mirrors the observed export shape. The fixture is only for parser tests; it is not the production catalog.
- [x] Write a failing test for deterministic output, required fields, category IDs, unusable objects, and malformed source rejection.
- [x] Run the focused test and confirm it fails because the builder is absent.
- [x] Implement a narrow parser for the observed export shape. Do not add broad heuristic fallbacks.
- [x] Normalize item IDs to strings; preserve allowed negative category IDs; normalize aliases with Unicode-aware case folding and whitespace trimming.
- [x] Compute usableAsIngredient from the versioned rule, excluding category entries, non-edible objects and non-food types according to the inspected source fields. Record this decision in the builder version.
- [x] Preserve only catalog facts needed by the product: item ID, bilingual names, aliases, category/type, ingredient eligibility, and optional source edibility/sell price used for warning ranges.
- [x] Emit UTF-8 JSON with LF, two-space indentation, stable key order, and deterministic item ordering. Sort by numeric item ID and use the textual ID as a tie-breaker.
- [x] Add a CLI with exactly:

      python scripts/build_vanilla_catalog.py --source <path> --output <path>

- [x] Record provenance with gameVersion, assetName, extractedAt, sourceMethod, sourceSha256 and generatorVersion. extractedAt belongs only in provenance; it must not make vanilla-ingredients.json nondeterministic.
- [x] Rebuild the production output and inspect it for user data, absolute paths, API keys, timestamps, and source-local paths.

### Task 2: Build the catalog repository and fixed search behavior

Files:

- Create backend/src/pelican_town_specials/catalog/models.py.
- Create backend/src/pelican_town_specials/catalog/repository.py.
- Extend backend/tests/catalog/test_catalog.py.

- [x] Write failing tests for loading, required fields, duplicate IDs, missing IDs, invalid negative IDs, category lookup, exact ID search, exact normalized alias search, prefix search, token-overlap search, limit handling, and deterministic tie ordering.
- [x] Run only backend/tests/catalog/test_catalog.py and verify the failure is about the missing catalog package/behavior.
- [x] Implement strict CatalogItem/CatalogCandidate models and a read-only VanillaCatalog. Do not allow callers to mutate the loaded index.
- [x] Implement search order exactly as specified: exact ID, exact normalized alias, prefix, then token overlap. Ties are sorted by item_id after score.
- [x] Make require(item_id) the only source of authoritative item facts. Unknown IDs produce AppError with code PTS_VALIDATION_INGREDIENT_ID_UNKNOWN, HTTP 422, and no raw user payload in the message.
- [x] Make empty or over-limit searches deterministic and safe; never return a model-supplied display name.

### Task 3: Implement safe candidate mapping

Files:

- Create backend/src/pelican_town_specials/catalog/mapping.py.
- Extend backend/tests/catalog/test_mapping.py.

- [x] Write the required regression first:

      def test_mapping_cannot_return_id_outside_candidates(catalog) -> None:
          semantic = SemanticIngredient(
              name="番茄",
              normalized_name="tomato",
              visible_confidence=0.9,
          )
          with pytest.raises(AppError, match="PTS_VALIDATION_INGREDIENT_ID_UNKNOWN"):
              map_ingredient(
                  semantic,
                  [CatalogCandidate(item_id="NotReal", score=1.0)],
                  catalog,
              )

- [x] Add tests for an empty candidate list, a valid candidate, a candidate whose item exists but is not usable as an ingredient, score ties, and display-name/catalog-version copying.
- [x] Run the focused mapping tests and observe the expected red failure.
- [x] Implement mapping so every candidate is checked through catalog.require before selection. The mapper may select only from the supplied candidate IDs; it may not invent or accept a new ID from semantic text.
- [x] Select the highest score, break ties by item_id, copy displayName from CatalogItem, set the frozen catalog version stardew-1.6.15-v1, and produce a bounded mappingReason.
- [x] Use stable error codes for no candidate, unknown ID, and unusable ingredient. Keep raw candidate lists and model text out of error messages.

### Task 4: Implement recovery and Gameplay validation

Files:

- Create backend/src/pelican_town_specials/catalog/gameplay_rules.py.
- Extend backend/tests/catalog/test_gameplay_rules.py.

- [x] Write failing tests for:
  - valid and invalid catalog membership;
  - 1–8 ingredients and unique item IDs;
  - quantity 1–99;
  - edibility 0–500;
  - derived energyRestore=floor(edibility*2.5);
  - derived healthRestore=floor(edibility*1.125);
  - calculationVersion=stardew-1.6;
  - at most one Buff;
  - duration 10–1440 and a multiple of 10;
  - sellPrice 0–50,000;
  - stable warning codes for values outside the selected versioned soft rule range.
- [x] Run backend/tests/catalog/test_gameplay_rules.py and verify the expected red failure.
- [x] Implement validate_gameplay as a pure function returning the existing ValidationReport. Structural failures remain PTS_VALIDATION_* errors; warnings never make the report invalid.
- [x] Reuse the existing GameplaySpec, RecoverySpec and BuffSpec validators rather than duplicating their Pydantic constraints. Add catalog-specific checks for unknown IDs, category IDs used as ingredients, and entries marked unusable.
- [x] Keep RecoverySpec as the only calculation source. The catalog rule layer may expose a helper for display, but must not accept caller-supplied derived energy/health values.
- [x] Add a frozen GameplayRuleSet version. Edibility/sellPrice warning ranges come from the observed vanilla catalog; Buff duration uses the independent versioned gameplay reference `stardew-1.6-gameplay-reference-v1`. Include source/catalog versions in report details; never turn a soft warning into a hard rejection.
- [x] Ensure all ValidationIssue details are safe scalars and do not include prompts, API keys, file paths, or full model output.

### Task 5: Repeatability, integration checks, and documentation

- [x] Generate resources/catalogs/stardew-1.6.15/vanilla-ingredients.json from the real source.
- [x] Run the same build a second time to output/catalog-check.json:

      python scripts/build_vanilla_catalog.py --source resources/catalogs/stardew-1.6.15/Objects.json --output output/catalog-check.json

- [x] Compare the two JSON files with Compare-Object; expect no output after excluding the separately timestamped provenance file.
- [x] Run focused tests:

      python -m pytest backend/tests/catalog -q -p no:cacheprovider

- [x] Run backend regression, Ruff, mypy, git diff --check, and the local documentation-ignore verification.
- [x] Review the generated catalog for required IDs 256 (Tomato) and -5 (category), required bilingual fields, stable catalogVersion, and absence of user data.
- [x] Update the current Session, STATUS.md, README development status, and ignored design-source index with actual evidence. Do not mark the Task accepted before user review.

### Task 6: Independent review and acceptance boundary

- [x] Use a fresh implementer for each implementation subtask and a separate read-only reviewer after implementation.
- [x] Reviewer checks candidate-boundary enforcement, deterministic ranking, catalog provenance, no fabricated data, safe errors, recovery derivation, and warning/error semantics.
- [x] Main Agent reruns all commands from a clean temporary test location and records the results.
- [x] Report the scope, changed files, interfaces, tests, remaining external limitations, and proposed focused commit:

      git add resources/catalogs scripts/build_vanilla_catalog.py backend/src/pelican_town_specials/catalog backend/tests/catalog
      git commit -m "feat: add versioned Stardew ingredient catalog"

- [x] User acceptance received; the focused commit was created and pushed with separate authorization.

## Verification evidence to collect

- Source SHA-256 matches provenance.
- Generated catalog is deterministic across two builds.
- catalog.require("256").display_name_en is Tomato.
- catalog.require("-5").is_category is True.
- A model candidate outside the catalog cannot become a GameIngredient.
- A model display name cannot override the catalog display name.
- Recovery values are derived exactly from edibility.
- Hard invalid Gameplay specs return ERROR issues; soft balance concerns return WARNING issues.
- No generated file contains user data, API keys, absolute local paths, or nondeterministic timestamps except provenance.extractedAt.

## Plan review

- This plan follows the frozen Task8 file list and keeps API/frontend/model work out of scope.
- Bilingual-name provenance is resolved by the supplied Objects.zh-CN.json key map. Soft-warning thresholds use the explicit versioned observed-vanilla-range default; if a future product-specific range is needed, it must be a separate design change.
- The plan is ready for user confirmation and source-file handoff; no product code should be written before that confirmation.
