# M14 Task 67｜RAG 拒匹配可行性诊断

## 结论

在现有 Task65 固定本地 E5 模型、253 项目录向量和冻结正样本上，没有找到既拒绝 5/5 已观察无匹配样本、又保留正样本质量的通用本地判据。只按目录对象类型过滤成品料理可以改善一部分正样本，却不能阻止“鸡肉→蘑菇、豆腐→土豆”这类原料到原料的强行匹配；再加 cosine margin 拒识后虽可使 5/5 兜底，但正集全菜 Gold 命中从 94/120 降至 81/120。没有把该规则写入产品代码。

这说明当前 253 项索引的 E5 最近邻信号不能可靠区分“最接近的已有原料”和“确实能对应的原料”。如要继续，需由主 Agent 与用户决定是否接受保守拒识带来的正样本损失，或为新 Task 明确增加更可靠的本地语义证据（例如经审核的目录语义类别/拒识模型）；本诊断不擅自扩展现有合同。

## 输入与边界

- 负样本工作树 fixture SHA-256：`F50F02C6C847B7EFBF039128030784E8F08CBF582362A70661917A739B4303D8`。目录 SHA-256：`4D07E9B3EE45670543C1BDCFFA69F84CC2FB2829C4DB4CF2BEFD273B36374E2B`。
- 仅使用已观察的 5 条 seed（鸡肉、牛肉、羊肉、猪肉、豆腐）作为负样本；正样本为 Task64 24 菜/72 项及 Task66.1 96 菜/288 项。正样本 fixture SHA 分别为 `7B49E7B88393CCC627DD4AEC7545AC45FDAF4786081D2E9BCC973B202796EEB7` 与 `1E9B49077589E8A9B9699DD4FC140359DF1A9A6389D75C7911ACE4A14D92A25C`。正样本只按冻结 Gold ID 计算，不把 Gold 当作 JEV 语义真值。
- 资源为 `intfloat/multilingual-e5-small` 固定 revision `fd1525a9fd15316a2d503bf26ab031a61d056e98`；量化模型 SHA-256 `739C8F25BBE6D8A6001CD2F048701DA9879140CC67D4E9327716111E869DD717`，向量 SHA-256 `D640532CBD3316EED3A6831939A7289858D492E025D3223ECCFA7D93D8D4EC58`。
- 只读加载 `load_static_index` / `OnnxE5Encoder` 并通过 `StaticIngredientIndex.search` 检查真实 pinned cosine；正集使用冻结 fixture、`map_ingredient` 和相同菜内已用 ID 规则做本地模拟。没有写入冻结输入、历史输出或模型资源；没有 JEV、OpenRouter、其他远端调用。

## 判据实验

| 判据 | 5 条 seed | 正集逐项 Gold / 全菜 Gold | 结果 |
|---|---:|---:|---|
| 当前 RAG 基线 | 0/5 兜底；强行选择 ID `213, 240, 257, 213, 192` | 318/360；84/120 | seed 均误映射 |
| 绝对 top-1 cosine 阈值 | seed top-1 cosine 为 `0.8460–0.8639`；正集最低为 `0.7496` | 要高于 seed 最大值才能拒绝全部 seed；46 项无精确/词面候选的正样本也会被拒绝 | 分布重叠，绝对阈值会误拒正样本 |
| 无精确/词面命中时，若 cosine top-1 与 top-2 间隔 `≤0.0083` 则拒绝 | 5/5 兜底；seed 间隔 `0.00053, 0.00100, 0.00644, 0.00267, 0.00828` | 306/360；74/120；拒 28 项，其中 12 项原先命中 Gold | 能拒 seed，但正集明显退步 |
| 非精确候选排除 `type=Cooking` | 0/5 兜底；仍选 `281, 246, 257, 271, 192` | 330/360；94/120；0 项兜底 | 正集变好，但仍把负样本匹配到原料条目 |
| 排除 `Cooking`，并对无精确/词面命中的非 Cooking 向量 top-1/top-2 间隔 `≤0.013` 拒绝 | 5/5 兜底 | 314/360；81/120；34 项兜底 | 虽拒绝 seed，仍比 type-only 少 13 道全 Gold 菜，不能接受为当前默认规则 |

