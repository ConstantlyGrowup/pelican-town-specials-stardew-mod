# Session｜Task 63 本地原料 RAG 方案

| 字段 | 值 |
|---|---|
| session_id | `2026-09-23-task-63-local-ingredient-rag-design` |
| status | `auto_accepted` |
| session_type | `implementation` |
| owner | Codex 主 Agent |
| started_at | `2026-09-23` |
| base_commit | `46f3b72` |
| acceptance_contract_id | `m14-task63-local-ingredient-rag-design-v1` |
| revise_round | `0` |
| planning_status | `READY_FOR_IMPLEMENTATION` |

## Objective 与 user_visible_contract

以 Task 62 已核实的原料候选接缝为基础，冻结可在 Windows 本地离线应用中实现的原料 RAG 方案：检索单元、Embedding 模型、Top K、存储、离线索引、版本/迁移、回退、资源预算和后续验证门槛。此 Task 只交付设计，不改产品行为、依赖、安装包、PostHog 或 JEV。

## 可实施性闭包与 planning_rulings

- `R63-01`：现有目录为 1.6.15，253 个可用对象。一个物品对应一个检索单元；不按 token 长度切碎短条目。把准备好的候选交回现有 ID 合法性校验和领域约束，不把语义相似度等同于游戏合法性。
- `R63-02`：Task 62 说明实际旧链路是模型给出现实原料→目录 Top 5 字段搜索→确定性食用值评分/选择，不是整表交给 LLM。方案必须针对候选遗漏与合法但不合理的排序，不把上游视觉/语义错误算成检索可修复。
- `R63-03`：本 Task 可选定有条件采用的模型与存储方案，但不得把模型卡宣称、M12 Canonical 数据或理论量化大小当成 M14 实测。若包体/RAM/冷启动或冻结 Query 质量未过门槛，Task 65 不得无条件上线，必须保留可观察的旧检索回退。
- `R63-04`：用户要求本地轻量化，无独立数据库服务。对 253 项先比较预计算向量+进程内精确扫描与 SQLite/向量数据库；附磁盘数学估算与运行时待测清单。

## Context Packet

```yaml
task_id: M14-Task-63
base_commit: 46f3b72
planning_status: READY_FOR_IMPLEMENTATION
acceptance_contract_id: m14-task63-local-ingredient-rag-design-v1
revise_round: 0
objective: 交付本地原料 RAG 可实施技术设计、明确选择与验证门槛。
user_visible_contract: none；设计阶段不改变用户可见行为。
planning_rulings: [R63-01, R63-02, R63-03, R63-04]
acceptance_ledger:
  - criterion_id: C63-01
    source: M14 v1.3 Task 63; Task 62
    requirement: 明确旧/新链路边界、合法性与失败回退。
  - criterion_id: C63-02
    source: M14 v1.3 Task 63
    requirement: 双语模型与 M12 参照的许可、离线成本和证据层级比较。
  - criterion_id: C63-03
    source: M14 v1.3 Task 63
    requirement: 固定检索单元、Top K 与合并/重排策略。
  - criterion_id: C63-04
    source: M14 v1.3 Task 63
    requirement: 固定存储、离线索引及版本/损坏处理。
  - criterion_id: C63-05
    source: M14 v1.3 Task 63/66
    requirement: 区分估算和实测，列资源与质量验证门槛。
  - criterion_id: C63-06
    source: AGENTS.md; REVIEW_PROTOCOL.md
    requirement: 新 worker、独立 detector、主 Agent 复核与本地 focused commit。
contract_delta:
  documents: [新增正式本地技术设计与可提交摘要；同步设计源索引；更新 Session 与 STATUS]
  domain: []
  persistence: []
  application_api: []
architecture_budget:
  allowed: [只读源码/目录/打包配置分析；官方模型/运行时文档核查；撰写设计]
  forbidden: [产品或依赖修改；模型下载/推理/量化；JEV 或真实 Provider 调用；PostHog 写入；发布]
allowed_files:
  - path: docs/architecture/M14_INGREDIENT_RAG_TECHNICAL_DESIGN.md
    action: create
    reason: 正式记录模型、切分、检索、存储、版本、回退和验收门槛。
    criterion_ids: [C63-01, C63-02, C63-03, C63-04, C63-05]
  - path: docs/development/M14_TASK63_DESIGN_DECISIONS.md
    action: create
    reason: 将最小可审计选型摘要与待测门槛保留在可提交控制面。
    criterion_ids: [C63-02, C63-03, C63-04, C63-05]
  - path: docs/development/sessions/2026-09-23-task-63-local-ingredient-rag-design.md
    action: modify
    reason: 追加式记录合同与验收证据；主 Agent 所有。
    criterion_ids: [C63-06]
  - path: docs/development/STATUS.md
    action: modify
    reason: 唯一活动 Session；主 Agent 所有。
    criterion_ids: [C63-06]
  - path: StarValleyCook_项目设计源索引与状态快照.md
    action: modify
    reason: 该索引 §1.1–1.2 要求新增正式设计源在同一次工作中同步登记；主 Agent 所有，Git ignored。
    criterion_ids: [C63-06]
out_of_scope: [Task 64 Query/JEV/旧链路正式基线, Task 65 产品实现, Task 66 同集对照, 模型下载, 远端写入, 发布]
test_commands:
  - git diff --check
  - 检查设计约束/链接/文件范围与 253 项向量预算计算
```

