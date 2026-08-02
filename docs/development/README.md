# 开发控制面说明

这里记录“谁可以在什么时候修改项目、如何把状态交给下一个 Agent、何时需要用户验收”。它不承载产品需求，也不替代技术设计和实施计划。

## 快速回查

```text
AGENTS.md
  ↓
docs/development/STATUS.md
  ↓
docs/development/sessions/<当前 Session>
  ↓
docs/development/CONSTRAINTS.md
  ↓
技术设计 / 实施计划 / 相关测试和 Git 状态
```

- `AGENTS.md`：所有 Agent 的固定入口和协作规则。
- `STATUS.md`：唯一的当前状态真源，只描述当前 Session、工作树事实、阻塞和下一步。
- `sessions/`：每个 Session 的追加式记录，说明状态如何变化以及哪些证据支持结论。
- `CONSTRAINTS.md`：当前项目需要反复遵守的技术、产品、安全和 Git 约束。

## 串行工作流程

1. 主 Agent 读取入口链，检查当前 Session 和 Git 工作树。
2. 用户授权后建立一个 `planned` Session；开始修改时进入 `active`。
3. 一个 Task 只由一个 implementer Subagent 处理；它通过 Context Packet 获得任务目标、依赖、允许文件和验收标准。
4. 实现完成后进入 `verification`，运行自动测试、静态检查和计划中的人工验证。
5. 默认进入 `awaiting_user_acceptance`，向用户说明任务目标、变更、证据、限制和建议提交范围。
6. 纯后台且无功能变化的 Task 只有在测试完全覆盖目标时可自动审批；任何覆盖疑问都升级给用户。
7. 用户明确接受后进入 `accepted`，创建一个 focused commit，再进入 `committed`；推送远端需要另行授权。

## 当前状态

本项目已完成 MVP Task 3 与本地启动闭环、Task 4 领域模型和 Task 5 本地持久化，Task 5 focused commit 已推送。MVP Task 6 的用户级 Key 配置、Provider Settings 和统一错误响应已验收并创建 focused commit，当前等待下一 Task 授权；以 STATUS.md 中的当前 Session 和下一步为准。
