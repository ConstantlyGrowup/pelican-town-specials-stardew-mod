# Session｜M14 Task 67 原料 RAG 拒匹配与复测

| 字段 | 值 |
|---|---|
| session_id | `2026-09-24-task-67-ingredient-rag-abstention` |
| status | `committed` |
| session_type | `implementation` |
| owner | Codex 主 Agent |
| base_commit | `2adcc47` |
| acceptance_contract_id | `m14-task67-explicit-rag-provider-verifier-v5`（v1–v4 历史保留如下） |
| revise_round | `0`（v5 独立审阅；先前合同的返工记录保留如下） |
| planning_status | `READY_FOR_IMPLEMENTATION` |

## 冻结目标与用户可见边界

用户要求：对本地 RAG 无法明确对应到原版原料的现实原料，拒绝强行匹配并进入现有 catalog fallback；优化后实测拒识及已有可映射菜品，不能只修 5 个已知例子。显式 RAG 是唯一改动路径；产品默认仍为 LEGACY，API/UI/schema/目录/上游生成不变。旧 120 菜评测输入、JEV raw 与事后翻译歧义记录只读。没有新的付费 JEV 授权。

## planning_rulings

- `R67-01`：RAG 正常运行并判断无合理匹配，与模型/索引/推理异常是不同状态。前者必须到 mapper 的 `catalog fallback`，不能经 `_build_candidates` 再次走旧检索；后者保持 Task65 原有旧词法降级。`user_visible_delta` 仅是用户请求的无匹配行为。
- `R67-02`：当前 `CatalogCandidate.score` 为排名分，不是 E5 cosine/概率。拒识依据必须来自实际检索证据和目录语义，不得直接阈值化排名分或为冻结负样本做 query 特例。`user_visible_delta: none`（内部技术裁决）。
- `R67-03`：Task64/66.1 正样本、目录与历史 JEV 结果保持原样；先在本地完成新链路映射、负样本拒识与正样本 Gold/耗时复测。差异映射如需 JEV 新判断，另请求用户明确授权并限定字段/调用上限。`user_visible_delta: none`。
- `R67-04`：不自动改变产品默认或发行版本；Task67 的 PASS 仅表示显式 RAG 修复达到冻结合同。`user_visible_delta: none`。

## 冻结输入（实现前）

负样本 fixture `tests/fixtures/m14_ingredient_no_match_queries.json` 工作树 SHA-256 `F50F02C6C847B7EFBF039128030784E8F08CBF582362A70661917A739B4303D8`；20 条不同 query，其中 5 条已观察、15 条未在本 Task 实现前运行。目录 SHA-256 `4D07E9B3EE45670543C1BDCFFA69F84CC2FB2829C4DB4CF2BEFD273B36374E2B`。逐条检查无同名可用目录条目，并按现实语义人工判定无合理原料级对应物。`observed_seed` 允许校准，`unseen_challenge` 只用于实现冻结后的验证；不按结果删改。正样本继续用 Task64/66.1 的冻结 hash。

## Context Packet

```yaml
task_id: M14-Task-67
base_commit: 2adcc47
planning_status: READY_FOR_IMPLEMENTATION
acceptance_contract_id: m14-task67-rag-abstention-v1
revise_round: 0
objective: 修复显式 RAG 在无合理原版对应物时强行匹配，并对冻结负样本与既有正样本同集实测。
user_visible_contract: 显式 RAG 确认无匹配时走现有 catalog fallback；LEGACY 默认及 API/UI/schema 不变。
planning_rulings: [R67-01, R67-02, R67-03, R67-04]
contract_delta:
  documents: [Task67 计划、Session、结果报告、STATUS]
  domain: []
  persistence: []
  application_api: [内部 RAG 检索结果与 _build_candidates 分叉]
architecture_budget:
  allowed: [本地拒识判据、显式 no-match 状态、现有 mapper 兜底、离线同集复测]
  forbidden: [新 Provider/服务/数据库、Query 特例黑名单、产品默认切换、目录或历史评测改写]
allowed_files:
  - path: backend/src/pelican_town_specials/ingredient_rag/
    action: modify
    reason: 正常检索时形成可审计 no-match 判据
    criterion_ids: [C67-01, C67-02, C67-04]
  - path: backend/src/pelican_town_specials/generation/orchestrator.py
    action: modify
    reason: 区分语义 no-match 与资源故障旧检索降级
    criterion_ids: [C67-01, C67-02]
  - path: backend/tests/ingredient_rag/ and focused generation tests
    action: modify
    reason: 拒识、正样本与旧路径回归
    criterion_ids: [C67-01, C67-02, C67-03]
  - path: scripts/ and docs/development/M14_TASK67_INGREDIENT_RAG_ABSTENTION.md
    action: create
    reason: 冻结输入上的可复算离线结果及同集对照
    criterion_ids: [C67-03, C67-05]
acceptance_ledger:
  - criterion_id: C67-01
    source: 用户 Task67 请求与五项真实负样本诊断
    requirement: 显式 RAG 正常运行时，对冻结 20/20 无对应物查询拒绝强行映射并进入既有 catalog fallback；不靠硬编码 query；单列 5 条已观察与 15 条挑战集。
  - criterion_id: C67-02
    source: 用户要求的兜底与 Task65 既有故障保护
    requirement: 语义 no-match 不经旧检索二次匹配；资源/推理异常仍安全降级旧链路；LEGACY 默认及 mapper 合法性不变。
  - criterion_id: C67-03
    source: 用户要求优化后实测；冻结 Task64/66.1 输入
    requirement: 正负样本各自固定分母报告新旧候选、最终 ID、拒识、Gold 命中、全菜和逐项质量、耗时及失败；不可选择性删样。
  - criterion_id: C67-04
    source: M14 本地化设计与 Task65 资源预算
    requirement: 无新远端依赖/索引重建/默认切换；中英精确别名、已用 ID、线程安全与性能资源门槛不回归。
  - criterion_id: C67-05
    source: 用户本轮实测请求及 JEV 授权边界
    requirement: 新增真实 JEV API 请求只在单独授权后执行；同状态同版本可复用，未完成时不得声称最终 JEV 准确率。
out_of_scope: [默认切换、正式包、push/tag/Release、PostHog、上游原料生成、新付费调用预授权]
test_commands: [python -m pytest backend/tests/ingredient_rag backend/tests/catalog/test_mapping.py -q -p no:cacheprovider, python -m ruff check backend/src/pelican_town_specials/ingredient_rag backend/src/pelican_town_specials/generation/orchestrator.py backend/tests/ingredient_rag, git diff --check]
```

