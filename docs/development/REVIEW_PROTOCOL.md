# Pelican Town Specials｜全局 Review Protocol

本文是所有 Task、Session、Codex Main Agent、Review Subagent 和外部 Implementer 共同遵守的审阅协议。它只定义开发协作控制面，不增加产品功能。

## 1. 核心原则：验收合同冻结

每个 Task 在实现开始前必须生成一个 `Acceptance Ledger`，至少包含：

- 唯一 `acceptance_contract_id`；
- 带唯一 ID 的 MUST 验收项；
- 每项的权威来源（用户确认、技术设计、实施计划或明确的 Context Packet 条目）；
- 明确的 `out_of_scope`；
- 明确的 `architecture_budget` 和禁止的架构扩展；
- 当前 Task 的全局 `revise_round`。

Task 开始后，Acceptance Ledger 不得由 Main Agent、Review Subagent 或 Implementer 单方面增加、删除或提高标准。上一轮 `REVISE`、Review Subagent 的建议、代码中的新发现和额外探针结果都不是新的需求来源。

如果确实需要改变验收合同，必须停止当前 Task，返回 `BLOCKED`，由用户决定是否更新设计、建立新 Task 或把建议记录为后续加固项。

## 2. 三类审阅结果

### `MUST_FIX`

只有以下问题可以阻塞当前 Task，并返回 `REVISE`：

- 违反 Acceptance Ledger 中已有的 MUST 验收项；
- 违反已冻结的安全、隐私、数据不变量或用户可见接口；
- 计划中明确要求的测试、静态检查或人工验证失败；
- 实现越出已冻结的 `allowed_files` 或改变已批准接口。

每个 `REVISE` 项必须同时给出 `criterion_id`、权威来源、可复现证据和最小修复方案。只有 `P1/P2` 标签、最佳实践、主观偏好或“应该更健壮”不能单独构成 `REVISE`。

### `OPTIONAL_HARDENING`

不违反当前合同、但未来可以增强的内容只能记录为非阻塞观察，不得要求 Implementer 修改当前 Task。

### `NEW_DESIGN`

以下情况必须返回 `BLOCKED`，不能伪装成 `REVISE`：

- 新增事务日志、sidecar 协议、恢复协议、队列、缓存或其他架构层；
- 需要扩展 `allowed_files`；
- 需要改变技术设计、数据模型、用户可见行为或错误协议；
- 需要新增当前 Task 未声明的崩溃模型、性能目标或故障注入矩阵；
- 需要把后续 Task 的能力提前纳入当前 Task。

## 3. 全局硬性 Review 轮次上限

- 每个 Task 最多允许 **两轮 `REVISE`**。
- 轮次按 Task/Session 全局计数，不按 Agent、模型、Reviewer、工作树或问题数量计数。
- 更换 Implementer、启动新的 Review Subagent、重新生成 Context Packet 或把同一问题换一种表述，都不能重置计数。
- 第一轮 Review 可以一次列出多个已存在的 MUST_FIX 项；Implementer 应在同一轮内集中修复。
- 第二轮 Review 只能检查第一轮修复项和由修复直接造成的回归。
- 第二轮后仍不能 PASS，必须返回 `BLOCKED` 或进入用户 Review；不得开始第三轮 `REVISE`。

## 4. REVISE 的封闭范围

Review Subagent 在收到修复结果后不得重新进行开放式全仓库架构审查。它只能：

1. 验证上一轮列出的 `criterion_id`；
2. 验证修复没有破坏原有验收项；
3. 运行 Acceptance Ledger 中声明的测试和必要的相关回归。

新的非基线观察必须放入 `OPTIONAL_HARDENING` 或 `NEW_DESIGN`，不能自动变成下一轮的 MUST_FIX。

## 5. 强制 Review 输出格式

```yaml
review_decision: PASS | REVISE | BLOCKED
acceptance_contract_id: <immutable id>
revise_round: 0 | 1 | 2
checked_criteria:
  - <criterion_id>
must_fix:
  - criterion_id: <criterion_id>
    source: <权威来源>
    evidence: <测试、命令、文件和行号>
    minimal_fix: <最小修复>
optional_hardening:
  - <非阻塞建议或 none>
new_design:
  - <新设计请求或 none>
scope_delta: none | requested
reason_for_blocked: <仅 BLOCKED 时填写>
```

缺少 `criterion_id`、权威来源或可复现证据的 `REVISE` 不得转交 Implementer 执行；Main Agent 必须将其改为非阻塞观察或 `BLOCKED`。

## 6. 模型和路由校验

- Main Agent 和 Review Subagent 必须在交接中报告实际使用的模型与 reasoning effort。
- 指定模型不可用时不得静默 fallback；应返回 `BLOCKED`，除非用户已明确授权替代模型。
- 多模态路由只改变执行 Agent，不改变 Acceptance Ledger、轮次上限和 Task 范围。

