# Session｜Task 62 原料映射问题定位

| 字段 | 值 |
|---|---|
| session_id | `2026-09-23-task-62-ingredient-mapping-diagnosis` |
| status | `auto_accepted` |
| session_type | `implementation` |
| owner | Codex 主 Agent |
| started_at | `2026-09-23` |
| base_commit | `cf0e290` |
| acceptance_contract_id | `m14-task62-ingredient-diagnosis-v1` |
| revise_round | `0` |
| planning_status | `READY_FOR_IMPLEMENTATION` |

## Objective 与 user_visible_contract

定位当前 Ask Gus 现实语义原料到原版候选、最终 itemId 和兜底的实际代码/数据路径，区分上游语义输入、检索遗漏、排序选择和合法性校验问题；留下基于现有 1.6.15 目录的可复现样本，确定 M14 后续可改的最小原料链路。此 Task 不改变产品、Provider、目录、PostHog 或用户可见行为。

## 可实施性闭包与 planning_rulings

- 当前目录 `resources/catalogs/stardew-1.6.15/vanilla-ingredients.json`；`VanillaCatalog` 是只读版本化目录，`search_ingredients()` 是字段/别名检索；`_map_gameplay()` 调用 `_build_candidates()` Top 5 后用 `map_ingredient()` 校验并选择，`ensure_main_protein()` 可后置改动鱼类结果。
- `R62-01`：早期用户叙述“整份原料列表交给 LLM 选择”与现行代码不一致。按 M14 v1.3 §2 和源码，以真实的模型语义输出→目录 Top 5→确定性得分/选择→兜底为旧链路；不把旧叙述当当前实现事实。`user_visible_delta: none`。
- `R62-02`：Task 62 要“可复现样本”，Task 64 才冻结正式 Query/JEV 基线。此 Task 用离线目录和确定性单测重现机制，不报告准确率或将样本冒充真实用户/正式基线。`user_visible_delta: none`。
- `R62-03`：错误可能来自上游视觉分析、`design_ask_gus` 语义生成、字段检索/截断、评分/选择、目录合法性或后置鱼类守卫。只在观察到的边界内归类，不能把没有真实图片与模型输出的夹具归因为已发生的上游事故；Canonical HIT 和 Blueprint 不走此 Ask Gus 映射路径，需单列排除。`user_visible_delta: none`。

## Context Packet

```yaml
task_id: M14-Task-62
base_commit: cf0e290
planning_status: READY_FOR_IMPLEMENTATION
acceptance_contract_id: m14-task62-ingredient-diagnosis-v1
revise_round: 0
objective: 记录当前原料映射真实代码路径、错误分类、确定性可复现样本和后续最小改造接缝。
user_visible_contract: none；不修改产品行为、API、数据或远端系统。
planning_rulings: [R62-01, R62-02, R62-03]
contract_delta:
  documents: [新增 Task 62 诊断报告；更新 Session 与 STATUS]
  domain: []
  persistence: []
  application_api: []
architecture_budget:
  allowed: [只读代码/目录分析；新建诊断文档和专用可复现单测]
  forbidden: [修改产品源代码、目录、Prompt；调用真实 Provider/JEV/Embedding；RAG 设计或接线；PostHog 写入；发布]
allowed_files:
  - path: docs/development/M14_TASK62_INGREDIENT_DIAGNOSIS.md
    action: create
    reason: 保存路径、分类、样本证据和最小后续接缝。
    criterion_ids: [C62-01, C62-02, C62-03, C62-04]
  - path: backend/tests/catalog/test_task62_diagnosis.py
    action: create
    reason: 用现有 1.6.15 目录把检索遗漏、排序错误和合法性校验变成确定性复现。
    criterion_ids: [C62-03]
  - path: docs/development/sessions/2026-09-23-task-62-ingredient-mapping-diagnosis.md
    action: modify
    reason: 追加式记录合同、实施、复审和状态。
    criterion_ids: [C62-05]
  - path: docs/development/STATUS.md
    action: modify
    reason: 唯一活动 Session 和精确下一步。
    criterion_ids: [C62-05]
out_of_scope: [Task 63 方案选型, Task 64 正式 Query/JEV 基线, Task 65 产品实现, Task 66 对照, 发布, 远端写入]
test_commands:
  - python -m pytest backend/tests/catalog/test_task62_diagnosis.py -q -p no:cacheprovider --basetemp output/m14-task62/pytest-focused
  - python -m pytest backend/tests/catalog/test_mapping.py backend/tests/catalog/test_catalog.py -q -p no:cacheprovider --basetemp output/m14-task62/pytest-regression
  - git diff --check
```

