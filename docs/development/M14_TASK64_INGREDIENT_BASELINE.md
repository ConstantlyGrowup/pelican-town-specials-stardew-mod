# M14 Task 64｜原料评测集与旧链路基线

## 范围与证据边界

本报告固定 24 道菜、72 条现实语义原料映射项，测量仓库当前 Stardew Valley 1.6.15 目录上的旧链路：`_build_candidates()` Top 5 与分数 → `map_ingredient()` 目录校验、排序选择或兜底。它不覆盖照片识别、上游模型原料生成、鱼类后置守卫或真实用户行为；Query 是人工策划的测试输入，不是用户 Query、用户照片或 Provider 输出。

目录版本为 `stardew-1.6.15-v1`，游戏版本为 `stardew-1.6.15`。先冻结 Query/Gold，再运行旧基线：

| 输入 | SHA-256 |
|---|---|
| `tests/fixtures/m14_ingredient_queries.json` | `7B49E7B88393CCC627DD4AEC7545AC45FDAF4786081D2E9BCC973B202796EEB7` |
| `resources/catalogs/stardew-1.6.15/vanilla-ingredients.json` | `4D07E9B3EE45670543C1BDCFFA69F84CC2FB2829C4DB4CF2BEFD273B36374E2B` |

新增 Query fixture 在 `.gitattributes` 中固定为 LF 检出；定向测试核对工作树、Git blob 与 checkout-filter 输出均保持上述 SHA，避免 Windows 自动换行改变冻结输入。

集合覆盖中英文输入、英文别名/语义变体、类别级对应及易混条目；排除牛肉、羊肉、鸡肉等没有合理原版对应的菜品原料。72 条记录有 50 个不同的规范化 Query；重复项保留其菜品语境，并按原料出现次数计入逐项统计。每个 Gold ID 都由冻结目录校验为 `usableAsIngredient`；可以有多个可接受 ID。Gold 只用于本地候选 Recall 与结果核对，不进入 JEV 请求。

## 旧链路基线

首次离线运行时间：2026-09-23 09:20:27 UTC。结果为 72/72 条运行成功，1 条触发旧链路兜底，0 条映射运行错误。该兜底是可映射的别名 Query `aubergine` 未被旧搜索命中、最终选择 Egg `176`；它从 JEV 主准确率分母排除，但仍包含在固定 Query 集覆盖率分母中。

已逐项保留 Top 5 候选 ID、目录双语名、原始候选分数、最终 ID、`mappingReason`、fallback 状态和耗时。代表性确定性样本：

| Query | Top 候选关键项 | 旧链路选择 | Gold 对照 |
|---|---|---|---|
| `Carp` | `142 Carp` 1.06173；`209 Carp Surprise` 1.15556 | `209 Carp Surprise` | `142 Carp` |
| `white rice` | `157 White Algae` 1.07619；`232 Rice Pudding` 1.15048；`423 Rice` 0.41905 | `232 Rice Pudding` | `423 Rice` |
| `green onion` | `153 Green Algae` 1.2；`188 Green Bean` 1.05；`399 Spring Onion` 0.6 | `153 Green Algae` | `399 Spring Onion` |
| `cherry tomatoes` | `638 Cherry` 2.0 | `638 Cherry` | `256 Tomato` |
| `button mushroom` | `205 Fried Mushroom` 1.45378；`404 Common Mushroom` 0.75070 | `205 Fried Mushroom` | `404 Common Mushroom` |
| `aubergine` | 无候选 | fallback `176 Egg` | `272 Eggplant`；该行不进入 JEV 主准确率分母 |

这些结果是冻结测试输入上的当前代码基线，不表示相同错误已在某个用户菜品中发生。

## JEV 评测协议

