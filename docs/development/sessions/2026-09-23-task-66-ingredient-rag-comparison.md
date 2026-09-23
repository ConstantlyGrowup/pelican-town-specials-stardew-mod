# Session｜M14 Task 66 原料 RAG 同集对照

| 字段 | 值 |
|---|---|
| session_id | `2026-09-23-task-66-ingredient-rag-comparison` |
| status | `auto_accepted` |
| session_type | `implementation` |
| owner | Codex 主 Agent |
| started_at | `2026-09-23` |
| base_commit | `ce14827` |
| acceptance_contract_id | `m14-task66-ingredient-rag-comparison-v1` |
| revise_round | `0` |
| planning_status | `READY_FOR_IMPLEMENTATION` |

## Objective 与证据边界

以 Task64 冻结的 24 道菜、72 项现实语义原料 Query、Gold、原版目录、JEV typed Choice rubric 和旧结果为共同输入，运行 Task65 的显式本地 RAG 候选路径，记录逐项 Top5、最终映射和失败状态，对新链路全量进行 JEV 判定，再按固定菜品分母比较旧/新“全部原料合理率”。不更换 Query、标签、模型、K 或判定选项，不筛掉失败样本，不通过局部调参追逐结果。Task65 已知用户默认 backend 仍为 LEGACY；本 Task 仅产出同集质量结论和是否符合采用门槛的建议，不自动改变产品默认、发布或修改 main。

## planning_rulings

- `R66-01`：Task64 报告在当时以逐项非兜底合理率为主；用户后来明确将 Task66 的主指标改为固定集菜品全部合理率。Task64 14/24 历史菜品全合理结果作为旧基线，逐项合理率保留为辅助，历史原始输出不得回写；`user_visible_delta: none`。
- `R66-02`：Task65 的 RAG 必须显式 selector 才可执行，而产品默认保持 LEGACY。评测器从同一冻结语义输入按菜逐项调用实际 RAG 候选 seam + mapper，跟踪同菜已用 ID；不调用图片/生成 Provider、Canonical 或 Blueprint。不得误把失败后旧检索回退的结果当作 RAG 命中；`user_visible_delta: none`。
- `R66-03`：Task64 JEV 响应为 `typesafe/jev-1.13-20260917`，同一输入状态（菜/语义原料/最终目录项完全一致）的已完成 typed Choice 可作为已判定结果复用，以减少费用和随机判定噪声；其它非兜底项须用原协议、同 rubric、盲化旧/新标签调用 JEV，不接受人工替代。若实际返回模型版本不同，须在两个方案上使用同一新版本重评并把 Task64 历史结果单列，禁止跨版本拼接；`user_visible_delta: none`。
- `R66-04`：Task64 输出和 Task65 资源测量在 ignored `output/`，新 side 的 JSONL/manifest/原始 JEV 响应也写 ignored 路径；可提交报告仅放聚合、可复算 hash、非敏感案例与方法限制。Key 从 Windows 用户环境读取，不打印或落盘；`user_visible_delta: none`。
- `R66-05`：设计 §7 的采用 gate 要求菜品全部合理率严格高于旧基线、Gold Recall@5 不低于旧值、固定集 JEV 合理覆盖不下降，且 Task65 资源预算已通过。Task66 只给是否达标的证据结论；无论结果如何都不自动更改默认 backend。未达标时保留旧链路，不在同一冻结集上补规则再重测；`user_visible_delta: none`。

## Context Packet