## Acceptance Ledger

| ID | 来源 | MUST 验收项 |
|---|---|---|
| C62-01 | M14 v1.3 Task 62；源码/技术设计 | 从视觉分析和设计语义输出到 `_map_gameplay`、`_build_candidates`、`VanillaCatalog.search_ingredients`、`map_ingredient`、兜底、后置 guard 与 `validate_gameplay` 记录实际路径和关键字段/版本；明确 Canonical HIT/Blueprint 边界。 |
| C62-02 | M14 v1.3 Task 62 | 分类上游语义错误、检索遗漏、排序/选择错误、合法性校验与兜底，并给出每类能/不能从现有证据判定的条件；不把目录合法当语义正确。 |
| C62-03 | M14 v1.3 Task 62 | 用现有 1.6.15 目录和确定性专用单测复现至少：有合理原版对应但搜索遗漏/错误候选、正确候选已在 Top 5 却被评分改选为不合逻辑的合法 ID、非法候选被校验拒绝；明确样本不是正式准确率基线。 |
| C62-04 | M14 v1.3 Task 62/63 分工 | 指定后续 M14 最小可改接缝及不应改动的领域约束；不得在本 Task 选定模型/数据库/Top K 或改产品代码。 |
| C62-05 | AGENTS.md / REVIEW_PROTOCOL.md | worker 实施、独立 detector 只读审阅、主 Agent 核对证据与来源，准确记测试和工作树边界；PASS 后本地 focused commit，不自动推送。 |

## Worker ownership

实施 worker 仅拥有诊断报告与专用测试两文件；主 Agent 拥有本 Session、STATUS 和最终集成/提交。所有角色共享工作树，不得撤销他人的改动；已有 M12 本地文档修改与其他未跟踪文件不在 Task 62 范围。

## Worker handoff（2026-09-23）

- worker 仅创建 `docs/development/M14_TASK62_INGREDIENT_DIAGNOSIS.md` 与 `backend/tests/catalog/test_task62_diagnosis.py`；C62-01..05 自报完成，R62-01..03 已应用，`implementation_scope_delta: none`，未改产品、目录、Session、STATUS 或远端。
- 离线样本：`Carp` 的 `142` 检索首位却被食用值评分改选为 `209 Carp Surprise`；`cherry tomatoes` 只召回 `638 Cherry` 而非 `256 Tomato`；`樱桃番茄` 无候选走 Egg `176` fallback；人为注入 `NotReal` 被 `PTS_VALIDATION_INGREDIENT_ID_UNKNOWN` 拒绝。报告明确这些是机制样本而非真实用户案例或 Task 64 正式基线。
- focused pytest `4 passed`；既有 mapping/catalog 回归在普通沙箱因 pytest 临时目录 `WinError 5` 失败，在获准本地执行环境用独立 basetemp 重跑 `56 passed in 1.18s`。`git diff --check` exit 0，新文件无行尾空白。目录 `stardew-1.6.15-v1`、808 items/253 usable、SHA-256 `4D07E9B3EE45670543C1BDCFFA69F84CC2FB2829C4DB4CF2BEFD273B36374E2B`。
- worker 角色路由配置为 `gpt-6-luna/max`，运行时未向其暴露可独立自报的 model/effort。独立 detector 复审待进行；主 Agent 不默认重复 worker 已通过的完整测试。

## 独立复审与收口

- 新 `detector` 按冻结合同 `m14-task62-ingredient-diagnosis-v1`、round 0 只读复审 C62-01..05 与 R62-01..03，结论 `PASS`；`must_fix=[]`、`optional_hardening=[]`、`new_design=[]`、`scope_delta=none`。审阅独立核对代码路径、Canonical/Blueprint 排除、故障归因边界、四类离线样本和目录 SHA。
- detector 自行 focused pytest `4 passed`；mapping/catalog 回归普通沙箱遇 pytest 临时目录 `WinError 5`，获准本地环境重跑 `56 passed`；`git diff --check` exit 0。主 Agent 核对交接证据、源码关键边界和提交范围，无证据缺口，不重复全量测试。
- 路由配置：worker `gpt-6-luna/max`，detector `gpt-6-sol/medium`；二者运行时均未暴露自报模型/effort，主 Agent 运行时也未暴露可核实标识。结论依据固定路由配置和成功启动，不伪造自报信息。
- 用户仅授权启动 Task 62；本 Task `PASS` 后按项目协议 `auto_accepted` 并创建本地 focused commit，不推送、不发布、不启动 Task 63。已有 M12 文档修改与其他无关未跟踪文件保持原样。