## 当前进度

前置报告 Session `2026-09-24-m14-rag-human-review-report` 已获用户接受并本地提交 `2adcc47`；未推送。Task67 负样本先冻结 SHA 并人工核对后再派发新 implementer；原五项已观察结果不能冒充独立盲测，新增十五项在实现前冻结。无新 JEV 付费调用授权。

## 2026-09-24 合同修订 v2（用户明确授权）

v1 实施者用现有 E5/目录信号试过绝对 cosine、top-1/top-2 margin、`Cooking` 类型过滤及组合；可拒 5/5 已观察负例的组合让正样本全菜 Gold 从类型过滤单独的 `94/120` 降至 `81/120`。这只是探索性诊断，原内联探针未持久化，精确数值待可复算 runner 独立复核；没有产品实现，v1 不视为 PASS。实施者核对 fixture 时意外看到了十五条挑战文本但未运行或用于调参，因此只能称“预先冻结、未运行”，不能称严格盲测。诊断见 `docs/development/M14_TASK67_ABSTENTION_DIAGNOSIS.md`。

用户收到上述取舍后，明确授权扩展为“增加本地语义核验/目录类型知识后再实测”。以下 v2 合同取代 v1 的可实施范围与验收门槛，保留 v1 历史事实，不改原冻结正负输入：

- `R67-05`：优先使用可审计的静态目录语义类别/别名知识和已有本地 E5；若确需新增本地验证模型，须记录来源、许可证、固定版本/hash、资源大小、冷/热延迟与离线装包可行性。不得增加远端请求、服务、数据库或硬编码冻结查询。`user_visible_delta` 仍只限于显式 RAG 无匹配兜底。
- `R67-06`：新增可复算的本地评测 runner，逐项输出候选证据、最终 ID、拒识理由、Gold 命中、同菜去重、失败与耗时。探索性 v1 数值须标“未独立复算”，不能直接作新方案的前后统计。
- `R67-07`：20 条原负集固定分母不删改；十五条文本已泄露给 v1 实施者，因此 v2 应额外在代码冻结后由主 Agent 构造独立压力样本，并单列两组，不把后者冒充预注册集。
- `C67v2-01`：正常显式 RAG 在固定 20/20 无对应物上拒匹配并到现有 catalog fallback；代码无 query 黑名单，且新的独立压力样本结果单列。
- `C67v2-02`：语义 no-match 与模型/索引故障有独立状态；前者不经过 legacy 二次检索，后者保持旧降级；LEGACY 默认、API/UI/schema/目录不改。
- `C67v2-03`：120 菜/360 项冻结正集同集 Gold 全菜与逐项均不得低于未修复显式 RAG 的 `84/120` 与 `318/360`；同时单列两批、fallback 与耗时，不靠删样或把 fallback 算正确。该本地门槛不替代 JEV 全菜合理率。
- `C67v2-04`：若映射变化需要新 JEV 判断，仍须另获用户付费 API 授权；同状态、同返回模型版本可复用。未取得授权不能宣称 JEV 主指标通过，也不能将 Task 关闭为完成。
- `C67v2-05`：精确别名、中英文、已用 ID、线程安全、资源故障与本地部署资源不回归；运行实际测试并由新只读 detector 按 v2 独立审阅。

v2 继续不包含产品默认切换、推送、tag、Release 或修改 PostHog。新的 implementer 仅能修改 RAG、orchestrator、聚焦测试与 Task67 本地评测 runner；控制面、冻结 fixture 与结论由主 Agent 维护。

