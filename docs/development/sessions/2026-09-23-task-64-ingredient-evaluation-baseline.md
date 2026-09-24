# Session｜M14 Task 64 原料评测与旧链路基线

| 字段 | 值 |
|---|---|
| session_id | `2026-09-23-task-64-ingredient-evaluation-baseline` |
| status | `auto_accepted` |
| session_type | `implementation` |
| owner | Codex 主 Agent |
| started_at | `2026-09-23` |
| base_commit | `1a7cd94` |
| acceptance_contract_id | `m14-task64-ingredient-baseline-jev-v1` |
| revise_round | `0` |
| planning_status | `READY_FOR_IMPLEMENTATION` |

## Objective 与证据边界

按 M14 v1.3 Task 64 冻结不少于 20 道菜、60 个可映射现实原料 Query 及可接受的 Stardew 1.6.15 原版 ID，建立只用于评测的 JEV typed choice 判定器，在同一集合上记录当前 `_build_candidates()` → `map_ingredient()` 的逐条旧链路结果。Query 是策划的语义输入，不是用户照片、真实 Provider 输出或真实用户事故；不把此基线误称全生成链路质量。JEV 是主要判定者，人工只核查校准/争议；不能把 Gold 标签或人工判断冒充 JEV 输出。

## planning_rulings

- `R64-01`：既有产品链路先生成现实语义原料、再做目录映射；没有可复现的用户原图/上游 Provider 样本。Task 64 固定从语义原料边界输入，测 `_build_candidates()`/mapper，不调用图片或产品 Provider；`user_visible_delta: none`。
- `R64-02`：初始环境未发现 `OPENROUTER_API_KEY`，用户正设置。离线实现和基线不依赖凭证；JEV 小样本协议探针及全量真实判定须等凭证可用。不可用时报告未完成/待凭证，不生成伪 JEV 指标；`user_visible_delta: none`。
- `R64-03`：JEV 是 typed decision，不是普通聊天模型。依据 TypeSafe System One 与 OpenRouter 官方 Jev examples，使用 Choice 的固定 `合理/不合理/无法判定` 选项、confidence/probabilities；先做真实协议探针，不接受自由文本替代或错误端点静默降级；`user_visible_delta: none`。
- `R64-04`：原始运行 JSONL/CSV 和可能含具体 Query 的请求响应放在 Git ignored `output/m14-task64/`；可提交的 Query/Gold 源文件为后续 Task 66 复跑真源，冻结 SHA 与目录 SHA。报告只存可复算聚合和非敏感摘要；`user_visible_delta: none`。
- `R64-05`：主指标仅统计 JEV 可评且旧链路非 fallback 的条目，同时报告固定全集覆盖与排除/失败数；不能因旧侧 fallback 提高表观准确率。Gold Recall@5 与菜品全对分别计算，不以 Gold 替代 JEV 主判定；`user_visible_delta: none`。

## Context Packet

