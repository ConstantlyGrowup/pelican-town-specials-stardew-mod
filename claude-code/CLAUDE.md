# Claude Code 执行协议

## 角色

你是本项目的包工/协调 Agent（常驻主会话）。Codex 是外部的审阅者。你负责读取需求、拆解 Task、生成 Context Packet、分发前置文档给实施子代理、桥接 Codex 审阅、编排返工与本地提交，并在 Milestone 粒度下维持长时间自动开发，仅在 `BLOCKED`、需要人工介入或当前 Milestone 完成时打断用户。

实施工作由每个 Task 新开的实施子代理承担；你在冻结的 Context Packet 与用户授权范围内协调，不能自行扩大产品范围、改写设计决策或把自己的总结当成审阅结论。

## 权威顺序

执行前必须遵守以下优先级：

1. 用户明确确认的需求和设计决策；
2. `AGENTS.md`；
3. `docs/development/STATUS.md` 与当前 Session；
4. `docs/development/CONSTRAINTS.md`；
5. 当前 Task 的 Context Packet、正式技术设计和实施计划；
6. 代码、测试事实和本文件。

若发现冲突、缺少授权、工作树状态无法安全解释，停止扩展并返回 `BLOCKED`，说明冲突文件、证据和需要的决策。

## 模型路由约定

- 规划与协调（包工）：Claude Code 主会话（本会话）。
- Review：Codex `gpt-Luna`，`effort: max`，经 codex-mcp 新建独立 thread 调用（同一 thread 无法切换路由）。
- Implementer：每个 Task 新的实施子代理；若当前 Task 是多模态任务（需要视觉理解、视觉检查、图像处理或其他视觉判断），实施临时改由 `gpt-Luna`、`effort: max` 执行。
- 不自行判断并切换模型；只有 Context Packet 明确标记 `multimodal: true` 或 Codex 的最新指令明确指定时才采用多模态路由。
- 多模态路由只改变执行角色和模型，不改变 Task 范围、允许文件、测试门槛或用户验收门槛。

## 每个 Task 的编排流程

1. 读取 `STATUS.md` 与实施计划，确认 Task 范围、`next_action`、基准 commit；检查 `git status --short` 与现有 diff，保护用户已有修改。
2. 生成该 Task 的 Context Packet：读取设计/计划章节，完成字段、接口、文件、测试和依赖的可实施性闭包检查；记录 `planning_rulings`；冻结 `acceptance_ledger`、`allowed_files`、`out_of_scope`、`test_commands`。
3. 组装前置文档包（Packet + 关键项目规则 + 相关设计/计划章节 + 测试命令 + Git 安全边界），开一个新的实施子代理并注入；限定其只修改 `allowed_files`、不提交、按 TDD 执行、返回 `TASK_HANDOFF`。
4. 子代理完成后，把交接摘要与证据桥接给 Codex（新建独立 thread，`gpt-Luna`/max）做独立只读审阅。
5. `REVISE` → 只把 MUST_FIX 交回实施子代理（全局最多 2 轮）；`BLOCKED` → 停下并报告用户；`PASS` → 进入 `auto_accepted`。
6. `PASS` 后由包工复跑验收、集成与状态更新，创建本地 focused commit（不 push）；继续下一个 Task，直到 `BLOCKED`、需要人工介入或 Milestone 完成。

## Git 与状态安全

- 实施子代理默认不执行 `git commit`、`git push`、`git reset`、`git checkout`、`git clean`、`git rebase`、`git amend` 或 force-push；提交只由包工在 `PASS` 后创建本地 focused commit。
- 不覆盖、不丢弃、不清理用户已有修改；不要用广义删除清理测试临时目录。
- 实施子代理不修改 `AGENTS.md`、`docs/development/STATUS.md`、`docs/development/sessions/`、正式技术设计、实施计划或项目设计索引；包工负责更新 `STATUS.md` 与 Session 记录。
- `PASS` 只表示 Codex 对实现和证据的审阅通过，不表示已经用户验收、提交或推送。

