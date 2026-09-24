# Session｜M14 Task 66.1 扩样独立原料同集对照

| 字段 | 值 |
|---|---|
| session_id | `2026-09-23-task-66-1-expanded-ingredient-holdout` |
| status | `committed` |
| session_type | `implementation` |
| owner | Codex 主 Agent |
| started_at | `2026-09-23` |
| base_commit | `ab3ee2d` |
| acceptance_contract_id | `m14-task66-1-expanded-ingredient-holdout-v1` |
| revise_round | `0` |
| planning_status | `READY_FOR_IMPLEMENTATION` |

## Objective 与边界

用户认为 Task66 的 24 菜/72 项可能过小，要求加大样本量再做一轮对比。新增**不与 Task64 菜品重复**的 96 道菜、每道 3 项现实语义原料（288 项），先构建、核对可接受游戏 ID 并冻结新 fixture 的字节 hash，再在不改旧 fixture、目录、RAG 规则、Top K、JEV rubric 的条件下，逐菜分别运行真实 LEGACY 与显式 RAG 候选+mapper，并对两侧非兜底结果使用同一版本 JEV typed Choice 盲判。以新集固定 96 道菜“全部原料合理”为主指标，另将原 24 菜作为历史复制验证而非新样本。报告差异、配对转移、分层、重复 Query、JEV/Gold 分歧、失败和抽样局限。新结果不自动修改产品默认或推送。

本 Task 的真实 JEV API 阶段以用户对本轮目标字段/目的地/最多 576 次计费请求的明确授权为前置；不能静默借用 Task66 的最多 72 次旧授权。用户已明确选择“主要增加菜品数量”，以新 96 道菜为主尺度，菜系/风格只作描述；并已单独授权本轮最多 576 次 OpenRouter JEV Decisions API 计费盲评，限定发送菜名、现实原料、最终游戏目录项和固定 rubric，不发送 Gold、方案标签、候选分数或 Key。该授权不取消先冻结样本的阶段门。

## planning_rulings

- `R66.1-01`：既有 14/24→18/24 是策划固定集上 4 道菜净改善、0 道退步，不是统计上稳健的真实用户效果；新集独立报告，累计 120 菜仅在目录、判定选项与**返回 JEV 版本**一致时附列，不能用累计结果掩盖新集方向；`user_visible_delta: none`。
- `R66.1-02`：为检验难度构成而非只堆同名易题，预设 4 个菜品级分层，每层 24 道：`direct_name`、`bilingual_or_synonym`、`ambiguous_name`、`raw_vs_prepared`。每菜 3 项，至少 80 个不同 normalized Query、至少 40 个旧集未出现的 normalized Query；中文与英文输入各至少 90 项。分层是有意策划，不称随机用户样本；`user_visible_delta: none`。
- `R66.1-03`：每项至少 1 个目录中 `usableAsIngredient` 的 Gold ID，允许多个合理 ID；只在映射执行前排除目录无合理对应物的原料。冻结后不按任何侧的失败/成绩删除或替换，兜底、错误、JEV 失败均留在固定菜品分母；`user_visible_delta: none`。
- `R66.1-04`：JEV 请求只含菜名中英、现实语义原料、最终目录项 ID/中英名与原 Choice rubric，不含 Gold、方案标签、Top5/分数。两侧完全相同 request state 可在同一返回版本下复用一次 typed 判定；先做单次版本探针，运行中版本漂移则暂停混合聚合并报告，不能用人工填补；`user_visible_delta: none`。
- `R66.1-05`：新集主结论为配对的菜品全部合理率差及改善/退步；同时给出精确 McNemar 双侧 p 值及按菜聚类的差值区间作有限样本描述，不把非随机策划集上的 p 值/区间解释成真实用户总体推断。分层与新旧 Query 重复程度单列；资源预算沿用 Task65 实测证据，不冒充新增打包测量；`user_visible_delta: none`。

## Context Packet