v1 诊断的独立只读 detector 返回 `REVISE`：生产拒识和 no-match 分叉均未实现，也没有 20 条负样本与优化后正样本完整实测；探索数字无持久化逐项输出，无法独立复算。该结论不追认 v1 PASS。v2 新 implementer 和后续新 detector 必须按以上 v2 门槛工作。

v2 首轮实现已由新 implementer 交接：本地双语目录语义类别、显式 no-match 分叉和可复算逐项 runner；focused pytest `92 passed`、Ruff/mypy 通过。主 Agent 代码冻结后独立运行原 20 条负集，`15/20` 正确兜底、5 条强配，且 0 基础设施失败；另构造并单列的 10 条独立压力样本为 `4/10`。正集保持 `84/120` 全菜 Gold、`318/360` 逐项 Gold。v2 独立 detector round 0 返回 `REVISE`，唯一 MUST_FIX 为 `C67v2-01`，不得验收或提交。正集/负集可复算输出位于 ignored `output/m14-task67-full-v2/`；压力输出位于 ignored `output/m14-task67-pressure-v2/`。压力文本不提供给返工实施者调参。

返工 round 1 限于已授权的本地语义核验：先在 ignored 工作目录评估轻量多语成对语义验证模型的来源、许可、量化资源及正负集表现；不在未证实效果前引入产品依赖或安装包资产。若模型不满足拒识和正集质量门槛，保留证据并回报，不通过增加失败 query 词条伪装为泛化。

返工 round 1 已完成离线原型、未改产品代码：MIT 多语 MiniLM NLI 量化资源约 107 MB，虽可复用当前推理依赖且推理延迟可接受，固定 20 负例与 120 菜正例上却没有同时达到拒识/Gold 门槛的阈值；详细数值和固定资源 hash 见 `M14_TASK67_ABSTENTION_DIAGNOSIS.md` 及 ignored `output/task67-v2-nli-prototype/nli-full.json`。v2 产品实现仍只有 `15/20`，独立压力 `4/10`；不能验收或提交。用户可见架构分叉已请求用户选择：是否改用现有文本 LLM 对 Top5＋无匹配按菜批量核验，或继续更大本地模型，或暂停。收到方向前不新增生产代码、JEV 请求或推送。

## 2026-09-24 合同修订 v3：现有文本 LLM 批量核验可行性

用户明确选择“允许评估现有 LLM 核验”。该回复授权可行性评估，不等于已验收 v2、更不等于直接接入产品默认链路或无限额真实模型调用。v3 单独冻结为先构建无付费的离线协议/runner，再向用户确认真实试跑的请求上限和所用配置。原 v2 负集/正集与本地失败证据保持只读。

```yaml
task_id: M14-Task-67-LLM-verifier-feasibility
base_commit: 2adcc47
planning_status: READY_FOR_IMPLEMENTATION
acceptance_contract_id: m14-task67-llm-verifier-feasibility-v3
revise_round: 0
objective: 评估用应用已有文本模型一次按菜核验全部现实原料的 RAG Top5 候选及无匹配选项。
user_visible_contract: 此阶段仅离线评估协议，不改变产品链路；若后续接入，仅显式 RAG 增加一次按菜文本请求，LEGACY 默认不变。
planning_rulings:
  - R67v3-01: 仅候选 ID/中英名称和现实原料/菜名可送现有文本模型；目录 type/category 亦不得进 prompt。Gold、旧新方案、分数、历史判定、密钥、图像与用户原始上下文不得进 prompt。
  - R67v3-02: 一道菜全部原料合并为一个请求，每项模型输出候选 ID 或 null；程序须验证每个选择属于该项 Top5、项数完整且无重复 ID，非法响应不得静默强配。
  - R67v3-03: 20 条负集先按单原料请求独立评测，正集按 120 道菜评测；真实 API 调用数/字段/提供方在执行前另获明确上限授权，不能复用 JEV 授权。JEV 仍为独立评测者。
  - R67v3-04: 本阶段不改正式 Provider/Orchestrator/API/schema、默认分支、打包或发布；如评测有效，再冻结接入合同并请求用户确认。
architecture_budget:
  allowed: [离线 prompt、严格 DTO、响应校验、假 Gateway 测试、可复算 runner、只读冻结输入]
  forbidden: [未授权真实请求、JEV 调用、生产链路改写、新服务、新数据库、修改历史原始输出或 Gold]
allowed_files:
  - path: scripts/evaluate_task67_llm_verifier.py
    action: create
    reason: 脱敏批量请求与可复算结果
    criterion_ids: [C67v3-01, C67v3-02, C67v3-03]
  - path: backend/tests/tools/test_task67_llm_verifier.py
    action: create
    reason: 假 Gateway 与协议验证
    criterion_ids: [C67v3-01, C67v3-02, C67v3-03]
acceptance_ledger:
  - criterion_id: C67v3-01
    source: 用户选择现有文本 LLM 核验、项目隐私与原料评测边界
    requirement: 每道菜最多一个批量请求；输入只含菜名、现实原料、每项 Top5 的 ID/双语目录名及 null 选项，绝不含目录 type/category、Gold、分数、方案标签、图像、Key 或用户原始上下文；负例使用同一协议。
  - criterion_id: C67v3-02
    source: 用户的拒匹配兜底目标与原目录校验规则
    requirement: 结构化返回完整逐项候选 ID 或 null；程序校验项数、候选归属和不重复，null 走 catalog fallback；异常与非法结果不静默强配。
  - criterion_id: C67v3-03
    source: 用户要求同集实测与付费边界
    requirement: runner 固定读取 120 菜/360 项与 20 负例，保留分母、逐项结果、耗时、调用数和原始输出哈希；默认纯 fake 无远端请求，真实模式须独立显式启用并受用户授权上限约束。
  - criterion_id: C67v3-04
    source: 本次仅允许评估、非上线授权
    requirement: 不改正式 Provider/Orchestrator/API/默认开关/安装包；不新增 JEV 请求、推送或提交，输出为可行性结论而非产品验收。
out_of_scope: [产品接入、JEV 全量评测、正式包、默认切换、push/tag/Release]
test_commands: [python -m pytest backend/tests/tools/test_task67_llm_verifier.py -q -p no:cacheprovider, python -m ruff check scripts/evaluate_task67_llm_verifier.py backend/tests/tools/test_task67_llm_verifier.py, git diff --check]
```

