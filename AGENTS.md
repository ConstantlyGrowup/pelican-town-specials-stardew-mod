# Pelican Town Specials｜Agent 协作入口

本文件是仓库内所有 Codex、Subagent 和后续接力 Agent 的稳定入口。它只定义开发协作边界；产品机制和编码接口仍以项目的正式设计与实施文档为准。

## 开始任何工作前的读取顺序

1. 读取本文件。
2. 读取 `docs/development/STATUS.md`，确认唯一活动 Session、Session 状态和精确下一步。
3. 读取 `docs/development/sessions/` 中由 `STATUS.md` 指定的当前 Session 记录；如果没有活动 Session，则读取最近一次已关闭 Session 和本次明确的维护 Session。
4. 读取 `docs/development/CONSTRAINTS.md`。
5. 根据任务范围读取 `docs/architecture/MVP_TECHNICAL_DESIGN.md`、`docs/plans/MVP_IMPLEMENTATION_PLAN.md` 和项目设计源索引。
6. 在修改前检查 `git status --short`、`git diff` 和最近 Git 历史；需要时再读取历史 Session。

如果上述文档之间出现矛盾，必须报告矛盾位置，不得静默选择或覆盖。用户明确确认的规则优先于所有项目文档；技术设计优先于实施计划；`STATUS.md` 只是真实开发状态的权威，不替代产品设计。

## 当前工作模式

2026-09-04 最新状态：Task 56「Gus Provider 故障后持久化续作」已实现、验证并获用户验收及提交推送 MVP 分支授权；合同见 `docs/plans/2026-09-03-task-56-gus-generation-resume.md`。成功阶段保存到现有本地 staging；Provider 故障/重启后手动继续，主动完整重新生成仍从头；不自动收费重放、不扩展 Blueprint。本次不修改 main、不打 tag/发布，正式安装包仍为 v1.5.4。M12 已按用户后续指令恢复：Task 50 正在补完独立审阅与修复，随后按计划推进至实际人工参与处暂停。精确状态以 STATUS.md 为准。

Milestone 6–8 与 Task 30 已随 v1.3.0 发布。Milestone 9“全局生成记忆与 Canonical 召回”Task 31–36、Task 36.1“原图参考像素图标生成补丁”和 Task 36.2“官方/非官方 OpenAI-compatible 端点适配补丁”均已实现、独立审阅并验收；Canonical 当前开发命中阈值为 `0.85`（2026-09-03 用户调整，边界命中、`0.849` 与 `0.80` miss；正式 v1.5.4 包仍为 0.80）。Milestone 10“EXE 无感使用统计”Task 37–39 已在 Codex 全量接管范式下实现并通过 detector/主 Agent 全量验收，focused commits 为 `d198a3e`、`3600d09`、`c4c1bcf`。M10 在配置完整的 Release 后端静默记录最小 personless 人工事件，不改变 UI/API，不采集创作内容、Provider、设备指纹、IP/Geo 或页面行为，采集故障不得影响业务。用户于 2026-08-29 已配置 Repository Variables并接受首次验收数据直接参与匿名聚合；v1.4.0 已正式发布（GitHub Actions run `33228870083` success，setup.exe + portable ZIP + SHA256SUMS 均核验通过）。用户提供的 M9 对照样本仅 `n=2`，只作为正向实测信号，不承诺稳定节省。2026-08-30 用户已验收 Milestone 11“试用体验与可用性保护”规划并授权开发：Task 40–42 已完成；2026-08-31 用户验收确认失败不扣次修复有效，并追加“稍后重试→直接重试”、试用 Key 轮换、Task 43“蓝图分类/标签可直接移除”和 Task 44“试用不可用时放弃草稿并返回主页”。新增 UI Task 均经 `luna_worker` 实施、detector PASS，完整构建与 bundle smoke 全绿；用户已统一验收。v1.5.0 已正式发布（GitHub Actions run `33403142756` success）。Task 45“料理蓝图英文分类/标签显示与搜索”保持中文 canonical 存储不变，已同步 `main` 与 `feat/mvp-implementation` 并随 v1.5.1 正式发布（GitHub Actions run `33464868361` success）。Task 46“生成错误提示英文本地化”已同步两分支并随 v1.5.2 正式发布（GitHub Actions run `33470806371` success，setup.exe + portable ZIP + SHA256SUMS 均独立下载核验通过）。Task 47“公共试用模型/额度热修复”已通过 `luna_worker`、detector 与主 Agent验收：隐藏试用改用 `gpt-image-2`，额度为 5，合法 v1/v2 状态一次性迁移 schema v3 并为所有旧用户重置完整 5 次，个人默认模型不变；已随 v1.5.3 发布；Task 48 收集品批量删除已随 v1.5.4 发布并核验。当前正式版本为 v1.5.4。2026-09-03 用户授权 Task 49：优化上游双语分析命名一致性，将最终匹配阈值调到 0.85；保持 schema、历史记忆、temperature 省略与本地评分不变，已按 luna_worker → detector PASS → 主 Agent 流程完成本地验证与 focused commit（全量 880 passed/2 skipped，focused 76 passed）；已推送 MVP（2026-09-04 fetch 核验 54ffc68）、未发布，真实一致性和命中率效果待实测。后续完整队列、Redis、夜间批处理和多用户在线架构不属于第三期。