```yaml
task_id: M14-Task-64
base_commit: 1a7cd94
planning_status: READY_FOR_IMPLEMENTATION
acceptance_contract_id: m14-task64-ingredient-baseline-jev-v1
revise_round: 0
objective: 冻结原料 Query/Gold 集，构建 JEV 评测器并取得旧链路逐条基线。
user_visible_contract: none；不改变产品链路、安装包、PostHog 或用户数据。
planning_rulings: [R64-01, R64-02, R64-03, R64-04, R64-05]
contract_delta:
  documents: [本 Session, STATUS, Task64 可提交结果摘要]
  domain: []
  persistence: []
  application_api: []
architecture_budget:
  allowed: [评测专用 Query/Gold fixture, 离线基线与 JEV Decisions API 脚本, 定向测试, ignored 运行产物]
  forbidden: [生产原料映射修改, RAG/Embedding 实现, 新服务或数据库, 图片/Provider 调用, PostHog 写入, 发布, 将未实测结果当实测]
allowed_files:
  - path: tests/fixtures/m14_ingredient_queries.json
    action: create
    reason: 冻结可映射语义 Query、菜品分组与 Gold ID；worker 所有。
    criterion_ids: [C64-01, C64-02]
  - path: scripts/evaluate_ingredients.py
    action: create
    reason: 离线旧链路、JEV typed decision 与指标复算；worker 所有。
    criterion_ids: [C64-02, C64-03, C64-04, C64-05]
  - path: backend/tests/tools/test_m14_ingredient_evaluation.py
    action: create
    reason: fixture/目录、mapper、JEV 协议/失败分支、指标合同测试；worker 所有。
    criterion_ids: [C64-01, C64-02, C64-03, C64-04]
  - path: docs/development/M14_TASK64_INGREDIENT_BASELINE.md
    action: create
    reason: 可审计的集合 hash、运行方法、基线/JEV 汇总和限制；worker 所有。
    criterion_ids: [C64-01, C64-04, C64-05]
  - path: docs/development/sessions/2026-09-23-task-64-ingredient-evaluation-baseline.md
    action: modify
    reason: 合同/交接/验证记录；主 Agent 所有。
    criterion_ids: [C64-06]
  - path: docs/development/STATUS.md
    action: modify
    reason: 唯一活动状态；主 Agent 所有。
    criterion_ids: [C64-06]
acceptance_ledger:
  - criterion_id: C64-01
    source: M14 计划 §3 Task64 与 §4.1
    requirement: ≥20 道菜、≥60 个可映射条目；中英/别名/类属/易混淆均覆盖；Gold 可多 ID，每个 ID 属于固定可用目录，排除牛羊鸡等无合理原版对应物；先冻结 Query/标签/hash 后运行基线。
  - criterion_id: C64-02
    source: M14 计划 §2、§4.1；Task62 诊断
    requirement: 对全部冻结条目调用真实旧检索和 mapper，保留 Top5 顺序/分数、最终 ID、fallback 和失败状态，验证目录版本/hash；不使用 Task62 机制样本冒充统计基线。
  - criterion_id: C64-03
    source: 用户 JEV 输出边界；M14 计划 §4.3
    requirement: 用固定 Jev 1.13 typed choice 结构，仅判合理/不合理/无法判定及置信度；先真实小样本协议探针再全量评测。任何 API 不支持/响应异常显式失败，不降级为聊天文本或人工主判。
  - criterion_id: C64-04
    source: M14 计划 §4.2–4.4
    requirement: 复算非兜底合理率、菜品全对、Gold Recall@5、错误/无法判定/调用失败和固定全集合理覆盖；逐条原始结果在 ignored 输出，报告标明来源、模型版本、时间和真实/未完成边界。
  - criterion_id: C64-05
    source: M14 计划 §4.3；用户补充
    requirement: 人工仅抽查小样本校准及争议复核，不作为主要评测者；保存抽查差异与 JEV 原输出，不要求 JEV 解释理由。
  - criterion_id: C64-06
    source: AGENTS.md 与 REVIEW_PROTOCOL.md
    requirement: 新 worker 实施、独立 detector 审阅、主 Agent 核对及本地 focused commit；push 另需授权。
out_of_scope: [Task65/66, 产品 RAG 接线, 完整照片到生成的评测, PostHog 数据改动, main/tag/Release, 自动推送]
test_commands: [python -m pytest backend/tests/tools/test_m14_ingredient_evaluation.py -q -p no:cacheprovider --basetemp output/m14-task64/pytest-focused, python -m ruff check scripts/evaluate_ingredients.py backend/tests/tools/test_m14_ingredient_evaluation.py, git diff --check]
```

## Acceptance Ledger

| ID | MUST 验收项 |
|---|---|
| C64-01 | Query/Gold ≥20 菜、≥60 项，覆盖中英、别名、类属与易混，目录合法且冻结可复算。 |
| C64-02 | 旧链路对全量冻结项逐条运行，候选、最终 ID、fallback/失败透明。 |
| C64-03 | JEV typed choice 小探针后全量判定，不借普通聊天/人工伪装。 |
| C64-04 | 主/辅助指标与失败排除口径可复算，原始输出 ignored。 |
| C64-05 | 人工仅校准/复核小样本；JEV 为主判。 |
| C64-06 | worker → detector → 主 Agent 本地提交，不推送。 |

## Worker ownership

worker 仅拥有 Query fixture、评测脚本、定向测试与 Task64 可提交报告；主 Agent 拥有 STATUS 与本 Session。所有角色共享工作树，不得撤销他人的改动。凭证不能写入文件、输出或交接文本。

## Worker handoff

