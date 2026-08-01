# Pelican Town Specials｜Agent 协作入口

本文件是仓库内所有 Codex、Subagent 和后续接力 Agent 的稳定入口。它只定义开发协作边界；产品机制和编码接口仍以项目的正式设计与实施文档为准。

## 开始任何工作前的读取顺序

1. 读取本文件。
2. 读取 `docs/development/STATUS.md`，确认唯一活动 Session、Session 状态和精确下一步。
3. 读取 `docs/development/sessions/` 中由 `STATUS.md` 指定的当前 Session 记录。
4. 读取 `docs/development/CONSTRAINTS.md`。
5. 根据任务范围读取 `docs/architecture/MVP_TECHNICAL_DESIGN.md`、`docs/plans/MVP_IMPLEMENTATION_PLAN.md` 和项目设计源索引。
6. 在修改前检查 `git status --short`、`git diff` 和最近 Git 历史；需要时再读取历史 Session。

如果上述文档之间出现矛盾，必须报告矛盾位置，不得静默选择或覆盖。用户明确确认的规则优先于所有项目文档；技术设计优先于实施计划；`STATUS.md` 只是真实开发状态的权威，不替代产品设计。

## 当前工作模式

当前项目处于“开发控制面已建立、产品开发尚未开始”阶段。除非用户明确授权开始实施，否则：

- 不执行 MVP 的 Task 1 或后续 Task；
- 不派发实现型 Subagent；
- 不创建业务代码、依赖、前端或后端骨架；
- 不把“控制面初始化”误记为产品功能完成；
- 不创建自动提交、自动推送或自动发布流程。

## 串行 Session 规则

- 同一时间最多存在一个 `active`、`verification` 或 `awaiting_user_acceptance` 的修改型 Session。
- 一个实施 Task 对应一个修改型 Session；一个 Session 只处理计划中一个 Task 的范围。
- 每个 Task 使用新的 implementer Subagent；它只接收该 Task 的 Context Packet、相关约束和必要的当前状态。
- implementer 完成后，使用独立的只读 Review Subagent 检查规格符合性和代码质量；主 Agent 负责复跑验收、集成和状态更新。
- Session 记录是追加式历史；`STATUS.md` 是当前状态真源。历史记录不能覆盖当前状态。
- 任何无法安全解释的状态冲突、脏工作树、重复活动 Session 或缺失下一步，都必须停下来报告。

## 验收与提交规则

默认情况下，完成一个 Task 后必须先进入 `verification`，再进入 `awaiting_user_acceptance`。向用户报告时必须明确：

- 这个 Task 的任务目标和不包含的范围；
- 修改了哪些文件、产生了哪些接口或行为；
- 实际运行了哪些测试和人工验证，以及观察到的结果；
- 仍存在的限制、需要用户操作的外部验证；
- 建议的 focused commit 边界。

只有用户明确接受当前验证结果，Session 才能进入 `accepted`，随后才能创建一个 focused commit。沉默、模糊回复或只要求补充信息都不视为接受。

唯一的自动审批例外是：Task 仅包含纯后台代码，未改变用户可见或功能行为，且自动测试、静态检查和必要的代码级检查能够完全覆盖该 Task 的目标。如果覆盖范围或“无功能变化”存在疑问，必须升级为用户 Review，并说明原因，请用户决定下一步。

## Git 安全边界

- 保护用户已有文件和未提交修改；初始化前后都检查状态，不使用 reset、checkout 覆盖、广义 clean 或其他丢弃操作。
- 不自动 amend、rebase、force-push、发布或删除远端内容。
- 使用用户已经配置的 Git name/email；提交信息描述项目变更，不添加 Agent、Codex、Claude、AI 或 assistant 署名及 `Co-authored-by`。
- 一个已接受的 Session 只产生一个 focused commit；提交后核验工作树干净。
- 推送远端需要单独的用户授权，即使本地 Milestone 验收已通过。

## 文件归属

- `AGENTS.md`、`docs/development/STATUS.md`、`docs/development/sessions/` 和 `docs/development/CONSTRAINTS.md` 是可提交的开发控制面。
- `docs/architecture/`、`docs/plans/`、`design docs/`、`最初设计功能清点/` 和项目设计源索引按用户约定保持 Git ignored；它们仍然是本地设计与计划真源。
- 不自动创建通用个人 Skill 包；当前规则只服务于本项目的开发接力。