## 7. Task 完成含义

`PASS` 只表示当前实现满足冻结 Acceptance Ledger。非阻塞观察可以保留，不要求为了“没有任何潜在问题”而继续迭代。`PASS` 之后仍遵守项目既定的用户验收、focused commit 和独立 push 授权门。

## 8. 规划自治与动态依赖闭包

本节是对前述 Review 规则的全局补充，并优先解释早期固定文件清单和旧的冲突处理表述。

- Main Agent 在生成最终 Context Packet 前必须完成字段、接口、文件、测试和依赖的可实施性闭包检查。
- 不改变用户可见行为的技术冲突由 Main Agent 按权威顺序和最小改动原则裁决，并记录在 `planning_rulings`。
- 正式设计、domain、persistence、application、API、测试和生成物均可进入当前 Task 的最小依赖闭包。
- 扩大原始 `allowed_files` 本身不是 `BLOCKED`；每个新增文件必须关联已有 criterion 并说明原因。
- 只有通过闭包检查的 Packet 才能标记 `READY_FOR_IMPLEMENTATION`。

最终 Packet 必须包含 `acceptance_contract_id`、`user_visible_contract`、`planning_rulings`、`contract_delta`、`architecture_budget`、带 `reason` 和 `criterion_ids` 的 `allowed_files`、`acceptance_ledger`、`out_of_scope`、`test_commands` 和 `revise_round`。字段定义以 `docs/development/CONTEXT_PACKET_SCHEMA.md` 为准。

## 9. 自治裁决与 BLOCKED 证据

以下问题不得单独返回 `BLOCKED`：

- 设计文档漏字段、章节不一致或技术表述冲突；
- 计划与现有代码接口不匹配；
- 需要增加或修改 domain/persistence 文件；
- 需要扩大原始 `allowed_files`；
- 需要补测试、DTO、迁移代码或 Repository 方法；
- 现有代码缺陷或技术债影响当前验收项；
- 存在多种内部实现方式但用户可见结果相同；
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

`BLOCKED` 必须给出用户可见分叉、不可逆操作、外部输入或环境失败的具体证据。缺少这些证据时，Main Agent 必须继续裁决并生成 Packet。不得把 `BLOCKED_PENDING_DESIGN_DECISION` 作为内部技术冲突的常规结果。

## 10. 实施期最小范围扩展

Implementer 发现规划期遗漏的相邻技术依赖时，可以记录以下结构并继续：

```yaml
implementation_scope_delta:
  user_visible_delta: none
  required_by_criterion: <existing criterion id>
  architecture_budget_exceeded: false
  added_files:
    - path: <path>
      reason: <why required>
```

Main Agent 在 Review 时验证该扩展。满足 `user_visible_delta: none`、已有 criterion 直接要求且不超出 `architecture_budget` 时，Review 必须接受；文件不在原始清单中不能单独构成 `REVISE`。

## 11. Review 封闭边界补充

- `planning_rulings` 在实现开始后冻结，Review 无权重新规划。
- 第一轮 Review 必须一次列出全部 `MUST_FIX`。
- 第二轮只能检查第一轮修复项和由修复直接造成的回归。
- 第二轮后剩余项不属于 Acceptance Ledger 时必须 `PASS`。
- 第二轮后仍有真实 criterion 失败时进入自动化失败并交给用户，不得创建第三轮。
- 事务日志、sidecar 协议、恢复协议、队列、缓存和未冻结的故障注入矩阵，如果不属于当前 Acceptance Ledger，只能是 `OPTIONAL_HARDENING` 或 `NEW_DESIGN`，不能自动变成 `MUST_FIX`。

## 12. Task 完成与 Milestone 提交门

- Task 9 是双 Agent 协作范式实验门；实验成功前仍需要用户确认是否启用自治提交范式。
- 实验成功后，普通 Task 的 `PASS` 自动进入 `auto_accepted`，自动更新 Session/`STATUS.md` 并创建本地 focused commit。
- 单个 Task 不自动 push；下一项已有正式计划且依赖满足时可以自动启动。
- Milestone 全量验证后进入 `awaiting_milestone_acceptance`，用户一次性验收并授权统一 push。

## 13. 强制模型与交接字段

Main Agent、Review Subagent 和 Implementer 必须报告实际模型与 effort。模型路由仍为 Main `gpt-sol/high`、Review `gpt-Luna/max`，多模态 Implementer `gpt-Luna/max`。路由变化不得重置 Acceptance Ledger 或 Review 轮次。

Review 输出除第 5 节字段外，必须包含：

```yaml
acceptance_contract_id: <exact packet contract id>
planning_rulings_checked: [<ruling id>]
implementation_scope_delta: none | <validated delta>
actual_models:
  main: <model and effort>
  review: <model and effort>
  implementer: <model and effort>
```