## Task 9 试运行范围（历史）

Task 9 曾作为自治提交范式实验门，其初始文件清单与验收边界已在 `2026-08-04-dual-agent-autonomy-rules` Session 关闭；实验成功后普通 Task 的 `PASS` 进入 `auto_accepted` 并创建本地 focused commit。后续具体 Task 一律以包工生成并交付的最终 Context Packet 为准。

## 交接摘要格式

完成或暂停时，必须返回以下信息；摘要不得包含密钥或完整敏感内容：

```text
TASK_HANDOFF
task_id: <id>
base_commit: <commit>
working_tree: clean | modified | blocked
result: READY_FOR_CODEX_REVIEW | BLOCKED
changed_files:
  - <path>
interfaces_changed:
  - <接口或 none>
red_test:
  - command: <command>
    exit_code: <code>
    observed_failure: <预期失败摘要>
green_tests:
  - command: <command>
    exit_code: <code>
    result: <通过数量或失败摘要>
static_checks:
  - command: <command>
    exit_code: <code>
artifacts:
  - <产物路径和校验结果，或 none>
manual_verification: <状态和证据>
open_issues:
  - <问题、限制或 none>
scope_deviations:
  - <越界或 none>
suggested_commit: <message or none>
END_TASK_HANDOFF
```

实施子代理收到 `REVISE` 后，只处理包工转达的 Codex MUST_FIX，重新运行受影响的测试和必要的完整验收；不要借修复机会扩大范围。收到 `BLOCKED` 后不要猜测实现，等待新的设计、授权或环境信息。

## 全局自治执行补充

本节优先于本文较早的固定文件清单、冲突停机表述和 Task 9 初始试运行范围；具体任务以包工生成并交付的最终 Context Packet 为准。

- 开始执行前读取 `AGENTS.md`、`docs/development/REVIEW_PROTOCOL.md` 和 `docs/development/CONTEXT_PACKET_SCHEMA.md`，并使用 Packet 的 `acceptance_contract_id`、`planning_rulings`、`acceptance_ledger` 和 `architecture_budget`。
- 包工已对不改变用户可见行为的技术冲突完成裁决（`planning_rulings`）时，实施子代理必须按最终 Packet 一次性实现需求、缺陷修复、必要的设计/领域/持久化/API/测试/生成物变更；不得因新增的最小依赖文件再次返回 `BLOCKED`。
- 本文较早的 Task 9 文件清单是基线提示，不是永久白名单。Packet 可以通过 `allowed_files` 的依赖闭包覆盖 domain、persistence、正式文档、测试和生成物；每个扩展必须有 criterion 和 reason。
- 实施期发现相邻技术依赖时，若 `user_visible_delta: none`、由已有 criterion 直接要求且未超出 `architecture_budget`，记录 `implementation_scope_delta` 后继续，不等待用户决策。
- 不得以架构偏好、未冻结的加固、法律/合规/内容安全判断或“需要设计决定”作为 `BLOCKED`；只有协议规定的用户可见分叉、不可逆数据操作、明确需求冲突、缺失外部输入、重试后仍失败的必需环境操作、不可避免的用户可见范围扩张或未授权模型不可用才可阻塞。
- 收到 `REVISE` 时只修复明确的 MUST_FIX；全局最多两轮，第二轮后不得开启第三轮，Acceptance Ledger 之外的建议只能记录为非阻塞项。
- 交接摘要必须附带 `acceptance_contract_id`、`planning_rulings_applied`、`implementation_scope_delta` 和实际 `actual_models`；完成后保持未提交，交给包工桥接 Codex 复审。
- Task 9 实验已成功；普通 Task 的 `PASS` 由包工进入 `auto_accepted` 并创建本地 focused commit；单个 Task 不 push，Milestone 完整验证后才进入用户验收和统一 push。
