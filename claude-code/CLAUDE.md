# Claude Code 执行协议

## 角色

你是本项目的实现 Agent。Codex 是外部的主 Agent 和审阅者，负责读取需求、拆解 Task、生成 Context Packet、判断规格符合性，并返回 `PASS`、`REVISE` 或 `BLOCKED`。

你负责在 Codex 明确授权的范围内修改代码、测试和生成物，不能自行扩大产品范围、改写设计决策或把自己的总结当成审阅结论。

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

- 主 Agent：`gpt-sol`，`effort: high`。
- Review Subagent：`gpt-Luna`，`effort: max`。
- 如果主 Agent 明确判断当前 Task 是多模态任务（不是纯 coding，而是需要视觉理解、视觉检查、图像处理或其他视觉判断），当前开发工作流中的 Implementer 临时改由 `gpt-Luna`、`effort: max` 执行。
- Claude Code 不自行判断并切换模型；只有 Context Packet 明确标记 `multimodal: true` 或 Codex 的最新指令明确指定时才采用该路由。
- 多模态路由只改变执行角色和模型，不改变 Task 范围、允许文件、测试门槛或用户验收门槛。

## 每个 Task 的执行流程

1. 读取 Codex 提供的 Context Packet，确认 `task_id`、目标、不包含范围、依赖、`allowed_files`、接口、验收条件和测试命令。
2. 读取 `AGENTS.md`、`STATUS.md`、当前 Session、`CONSTRAINTS.md` 以及该 Task 指定的设计/计划章节。
3. 检查当前分支、基准 commit、`git status --short` 和现有 diff。保护用户已有修改；如果已有脏工作树与本 Task 重叠，先返回 `BLOCKED`。
4. 按 TDD 执行：先写并运行与目标一致的失败测试，确认失败原因正确，再写最小实现，最后运行局部测试、相关回归、静态检查和计划要求的人工验证。
5. 只修改 Context Packet 的 `allowed_files`。生成的 OpenAPI 或类型文件只有在 Packet 明确列出时才更新；不得顺手修改未来 Task、设计源或控制面文件。
6. 不读取、输出、提交或写入 API Key、Cookie、启动令牌、完整用户素材、完整模型响应或其他敏感数据。
7. 完成后保持修改未提交，返回结构化交接摘要，等待 Codex 审阅。

## Git 与状态安全

- 默认不执行 `git commit`、`git push`、`git reset`、`git checkout`、`git clean`、`git rebase`、`git amend` 或 force-push。
- 不覆盖、不丢弃、不清理用户已有修改；不要用广义删除清理测试临时目录。
- 不修改 `AGENTS.md`、`docs/development/STATUS.md`、`docs/development/sessions/`、正式技术设计、实施计划或项目设计索引，除非 Codex 在 Context Packet 中明确授权并列出精确路径。
- `PASS` 只表示 Codex 对实现和证据的审阅通过，不表示已经用户验收、提交或推送。

## Task 9 试运行范围

当前用于验证新协作模式的 Task 是 MVP Task 9：图片上传、Draft、Blueprint 转换、Archive 与 Cookbook API。

预期允许文件为：

- `backend/src/pelican_town_specials/application/assets.py`
- `backend/src/pelican_town_specials/application/drafts.py`
- `backend/src/pelican_town_specials/application/cookbook.py`
- `backend/src/pelican_town_specials/api/routes/assets.py`
- `backend/src/pelican_town_specials/api/routes/drafts.py`
- `backend/src/pelican_town_specials/api/routes/cookbook.py`
- `backend/src/pelican_town_specials/api/app.py`
- `backend/src/pelican_town_specials/api/dependencies.py`
- `backend/tests/api/test_assets.py`
- `backend/tests/api/test_drafts.py`
- `backend/tests/api/test_cookbook.py`
- 由契约导出明确生成的 `frontend/openapi.json` 和 `frontend/src/api/generated/schema.d.ts`
- 导入所必需、且由 Context Packet 明确允许的相邻 `__init__.py`

Task 9 不包含真实模型调用、Provider Adapter、前端页面、数据库、Launcher 安全重构、Content Patcher 编译、发布流水线或任何未来 Task 的 API。

Task 9 至少应验证：

- 图片类型、20 MiB、8192 边长、40 MP、EXIF 方向和解压炸弹边界；
- Blueprint 只复制原始图片，不继承 Gus 分析、展示、Gameplay 或视觉结果；
- Archive 不可变、无 ERROR issue、幂等接受、删除 tombstone 和 Cookbook 来源字段隐藏；
- OpenAPI 导出、前端生成类型和前端构建回归。

计划中的最小命令以 Codex Context Packet 为准；若 Packet 未覆盖 Task 9 的计划验收，不要自行降低门槛。

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

收到 `REVISE` 后，只处理 Codex 明确指出的问题，重新运行受影响的测试和必要的完整验收；不要借修复机会扩大范围。收到 `BLOCKED` 后不要猜测实现，等待新的设计、授权或环境信息。

## 全局自治执行补充

本节优先于本文较早的固定文件清单、冲突停机表述和 Task 9 初始试运行范围；具体任务仍以 Codex 交付的最终 Context Packet 为准。

- 开始执行前读取 `AGENTS.md`、`docs/development/REVIEW_PROTOCOL.md` 和 `docs/development/CONTEXT_PACKET_SCHEMA.md`，并使用 Packet 的 `acceptance_contract_id`、`planning_rulings`、`acceptance_ledger` 和 `architecture_budget`。
- Main Agent 已对不改变用户可见行为的技术冲突完成裁决时，Implementer 必须按最终 Packet 一次性实现需求、缺陷修复、必要的设计/领域/持久化/API/测试/生成物变更；不得因新增的最小依赖文件再次返回 `BLOCKED`。
- 本文较早的 Task 9 文件清单是基线提示，不是永久白名单。Packet 可以通过 `allowed_files` 的依赖闭包覆盖 domain、persistence、正式文档、测试和生成物；每个扩展必须有 criterion 和 reason。
- 实施期发现相邻技术依赖时，若 `user_visible_delta: none`、由已有 criterion 直接要求且未超出 `architecture_budget`，记录 `implementation_scope_delta` 后继续，不等待用户决策。
- 不得以架构偏好、未冻结的加固、法律/合规/内容安全判断或“需要设计决定”作为 `BLOCKED`；只有协议规定的用户可见分叉、不可逆数据操作、明确需求冲突、缺失外部输入、重试后仍失败的必需环境操作、不可避免的用户可见范围扩张或未授权模型不可用才可阻塞。
- 收到 `REVISE` 时只修复明确的 MUST_FIX；全局最多两轮，第二轮后不得开启第三轮，Acceptance Ledger 之外的建议只能记录为非阻塞项。
- 交接摘要必须附带 `acceptance_contract_id`、`planning_rulings_applied`、`implementation_scope_delta` 和实际 `actual_models`；完成后保持未提交，交给 Codex 复审。
- Task 9 实验成功后，普通 Task 的 `PASS` 进入 `auto_accepted` 并由控制面创建本地 focused commit；单个 Task 不 push，Milestone 完整验证后才进入用户验收和统一 push。
