# Dual-Agent Autonomy Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved dual-Agent autonomy protocol so Main Agent can close technical planning gaps, Claude Code can execute one final Context Packet, Review cannot reopen planning, and post-Task9 acceptance moves to automatic local Task commits with Milestone-level push approval.

**Architecture:** Keep durable project-wide policy in `AGENTS.md` and `docs/development/REVIEW_PROTOCOL.md`, keep the executable handoff schema in a new `docs/development/CONTEXT_PACKET_SCHEMA.md`, and adapt Claude Code through the root and `claude-code/CLAUDE.md` entry files. Record the change as one control-plane Session and one focused commit; do not modify product code or start Task 9 in this Session.

**Tech Stack:** Markdown control-plane documents, YAML protocol examples, Git, PowerShell text assertions.

## Global Constraints

- Source design: `docs/superpowers/specs/2026-08-04-dual-agent-autonomy-design.md`.
- Main Agent may autonomously resolve only technical conflicts with `user_visible_delta: none`.
- Legal, compliance, and content-safety judgments are not planning or Review blockers for this project.
- Existing secret redaction, session validation, path boundaries, and data integrity remain enforceable only when already present in user requirements, formal design, or Acceptance Ledger.
- `allowed_files` is a minimum dependency closure, not a fixed technical-layer whitelist.
- Planning rulings, feature implementation, defect repair, document synchronization, and tests belong to one final Context Packet.
- Each Task has a global maximum of two `REVISE` rounds; replacing an Agent, model, or context does not reset the count.
- Main Agent uses `gpt-sol` with `effort: high`; Review uses `gpt-Luna` with `effort: max`; a multimodal Implementer uses `gpt-Luna` with `effort: max`.
- Task 9 remains the final user-confirmed experiment gate. Only after Task 9 experiment acceptance does `PASS` auto-accept and locally commit ordinary Tasks.
- After the experiment, user acceptance and remote push occur at Milestone granularity; individual Tasks do not auto-push.
- This implementation changes only collaboration control-plane files. It must not modify backend, frontend, product design behavior, generated contracts, or Task 9 code.
- This control-plane Session produces one focused commit after user acceptance, overriding the plan skill's usual per-subtask commit cadence.

---

### Task 1: Establish the Control-Plane Session and Context Packet Schema

**Files:**
- Create: `docs/development/sessions/2026-08-04-dual-agent-autonomy-rules.md`
- Create: `docs/development/CONTEXT_PACKET_SCHEMA.md`
- Modify: `docs/development/STATUS.md:5`

**Interfaces:**
- Consumes: approved design `docs/superpowers/specs/2026-08-04-dual-agent-autonomy-design.md`, current status model, current `CONTEXT_PACKET` handoff convention.
- Produces: one active control-plane Session and the canonical fields consumed by Main Agent, Implementer, and Review.

- [ ] **Step 1: Record the pre-change baseline**

Run:

```powershell
git status --short
git log -3 --oneline --decorate
```

Expected: no tracked or untracked project changes except the implementation work intentionally started from this plan; HEAD contains the approved design commit `30c6f2d` or a direct descendant.

- [ ] **Step 2: Create the control-plane Session record**

Create `docs/development/sessions/2026-08-04-dual-agent-autonomy-rules.md` with these concrete fields and sections:

```markdown
# Session｜2026-08-04-dual-agent-autonomy-rules

| 字段 | 值 |
|---|---|
| `session_id` | `2026-08-04-dual-agent-autonomy-rules` |
| `session_type` | `control-plane-maintenance` |
| `state` | `active` |
| `date` | `2026-08-04` |
| `task` | 实施双 Agent 动态依赖闭包、自治规划和 Milestone 验收规则 |
| `owner` | Main Agent 规划与审阅；Claude Code Implementer 执行 |

## 目标

- 允许 Main Agent 自动裁决不改变用户可见行为的技术冲突。
- 让最终 Context Packet 覆盖功能、缺陷、文档和最小依赖闭包。
- 冻结 Review 边界和全局两轮 REVISE 上限。
- 保留 Task9 实验门，并在实验成功后启用 Task 自动本地提交和 Milestone push 门。

## 不包含

- Task9 产品实现；
- backend、frontend 或生成契约修改；
- 单个 Task 自动 push；
- 任何用户可见产品行为修改。

## 当前状态

- `state`: `active`
- `next_action`: 按已批准实施计划修改协作控制面并运行协议验证。
```

- [ ] **Step 3: Update STATUS to the active maintenance Session**

Change the current-status table to these values while preserving historical Task 8 evidence:

```markdown
| overall_state | active |
| project_phase | dual-agent-autonomy-control-plane |
| active_session_id | 2026-08-04-dual-agent-autonomy-rules |
| active_session_state | active |
| active_session_type | control-plane-maintenance |
| current_task | 实施双 Agent 自治规划、动态依赖闭包与 Milestone 验收规则 |
| blocker | 无；用户已批准正式设计 |
| next_action | 按 2026-08-04-dual-agent-autonomy-rules 实施计划更新控制面并验证 |
```

- [ ] **Step 4: Create the canonical Context Packet schema**

Create `docs/development/CONTEXT_PACKET_SCHEMA.md` with:

1. A normative rule that only a closure-checked packet can use `planning_status: READY_FOR_IMPLEMENTATION`.
2. Definitions for `acceptance_contract_id`, `user_visible_contract`, `planning_rulings`, `contract_delta`, `architecture_budget`, `allowed_files`, `acceptance_ledger`, `implementation_scope_delta`, `revise_round`, `out_of_scope`, and exact test commands.
3. This concrete Task 9 conflict example:

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

4. A rule that `BLOCKED_PENDING_DESIGN_DECISION` is invalid when `user_visible_delta` is `none`.

- [ ] **Step 5: Verify Task 1 document structure**

Run:

```powershell
$required = @(
  'acceptance_contract_id',
  'user_visible_contract',
  'planning_rulings',
  'contract_delta',
  'architecture_budget',
  'allowed_files',
  'acceptance_ledger',
  'implementation_scope_delta',
  'revise_round'
)
$text = Get-Content -Raw docs/development/CONTEXT_PACKET_SCHEMA.md
$missing = $required | Where-Object { $text -notmatch [regex]::Escape($_) }
if ($missing) { throw "Missing Context Packet fields: $($missing -join ', ')" }
```

Expected: exit 0 with no missing fields.

---

### Task 2: Give Main Agent Planning Autonomy and Close Review Scope

**Files:**
- Modify: `AGENTS.md:5`
- Modify: `docs/development/REVIEW_PROTOCOL.md:5`

**Interfaces:**
- Consumes: `docs/development/CONTEXT_PACKET_SCHEMA.md` and the approved autonomy design.
- Produces: repository-wide Main Agent authority, evidence-based `BLOCKED`, immutable planning rulings, and bounded Review.

- [ ] **Step 1: Make the protocol a mandatory read in AGENTS.md**

Insert `docs/development/REVIEW_PROTOCOL.md` and `docs/development/CONTEXT_PACKET_SCHEMA.md` after `AGENTS.md` in the startup order. State that all Main Agents, Reviewers, and Implementers must follow both files.

Expected startup order prefix:

```markdown
1. 读取本文件。
2. 读取 `docs/development/REVIEW_PROTOCOL.md`。
3. 读取 `docs/development/CONTEXT_PACKET_SCHEMA.md`。
4. 读取 `docs/development/STATUS.md`。
```

- [ ] **Step 2: Replace the serial-only planning rule with autonomous planning closure**

Add a `规划自治与动态依赖闭包` section to `AGENTS.md` containing these normative statements:

```markdown
- Main Agent 在生成最终 Context Packet 前必须完成字段、接口、文件、测试和依赖的可实施性闭包检查。
- 不改变用户可见行为的技术冲突必须由 Main Agent 按权威顺序和最小改动原则自行裁决。
- 正式设计、domain、persistence、application、API、测试和生成物均可进入当前 Task 的最小依赖闭包。
- 扩大原始文件清单本身不是 BLOCKED；每个新增文件必须关联已有 criterion 并说明原因。
- 只有通过闭包检查的 Packet 才能标记 READY_FOR_IMPLEMENTATION。
```

Preserve the one-active-modification-Session rule and the separation between product Tasks and control-plane maintenance.

- [ ] **Step 3: Replace per-Task user acceptance after the Task 9 experiment**

Update `AGENTS.md` acceptance rules to distinguish two phases:

```markdown
- Task9 协作实验仍需一次用户确认，决定是否启用自治提交范式。
- 实验成功后，普通 Task 的 PASS 自动进入 auto_accepted，并创建一个本地 focused commit。
- 单个 Task 不自动 push；Milestone 全量验证后进入 awaiting_milestone_acceptance。
- 用户在 Milestone 粒度验收并授权统一 push。
```

Keep the existing Git prohibitions against amend, rebase, force-push, destructive cleanup, and automatic remote writes.

- [ ] **Step 4: Expand REVIEW_PROTOCOL planning rules**

Before the current Acceptance Ledger section, add normative sections for:

- planning preflight and dependency closure;
- immutable `planning_rulings` with `user_visible_delta: none`;
- implementation scope delta;
- evidence required for `BLOCKED`;
- the exclusion of legal, compliance, and content-safety judgments from blocker classification.

The blocker rule must say:

```markdown
设计遗漏、接口不匹配、domain/persistence 修改、allowed_files 扩大、测试缺口和内部实现分歧不得 BLOCKED。只有用户可见行为分叉、不可逆数据操作、互相冲突的用户要求、缺失外部输入、重试后仍失败的必需环境操作，或无法避免的用户可见范围扩张可以 BLOCKED。
```