全菜 Gold 口径与人审简版报告中的事后修正 JEV 主指标不同：该报告的 RAG 为 92/120。此处单列 Gold 用于检查本地候选链路是否回归，不覆盖 JEV 结果，也不把它称为评测通过率。

另外试过给 query 增加中英文“ingredient/raw ingredient/recipe ingredient”语境，以及用同一 E5 临时编码双语候选名称复核 top-5。语境变体的正集 top-5 Gold 命中由原始查询模板的 349/360 降至 309–341/360；候选名分数未形成可拒绝 seed 且保留正例的分界。均未进入实现。

## 可复核命令与检查

模型分数实验由只读 PowerShell 内联 Python 探针运行，构造 `VanillaCatalog`、`load_static_index`、`OnnxE5Encoder`；余弦值直接取冻结 384 维向量 dot product，并按 top-1/top-2 计算 margin。fixture 哈希由以下命令复核：

```powershell
Get-FileHash tests/fixtures/m14_ingredient_no_match_queries.json -Algorithm SHA256
```

合同聚焦测试与静态检查：

```powershell
python -m pytest backend/tests/ingredient_rag backend/tests/catalog/test_mapping.py -q -p no:cacheprovider --basetemp output/m14-task67/pytest-worker-rag-abstention-escalated-20260924
python -m ruff check backend/src/pelican_town_specials/ingredient_rag backend/src/pelican_town_specials/generation/orchestrator.py backend/tests/ingredient_rag
git diff --check
```

pytest 在 sandbox 临时目录的默认 ACL 下初次报 5 个 `tmp_path` setup `WinError 5`，改用隔离工作区 basetemp 并经最小提升后 **43 passed**。Ruff **PASS**；diff check **PASS**（仅现存 LF/CRLF 提示）。没有新增或修改产品测试；没有测 Task67 规则的运行时延迟，因为没有可接受的规则进入实现。Task65/66 已报告的耗时不是本次拒识实验测量值。

## 样本可见性与状态

核对 fixture 哈希时误用 `Get-Content -TotalCount 80`，而该文件只有约 25 行，输出因此包含了全部 15 条 `unseen_challenge` 文本。此后未用这些文本调参或运行映射；该事实已报告主 Agent。故这 15 条不能由实施者声称为盲测；主 Agent 已表示会用另行新增的独立压力样本检验，不将原挑战集称作严格盲测。

本诊断未改生产源代码，未改负样本 fixture、目录或旧评测输出；未调用 JEV/OpenRouter、未提交、未推送。工作树中 `.gitattributes`、`STATUS.md`、Task67 Session 与 fixture 改动由主 Agent维护，未由本诊断覆盖。

## v2 实测与返工 round 1（主 Agent 追加）

用户授权增加本地语义核验后，v2 首轮实现引入目录语义家族与独立 no-match 分叉，并新增可复算 runner；尚未提交或切换默认。主 Agent 在代码冻结后用原 20 条负集独立运行：`15/20` 正确兜底，5 条仍强行映射（培根、明胶、酵母、gelatin、baking soda），`0` 基础设施故障。另构造并单列的 10 条压力样本仅 `4/10` 兜底，不把它冒充预注册集。正集为 `318/360` 项 Gold、`84/120` 道全 Gold、`346/360` Recall@5，和未修复显式 RAG 相同；这些是 Gold 而不是新的 JEV 合理率。独立 detector 按 v2 冻结合同返回 `REVISE`（`C67v2-01` 未过）。逐项原始输出分别在 ignored `output/m14-task67-full-v2/` 和 `output/m14-task67-pressure-v2/`。