v3 实施者只拥有上述新脚本和聚焦测试。主 Agent 拥有本 Session、STATUS、计划、诊断与授权边界；本地 v2 未验收代码仍属于同一脏工作树，不可被覆盖或顺手提交。

用户随后单独授权首轮最多 `15` 次真实个人文本 Provider 请求：`10` 道冻结菜＋`5` 个无对应物原料；不使用公共试用，也不调用 JEV。发送字段仅限菜名、现实原料、各项 Top5 的目录 ID/中英名和明确“无匹配”选项；不得发送 Gold、候选分数、图片、用户原始内容或密钥。按个人 Provider 计费，实际请求数不得超限。此授权不涵盖剩余 110 道菜/15 负例的全量试跑，也不授权生产接入、默认切换、提交或推送。

首轮试跑样本在任何真实调用前固定为：Task64 `d07`、`d18`；Task66.1 四层各取排序后的第 6、19 条，即 `h66-ambiguous_name-06/-19`、`h66-bilingual_or_synonym-06/-19`、`h66-direct_name-06/-19`、`h66-raw_vs_prepared-06/-19`；负样本为原本地规则未拒识的 `n13`、`n14`、`n15`、`n19`、`n20`。这是有意覆盖分层与已知失败的诊断试点，不是随机总体估计，也不能代替 120 菜/20 负例正式同集实测。选择与模型输出无关，试点结果不可据此删样。

### v3 实施、独立审阅与首轮真实试点

指定 `luna_worker`（`gpt-6-luna/max`）完成仅有的两个新离线文件 `scripts/evaluate_task67_llm_verifier.py` 与 `backend/tests/tools/test_task67_llm_verifier.py`；曾遇用量限制，用户明确要求恢复后重试，原子代理恢复并完成。正例候选读取实际 `mapper_candidates`，负例读取规则拒识前的 `ranked_candidates_before_semantic_verification`。worker 报告 13 项聚焦测试、Ruff、py_compile、fake 与真实门控 dry-run 均通过，物理请求为 0。独立只读 `detector`（`gpt-6-sol/medium`）对 `C67v3-01..04`、`R67v3-01..04` 返回 `PASS`、无 MUST_FIX，并独立复跑 13 项聚焦测试、Ruff、diff check 及 15-ID dry-run；强调物理调用上限按单次运行控制，跨运行须主 Agent 记录。

主 Agent 在独立 PASS 后以独立输出目录执行授权的精确 15-ID 试点一次，未重试任何项：`logical_call_count=15`、`network_request_count=15`、`jev_calls=0`，模型 `gpt-5.6-terra`。全部 5 条有意预选的负例从 v2 `0/5` 兜底改善为文本核验 `5/5`；10 菜全 Gold 仍为 `9/10`，逐项 v2 `29/30`→文本核验 `27/30`。一菜 `h66-ambiguous_name-06` HTTP 200 后评分发现 `duplicate_final_item_id`，该菜 3 项按 invalid，不将其称作模型语义错误或 Provider 失败；其余 9 菜全部 Gold。总耗时 121.4 秒，单请求中位 4.55 秒、p95 27.34 秒。ignored 输出 `output/m14-task67-v3-pilot-20260924/`，manifest SHA-256 `AB7F1DE9C427F6FF9AEED4A3B2277DB1303A0D7EE526CB8CFCDF74F20522B6AD`；完整解释见 `M14_TASK67_ABSTENTION_DIAGNOSIS.md`。