自 2026-08-04 起采用「包工-子代理-Codex 审阅」协作模式：

### Milestone 9 临时 Codex 全量接管（2026-08-25 用户明确授权）

本节记录 Milestone 9 Task 31–36 已实际采用并完成的临时优先流程；M9 已获用户统一验收并推送。它不删除或永久改写下方历史/default 的 Claude+Codex 通信流，后续是否继续采用 Codex 全量接管由用户另行决定。

- Codex 主 Agent 作为 M9 常驻协调者和最终验收者：持有状态真源、生成/冻结 Context Packet、串行派发、复核证据、编排返工、更新控制面并创建 PASS 后的本地 focused commit。
- 每个 Task 使用新的自定义 `luna_worker`（`gpt-5.6-luna` / `max`）实施；worker 只处理一个范围明确、边界清晰、可独立完成的委派任务，不改变主任务目标、不扩大冻结范围、不提交或 push。
- 实施完成后使用新的自定义 `detector`（`gpt-5.6-sol` / `medium`，read-only）按冻结 Acceptance Ledger 和 `REVIEW_PROTOCOL.md` 独立审阅，返回 `PASS` / `REVISE` / `BLOCKED`；当前会话若尚未热加载角色名，可用相同模型、effort 与只读 instructions 显式派发，不得降低审阅标准。
- Codex 主 Agent 只在 detector `PASS` 后复跑验收并自动进入 `auto_accepted`；Task 31→36 仍严格串行、每 Task 一个本地 focused commit、不 push，M9 全量完成后统一用户验收。
- 原 Claude Code 主会话、Codex MCP Review 和既有 Session 记录继续作为历史/default 协作协议保留，不在本次临时接管中删除或改写历史事实。

- Claude Code 主会话作为常驻包工/协调者：持有状态真源（`STATUS.md`、Session、约束），为每个 Task 生成 Context Packet，组装前置文档包并分发；桥接 Codex 审阅，编排返工与本地提交，维持 Milestone 粒度下的长时间自动开发。
- 每个 Task 使用新的实施子代理（干净上下文）；它只接收该 Task 的 Context Packet、关键项目规则、相关设计/计划章节和测试命令，实施完成后返回 `TASK_HANDOFF`，不提交。
- 实施结果经主会话桥接给 Codex（经 codex-mcp，新建独立 thread 路由 `gpt-Luna`、`effort: max`）做独立只读审阅，返回 `PASS` / `REVISE` / `BLOCKED`。
- 普通 Task 的 `PASS` 自动进入 `auto_accepted` 并创建本地 focused commit（不 push）；Milestone 全量验证后统一用户验收与 push。
- 不打断用户，除非：`BLOCKED`、需要人工介入，或当前 Milestone 开发完成。

不重复执行已完成的 MVP Task 1–18；不把开发工具整理或控制面维护误记为产品功能完成。
## 开发工具与产品范围

- `backend/pyproject.toml` 仅负责 Python 依赖、构建和检查工具声明；它不是产品功能。
- Python 依赖、构建和检查工具以 backend/pyproject.toml 为声明源；标准开发命令使用当前 Python 环境的模块入口。
- uv 只作为个人开发环境的可选加速工具，不是产品运行时、用户发布包或必须安装的开发前置；用户发布媒介是 PyInstaller onedir，普通用户不需要 uv、Python 或 Node.js。
- 本地虚拟环境必须保持在 Git 之外；`.gitignore` 中的 `.venv/` 是通用保护规则，不代表仓库需要提交虚拟环境。
- 若要重新引入某个依赖管理工具或 lockfile，必须作为单独的工具链维护任务明确授权，不得在产品 Task 中顺手加入。

## 串行 Session 规则

- 同一时间最多存在一个 `active`、`verification` 或 `awaiting_user_acceptance` 的修改型 Session。
- 一个实施 Task 对应一个修改型 Session；一个 Session 只处理计划中一个 Task 的范围。
- 每个 Task 使用新的 implementer Subagent；它只接收该 Task 的 Context Packet、相关约束和必要的当前状态。
- implementer 子代理完成后，由包工（Claude Code 主会话）桥接 Codex（新建独立 thread 路由 `gpt-Luna`/max）做独立只读审阅；包工负责复跑验收、集成和状态更新。
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