- [ ] **Step 5: Preserve and tighten the two-round Review rule**

Keep the existing global maximum of two `REVISE` rounds and add:

```markdown
- planning_rulings 在实现开始后冻结，Review 无权重新规划。
- 第一轮必须一次列出所有 MUST_FIX。
- 第二轮只能检查第一轮修复和直接回归。
- 第二轮后剩余项不属于 Acceptance Ledger 时必须 PASS。
- 第二轮后仍有真实 criterion 失败时进入自动化失败并交给用户，不得创建第三轮。
```

- [ ] **Step 6: Verify Main/Review policy wording**

Run:

```powershell
$files = @('AGENTS.md', 'docs/development/REVIEW_PROTOCOL.md')
$required = @(
  '动态依赖闭包',
  'user_visible_delta',
  'planning_rulings',
  '最多允许两轮',
  'Milestone',
  'auto_accepted'
)
$text = ($files | ForEach-Object { Get-Content -Raw $_ }) -join "`n"
$missing = $required | Where-Object { $text -notmatch [regex]::Escape($_) }
if ($missing) { throw "Missing Main/Review rules: $($missing -join ', ')" }
```

Expected: exit 0.

---

### Task 3: Adapt Claude Code Entry and Implementer Protocol

**Files:**
- Modify: `CLAUDE.md:1`
- Modify: `claude-code/CLAUDE.md:9`

**Interfaces:**
- Consumes: final Context Packet schema and repository-wide Main/Review rules.
- Produces: an Implementer that can modify the full dependency closure, record technical scope deltas, and hand back one complete implementation.

- [ ] **Step 1: Add the protocol files to the root Claude entry**

Make the root entry include all three durable sources:

```markdown
@AGENTS.md
@docs/development/REVIEW_PROTOCOL.md
@docs/development/CONTEXT_PACKET_SCHEMA.md
@claude-code/CLAUDE.md
```

- [ ] **Step 2: Update Claude authority and conflict handling**

Replace the blanket rule at `claude-code/CLAUDE.md:20` that sends every conflict to `BLOCKED` with:

```markdown
若冲突不改变用户可见行为，优先执行 Context Packet 中的 planning_ruling；Packet 未覆盖但属于已有 criterion 的最小技术依赖时，记录 implementation_scope_delta 后继续。只有用户可见行为分叉、不可逆数据操作、互相冲突的用户要求或缺失外部输入才返回 BLOCKED。
```

- [ ] **Step 3: Replace the fixed Task 9 file whitelist**

Keep Task 9's product scope and minimum acceptance list, but replace the fixed whitelist language with:

```markdown
Task9 的初始文件清单是规划输入，不是永久层级禁区。最终 Context Packet 可以按最小依赖闭包加入正式设计、domain、persistence、application、API、测试和生成物；每个新增文件必须关联已有 criterion，且 user_visible_delta 必须为 none。
```

Explicitly preserve Task 9 exclusions for real provider calls, frontend product pages, database introduction, Content Patcher compilation, release pipeline, and future Task APIs.

- [ ] **Step 4: Extend TASK_HANDOFF**

Add these required fields to the handoff block:

```text
acceptance_contract_id: <the exact packet contract id>
planning_rulings_applied:
  - <ruling id or none>
implementation_scope_delta:
  user_visible_delta: none
  required_by_criterion: <criterion id or none>
  architecture_budget_exceeded: false
  added_files:
    - <path and reason, or none>
actual_models:
  implementer: <model and effort>