这 15 次授权已耗尽；没有运行其余 110 菜/15 负例，没有新增 JEV、产品接入、默认切换、提交、推送或发布。v2 未验收产品改动仍在工作树，Task67 不可标记完成。下一步等待用户决定是否扩大付费验证，并先明确处理按菜 `null` 兜底与同菜已选候选的去重冲突；不能以诊断试点替代完整同集实测。

试点后识别到上述去重冲突可在离线评分阶段按原合同修复：先为所有明确、合法的非空选择预留 ID，再给 `null` 逐项分配目录兜底；重复最终 ID 仍为非法，兜底不计 Gold。原 implementer 只改 v3 两个获准文件并增加针对性测试，聚焦 `15 passed`、Ruff/py_compile PASS；新的只读 detector 定向复审 `PASS`。既有试点 manifest SHA-256 保持 `AB7F1DE9C427F6FF9AEED4A3B2277DB1303A0D7EE526CB8CFCDF74F20522B6AD`，历史那道无效菜不追溯重算，亦无新远端请求。剩余阻塞是全量试验与产品接入未授权；上述“先明确处理去重冲突”的待办已由离线评分器修复满足，不代表生产已修复。

主 Agent 随后运行一次纯 fake 全集冒烟：120 菜/360 项＋20 负例均有输出，140 个逻辑 case、**0** 个网络请求、0 无效项；目录为 ignored `output/m14-task67-v3-fake-20260924/`。fake 结果只验证 runner 分母与协议，不代表文本模型质量或负例拒识率；真实试点文件仍未覆盖。

## 2026-09-24 用户授权全量文本核验及条件生产接入

用户确认本地规则的 `15/20` 拒识在不损伤正常菜品时是可接受的 tradeoff，接受显式 RAG 每菜增加一次个人文本 Provider 核验的耗时与费用，授权全量 Provider 测验；若表现可以，允许改造原有链路。此新指令取代 v3“仅 15 次试跑、产品接入未授权”的未来限制，但不追改 v3 已发生的 15 次、冻结输入、历史结果或 JEV 授权边界。新阶段最大新增物理请求为剩余 `110` 菜＋`15` 负例＝`125` 次；首轮 15 例只复用、不重发。仍仅使用个人文本 Provider，发送字段沿用 v3 最小集合；不调用 JEV、不用公共试用、不切 LEGACY 默认、不推送或发布。

全量前冻结“表现可以”的本地判据：固定 120 菜/360 项全菜 Gold 至少 `84/120`、逐项 Gold 至少 `318/360`，固定 20 负例至少 `15/20` 正确进入 catalog fallback；失败、非法响应和首轮试点无效菜保留分母，不因事后修复离线评分器而重算或重发。`15/20` 是用户明确接受的最低 tradeoff，而非目标宣传值；须单列 5 已观察、15 挑战和独立压力集。报告每菜一次请求的时延、请求数与错误。Gold 是本地候选与冻结可接受 ID 的验证，不冒充新增 JEV 全菜合理率；若生产接入会改变既有 JEV 映射状态，新的 JEV 付费判定仍需单独授权。