```yaml
task_id: M14-Task-66
base_commit: ce14827
planning_status: READY_FOR_IMPLEMENTATION
acceptance_contract_id: m14-task66-ingredient-rag-comparison-v1
revise_round: 0
objective: 在冻结 Task64 Query 上对 Task65 显式 RAG 与旧链路做 JEV 同集菜品级质量对照，作有边界的采用判断。
user_visible_contract: none；不改变普通用户默认 LEGACY、API/UI/schema/目录/试用/Canonical/Blueprint/Mod 或用户数据。
planning_rulings: [R66-01, R66-02, R66-03, R66-04, R66-05]
contract_delta:
  documents: [本 Session, STATUS, Task66 同集对照报告]
  domain: []
  persistence: []
  application_api: []
architecture_budget:
  allowed: [复用现有 Task64 JEV typed Choice 评测器, 明确 RAG selector 的离线新侧结果采集, ignored JSONL/manifest, 同集指标复算和回归测试]
  forbidden: [修改冻结 Query/Gold 或 Task64 原始输出, 训练/微调/调整 TopK/别名/规则以改善本集成绩, 独立向量服务, 照片/生成 Provider 调用, PostHog 写入, 人工作为主评测者, 把 RAG 设为用户默认, push/tag/Release]
allowed_files:
  - path: scripts/evaluate_ingredients.py
    action: modify
    reason: 在现有 Task64 协议/状态/解析器上复用相同 JEV rubric 与结果校验；必要时只加可复用只读接口
    criterion_ids: [C66-03, C66-04]
  - path: scripts/compare_ingredient_rag.py
    action: create
    reason: 跑冻结新侧 RAG 候选/mapper、JEV 比较和指标/失败复算
    criterion_ids: [C66-01, C66-02, C66-03, C66-04, C66-05]
  - path: backend/tests/tools/test_m14_ingredient_comparison.py
    action: create
    reason: 冻结输入/hash、同菜映射、盲化复用/版本漂移、固定菜分母、指标和失败门禁测试
    criterion_ids: [C66-01, C66-02, C66-03, C66-04, C66-05]
  - path: docs/development/M14_TASK66_INGREDIENT_RAG_COMPARISON.md
    action: create
    reason: 可审计的真实同集结果、主/辅指标、逐菜变化、门槛/限制与建议
    criterion_ids: [C66-04, C66-05]
  - path: docs/development/sessions/2026-09-23-task-66-ingredient-rag-comparison.md
    action: modify
    reason: 主 Agent 冻结合同、记录 handoff/review/提交；worker 不拥有
    criterion_ids: [C66-06]
  - path: docs/development/STATUS.md
    action: modify
    reason: 主 Agent 维护唯一活动 Session 与事实状态；worker 不拥有
    criterion_ids: [C66-06]
acceptance_ledger:
  - criterion_id: C66-01
    source: M14 计划 Task66/§4；Task64 冻结报告
    requirement: 核对 Task64 24 菜/72 项 fixture SHA、目录 SHA/版本、旧 baseline/JEV 输出，保持旧原始文件只读且全量固定分母；记录 RAG index/model revision/hash。
  - criterion_id: C66-02
    source: M14 计划 Task66；Task63 设计 §2–3；Task65 实施
    requirement: 对所有冻结语义项按菜顺序显式调用真实 RAG Top5+现有 mapper，保留候选顺序/分数、最终 ID、fallback、检索降级/错误、查询耗时；旧/新并列，不能把降级算成 RAG 命中。
  - criterion_id: C66-03
    source: 用户 JEV 全量评测规则；Task64 固定协议；M14 计划 §4
    requirement: 所有新侧非兜底项都有 JEV typed Choice 原判或相同状态的 Task64 完成判定复用；新 API 请求不泄露 Gold/方案/候选分数，保存 Choice/confidence/probabilities/version/cost；版本漂移时不能做跨版本比较；失败/undecidable 显示且不得用人工填补。
  - criterion_id: C66-04
    source: 用户菜品全部合理主指标；M14 计划 v1.4 §4；Task64 结果
    requirement: 主指标按固定 24 菜计算“每项均非兜底且 JEV reasonable”，报告旧/新分子分母及逐菜改善/退步；辅助逐项合理率、固定全集覆盖、Gold Recall@5/候选命中/最终命中、fallback/失败/争议，保留全部 72 项 raw ignored 输出和可复算脚本。
  - criterion_id: C66-05
    source: M14 Task63 设计 §7 与计划 Task66
    requirement: 按严格菜品改善、Gold Recall@5 不下降、固定集合理覆盖不下降及 Task65 实测资源 gate 给出达标/未达标结论，拆分新旧检索延迟、冷加载/RAM/包体来源，不把局部或策划 Query 结果说成真实用户因果效果；默认仍 LEGACY。
  - criterion_id: C66-06
    source: AGENTS.md 与 REVIEW_PROTOCOL.md
    requirement: 新 luna_worker 实施、独立 detector 审阅、主 Agent 核对和本地 focused commit；push 另需授权。
out_of_scope: [质量不达标后在同集上调参, 开启生产 RAG 默认, 真照片/真实生成 Provider 端到端质量, PostHog 数据变更, main/tag/Release, 自动推送]
test_commands: [python -m pytest backend/tests/tools/test_m14_ingredient_comparison.py backend/tests/tools/test_m14_ingredient_evaluation.py backend/tests/ingredient_rag -q -p no:cacheprovider --basetemp output/m14-task66/pytest-focused, python -m ruff check scripts/evaluate_ingredients.py scripts/compare_ingredient_rag.py backend/tests/tools/test_m14_ingredient_comparison.py, git diff --check]
```

