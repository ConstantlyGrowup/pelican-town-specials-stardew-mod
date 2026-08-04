# Pelican Town Specials｜Context Packet Schema

本文是包工（Claude Code 主会话）、实施子代理和 Codex Review 之间的 Context Packet 规范。它与 `docs/development/REVIEW_PROTOCOL.md` 配套使用；本文定义交接结构，Review Protocol 定义裁决和审阅边界。

## 1. Ready 条件

只有完成字段、接口、文件、测试和依赖的可实施性闭包检查后，Packet 才能使用：

```yaml
planning_status: READY_FOR_IMPLEMENTATION
```

不得同时返回完整 Packet 和 `BLOCKED_PENDING_DESIGN_DECISION`。后者不是允许的最终状态；不改变用户可见行为的技术冲突必须由包工通过 `planning_rulings` 解决。

## 2. 必需字段

最终 Packet 至少包含：

```yaml
task_id: <stable task id>
base_commit: <base commit>
planning_status: READY_FOR_IMPLEMENTATION
acceptance_contract_id: <immutable contract id>
revise_round: 0

objective: <task objective>
user_visible_contract: <frozen user-visible behavior>

planning_rulings:
  - conflict: <observed conflict>
    sources: [<authoritative locations>]
    decision: <minimal technical ruling>
    rationale: <compatibility rationale>
    user_visible_delta: none

contract_delta:
  documents: [<required document changes>]
  domain: [<required domain changes>]
  persistence: [<required persistence changes>]
  application_api: [<required application/API changes>]

architecture_budget:
  allowed: [<necessary structural changes>]
  forbidden: [<nonessential upgrades>]

allowed_files:
  - path: <path>
    action: create | modify | generated
    reason: <dependency-closure reason>
    criterion_ids: [<criterion id>]

acceptance_ledger:
  - criterion_id: <unique criterion id>
    source: <authoritative source>
    requirement: <verifiable requirement>

out_of_scope: [<explicit exclusions>]
test_commands: [<exact commands>]
```

The angle-bracket values above describe field types. A real Packet must replace them with concrete values before it is handed to Implementer.

## 3. Planning rulings

`planning_rulings` records every technical contradiction that the foreman (Claude Code main session) resolved before implementation. Each ruling must cite the authoritative sources, state the minimal decision, and explicitly state whether user-visible behavior changes.

If `user_visible_delta` is `none`, the ruling is autonomous. It may add formal documents, domain models, persistence ports, repositories, application services, API files, tests, or generated artifacts to the minimum dependency closure.

If the ruling changes a user-visible API, UI behavior, persisted user semantics, or irreversible data operation, the foreman must return evidence-based `BLOCKED` instead of silently choosing.

## 4. Implementation scope delta

Implementer should normally receive the complete dependency closure. If an unanticipated adjacent technical dependency is discovered, it may be recorded without user escalation when all conditions hold:

```yaml
implementation_scope_delta:
  user_visible_delta: none
  required_by_criterion: <existing criterion id>
  architecture_budget_exceeded: false
  added_files:
    - path: <path>
      reason: <why this file is required>
```

The foreman verifies the delta during Review. A file being absent from the initial list is not itself a Review failure.

## 5. Task 9 planning-conflict fixture

This is a new protocol fixture for the Task 9 rerun. It is not an old Task 9 Context Packet and does not authorize Task 9 implementation by itself.

```yaml
task_id: MVP-Task-9-rerun
planning_status: READY_FOR_IMPLEMENTATION
acceptance_contract_id: mvp-task-9-rerun-v1
revise_round: 0
user_visible_contract:
  - Blueprint creation returns baseTemplateVersion "blueprint-v1".
  - Blueprint conversion copies only originalImageAssetId.
planning_rulings:
  - conflict: DraftRecord lacks baseTemplateVersion although the plan requires it.
    sources:
      - docs/architecture/MVP_TECHNICAL_DESIGN.md:703
      - docs/plans/MVP_IMPLEMENTATION_PLAN.md:903
      - backend/src/pelican_town_specials/domain/draft.py:83
    decision: Add the persisted field and its domain/repository tests to the minimum dependency closure.
    rationale: This fulfills the already-defined API behavior without creating a new product choice.
    user_visible_delta: none
architecture_budget:
  allowed:
    - Add the missing domain field and persistence compatibility required by the frozen behavior.
  forbidden:
    - Transaction logs, new recovery protocols, queues, caches, or unrelated refactors.
allowed_files:
  - path: backend/src/pelican_town_specials/domain/draft.py
    action: modify
    reason: Persist the already-required Blueprint template version.
    criterion_ids: [T9-BLUEPRINT-001]
  - path: backend/tests/domain/test_models.py
    action: modify
    reason: Verify strict serialization and validation of the new field.
    criterion_ids: [T9-BLUEPRINT-001]
acceptance_ledger:
  - criterion_id: T9-BLUEPRINT-001
    source: MVP_IMPLEMENTATION_PLAN.md Task 9 Step 4
    requirement: A Blueprint Draft persists and returns baseTemplateVersion "blueprint-v1".
```

The correct result for this fixture is a `READY_FOR_IMPLEMENTATION` Packet with an expanded dependency closure, not `BLOCKED_PENDING_DESIGN_DECISION`.

## 6. Handoff requirements

Implementer must return the exact handoff schema from `claude-code/CLAUDE.md`, including:

- the unchanged `acceptance_contract_id`;
- every applied `planning_ruling`;
- any `implementation_scope_delta`;
- actual model and effort used;
- focused, contract, static, regression, and manual verification evidence;
- `scope_deviations` and `open_issues` without secrets or complete sensitive content.