```yaml
task_id: M14-Task-67-full-text-verifier-evaluation
base_commit: 2adcc47
planning_status: READY_FOR_IMPLEMENTATION
acceptance_contract_id: m14-task67-full-text-verifier-evaluation-v4
revise_round: 0
objective: 在不重复首轮请求的条件下完成剩余 125 case 的个人文本 Provider 核验，并按冻结正负分母判定是否进入生产接入。
user_visible_contract: 仅评测阶段；现有产品行为与 LEGACY 默认不变。若达门槛，再在本 Task 后续冻结生产接入 Packet。
planning_rulings:
  - R67v4-01: v3 脚本仅准首轮 15 ID，与新授权冲突；新增独立 remaining-ID allowlist 和每 case 独立输出，最大 1 次物理请求/调用，以主 Agent 的 125-ID 去重台账控制跨运行总量。首轮 ID 禁止重发。
  - R67v4-02: 扩样只复用既有 120 菜/360 项与 20 负例的冻结输入、目录和 v2 候选；不改 Query、Gold、Top5、prompt 字段或已存试点结果。
  - R67v4-03: 非正常返回、进程中断或输出目录已存在都不得自动重试；保留已尝试 case 的目录为消耗证据，无法确认物理调用数的 case 停止并人工核对，不擅自补请求。
  - R67v4-04: 质量按本节事前冻结门槛和全分母判定；JEV 不在本授权内，产品接入另由主 Agent 在结果达门槛后冻结合同与独立实施审阅。
contract_delta:
  documents: [本 Session、STATUS、Task67 诊断/结论]
  domain: []
  persistence: []
  application_api: [离线 runner 的剩余 case 单次执行入口]
architecture_budget:
  allowed: [离线剩余 ID 白名单、一次一 case 的显式真实模式、排他输出、假 Gateway/边界测试、只读聚合]
  forbidden: [自动重试、JEV、公共试用、生产链路修改、改历史输入/产物、新服务/数据库、跨运行无限额调用]
allowed_files:
  - path: scripts/evaluate_task67_llm_verifier.py
    action: modify
    reason: 新授权的剩余 case 白名单、单次物理请求上限与可恢复输出边界
    criterion_ids: [C67v4-01, C67v4-02]
  - path: backend/tests/tools/test_task67_llm_verifier.py
    action: modify
    reason: 白名单/重复/单次限额/隐私/失败保护回归
    criterion_ids: [C67v4-01, C67v4-02]
acceptance_ledger:
  - criterion_id: C67v4-01
    source: 用户本次全量 Provider 授权与先前 15 次已耗尽事实
    requirement: 真实剩余模式只接受 125 个未试 ID，每次精确一 case、最多一次物理请求、无重试/repair；首轮 15 ID 拒绝；排他输出在发请求前创建，不覆盖历史。
  - criterion_id: C67v4-02
    source: v3 隐私边界和固定评测协议
    requirement: 只发 v3 准许字段，读取冻结输入并验证 hash；失败/非法响应保留分母，不打印/保存 Key 或原始敏感响应；fake 默认零网络。
  - criterion_id: C67v4-03
    source: 用户要求全量实测与条件接入
    requirement: 聚合首轮 15 和新增 125 的唯一 case，原始 trial 不重算，固定 120/360/20 分母，报告 Gold、拒识、错误、逐项/全菜、耗时和请求数；不以 fake 或事后删样宣称通过。
  - criterion_id: C67v4-04
    source: 用户接受 15/20 tradeoff 且强调正常菜品不退步
    requirement: 事前门槛为全菜 Gold ≥84/120、逐项 Gold ≥318/360、负例兜底 ≥15/20；未达到不得进入生产接入；JEV 仍为独立未授权判定。
out_of_scope: [JEV 新请求、生产接入、LEGACY 默认切换、push/tag/Release、重发首轮 15 例]
test_commands: [python -m pytest backend/tests/tools/test_task67_llm_verifier.py -q -p no:cacheprovider, python -m ruff check scripts/evaluate_task67_llm_verifier.py backend/tests/tools/test_task67_llm_verifier.py, python -m py_compile scripts/evaluate_task67_llm_verifier.py backend/tests/tools/test_task67_llm_verifier.py, git diff --check]
```

此 Packet 只授权先修改离线脚本/测试并做 fake/dry-run；实施者不得亲自发真实请求。主 Agent 在独立 detector PASS 后负责精确 125-ID 台账和真实执行，再据完整结果决定是否启动条件生产接入。原工作树的 v2 未验收产品改动保持不动。

### v4 全量结果及用户的接入裁决

v4 执行器先经实施者聚焦 `20 passed` 和独立 detector round 0 `REVISE`：旧 pilot scope 仍可重发已消耗 15 ID；封闭返工后 round 1 `PASS`，真实 pilot 入口在 Provider 配置和请求前拒绝。主 Agent 用 personal 文本 Provider 逐 case 跑了剩余 125 条，首轮 15 条只读复用；共 140 个唯一 case、140 次物理请求，全部冻结输入/产物 hash 匹配，0 JEV。两次 Provider 超时和首轮一菜无效仍计入分母。按原始 Gold 全菜 `84/120→94/120`、逐项 `318/360→327/360`、负例兜底 `15/20→20/20`；配对改善 12、退步 2、持平 106；140 次核验调用 p50 `8.32s`、p95 `50.48s`。独立只读 detector 对 `C67v4-03/04` 返回 PASS。完整证据见 `M14_TASK67_ABSTENTION_DIAGNOSIS.md` 及 ignored `output/m14-task67-v3-pilot-20260924/`、`output/m14-task67-v4-remaining-20260924/`。

两道退步明确为 `berries` 和 `root vegetables` 被文本模型过度拒匹配；这意味着“正常菜完全零回归”不成立。用户收到 12 改善／2 退步与 20/20 负例的精确取舍后，明确接受，并授权接入**仅显式启用的 RAG 路径**。这不包含把产品默认 LEGACY 切成 RAG、推送、发布或新的 JEV 付费评测。v4 的“若达门槛再冻结接入 Packet”条件至此满足。

## 2026-09-24 v5 条件生产接入合同

