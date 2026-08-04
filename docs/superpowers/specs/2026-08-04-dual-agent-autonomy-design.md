# 双 Agent 自治开发闭环设计

日期：2026-08-04
状态：已获用户设计确认，等待规则实施计划

## 1. 背景

项目采用双 Agent 协作：Codex Main Agent 负责规划与审阅，Claude Code Implementer 负责修改、测试和产物生成。Task 9 试运行暴露出两类失败：

1. Review 在多轮 `REVISE` 中增加未冻结的架构要求，造成验收目标漂移；
2. Main Agent 在规划期发现技术设计、实施计划、现有模型和允许文件不闭合后，直接要求用户裁决，导致实现尚未开始便进入 `BLOCKED`。

现有全局两轮 `REVISE` 上限解决了审阅无限加码问题，但还没有赋予 Main Agent 足够的规划自治权。本设计补足规划、实现、审阅、本地提交与 Milestone 推送之间的完整闭环。

## 2. 目标

- Main Agent 在一轮规划中发现并裁决不改变用户可见行为的技术冲突。
- 将功能需求、既有缺陷修复、必要文档修订和最小依赖闭包合并为一份最终 Context Packet。
- Implementer 一次性交付代码、测试、文档和生成物。
- Review 只验证冻结合同，不重新打开规划或追加架构目标。
- Task 9 实验成功后，每个 Task 自动验收并创建本地 focused commit。
- 用户介入收敛到真正的用户可见行为分叉、不可逆数据操作、缺失外部输入和 Milestone 验收/push。

## 3. 非目标

- 不允许 Main Agent 自主改变用户可见产品行为。
- 不允许 Implementer 以技术修复名义提前实现未来 Task。
- 不取消 Acceptance Ledger、两轮 `REVISE` 上限或测试门槛。
- 不允许 Review 以最佳实践或潜在加固替代已冻结验收项。
- 不自动 push 单个 Task。
- 法律、合规和内容安全不作为本项目的规划或审阅阻塞条件。

项目已经明确的密钥脱敏、会话验证、路径边界和数据完整性仍属于技术功能契约；只有它们已经存在于用户需求、正式设计或 Acceptance Ledger 中时才能阻塞。

## 4. 角色与权限

### 4.1 Main Agent

Main Agent 负责：

- 读取用户需求、正式设计、实施计划、现有代码、测试和开发状态；
- 在生成 Context Packet 前执行可实施性闭包检查；
- 裁决所有不改变用户可见行为的技术冲突；
- 定义最小依赖闭包和最终 `allowed_files`；
- 冻结 Acceptance Ledger、架构预算和规划裁决；
- 审阅 Implementer 交付并返回 `PASS`、`REVISE` 或证据充分的 `BLOCKED`；
- `PASS` 后驱动自动状态更新和本地 focused commit。

Main Agent 在规划阶段不直接修改产品代码。需要修订正式设计、计划或控制面时，应把这些修改作为 Context Packet 的实施内容交给 Implementer。

### 4.2 Implementer

Implementer 负责：

- 按最终 Context Packet 修改文档、domain、persistence、application、API、测试和生成物；
- 按 TDD 或 Packet 指定顺序完成实现；
- 运行 Packet 中全部 focused、contract、static 和 regression 验证；
- 记录必要的实施期最小范围扩展；
- 保持工作树未提交并返回结构化交接，等待 Main Agent Review。

Implementer 不得改变 `user_visible_contract`、删除验收项或扩大架构预算。

### 4.3 Review Subagent

Review Subagent 是只读验证者。它只检查 Acceptance Ledger、冻结的 `planning_rulings`、允许的实施期范围扩展和回归证据。它无权重新规划 Task。

## 5. 规划期可实施性闭包

Main Agent 在交付 Context Packet 前必须检查：

1. 每个验收项都有对应实现位置和测试路径；
2. 计划引用的字段、DTO、端点、Repository 方法和生成脚本真实存在，或已经列入修改范围；
3. `allowed_files` 足以完成全部验收项；
4. 正式设计、实施计划、现有模型和持久化接口之间不存在未裁决冲突；
5. 依赖 Task 的实际接口满足当前 Task，不以文档中的理想接口替代代码事实；
6. 架构预算明确区分当前 Task 必需调整与未来加固；
7. 用户可见行为已经冻结且没有未决分叉。

发现技术冲突时，Main Agent 必须按以下顺序裁决：