```yaml
task_id: M14-Task-66.1
base_commit: ab3ee2d
planning_status: READY_FOR_IMPLEMENTATION
acceptance_contract_id: m14-task66-1-expanded-ingredient-holdout-v1
revise_round: 0
objective: 预冻结 96 菜/288 项独立扩样，运行 LEGACY/RAG 同集映射和同版本 JEV，评估菜品全部合理率的稳健性。
user_visible_contract: none；产品默认 LEGACY、API/UI/schema/目录/原 Task64/66 输出不变。
planning_rulings: [R66.1-01, R66.1-02, R66.1-03, R66.1-04, R66.1-05]
contract_delta:
  documents: [本 Session, STATUS, 扩样报告]
  domain: []
  persistence: []
  application_api: []
architecture_budget:
  allowed: [新冻结 Query fixture, 独立离线运行器与测试, 复用既有 JEV typed Choice 协议, ignored raw/manifest, 同集统计]
  forbidden: [改 Task64/66 冻结输入或原始结果, 查看新侧结果后修改新 fixture/Gold/rubric, 调参 TopK/alias/模型/mapper, 生产默认切换, 新数据库/服务, PostHog/照片/生成 Provider, push/tag/Release]
allowed_files:
  - path: tests/fixtures/m14_ingredient_holdout_queries.json
    action: create
    reason: 96 菜/288 项新集，映射前冻结字节 hash 与 Gold
    criterion_ids: [C66.1-01, C66.1-02]
  - path: .gitattributes
    action: modify
    reason: Windows checkout 的新 fixture 保持 LF，防止冻结 SHA 漂移
    criterion_ids: [C66.1-02]
  - path: scripts/evaluate_ingredient_holdout.py
    action: create
    reason: 复用真实 LEGACY/RAG seam 和旧 typed JEV 协议，原始记录/指标可复算
    criterion_ids: [C66.1-02, C66.1-03, C66.1-04, C66.1-05]
  - path: backend/tests/tools/test_m14_ingredient_holdout.py
    action: create
    reason: 冻结、样本分布、双侧映射、盲化复用、模型漂移、固定分母和统计回归
    criterion_ids: [C66.1-01, C66.1-02, C66.1-03, C66.1-04, C66.1-05]
  - path: docs/development/M14_TASK66_1_EXPANDED_HOLDOUT.md
    action: create
    reason: 新集、旧集和可比累计结论、逐菜转移、边界和原始 hash
    criterion_ids: [C66.1-04, C66.1-05]
  - path: docs/development/sessions/2026-09-23-task-66-1-expanded-ingredient-holdout.md
    action: modify
    reason: 主 Agent 控制合同、预运行冻结和 review/提交记录；worker 不拥有
    criterion_ids: [C66.1-06]
  - path: docs/development/STATUS.md
    action: modify
    reason: 主 Agent 维护唯一活动 Session；worker 不拥有
    criterion_ids: [C66.1-06]
acceptance_ledger:
  - criterion_id: C66.1-01
    source: 用户本轮扩样请求；M14 计划 §4；R66.1-02/03
    requirement: 新集 96 道不同于旧集的菜、288 项、四层各 24 菜、至少 80 不同 normalized Query/40 旧集未见 Query、中英输入各至少 90；每项 Gold 合法且不预读链路结果挑样。
  - criterion_id: C66.1-02
    source: M14 计划 §4；Task64/66 冻结方法；R66.1-03
    requirement: 先记录新 fixture 工作树/Git blob SHA、目录与 Task65 资产 hash，并由主 Agent 在任何新侧映射前检查冻结；旧 Task64/66 输入/原始输出只读；全部 288 项按菜逐项真实执行 LEGACY 与 RAG，保留候选/最终 ID、used IDs、兜底/失败/降级和耗时。
  - criterion_id: C66.1-03
    source: 用户 JEV 全量主评测要求；Task64 typed Choice 协议；R66.1-04
    requirement: 获本轮明确授权后，对两侧全部新集非兜底项完成同返回版本 typed Choice 或精确同状态复用；盲化请求、raw provenance/usage/费用、失败与版本漂移可审计；调用不超过 576 次，不以人工替代。
  - criterion_id: C66.1-04
    source: 用户菜品全部合理主指标；M14 计划 §4；R66.1-01/05
    requirement: 新集固定 96 菜分母及 paired 改善/退步/持平、各层结果、逐项合理覆盖和 Gold Recall@5、fallback/错误/JEV 分歧，另报 McNemar 精确双侧 p 与按菜重抽样差值区间；原 24 菜只作为历史附列，版本一致才给累计 120 菜。
  - criterion_id: C66.1-05
    source: M14 Task63 设计 §7；用户扩样复测请求
    requirement: 不按扩样结果调参；真实结果无论升降完整报告，区分策划样本与用户流量、JEV 判断与 Gold、旧/新资源数据口径，产品默认仍 LEGACY。
  - criterion_id: C66.1-06
    source: AGENTS.md 与 REVIEW_PROTOCOL.md
    requirement: 新 luna_worker 实施、独立 detector 审阅、主 Agent 核对和仅本地 focused commit；push 单独授权。
out_of_scope: [上游照片/模型生成质量, 后置鱼类守卫, 真实用户统计, 修改 Task65 产品代码或默认, 发布/推送, 未授权的 API 调用]
test_commands: [python -m pytest backend/tests/tools/test_m14_ingredient_holdout.py backend/tests/tools/test_m14_ingredient_comparison.py -q -p no:cacheprovider --basetemp output/m14-task66-1/pytest-focused, python -m ruff check scripts/evaluate_ingredient_holdout.py backend/tests/tools/test_m14_ingredient_holdout.py, git diff --check]
```