```yaml
task_id: M14-Task-67-explicit-rag-provider-verifier
base_commit: 2adcc47
planning_status: READY_FOR_IMPLEMENTATION
acceptance_contract_id: m14-task67-explicit-rag-provider-verifier-v5
revise_round: 0
objective: 把已通过全量本地 Gold/拒识门槛的按菜文本核验接入显式 RAG 生成路径；无匹配走 catalog fallback。
user_visible_contract: 只有内部显式选择 RAG 且 Ask Gus 新生成确实需要原料映射时，最多增加一次同一 Provider 的文本核验；LEGACY 默认、Canonical HIT、Blueprint、UI/API/schema 与现有试用接管规则不变。
planning_rulings:
  - R67v5-01: 现有 _map_gameplay 为同步逐项映射，而 Provider 是异步按菜调用；保留旧同步 LEGACY 路径，增设 RAG 专用异步编排，先用真实本地 RAG 对整菜各项形成 Top5，再一次批量核验。不得一项一请求。
  - R67v5-02: v2 本地明确 no-match 具有否决权并进入 catalog fallback；对可选 Top5，Provider 仅返回其中一 ID 或 null。null 不做旧词法二次匹配；映射前保留全部明确选择 ID，避免兜底抢占后续选择。模型失效/协议非法则整菜退回 v2 本地 RAG 映射，不出现部分应用。
  - R67v5-03: 为兑现每菜最多一个新增请求，Verifier Provider 方法必须禁用本步骤的自动重试和结构化修复，不改变其他 Provider 方法的现有重试策略。取消继续传播；不得在日志、错误、checkpoint 或遥测记录 prompt、原始响应、Key、菜名或原料文本。
  - R67v5-04: 核验使用当前 attempt 已选的 gateway/profile；不从公共试用静默切到个人服务，不新增试用额度 claim/扣次或单独探测。默认构造仍为 LEGACY，显式 RAG 仅内部依赖注入，不加用户设置/API。
  - R67v5-05: 新生产 Prompt 只含可用菜名、现实语义原料以及每项 Top5 的目录 ID/中英名和 null；生产只有单语菜名时不得为模拟双语而额外发送用户上下文/图片或调用翻译服务。此与离线 fixture 的双语菜名差异须在结论中披露。
contract_delta:
  documents: [本 Session、STATUS、Task67 结论、必要的正式 M14 技术设计同步]
  domain: []
  persistence: []
  application_api: [内部 ModelGateway 核验 DTO/方法、OpenAI-compatible 单次核验、RAG 专用异步原料映射及内部选择器]
architecture_budget:
  allowed: [严格内部 DTO、单次文本调用、RAG 专用异步路径、同菜 ID 校验与无匹配兜底、失败回原本地 RAG、fake/捕获请求测试]
  forbidden: [新服务/数据库、逐原料 Provider 请求、自动 repair/retry、JEV 调用、LEGACY 默认切换、新 UI/API/schema/遥测字段、修改冻结原始评测]
allowed_files:
  - path: backend/src/pelican_town_specials/providers/contracts.py
    action: modify
    reason: 严格核验请求/响应和 ModelGateway 内部接口
    criterion_ids: [C67v5-01, C67v5-02]
  - path: backend/src/pelican_town_specials/providers/openai_compatible.py
    action: modify
    reason: 同配置文本模型一次结构化核验，不继承本步骤的自动重试/修复
    criterion_ids: [C67v5-01, C67v5-02, C67v5-04]
  - path: backend/src/pelican_town_specials/providers/prompts/ingredient_verifier_v1.py
    action: create
    reason: 固定最小字段、按菜批量和 null 指令
    criterion_ids: [C67v5-02]
  - path: backend/src/pelican_town_specials/generation/orchestrator.py
    action: modify
    reason: 显式 RAG 异步按菜核验/兜底/失败本地回退与内部选择器
    criterion_ids: [C67v5-01, C67v5-03, C67v5-04]
  - path: backend/src/pelican_town_specials/ingredient_rag/
    action: modify
    reason: 仅保留并集成既有 v2 本地语义拒识与检索证据；若需额外字段满足同菜闭包则最小修改
    criterion_ids: [C67v5-03]
  - path: backend/tests/providers/ and backend/tests/generation/ and backend/tests/ingredient_rag/
    action: modify
    reason: 先观察失败测试，再覆盖单请求、字段、null/错误、去重、LEGACY、并发/续作回归
    criterion_ids: [C67v5-01, C67v5-02, C67v5-03, C67v5-04]
acceptance_ledger:
  - criterion_id: C67v5-01
    source: 用户同意按菜增加一个 Provider 步骤、仅显式 RAG 接入
    requirement: RAG 正常 Ask Gus 映射每菜最多一个新增文本请求，独立原料合并；LEGACY 默认无该请求，Canonical HIT/Blueprint 不新增请求。
  - criterion_id: C67v5-02
    source: v4 已授权最小字段与 v3 响应协议
    requirement: 请求仅含菜名、现实原料、每项 Top5 目录 ID/双语名和 null；响应项数/索引/成员/唯一 ID 严格校验，null 与本地 no-match 到 catalog fallback，最终同菜 ID 唯一、目录合法。
  - criterion_id: C67v5-03
    source: Task67 原始兜底请求、v2 故障分叉和 v4 超时实测
    requirement: Provider 超时、鉴权、协议非法等不能强配或部分应用；整菜退回现有 v2 本地 RAG（资源故障仍旧词法降级）；取消不吞；无 prompt/原始响应/敏感正文落盘或日志。
  - criterion_id: C67v5-04
    source: 用户接受费用/耗时但未授权默认/试用机制改变
    requirement: 单核验调用本身零自动重试/repair，使用当前 attempt 同一 gateway/profile；试用预留/确认/失败释放、三槽与 Task56 checkpoint 语义不回归，LEGACY 默认不变。
  - criterion_id: C67v5-05
    source: M14 本地化方案与本轮条件接入边界
    requirement: 不改冻结 Query/Gold、历史 JEV、目录或向量资源，不新增 API/UI/schema/设置/遥测；聚焦测试、静态检查及相关生成/Provider 回归通过。
out_of_scope: [JEV 新请求、默认 RAG 切换、push/tag/Release、PostHog、上游现实原料提取改造]
test_commands: [python -m pytest backend/tests/providers/test_openai_compatible.py backend/tests/generation/test_ask_gus.py backend/tests/ingredient_rag -q -p no:cacheprovider, python -m ruff check backend/src/pelican_town_specials/providers backend/src/pelican_town_specials/generation/orchestrator.py backend/src/pelican_town_specials/ingredient_rag backend/tests/providers backend/tests/generation backend/tests/ingredient_rag, python -m mypy backend/src/pelican_town_specials/providers backend/src/pelican_town_specials/generation/orchestrator.py backend/src/pelican_town_specials/ingredient_rag, git diff --check]
```