## Acceptance Ledger

| ID | 来源 | MUST 验收项 |
|---|---|---|
| C63-01 | M14 v1.3 §2/Task 63；Task 62 | 画清旧/新边界：上游语义→候选召回/排序→现有合法 ID、去重、鱼类守卫/兜底；Canonical/Blueprint 不变。写出可实现的新链路和失败回退。 |
| C63-02 | M14 v1.3 Task 63 | 选定本地双语 Embedding 模型/revision 固定策略和一个 M12 CPU 模型参照；比较许可证、离线依赖、原始/量化包体、RAM/冷启动、检索质量证据层级，不能把 M12 Canonical 结果当原料结果。 |
| C63-03 | M14 v1.3 Task 63 | 固定“每个目录物品一个检索单元”的字段、类别/别名校验、查询规范化、词面优先与语义 Top K、合并/重排/选择规则；给出 K 的理由和 Task 64/66 可测的 Recall@K。 |
| C63-04 | M14 v1.3 Task 63 | 比较本地文件/SQLite 精确扫描与向量 DB/ANN，明确选定存储、离线构建、校验哈希、版本/损坏迁移协议；不要求用户安装服务。 |
| C63-05 | M14 v1.3 Task 63/66 | 磁盘向量估算、模型/运行时资源预算、冷启动/检索/RAM/installer 增量的测量门槛、质量未过线的回退方案；明确估算/已有测量/未来验证。 |
| C63-06 | AGENTS.md / REVIEW_PROTOCOL.md | 新 worker 实施、独立 detector 只读复审；主 Agent 核对证据和工作树，仅 PASS 后本地 focused commit，不推送。 |

## Worker ownership

实施 worker 仅拥有正式技术设计和可提交选型摘要两个新文件；主 Agent 拥有本 Session、STATUS、设计源索引与最终集成/提交。设计源索引作为源文件新增时的最小文档依赖闭包加入，不改变验收要求或用户可见行为。所有角色共享工作树，不得撤销他人的改动；已有 M12 本地修改与其他未跟踪文件不在 Task 63 范围。

## Worker handoff（2026-09-23）

- worker 按冻结范围创建正式设计与可提交选型摘要；C63-01..05 自报满足，`implementation_scope_delta: none`。模型为条件选型而非已测产品结果；没有产品代码、依赖、数据或远端变更。
- 设计选择通用 CPU ONNX 动态 INT8 的 `multilingual-e5-small` 作为候选；一个可用目录物品一条检索单元，词面优先和语义 Top 5 融合，flat 向量文件 + manifest + 进程内精确扫描。253×384×4 = 388,608 bytes / 379.5 KiB；模型/运行时和质量仍待 Task 65/66 测量。
- worker `git diff --check` exit 0，新文件无尾随空白；未执行产品测试，符合仅文档 Task；未下载/运行模型，未调用 JEV、Provider 或 PostHog。独立 detector 待复审。
- worker 发现根设计源索引 §1.1–1.2 的新增设计同步规则；主 Agent 已按全局最小依赖闭包将 ignored 索引纳入 Session allowed_files，并负责同步，`user_visible_delta: none`。既有 M12 修改未碰触。

## 独立复审与收口

- `detector` 按 `m14-task63-local-ingredient-rag-design-v1`、round 0 只读审阅 C63-01..06 和 R63-01..04，结论 `PASS`；`must_fix=[]`、`optional_hardening=[]`、`new_design=[]`、`scope_delta=none`。官方模型卡/文件目录与 ONNX 量化资料支持设计中的事实；量化包体、内存、冷加载和 M14 原料质量均标为待测。
- detector `git diff --check` exit 0；两个新文档的 `git diff --no-index --check` 无空白错误，向量体积 388,608 bytes / 379.5 KiB。主 Agent 核对报告与可提交摘要、ignored 正式设计和索引同步；没有执行产品测试、模型调用或下载。M12 用户改动保持不变。
- worker 路由配置 `gpt-6-luna/max`，detector 路由配置 `gpt-6-sol/medium`；运行时未提供自报模型/effort。按项目 Task 自动验收路径收口，本地 focused commit 仅纳入可提交摘要、Session、STATUS；ignored 技术设计与根索引保留本地真源，不推送或发布。