## Worker ownership

`luna_worker` 仅拥有评测脚本、新测试、Task66 结果报告和 ignored `output/m14-task66/`；主 Agent 拥有 STATUS/Session。worker 不是代码库唯一使用者，不得撤销或覆盖他人修改；相邻依赖闭包须依协议记录。不得修改冻结 Query/Gold、Task64 原始运行文件、RAG 产品默认、生产源码、PostHog、main/tag/Release；不提交或 push。允许 Task66 范围内的小额真实 JEV Decisions API 调用，先做版本/协议探针，Key 只从已配置的用户级环境变量读取，不得输出或写入。

## 验收记录

### Worker handoff（2026-09-23）

`luna_worker / gpt-6-luna / max` 已交付 `scripts/compare_ingredient_rag.py`、`backend/tests/tools/test_m14_ingredient_comparison.py`、`docs/development/M14_TASK66_INGREDIENT_RAG_COMPARISON.md` 与 ignored `output/m14-task66/`；`scripts/evaluate_ingredients.py` 未改。其交接声明 `R66-01..05` 均已执行、`implementation_scope_delta: none`，未提交或推送。实际返回 JEV 版本为 `typesafe/jev-1.13-20260917`；运行时 worker 模型号不可独立读取，以上为配置路由。

交接证据：冻结 24 菜/72 项与 Task64 五个原始文件前后 hash 一致；实际显式 RAG selector + mapper 完成 72/72，0 fallback、0 检索/映射失败；JEV 72/72 typed 判断由 64 条 Task64 同状态完成判定复用及 8 次本轮 API 成功调用构成，0 版本漂移/失败/undecidable；本轮新增用量费用 `$0.000187152`。固定主指标旧 `14/24` → 新 `18/24`，逐菜改善 4、退步 0、持平 20；冻结质量/资源门槛按报告为 met，产品默认仍为 LEGACY。Task65 资源值为既有 host-Python 测量，不是 Task66 重测或 EXE RAG 验证。worker 报告 focused pytest 39 passed、Ruff PASS、`git diff --check` 退出码 0；原始 RAG/JEV 文件各 72 行，64 条复用 provenance，详见 Task66 报告与 ignored manifest。

### Independent detector 与主 Agent 收口（2026-09-23）

独立 `detector / gpt-6-sol / medium` 按冻结合同 round 0 返回 `PASS`，核对 `C66-01..06` 与 `R66-01..05`，`must_fix: []`、`scope_delta: none`、`implementation_scope_delta: none`。其只读检查确认 Task64 五个源文件 hash 与 Task66 manifest 一致、新侧 RAG/JEV 原始记录各 72 条、JEV 来源为 64 复用/8 新调用、菜品主指标 `14/24 → 18/24`、配对改善 4/退步 0、门槛 met、默认 LEGACY；Ruff PASS、`git diff --check` 退出码 0。审阅沙箱读取 Task65 模型清单遇 `PermissionError`，因此其独立 `calculate_metrics()` 复算未执行；worker 的 focused pytest 为 39 passed，此边界作为 optional hardening 记录，不扩大冻结合同。

主 Agent 已核对 worker handoff、独立 PASS、Task66 报告和产品默认边界，依项目自动验收路径进入 `auto_accepted`。本 Session 只包含 Task66 新侧评测工具、测试、结果报告、ignored 原始证据与必要控制面；不包含产品默认切换、push/main/tag/Release。仅创建本地 focused commit；推送和后续产品切换需要用户单独决定。