v5 implementer 拥有上述生产代码及聚焦测试，不改本 Session、STATUS、计划与诊断。主 Agent 审阅交接、派独立 detector、核对全量门槛与失败回退；任何真实生产调用仍需用户在实际产品路径中触发，本 Task 不再次运行付费模型或 JEV。默认不切换、无 commit/push/Release，直至该 Task 按冻结合同独立复审与用户可见行为验收。

### v5 实施、验证与待验收交接

用户已明确接受 v4 的 12 道改善／2 道退步，并授权仅显式 RAG 接入。指定 `luna_worker` 完成 `m14-task67-explicit-rag-provider-verifier-v5`：新增严格核验 DTO/最小 Prompt/单次无重试 Provider 方法，在 Ask Gus 内部显式 RAG 路径按菜合并 Top5 后调用；明确选择的 ID 先预留，`null` 与本地 no-match 走目录兜底，Provider 故障/协议非法则整菜退回 v2 本地 RAG，取消继续传播。默认 LEGACY、Canonical 命中、Blueprint、UI/API/schema/设置/遥测均未改变。生产代码和聚焦测试文件清单以 v5 Packet `allowed_files` 与交接为准；新增 `backend/tests/providers/test_ingredient_verifier.py` 和 `backend/tests/generation/test_rag_provider_verifier.py`。

实施者记录：Provider/Ask Gus/RAG/Task56 resume/三槽并发综合回归 `140 passed`；新增两份测试 `13 passed`；Ruff PASS、mypy 23 source files PASS、`git diff --check` PASS。原 pytest 临时目录出现 `WinError 5`，经已授权的最小权限测试执行后全绿，未改 ACL。未发真实 Provider/JEV 请求，未提交或推送。

主 Agent 将状态由 `active` 经 `verification` 推进。独立只读 `detector` 对 `C67v5-01..05` 与 `R67v5-01..05` 返回 PASS，无 must-fix/scope delta；它独立复跑 Provider 聚焦 `6 passed`、Ruff、mypy（23 source files）及 diff check。其生成侧 pytest 因本机临时目录 `WinError 5` 不能复跑，故保留上述实施者 140/13 项结果为该部分证据，不伪称 detector 全量复跑。v4 同集 Gold/负例门槛与 2 道回归的用户取舍不变；生产只有可用的单语菜名，离线双语 fixture 的效果不能完全等同产品实时表现。当前状态 `awaiting_user_acceptance`，待用户明确验收后才处理本地 focused commit；push、默认切换、JEV 新评测与 Release 均需另行授权。

### 原始搜索匹配 vs 完整 RAG 的同集人审简版

用户追加要求以**原始搜索匹配链路**为对照写可读结论。主 Agent 仅只读归并 Task64 旧 24 菜和 Task66.1 旧 96 菜逐项输出，与 Task67 v3 首轮 10 菜、v4 剩余 110 菜的完整 RAG 输出对齐：360 个 query ID 无缺失或重复，双方每项 Gold 可接受 ID 集合一致。全菜 Gold 为旧 `56/120`→完整 RAG `94/120`（配对改善 38、退步 0、持平 82）；逐项 Gold 为 `264/360`→`327/360`；非兜底项为 `314/360`→`345/360`。中间本地 RAG `84/120`、`318/360` 只用于解释提升构成。报告见 `M14_TASK67_LEGACY_VS_FULL_RAG_REVIEW.md`。这不是新增 JEV 或产品线上测量，且不改变当前待验收状态、提交或推送边界。

### 用户验收与提交推送授权

用户明确表示报告和新接入链路均通过验收，并授权提交、推送。Session 从 `awaiting_user_acceptance` 经 `accepted` 进入 `committed`；Task67 实施、评测工具/fixture、技术诊断、人审简版、状态和本 Session 构成一个 focused commit。当前分支在本提交前已有 5 个与 M14 Task66/扩样/报告相关的未推送本地提交，用户本次授权推送当前分支；实际 commit 与 push 结果以 Git 核验为准。产品默认仍为 LEGACY，不推 tag/Release，也不调用新的 Provider/JEV。