1. 保持用户已经冻结的可见行为；
2. 遵守正式技术设计，必要时修复设计内部遗漏；
3. 保持现有合法数据和兼容行为；
4. 选择修改范围最小、复用现有抽象、测试最容易覆盖的方案；
5. 在同等可行方案中选择架构复杂度最低的一种。

文档漏字段、接口不匹配、缺少 Repository 能力或原始文件清单不完整，都必须在规划期转化为 `planning_ruling`，不得直接要求用户裁决。

## 6. 动态依赖闭包

`allowed_files` 不再是预先固定的层级白名单，而是完成冻结验收项所需的最小依赖闭包。

Main Agent 可以把以下文件加入同一个 Context Packet：

- 正式技术设计与实施计划；
- domain 模型和领域测试；
- persistence port、Repository 和持久化测试；
- application service、API DTO、route 和 API 测试；
- OpenAPI、前端生成类型和其他明确生成物；
- Task 状态与 Session 控制面文件。

每个文件必须记录 `action`、`reason` 和对应的 `criterion_ids`。加入底层文件本身不构成范围扩张；只有与冻结验收项无关的修改才属于越界。

## 7. 单一最终 Context Packet

最终 Packet 至少包含：

```yaml
task_id: <stable-task-id>
base_commit: <commit>
planning_status: READY_FOR_IMPLEMENTATION
acceptance_contract_id: <immutable-id>
revise_round: 0

objective: <task objective>
user_visible_contract: <frozen behavior>

planning_rulings:
  - conflict: <observed conflict>
    sources: [<authoritative locations>]
    decision: <minimal technical ruling>
    rationale: <why this is compatible>
    user_visible_delta: none

contract_delta:
  documents: [<required changes>]
  domain: [<required changes>]
  persistence: [<required changes>]
  application_api: [<required changes>]

architecture_budget:
  allowed: [<necessary structural changes>]
  forbidden: [<nonessential upgrades>]

allowed_files:
  - path: <path>
    action: create | modify | generated
    reason: <dependency closure reason>
    criterion_ids: [<criterion-id>]

acceptance_ledger:
  - criterion_id: <unique-id>
    source: <authoritative source>
    requirement: <verifiable requirement>

out_of_scope: [<explicit exclusions>]
test_commands: [<exact commands>]
```

只有通过可实施性闭包检查的 Packet 才能使用 `READY_FOR_IMPLEMENTATION`。不得同时返回完整 Packet 和 `BLOCKED_PENDING_DESIGN_DECISION`。

## 8. 自治裁决与 BLOCKED

以下问题不得返回 `BLOCKED`：

- 设计文档遗漏、章节不一致或技术表述冲突；
- 计划与现有代码接口不匹配；
- 需要增加或修改 domain/persistence 文件；
- 需要扩大原始 `allowed_files`；
- 需要补测试、DTO、迁移代码或 Repository 方法；
- 现有代码缺陷或技术债影响当前验收项；
- 存在多种内部实现，但用户可见结果相同；
- Reviewer 偏好其他架构或希望增加加固；
- 法律、合规或内容安全判断。

只有以下情况可以 `BLOCKED`：

- 可行方案会产生不同的用户可见行为，现有需求无法确定选择；
- 必须删除、覆盖或不可逆迁移已有用户数据；
- 用户的明确要求彼此冲突；
- 缺少 Agent 无法生成或获取的外部输入；
- 当前环境经过合理重试后仍无法执行必需操作；
- 完成任务必然超出冻结的用户可见产品范围；
- 指定模型不可用且没有用户预授权的替代模型。

`BLOCKED` 必须给出用户可见分叉、不可逆操作、外部输入或环境失败的具体证据。缺少这些证据时，Main Agent 必须继续裁决并生成 Packet。

## 9. 实施期范围扩展

可实施性闭包应尽量覆盖全部文件。Implementer 仍可能发现未预见的技术依赖。只要不改变用户可见行为、由已有验收项直接要求且不超出架构预算，Implementer 可以自动加入最小文件范围，并在交接中记录：

```yaml
implementation_scope_delta:
  user_visible_delta: none
  required_by_criterion: <criterion-id>
  architecture_budget_exceeded: false
  added_files:
    - path: <path>
      reason: <why required>
```

Main Agent 在 Review 时验证该扩展。满足条件时必须接受，不能仅因文件不在原始清单中返回 `REVISE`。

## 10. Review 封闭边界

