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