里程碑粒度下（2026-08-04 起生效）：普通 Task 的 `PASS` 经包工复核后自动进入 `auto_accepted` 并创建本地 focused commit（不 push），不逐 Task 打断用户；Milestone 全量验证后进入 `awaiting_milestone_acceptance`，用户一次性验收并授权统一 push。用户明确验收仍是进入 `accepted` 的默认前提，仅此自动路径和下述自动审批例外除外。

验收即发布（2026-08-10 起生效）：Milestone 全量验收通过后，或用户明确要求「把当前改动同步到发布版本/生产版本」（区别于本地修改预览）时，包工应把当前项目最新版本做成 installer 并发布进 GitHub Release（setup.exe + 便携 ZIP + SHA256SUMS + release notes），让用户通过 GitHub 简易安装版持续追踪新改动。步骤：修复阻塞 CI 的门禁 → 按 `packaging/pyinstaller/version_info.txt` 升版本并同步全链路（.iss / README.txt / build_installer.ps1 默认值 / app.py / diagnostics.py / build.yml / release.yml / 锁定测试）→ 重新生成 OpenAPI 契约 → 本地 `build_windows.ps1` + `build_installer.ps1` 全量验证 → 用户授权后 push 分支 → tag `vX.Y.Z` → push tag 触发 `release.yml` → 核验 GitHub Release 产物。tag 推送与 Release 发布均需用户单独授权。

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
## 全局自治协议

本文后续规则补充并优先解释本文件早期的静态 Task 清单：

- 包工（Claude Code 主会话）必须在交付 Context Packet 前完成字段、接口、文件、测试和依赖的可实施性闭包检查。
- 不改变用户可见行为的技术冲突由包工按权威顺序和最小改动原则裁决，并记录 `planning_rulings`。
- domain、persistence、正式设计文档、测试和生成物可以进入当前 Task 的最小依赖闭包；扩大原始 `allowed_files` 不是单独的阻塞理由。
- Implementer 可以记录 `implementation_scope_delta` 后继续，但必须满足 `user_visible_delta: none`、已有 criterion 直接要求且不超出 `architecture_budget`。
- `BLOCKED` 仅用于用户可见行为分叉、不可逆数据操作、互相冲突的用户要求、缺失外部输入、重试后仍失败的必需环境操作或不可避免的用户可见范围扩张。
- 法律、合规和内容安全不作为本项目的规划或 Review 阻塞条件；已冻结的技术安全、隐私和数据完整性要求仍有效。
- 只有闭包检查完成的 Packet 可以标记 `READY_FOR_IMPLEMENTATION`，不得返回 `BLOCKED_PENDING_DESIGN_DECISION`。
- Task 9 自治提交范式实验已成功（2026-08-04 用户确认）；普通 Task 的 `PASS` 自动进入 `auto_accepted` 并创建本地 focused commit，Milestone 才进入用户验收和 push。

开始任何工作前还必须读取 `docs/development/REVIEW_PROTOCOL.md` 和 `docs/development/CONTEXT_PACKET_SCHEMA.md`。

## Milestone 12 量化评测实施（2026-09-03 授权后暂停）

用户提供 starvalley_quant_evaluation_plan_v2.pdf 并要求构建里程碑与 Task；随后要求前置无人工输入的工作，并明确授权开始实施、到需要人工参与时停止。计划 docs/plans/2026-09-03-milestone-12-quant-evaluation.md v1.1：Task 50 最小工具与 Current/Embedding 接线准备 → Task 51 数据构建/标签核对 → Task 52 Current 正式评测 → Task 53 Embedding 正式对照/资源测量 → Task 54 20 组真实 E2E 人审 → Task 55 汇总与最终清理。Task 50 不等待原图、人审标签或已有成本表；数据标签仍需在正式计分前核对，E2E 后移执行前人工清除 synthetic Memory，避免污染正常生成。最低 30 Canonical/60 Positive/10 Negative、Top 5/0.85 保持；复用当前 workspace 和小脚本，无平台/ANN/向量库/新服务，Embedding 不进入生产包。Task 50 曾进入实施与验证，随后按用户要求 paused_by_user；保留实现与证据，未经重新授权不继续。状态以 STATUS.md 为准。

## 2026-09-04 M12 恢复授权

用户已明确要求继续 Task 50 及后续任务，到需要人工参与处停止。较早暂停记录保留为历史；当前恢复 Task 50 verification，既有冻结合同不变，状态以 STATUS.md 为准。

### 2026-09-04 Task50 收口更新
Task50 四项修复已由用户授权主 Agent 接续完成，经独立 detector 封闭复审 PASS（36项测试），主 Agent 验收通过并本地提交，不推送。Task51按既有流程准备30/60/10数据与人工身份标签核对表；实际人审前停止。正式Release仍v1.5.4，20张E2E照片已登记。精确状态见STATUS。