- `implementation_scope_delta: none`，仅新增冻结 Query fixture、评测脚本、定向测试和结果摘要；不改产品原料链路、目录、发布包或 PostHog。路由配置 `luna_worker` / `gpt-6-luna/max`，运行时未暴露模型自报；无 commit/push。
- 冻结输入为 24 道菜、72 原料项、50 个不同规范化 Query，fixture SHA `7B49E7B88393CCC627DD4AEC7545AC45FDAF4786081D2E9BCC973B202796EEB7`，目录 SHA `4D07E9B3EE45670543C1BDCFFA69F84CC2FB2829C4DB4CF2BEFD273B36374E2B`；全部 Gold ID 均属目录可用原料。
- 旧链路 `_build_candidates()` → `map_ingredient()` 对 72 项全部运行：71 非兜底、1 兜底、0 映射错误。逐条候选顺序/分数、最终 ID、fallback/耗时保存在 ignored `output/m14-task64/`。
- JEV Decisions API 3 项 typed Choice 协议探针成功，复用后对其余 68 项全量调用。响应模型 `typesafe/jev-1.13-20260917`、provider `TypeSafe`；合理 61、不合理 10、无法判定 0、独立 Query 调用失败 0。主率 61/71（85.92%）、固定集合理覆盖 61/72（84.72%）、菜品全对 14/24；Gold Recall@5 均值 97.22%、候选至少一项 Gold 命中 70/72、最终 Gold 命中 60/72。71 次成功响应费用合计 `$0.001666014`、input 39,667/output 3,225 tokens；单次 p50 299.293ms / p95 462.011ms。普通沙箱首次连接失败 WinError 10061，在忽略输出保留尝试记录，最小网络提升权限后全量成功。
- 人工审了 3 个探针样本和全部 7 条 JEV/Gold 二元差异，均未改写 JEV/Gold。JEV 对 Carp Surprise 和 Fried Mushroom 等成品判 reasonable，且把 Wheat Flour 精确匹配判 unreasonable；另有 Oil of Garlic 被判 reasonable 而 Gold 只含 Oil，存在标签覆盖争议。详情与交叉表见结果文档；不以此推断真实用户误差率。
- 定向 pytest 在获准临时目录权限后 `10 passed in 1.26s`，Ruff 与 `git diff --check` PASS。普通沙箱 pytest 被本机 WinError 5 临时目录权限挡住；原始 JSONL、真实请求/响应与复算 JSON 均在 ignored 输出，凭证未打印或写入。独立 detector 尚待复审。

## 独立复审与主 Agent 收口

- 新只读 `detector` 按合同 `m14-task64-ingredient-baseline-jev-v1`、round 0 检查 `C64-01..06` 与 `R64-01..05`，结论 `PASS`；`must_fix=[]`、`optional_hardening=[]`、`new_design=[]`、`scope_delta=none`。路由配置为 `gpt-6-sol/medium`，实施者为 `gpt-6-luna/max`；主 Agent 型号未向 detector 暴露。
- detector 独立比对冻结 fixture/目录 SHA，72 条 baseline（1 兜底、0 失败）和 71 条 TypeSafe typed Choice 响应（3 probe + 68 full）；复核 61/71 主率、61/72 全集覆盖、14/24 菜品全对、Gold Top5 命中 70/72、7 条 JEV/Gold 差异。JEV 请求不含 Gold/旧新方案标签，原始响应在 ignored 输出。Ruff/diff check PASS；不重复付费调用，pytest 采用 worker 的 `10 passed` 交接证据。
- 主 Agent 核对四个新增可提交文件的边界，原始运行输出被 `.gitignore` 的 `output/` 排除；不修改生产原料链路。Task 64 `auto_accepted`，仅创建本地 focused commit；不推送、不启动 Task 65 或发布。

### 提交前冻结 SHA 的换行闭包

主 Agent 在暂存后发现 `core.autocrlf=true`，新增 fixture 为 LF-only，但原 `.gitattributes` 仅有 `* text=auto`；fresh Windows checkout 可能把 fixture 变为 CRLF，使 C64-01 冻结原始字节 SHA 校验误报失败。此为同一 C64-01 的实现依赖，不改变输入内容、Gold、JEV 结果或验收标准。worker 仅给 `.gitattributes` 加入 `tests/fixtures/m14_ingredient_queries.json text eol=lf`，并在既有定向测试中验证工作树、暂存 blob 与 Git checkout-filter 输出的 SHA 均为 `7B49E7B88393CCC627DD4AEC7545AC45FDAF4786081D2E9BCC973B202796EEB7`，`git check-attr` 返回 `text: set` / `eol: lf`。未改目录规则/内容，也未再次调用 JEV。

`implementation_scope_delta: {user_visible_delta: none, required_by_criterion: C64-01, architecture_budget_exceeded: false, added_files: [{path: .gitattributes, reason: fixture 原始字节 SHA 的跨 checkout 稳定性}]}`。worker 补充定向 pytest `11 passed`（既有本机临时目录权限需最小提升）、Ruff 与 staged/unstaged diff check PASS。独立只读补充复审尚待完成。

补充只读 `detector` 在同一合同 / round 0 核查 C64-01..06 后 `PASS`，`must_fix=[]`、`scope_delta=none`，接受上述最小依赖闭包。其定向测试 `1 passed`、两类 diff check PASS；工作树与 Git checkout-filter 产出保持相同 SHA，cleaned/staged blob ID 一致。没有再次调用 JEV。Task 64 恢复 `auto_accepted`，仅创建本地 focused commit；不推送或启动 Task 65。