返工 round 1 只做本地原型，未接入产品：尝试 MIT 许可的 [multilingual MiniLMv2-L6 NLI](https://huggingface.co/MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli)，固定 revision `0a71e92a985b6e1ad1828cf67ce9c459639c1dca`。量化 ONNX `107,333,572` 字节，SHA-256 `308D357A08D35A5309D9B9DEF494A0CCB56F0207F5BA1F979A130DC2F45037B3`，可复用现有 SentencePiece/ONNX Runtime；单对热推理中位数约 `3.1 ms`，5 候选双向约 `23–29 ms`。在固定 20 负例与 120 菜正例上扫描中英模板及前/反向分数：不降低正集 Gold 的设定仍只有 `15/20` 负例兜底；例如 `17/20` 时正集已跌到 `226/360` 项、`21/120` 道（English forward 0.15），或 `246/360` 项、`40/120` 道（Chinese reverse 0.30）；达到 `20/20` 则只剩 `37/360` 或 `58/360` 项，`0/120` 道全 Gold。因此不采用该模型。详细逐项/阈值结果在 ignored `output/task67-v2-nli-prototype/nli-full.json`，SHA-256 `3F50B9201554B70A7D8BE92D37A8CC6644FD9B91FE788489E2A7E27EB698E9B2`；压力集未用于模型调参。

截至此记录，Task67 尚未满足“明确无对应物应拒匹配”的验收门槛；新增真实 JEV、推送、默认切换及发布均未执行。下一步需要用户选择是否允许使用应用现有文本 LLM 对 RAG 候选及“无匹配”按菜批量核验（会增加一次请求/费用与延迟），或继续承担更大本地模型的不确定性，或暂停。不能把当前部分改进记为已完成修复。

## v3 按菜文本核验试点（主 Agent 追加）

用户随后允许评估现有个人文本 Provider 的 Top5＋无匹配方案，并单独授权固定 10 菜＋5 负例、最多 15 次真实请求。实施者只新增离线 runner 与 fake Gateway 测试；独立 detector 对 `C67v3-01..04` 返回 PASS。请求只含菜名、现实原料、每项候选 ID/中英名及 `null`，不含 Gold、分数、目录类别、方案标签、用户上下文或密钥；不使用公共试用/JEV，自动重试与结构化修复均关闭。产品链路未接入该核验器。

一次真实试点使用个人文本模型 `gpt-5.6-terra`，共 **15 次物理请求**、无重试，耗时 **121.4 秒**；单请求中位 **4.55 秒**、p95 **27.34 秒**。5 条原先被 v2 强配的无对应物（`n13/n14/n15/n19/n20`）全部选择无匹配并进入 catalog fallback，即 **0/5→5/5**。固定 10 道正菜全部 Gold 为 v2 **9/10**、本试点 **9/10**；逐项 Gold 为 v2 **29/30**、本试点 **27/30**。本试点有一道菜的模型返回通过 HTTP 200，但评分时触发 `duplicate_final_item_id`，该菜的 3 项均按无效计入分母；不是 Provider 网络故障，也不得把它当作三项语义判断错误。其余 9 道均全部命中 Gold。正菜样本只有 10 道且按诊断目的预选，不能推断 120 菜整体效果；负例也是刻意选择 v2 未拒识的 5 条。

原始可复算文件保存在 ignored `output/m14-task67-v3-pilot-20260924/`，`manifest.json` SHA-256 为 `AB7F1DE9C427F6FF9AEED4A3B2277DB1303A0D7EE526CB8CFCDF74F20522B6AD`，其中固定输入与输出各文件 hash、请求数、模型及分母均有记录。`summary.json` SHA-256 为 `5D66D5080DC819A57115D53716B841C2B9B47E13AA8FC24B52952F01E7142C19`。此次授权的 15 次请求已全部使用，不重跑异常菜。试点后只对离线评分器修复同菜去重次序：先保留所有明确选定的 ID，再为 `null` 分配目录兜底；新增测试覆盖该冲突，15 项聚焦测试与独立 detector 复审 PASS。修复没有追改历史试点结果或重新请求模型。v3 结果支持继续研究“文本核验能否拒识”，但**不等于 Task67 链路修复完成**：现有产品显式 RAG 仍只有 15/20 冻结负例兜底，完整 120 菜/20 负例同集文本核验、JEV 质量与生产接入均未执行，也未获这轮调用授权。下一步需单独决定是否扩大付费试验；在此之前不提交未验收产品改动、不切默认或推送。

## v4 全量个人文本 Provider 验证（主 Agent 追加）

用户进一步授权剩余 110 菜＋15 负例全量试验。原 15 例不重发；新增 runner 对 125 个 case 逐例单请求、先建排他占位目录、关闭重试/修复。首轮 15 与本轮 125 共 **140 个不同 case／140 次物理请求**，覆盖固定 **120 菜／360 项正常原料＋20 条无对应物**。所有本地结果 hash 和冻结输入 hash 均经只读复核；2 次 Provider 超时、首轮 1 道评分无效菜仍留在分母，没有重试。当前仅为个人文本模型 `gpt-5.6-terra` 的选择结果，**没有新增 JEV 判定或服务商账单核验**。

| 固定指标 | 本地 v2 RAG | 加按菜文本核验 | 变化 |
|---|---:|---:|---:|
| 全菜 Gold（120 菜每项均命中才通过） | 84/120 | **94/120** | +10 道；配对改善 12、退步 2、持平 106 |
| 单原料 Gold | 318/360 | **327/360** | +9 项 |
| 无对应物正确进入 catalog fallback | 15/20 | **20/20** | +5 条 |

两条配对退步是 `h66-ambiguous_name-01` 的 `berries` 与 `h66-ambiguous_name-05` 的 `root vegetables`：本地 RAG 命中冻结 Gold，文本核验却选择 `null` 进入兜底；它们是实际的过度拒匹配，不能用净提升掩盖。用户已看到 `12` 改善／`2` 退步的取舍，并明确接受在**仅显式启用 RAG** 的链路接入核验；LEGACY 默认不变。主 Agent 的事前门槛为全菜 ≥84/120、单项 ≥318/360、负例 ≥15/20，本轮均通过；这不等于零回归，也不代表 JEV“全部原料合理率”已复测。

140 次调用耗时中位 **8.32 秒**、p95 **50.48 秒**，算术平均约 **17.01 秒**，最大约 **120.08 秒**（超时）；这是新增核验步骤的测量，不含本地 E5、其他生成阶段或图片调用。费用与 token 使用量未从服务商账单核验，不能称为具体成本。首轮产物在 ignored `output/m14-task67-v3-pilot-20260924/`，其余 125 个独立产物在 ignored `output/m14-task67-v4-remaining-20260924/`。v4 离线执行器经 `20 passed`、Ruff/py_compile、独立 detector 封闭复审 PASS；结果聚合另由只读 detector 对 `C67v4-03/04` 复核 PASS。下一步是冻结并实施仅显式 RAG 的产品接入与失败回退，不追改历史评测或默认开关；新 JEV、push/tag/Release 均需另行授权。

## v5 仅显式 RAG 的产品接入（待用户验收）

用户接受上述 12 道改善／2 道退步后，已授权把按菜文本核验接入**内部显式启用**的 RAG Ask Gus 映射。实现每道菜最多一次、使用当前 attempt 的同一 Provider；请求仅含可用菜名、现实原料和每项 Top5 的目录 ID/中英名及无匹配选项。非法回复或 Provider 故障时整道菜沿用 v2 本地 RAG；明确无匹配则走目录兜底，不以词法匹配强行替代。默认 LEGACY 不发该请求，也未新增 UI/API/设置。

实施者的新测试 `13 passed`、相关回归 `140 passed`，Ruff、mypy（23 source files）和 diff check 通过；独立只读 detector 对 v5 冻结合同返回 PASS，并独立复跑 Provider 6 项及静态检查。detector 的生成侧复跑受到本机 pytest 临时目录 `WinError 5` 阻碍，故不能称它独立复跑了全部 140 项。接入阶段**未做真实产品路径 Provider 调用或新的 JEV 判定**；v4 离线效果不能直接宣称为产品线上准确率，尤其离线 fixture 给了双语菜名，而生产只提供当前可用的单语菜名。完整交接和限制见 Task67 Session。默认 LEGACY、未提交/推送、未发布，等待用户验收。