## Worker ownership 与两阶段运行门

`luna_worker` 仅拥有新 fixture、精确 `.gitattributes` 行、新 runner/测试/报告及 ignored `output/m14-task66-1/`。主 Agent 拥有 STATUS/Session；worker 不是代码库唯一使用者，不能撤销或覆盖他人修改，不提交或推送。

阶段 A：只构建并验证 fixture 与测试，不运行 LEGACY/RAG、不得读取新结果；把新 fixture SHA、样本分布、Gold ID 检查和必要的人工合理性核对交给主 Agent。主 Agent记录冻结 SHA 与准许继续后，阶段 B 才跑两侧。API 阶段还须本轮明确用户授权；若缺少授权，停在离线结果，不重试或变相调用。冻结后任何 Gold/Query 修正都必须废弃该轮结果并重新说明，不能隐藏历史结果。

## 验收记录

### 阶段 A 预运行冻结（2026-09-23 14:47 UTC）

worker 在任何新侧映射/JEV 前构建并验证新 fixture；主 Agent 逐菜通读摘要，要求在预运行阶段把 `direct_name` 中原先 24 道鱼菜改为 12 道鱼、12 道蔬果/谷物/乳品等，修正 Goat Milk 与普通 Milk 的 Gold 不一致、茶叶与 Green Tea 成品概念混淆，以及个别菜名/Gold ID。修订后 worker 的纯 validator 与 focused pytest `5 passed`；主 Agent 复核修订后的 24 道 direct-name 菜、三处重点样本及旧 fixture/catalog hash。没有运行 LEGACY/RAG，也没有发送 JEV。

冻结 fixture 为 `tests/fixtures/m14_ingredient_holdout_queries.json`：工作树 SHA-256 `1E9B49077589E8A9B9699DD4FC140359DF1A9A6389D75C7911ACE4A14D92A25C`，Git blob SHA `7856d22f32a51de937cf6cf5f7cedf7a23aeff85`，`.gitattributes` 为此文件指定 LF。96 菜/288 项，四层各 24；142 个不同 normalized Query、112 个未见于 Task64；英文/中文输入 192/96；全部 288 项 Gold ID 均为冻结目录中可用原料。菜系/风格标签只用于描述，主尺度为 96 道独立菜品。