- `planning_rulings` 在实现开始后冻结；Review 不得重新讨论或推翻。
- Review 只能检查 Acceptance Ledger 中已有 criterion。
- 第一轮 Review 必须一次列出全部 `MUST_FIX`。
- 每项 `MUST_FIX` 必须包含 `criterion_id`、权威来源、可复现证据和最小修复方案。
- 架构偏好、额外加固和未来扩展只能进入 `OPTIONAL_HARDENING`。
- 第二轮只验证第一轮修复项和由修复直接造成的回归。
- 每个 Task 全局最多两轮 `REVISE`；更换 Agent、模型或上下文不重置计数。
- 第二轮后不得开始第三轮 Review。
- 第二轮后只剩非阻塞项时必须 `PASS`；仍有真实未满足 criterion 时进入自动化失败并交给用户。

## 11. 模型路由

- Main Agent 使用 `gpt-sol`，`effort: high`。
- Review Subagent 使用 `gpt-Luna`，`effort: max`。
- 需要视觉理解、视觉检查或其他多模态判断时，Implementer 临时使用 `gpt-Luna`，`effort: max`。
- 路由变化不改变 Context Packet、Acceptance Ledger、架构预算或 Review 轮次。
- Agent 必须报告实际模型和 effort；指定模型不可用时不得静默 fallback。

## 12. Task 9 实验门

Task 9 仍按实验模式执行：

```text
Task 9 planning → implementation → review → PASS
                                        ↓
                              用户确认实验成功
                                        ↓
                              启用自动提交范式
```

Task 9 的用户确认只判断双 Agent 协作实验是否成功，不重新打开已经 PASS 的技术验收项。

## 13. 实验成功后的 Task 生命周期

```text
planned
  → implementation
  → verification
  → PASS
  → auto_accepted
  → local focused commit
  → next planned Task
```

规则如下：

- `PASS` 自动等价于当前 Task 验收通过；
- 自动更新 Session 和 `STATUS.md`；
- 自动创建一个本地 focused commit；
- 不再要求用户逐 Task 确认；
- 下一 Task 已有正式计划且依赖满足时可以自动启动；
- 不自动 push 单个 Task；
- 真正的 `BLOCKED` 立即交给用户，不等待 Milestone。

## 14. Milestone 验收与 push

Milestone 完成后统一执行：

1. 运行 Milestone 全量后端、前端、契约和必要人工验证；
2. 汇总本 Milestone 的 focused commits、用户可见变化、技术裁决和已知限制；
3. 将状态更新为 `awaiting_milestone_acceptance`；
4. 用户一次性验收整个 Milestone；
5. 用户验收后 push 该 Milestone 的全部本地提交。

因此，实验成功后的人类介入点只有：

- 真正涉及用户可见行为分叉的 `BLOCKED`；
- 不可逆数据操作或缺失外部输入；
- 两轮 Review 后仍存在真实 criterion 失败；
- Milestone 验收与 push。

## 15. 协议验证场景

规则实施后至少用以下场景验证：

1. **缺失领域字段**：计划要求字段但 domain model 缺失。Main Agent 自动把 domain 文件、测试和文档修订加入 Packet，不得 `BLOCKED`。
2. **持久层接口不匹配**：API 要按 ID 查询，现有 store 只接受完整引用。Main Agent 选择最小兼容接口并扩大闭包，不要求用户裁决。
3. **Archive 加固建议**：Reviewer 建议事务日志、sidecar 或故障注入，但 Acceptance Ledger 未要求。结果必须是 `OPTIONAL_HARDENING`，不得 `REVISE`。
4. **用户可见分叉**：两种方案会改变 API 或 UI 行为且需求未选择。Main Agent 返回有证据的 `BLOCKED`。
5. **实施期邻接文件**：Implementer 发现必须修改相邻 domain/persistence 测试。记录 scope delta 后继续，Review 验证最小性。
6. **两轮 Review**：第二轮后不得更换 Reviewer 开始第三轮；非阻塞剩余项必须 PASS。
7. **自动提交**：Task 9 实验成功后，普通 Task PASS 自动更新状态并创建本地 focused commit，不 push。
8. **Milestone gate**：Milestone 全量验证后等待一次用户验收，再统一 push。

## 16. 规则实施范围

后续实施计划应至少更新：

- `AGENTS.md`：加入规划自治、动态依赖闭包、自动 Task 提交和 Milestone 用户门；
- `docs/development/REVIEW_PROTOCOL.md`：扩展规划期裁决、BLOCKED 证据和实施期 scope delta；
- `claude-code/CLAUDE.md`：允许 Packet 内的 domain/persistence/文档修改及实施期最小扩展；
- 必要的协议示例或验证 fixture，用于 Task 9 重新试运行。

规则实施本身是独立控制面 Task，不计入 MVP 产品功能，也不与 Task 9 产品实现混合提交。