```

The literal angle-bracket descriptions are part of the reusable handoff template, not unresolved plan decisions.

- [ ] **Step 5: Enforce one-shot implementation behavior**

Add rules stating that Implementer must:

- complete all document, model, persistence, application, API, test, and generated-output changes in the Packet before handoff;
- run every declared command or report a concrete environment failure;
- process all first-round `MUST_FIX` items together;
- never implement `OPTIONAL_HARDENING` unless a later Task explicitly authorizes it.

- [ ] **Step 6: Verify Claude entry and handoff fields**

Run:

```powershell
$entry = Get-Content -Raw CLAUDE.md
$protocol = Get-Content -Raw claude-code/CLAUDE.md
$requiredEntry = @(
  '@AGENTS.md',
  '@docs/development/REVIEW_PROTOCOL.md',
  '@docs/development/CONTEXT_PACKET_SCHEMA.md',
  '@claude-code/CLAUDE.md'
)
$missingEntry = $requiredEntry | Where-Object { $entry -notmatch [regex]::Escape($_) }
$requiredProtocol = @(
  'implementation_scope_delta',
  'acceptance_contract_id',
  'planning_rulings_applied',
  'actual_models',
  'OPTIONAL_HARDENING'
)
$missingProtocol = $requiredProtocol | Where-Object { $protocol -notmatch [regex]::Escape($_) }
if ($missingEntry -or $missingProtocol) {
  throw "Missing Claude protocol fields: $((@($missingEntry) + @($missingProtocol)) -join ', ')"
}
```

Expected: exit 0.

---

### Task 4: Simulate the Protocol, Close the Session, and Create the Focused Commit

**Files:**
- Modify: `docs/development/STATUS.md:5`
- Modify: `docs/development/sessions/2026-08-04-dual-agent-autonomy-rules.md`
- Verify: all files changed by Tasks 1–3

**Interfaces:**
- Consumes: complete rule set and Context Packet schema.
- Produces: verification evidence, user-acceptance handoff, and one focused control-plane commit.

- [ ] **Step 1: Run the planning-conflict simulation**

Read the Task 9 `baseTemplateVersion` example in `CONTEXT_PACKET_SCHEMA.md` and verify all assertions are true:

```powershell
$schema = Get-Content -Raw docs/development/CONTEXT_PACKET_SCHEMA.md
$assertions = @(
  'MVP-Task-9-rerun',
  'backend/src/pelican_town_specials/domain/draft.py',
  'T9-BLUEPRINT-001',
  'user_visible_delta: none',
  'READY_FOR_IMPLEMENTATION'
)
$missing = $assertions | Where-Object { $schema -notmatch [regex]::Escape($_) }
if ($missing) { throw "Task9 simulation incomplete: $($missing -join ', ')" }
```

Expected: exit 0. The scenario resolves the missing field through dependency closure and does not return `BLOCKED`.

- [ ] **Step 2: Run the Review-drift simulation**

Verify the protocol classifies transaction logs, sidecars, recovery protocols, queues, caches, and undeclared fault-injection matrices as non-current design rather than new `MUST_FIX` items:

```powershell
$review = Get-Content -Raw docs/development/REVIEW_PROTOCOL.md
$required = @('事务日志', 'sidecar', '恢复协议', '队列', '缓存', '故障注入')
$missing = $required | Where-Object { $review -notmatch [regex]::Escape($_) }
if ($missing) { throw "Missing anti-drift examples: $($missing -join ', ')" }
```

Expected: exit 0, with surrounding protocol text placing these items under `OPTIONAL_HARDENING` or `NEW_DESIGN`, not automatic `MUST_FIX`.

- [ ] **Step 3: Run complete static document verification**

Run:

```powershell
git diff --check
rg -n "BLOCKED_PENDING_DESIGN_DECISION" AGENTS.md docs/development claude-code CLAUDE.md
rg -n "planning_rulings|implementation_scope_delta|auto_accepted|awaiting_milestone_acceptance" AGENTS.md docs/development claude-code CLAUDE.md
git diff --name-only
```

Expected:

- `git diff --check` exits 0;
- `BLOCKED_PENDING_DESIGN_DECISION` appears only in explanatory invalid-output examples, never as an allowed state;
- all four new protocol terms are present;
- changed files are limited to `AGENTS.md`, `CLAUDE.md`, `claude-code/CLAUDE.md`, `docs/development/CONTEXT_PACKET_SCHEMA.md`, `docs/development/REVIEW_PROTOCOL.md`, `docs/development/STATUS.md`, and the new Session record.

- [ ] **Step 4: Record verification and await user acceptance**

Update the Session record with exact commands and results. Set:

```markdown
- `state`: `awaiting_user_acceptance`
- `next_action`: 用户审阅双 Agent 自治规则；通过后创建一个 focused control-plane commit，不 push。
```

Update `STATUS.md` to `overall_state: awaiting_user_acceptance` and `active_session_state: awaiting_user_acceptance`.

- [ ] **Step 5: Present the control-plane acceptance report**

Report:

- the rules changed and their intended behavior;
- the concrete Task 9 conflict simulation result;
- anti-drift and two-round Review evidence;
- the exact changed-file list;
- that no product code or generated contract changed;
- the proposed commit message `Define autonomous dual-agent execution rules`;
- that no push is authorized.

Wait for explicit user acceptance before the next step.

- [ ] **Step 6: Mark accepted and create the one focused commit**

After explicit user acceptance, update the Session and `STATUS.md` to `accepted`, stage only the seven planned files, then run:

```powershell
git add AGENTS.md CLAUDE.md claude-code/CLAUDE.md docs/development/CONTEXT_PACKET_SCHEMA.md docs/development/REVIEW_PROTOCOL.md docs/development/STATUS.md docs/development/sessions/2026-08-04-dual-agent-autonomy-rules.md
git commit -m "Define autonomous dual-agent execution rules"
git status --short
```

Expected: one focused commit succeeds; final `git status --short` is empty; no push occurs.