JEV 使用 OpenRouter 官方 Jev 1.13 Decisions API（`POST /api/alpha/decisions`），不使用 Chat Completions。请求模型为 `typesafe/jev-1.13`，唯一问题采用 `choice`，固定选项为 `reasonable`、`unreasonable`、`undecidable`；保存模型版本、confidence、可用的 probabilities、usage 与原始响应。此端点和 typed Choice 字段按 [OpenRouter 的 Jev API 示例](https://openrouter.ai/blog/tutorials/jev-vs-llm-when-to-use-each/) 实现；JEV 是文本快速判断器，判定标准写入每个固定选项，不要求解释理由，参见 [TypeSafe System One](https://docs.typesafe.ai/concepts/system-one)。

每个请求 state 仅包含菜名（中英）、现实语义原料（输入名及规范名）、旧链路实际选择的目录对象（ID 和中英文名）。不发送 Gold、候选列表、旧/新方案标记、映射分数或评测结果；候选/Gold 与 JEV 输出在本地按 `query_id` 关联。兜底行不调用 JEV。

先用固定 3 条样本 `d01-i01`、`d02-i01`、`d03-i01` 做真实协议探针。探针通过后，全量对所有非兜底项调用 JEV；探针结果复用，避免重复调用。解析器严格检查 Decisions `answers`、Choice 类型、固定选项、有限 confidence、请求模型版本以及 TypeSafe provider（若返回）；遇到自由文本、聊天格式、未知选项或结构漂移即停止，不做人工或其他模型降级。异常协议的原始响应保存在 ignored 输出供核查。

## 指标定义

- JEV 主合理率：JEV 判为 `reasonable` 的非兜底项 / 有成功调用且判定为 `reasonable` 或 `unreasonable` 的非兜底项。`undecidable`、调用失败、旧链路兜底分别报告，不塞进主准确率分母。
- 固定集合理映射覆盖：JEV 判为 `reasonable` 的项 / 固定 72 项。它保留兜底、无法判定与调用失败的影响，避免覆盖变差时只看条件准确率。
- 菜品全对率：三个原料都非兜底且均被 JEV 判为 `reasonable` 的菜品 / 固定 24 道菜。另报三项均可判定菜品中的条件全对率。
- Gold Recall@5：对每条 Query 计算 Top 5 中可接受 Gold ID 的比例，再按 Query occurrence 求均值；同时报告至少命中一个 Gold ID 的项数、最终选择命中 Gold 数、候选遗漏数和“候选命中但最终选择非 Gold”数。此指标衡量目录检索候选，不替代 JEV 语义主判。

JEV Choice 与“旧链路最终 ID 是否属于冻结 Gold 集”的交叉表只用于人工校准差异检查。Gold 命中不是语义正确的替代真值；多 ID 标签也可能存在遗漏。人工抽查不改写 JEV 答案，不作为主评测者。

逐条基线与 JEV 原始结果、请求状态、confidence/probabilities、调用耗时及复算 JSON 写入 `.gitignore` 下的 `output/m14-task64/`，不提交原始运行输出。可复跑命令：

```powershell
python scripts/evaluate_ingredients.py baseline
python scripts/evaluate_ingredients.py probe
python scripts/evaluate_ingredients.py full
python scripts/evaluate_ingredients.py metrics
```

## JEV 真实运行状态

2026-09-23 已完成。主 Agent 确认 User-scope `OPENROUTER_API_KEY` 可用后，评测进程从 Windows User 环境读取 Key；未在输出、源码、报告或运行文件记录 Key。第一次沙箱网络探针在连接前被本机拒绝（WinError 10061），保留 1 条失败尝试记录；按授权提升该单一探针后，3 条 typed Choice 探针成功。确认真实 API 协议后，用同一冻结请求标准完成非兜底集合全量评测。

| 运行项 | 实测结果 |
|---|---|
| 请求模型 / 返回模型 | `typesafe/jev-1.13` / `typesafe/jev-1.13-20260917` |
| 返回 provider | `TypeSafe` |
| 成功 provider calls | 71（3 条探针 + 68 条全量新增请求；探针结果复用） |
| 初次网络失败尝试 | 1（连接未建立；无响应、无费用） |
| 全量查询项 | 71 条非兜底；1 条 fallback 不调用 JEV |
| Choice 分布 | reasonable 61；unreasonable 10；undecidable 0；成功调用失败 0 |
| JEV 主合理率 | 61 / 71 = **85.92%** |
| 固定集合理映射覆盖 | 61 / 72 = **84.72%** |
| 菜品全对率 | 14 / 24 = **58.33%**；排除含兜底的不可评菜品后 14 / 23 = **60.87%** |
| Gold Recall@5 | 均值 **97.22%**；至少命中一个 Gold ID 为 70 / 72 |
| 旧链路最终 ID 命中 Gold | 60 / 72 |
| API 费用 | **$0.001666014**（71 次成功响应 usage 汇总；不含连接前失败尝试） |
| Token | input 39,667；output 3,225 |
| 请求耗时 | p50 299.293 ms；p95 462.011 ms（nearest-rank，单条 Decisions 请求） |

完整 Choice 与 Gold ID 对照如下。每格是“JEV Choice × 最终 ID 是否在 Gold”的条数；fallback 没有 JEV 输出，不进入表格。

| JEV Choice | Gold ID 命中 | Gold ID 未命中 | 合计 |
|---|---:|---:|---:|
| reasonable | 57 | 4 | 61 |
| unreasonable | 3 | 7 | 10 |
| undecidable | 0 | 0 | 0 |

7 条二元标签差异均保留如下。`Gold hit` 仅描述最终 ID 是否属于冻结 Gold 集，不把它表述为 JEV 对错的权威真值。

| query_id | JEV Choice | confidence | Gold hit | 抽查说明 |
|---|---|---:|---|---|
| `d02-i01` | reasonable | 0.54 | false | Carp 映射到成品 `Carp Surprise`；JEV 选择和“成品不是原料对应物”的 Gold 说明不一致。 |
| `d03-i02` | reasonable | 0.57 | false | Button mushroom 映射到成品 `Fried Mushroom`；JEV 没有稳定排除成品条目。 |
| `d05-i02` | unreasonable | 0.51 | true | Wheat Flour 精确命中 Gold；JEV 的 choice 与目录英文名不一致。 |
| `d10-i01` | reasonable | 0.55 | false | Generic mushroom 映射到成品 `Fried Mushroom`；与 d03 的成品条目差异相同。 |
| `d13-i03` | unreasonable | 0.57 | true | Wheat Flour 精确命中 Gold；与 d05 同一 query 的判断一致。 |
| `d17-i02` | unreasonable | 0.70 | true | Wheat Flour 精确命中 Gold；与前两条 Wheat Flour 判断相同。 |
| `d19-i03` | reasonable | 0.69 | false | 中文“油”映射到 `Oil of Garlic`；这是同类烹饪油的可能合理替代，冻结 Gold 仅含 `Oil`，提示标签可能不完备。 |

JEV 的单次 confidence 是判断信号，不等同于该项正确概率；见 [OpenRouter 对 Jev confidence 的说明及其个体误判示例](https://openrouter.ai/blog/tutorials/jev-vs-llm-when-to-use-each/)。抽查确认：3 条协议探针中，西红柿→Tomato 与 cherry tomatoes→Cherry 符合当前标签预期；Carp→Carp Surprise 则有明显分歧且 confidence 为 0.54。全量交叉差异另显示成品蘑菇条目被判 reasonable，以及 Gold 命中的 Wheat Flour 被重复判 unreasonable。所有 JEV 原判和 Gold 标签保持原样；本轮没有根据结果调整 Query、标签或 rubric。后续报告任何比例只能描述这套固定策划 Query 上的机制评测，不能外推为真实用户问题比例或因果结论。