旧 Task64 fixture SHA-256 `7B49E7B88393CCC627DD4AEC7545AC45FDAF4786081D2E9BCC973B202796EEB7`，目录 SHA-256 `4D07E9B3EE45670543C1BDCFFA69F84CC2FB2829C4DB4CF2BEFD273B36374E2B`。主 Agent 经正常只读权限核验 Task65 最终资产：manifest `93E9AED32AA68DEC48D1C6E102C4F82FABDB916B84CD852E807F85BF3284DE85`、ONNX `739C8F25BBE6D8A6001CD2F048701DA9879140CC67D4E9327716111E869DD717`、SentencePiece `CFC8146ABE2A0488E9E2A0C56DE7952F7C11AB059ECA145A0A727AFCE0DB2865`、vectors `D640532CBD3316EED3A6831939A7289858D492E025D3223ECCFA7D93D8D4EC58`，与 Task66 记录一致。上述新 fixture SHA 是阶段 B 的只读输入；任何改动必须停止并重新说明，不可沿用本轮结论。

### 阶段 B worker handoff（2026-09-24）

此前“新集 output 尚不存在”是阶段 A 结束时的事实；阶段 B 后 `output/m14-task66-1/` 已产生 ignored 原始证据，未覆盖此前结果。`luna_worker / gpt-6-luna / max` 交付新 fixture、`.gitattributes` 精确 LF 行、`scripts/evaluate_ingredient_holdout.py`、`backend/tests/tools/test_m14_ingredient_holdout.py`、`docs/development/M14_TASK66_1_EXPANDED_HOLDOUT.md` 与 ignored 原始输出。声明执行 `R66.1-01..05`、`implementation_scope_delta: none`；未改产品代码、旧 Task64/66 原始证据、冻结 Query/Gold、rubric、TopK、STATUS/Session，也未提交或推送。

实际 LEGACY/RAG 均 288/288 映射：旧侧 45 catalog fallback、0 error，新侧 0 fallback/降级/error。JEV 返回 `typesafe/jev-1.13-20260917`，311 次成功新 API 调用（含 probe）、220 次精确同状态复用、45 个旧侧 fallback 不调用，0 失败/版本漂移；usage 汇总费用 `$0.007338282`，在用户授权的 576 次上限内。固定 96 菜主指标旧 `41/96` → RAG `59/96`，配对改善 18/退步 0/持平 78。worker 报告对冻结 96 菜统计了事后敏感性：18 道改善中 13 道旧侧含 fallback、5 道旧侧无 fallback；两侧均无 fallback 的 58 菜旧 `41/58`→新 `46/58`，不能替代主指标。报告按策划样本与真实用户效果、Gold 与 JEV 的边界描述，默认仍为 LEGACY。

worker 验证：focused pytest `19 passed`（Windows temp ACL 下最小提升）、Ruff/py_compile/fixture validator PASS、`git diff --check` 退出码 0；最终冻结 fixture 与六个 ignored 运行文件 hashes 与报告核对一致。Task65 资产普通权限读取受 ACL 阻断，最小只读提升后成功，未改 ACL。独立 detector 审阅、主 Agent 验收与 focused commit 待完成。

### Independent detector 与主 Agent 结论（2026-09-24）

独立只读 `detector / gpt-6-sol / medium` 按合同 round 0 返回 `PASS`，`C66.1-01..06`、`R66.1-01..05` 均核对，`must_fix: []`、`optional_hardening: []`、`scope_delta: none`、`implementation_scope_delta: none`。审阅者独立核验冻结 fixture 工作树/Git blob 与六份 ignored 产物哈希、冻结时间先于映射、96/288/四层/Query 新颖度/语言/Gold 分布；复算两侧各 288 项、旧/新 fallback 45/0、JEV 311 新调用+220 同状态复用+45 未调用、全量返回模型同版；按逐菜原始记录独立复算旧 `41/96`→新 `59/96`、改善 18/退步 0/持平 78，并核对复用 state hash/判定/版本。只读 validator、Ruff、diff check PASS；worker 的 19 项 focused pytest未由 detector 重跑，已如实保留证据边界。审阅未发 API、未写文件。

主 Agent 已核对 handoff、报告、敏感性拆分与 detector PASS，按项目普通 Task 自动路径进入 `auto_accepted`。本 Task 只增离线扩样 fixture、runner、测试、报告与 ignored 原始记录；不切换产品默认，不改原 Task64/66 证据，不 push/main/tag/Release。完成本地 focused commit 后等待用户决定推送或后续产品化。
