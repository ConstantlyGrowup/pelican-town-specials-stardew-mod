# M14 Task 66.1｜96 菜独立扩样对照

- 合同：`m14-task66-1-expanded-ingredient-holdout-v1`
- 运行日期：2026-09-24 UTC
- 目标：在预先冻结的 96 道新菜 / 288 项原料上，比较实际 LEGACY 与显式 RAG 映射；主指标为固定 96 菜分母下的“每道菜三项原料均非兜底且均被 JEV 判为 reasonable”。
- 产品默认仍为 `LEGACY`。本报告不授权默认切换、产品调整、push、tag 或 Release。

## 冻结样本与输入

96 道菜均不同于 Task64 的菜名，每菜 3 项；四个预设检索难度层各 24 菜。菜系与菜品类型标签只用于描述，不增加硬门槛。该固定策划集不是随机用户流量样本。

| 校验项 | 冻结值 / 结果 |
|---|---|
| 新 fixture 工作树 SHA-256 | `1E9B49077589E8A9B9699DD4FC140359DF1A9A6389D75C7911ACE4A14D92A25C` |
| 新 fixture Git blob SHA | `7856d22f32a51de937cf6cf5f7cedf7a23aeff85` |
| Task64 fixture SHA-256 | `7B49E7B88393CCC627DD4AEC7545AC45FDAF4786081D2E9BCC973B202796EEB7` |
| 冻结目录 | `stardew-1.6.15-v1` · `4D07E9B3EE45670543C1BDCFFA69F84CC2FB2829C4DB4CF2BEFD273B36374E2B` |
| Task65 manifest / ONNX / tokenizer / vectors | `93E9AED32AA68DEC48D1C6E102C4F82FABDB916B84CD852E807F85BF3284DE85` / `739C8F25BBE6D8A6001CD2F048701DA9879140CC67D4E9327716111E869DD717` / `CFC8146ABE2A0488E9E2A0C56DE7952F7C11AB059ECA145A0A727AFCE0DB2865` / `D640532CBD3316EED3A6831939A7289858D492E025D3223ECCFA7D93D8D4EC58` |
| 菜品 / 原料项 | 96 / 288；全部 288 个 Gold ID 均在冻结目录中且 `usableAsIngredient=true` |
| 分层 | `direct_name` 24；`bilingual_or_synonym` 24；`ambiguous_name` 24；`raw_vs_prepared` 24 |
| Query / 旧集新颖度 | 142 个不同 normalized Query；112 个未见于 Task64，30 个曾出现 |
| 输入语言 | 英文 192；中文 96 |
| 描述性种类标签 | 40 个 dish family；21 种 cuisine/style |

在任何新链路运行前完成了 Gold 合法性校验和人工抽核：direct-name 层调整为约半数鱼类、半数蔬果/谷物/乳品等；“Beetroot and Goat Milk Bake”的羊奶 Gold 为 `436` / `438`；“Green-Tea and Melon Cooler”以现实饮料基底 `green tea` 对应 `614`；“Blackberry Cream-Cheese Tart”使用黑莓、奶酪与面粉的自然 savory/sweet tart 组合。所有 Query/Gold 在结果产生后保持原样。

**兜底口径：**45 个旧侧 catalog fallback occurrence 不表示游戏中不存在合理原料。每项 Gold 均预先通过冻结目录校验；这些 fallback 是 LEGACY 搜索未给出可用候选、随后映射到兜底条目的结果。兜底保留在主 96 菜分母，不能当作质量 KPI，也不能因此缩小分母。

## 执行完整性

| 运行 | 菜项 | mapped | fallback | mapping failure | RAG retrieval |
|---|---:|---:|---:|---:|---|
| LEGACY | 288 | 288 | 45 | 0 | 不适用 |
| 显式 RAG | 288 | 288 | 0 | 0 | success 288/288，degraded 0 |

LEGACY 候选来自生产 `_build_candidates(..., LEGACY)`；RAG 使用冻结 Task65 资源并显式选择生产 RAG seam，再由原 `map_ingredient()` 校验与选择。两侧均保存逐项候选、最终 ID、同菜已用 ID、兜底/失败/降级状态和耗时。普通权限下读取 Task65 资源在检索启动前被 Windows ACL 拒绝；随后只对冻结资源核验及本地 RAG 运行采用获准的最小提升权限，没有更改 ACL，也没有产生 RAG 原始结果覆盖。Task64 与已完成 Task66 的冻结输入、原始输出在运行前后 hash 一致；详细逐文件 hashes 记录于 ignored `output/m14-task66-1/manifest.json`。

### JEV 盲评

在两侧映射完成后先做 1 次授权版本探针，随后只对非兜底映射逐项使用原 typed `Choice` 协议。请求只发送菜名、现实语义原料、最终目录项 ID/中英文名与固定 rubric；不发送 Gold、方案标签、候选列表/分数或 API Key。完全相同 request state 复用其已完成判定。

- 返回模型 / provider：`typesafe/jev-1.13-20260917` / `TypeSafe`；311 次成功 provider calls（含 1 次 probe）、220 次 exact-state reuse、0 次 provider failure、0 次版本漂移。
- 45 个 `not_attempted` 均为旧侧 fallback；RAG 288 项与 LEGACY 243 个非兜底项全部获得同版已完成判定（含复用）。
- 总计 311/576 次授权上限。API usage 汇总费用 `$0.007338282`；该数值为响应 usage 累计，不等同独立账单核验。
- JEV raw response、request state/hash、来源/复用关系、usage、失败/未尝试状态保存在 ignored `jev.jsonl`；Key 未写入文件或日志。

### 新集主要结果

| 指标 | LEGACY | 显式 RAG |
|---|---:|---:|
| 菜品全部合理（固定 96 菜） | 41/96 · **42.71%** | 59/96 · **61.46%** |
| 非兜底、二元 JEV 判定合理 | 206/243 · 84.77% | 245/288 · 85.07% |
| 固定 288 项合理覆盖 | 206/288 · 71.53% | 245/288 · 85.07% |
| Gold Recall@5（按原料 occurrence 平均） | **79.60%** | **90.08%** |
| 至少命中一个 Gold 的 Top-5 项数 | 234/288 | 274/288 |
| 最终选择 ID 命中 Gold | 206/288 | 252/288 |
| 候选遗漏 / 命中后选择非 Gold | 54 / 30 | 14 / 22 |
| fallback / mapping failure / retrieval degraded | 45 / 0 / 0 | 0 / 0 / 0 |
| JEV reasonable / unreasonable / undecidable | 206 / 37 / 0 | 245 / 43 / 0 |

Legacy 的 Recall@5 从逐项传给 mapper 的 `mapper_candidate_ids` 计算；成功 RAG 检索使用实际 `rag_candidate_ids`，RAG 降级时使用传给 mapper 的实际 legacy 候选。该旧字段回归由 `test_side_metrics_keep_fixed_dish_denominator_and_use_mapper_candidates` 锁定，防止旧侧 Recall@5 被错误计成零。

两侧配对结果：**18 道改善、0 道退步、78 道持平**，差值 **+18.75 个百分点**。固定样本上的 exact McNemar 双侧 `p=0.0000076294`；按菜配对 bootstrap（10,000 次、seed `661001`）95% 差值区间为 **[+11.46, +27.08] 个百分点**。这是非随机策划集上的描述性有限样本统计，不解释成用户总体效果或因果证明。

| 预设层 | LEGACY 全合理 | RAG 全合理 | 改善 / 退步 |
|---|---:|---:|---:|
| `direct_name` | 20/24 | 21/24 | 1 / 0 |
| `bilingual_or_synonym` | 5/24 | 9/24 | 4 / 0 |
| `ambiguous_name` | 1/24 | 10/24 | 9 / 0 |
| `raw_vs_prepared` | 15/24 | 19/24 | 4 / 0 |

同一 JEV 返回版本、目录与 rubric 满足可比条件，因此历史 24 菜可附列：Task64 LEGACY 14/24、Task66 RAG 18/24；新 96 菜仍单独作为本轮主结果。两组简单累计为 LEGACY 55/120、RAG 77/120（仅作补充，不以累计掩盖新集方向）。

### Fallback 敏感性（事后描述，不替代主指标）

45 个旧侧 fallback occurrence 分布在 **38/96 道菜**；RAG 侧无 fallback。18 道改善中，**13 道**旧侧含至少一个 fallback，RAG 三项均非兜底且三项均 reasonable；另外 **5 道**旧侧无 fallback、但有 JEV 不合理项，RAG 三项均 reasonable。按“两侧都无 fallback”事后限制得到 58 道菜：LEGACY **41/58**、RAG **46/58**，配对 5 改善 / 0 退步 / 53 持平。此子集依赖观察到的旧侧 fallback，属于 post-hoc 敏感性拆分，不能取代固定 96 菜的主结果。

### JEV 与 Gold 的交叉核对

下表只统计完成的二元 JEV 判定；Gold 命中仅是与冻结标签的对照，不把它当作 JEV 正误的权威真值，也不覆盖所有 Gold 可能不完备的情况。

旧侧最终 ID 命中 Gold 的 206 项中有 2 项是 fallback 项：它们计入全 288 项的 Gold 最终选择统计，但没有对应 JEV 判定；因此下表仅 completed 判定命中数合计 204，不与 206/288 的全项指标冲突。

| 方案 | JEV 判断 | Gold 命中 | Gold 未命中 | 合计 |
|---|---|---:|---:|---:|
| LEGACY | reasonable | 192 | 14 | 206 |
| LEGACY | unreasonable | 12 | 25 | 37 |
| RAG | reasonable | 237 | 8 | 245 |
| RAG | unreasonable | 15 | 28 | 43 |

二元 JEV/Gold 状态不同的 occurrence：LEGACY **26**，RAG **23**。具体 query、最终 ID、Gold membership 与 JEV confidence 均在 ignored `metrics.json` 的逐项表中，原判和 Gold 未作事后修改。

### 游戏翻译歧义的事后修正分析（2026-09-24 用户确认）

用户核对游戏目录后确认：物品 `246` 的英文原名为 `Wheat Flour`，目录中的中文显示名却是 `大麦粉`（来自 `Objects.zh-CN.json` 的 `WheatFlour_Name`）。对于现实语义原料 `Wheat Flour` / `小麦粉`，只要最终选择了非兜底的物品 `246`，即视为已定位到游戏原版小麦粉；中文显示名不应使其在原料准确率评测中被判否。这是对目录翻译歧义的人工裁决，不是 JEV 提供的理由，也不修改产品目录或映射链路。

在**已冻结的同一 96 菜**上，对 LEGACY 和 RAG 应用完全相同的事后规则：仅将上述语义原料→非兜底 `246` 且原 JEV 为 `unreasonable` 的记录改计为合理；其他 JEV 判定、Gold、兜底及固定分母不变。旧侧命中该条件 **12 项**，新侧 **15 项**；这些均为 JEV 判否但命中 Gold 的 `246` 记录。复算结果如下：

| 96 菜全部原料合理口径 | LEGACY | 显式 RAG | 配对改善 / 退步 / 持平 |
|---|---:|---:|---:|
| 原始冻结 JEV 主指标 | 41/96 · 42.71% | 59/96 · 61.46% | 18 / 0 / 78 |
| **事后翻译歧义修正** | **48/96 · 50.00%** | **71/96 · 73.96%** | **23 / 0 / 73** |

修正后同集差值为 **+23/96（+23.96 个百分点）**。修正发生在观察结果之后，因此只能作为**事后分析**并与原始主指标并列，不能回写冻结 `metrics.json`、`jev.jsonl`、Query/Gold 或声称它是预先规定的盲评结果。旧 24 菜的原始 14/24→18/24 仍单列，未在此重新裁决，也不合并成“修正后的 120 菜”指标。两组样本都是策划题集，不能推断真实用户总体效果；产品默认仍为 LEGACY。

### Query 构成与耗时

新集 288 次原料出现中共有 142 个 distinct normalized Query，47 个 Query 在新集中重复，首个 occurrence 之后另有 146 次重复出现；其中 30 个 distinct Query 曾见于 Task64。分层构成如下：

分层的 distinct/repeat 值按层内统计；同一 normalized Query 可跨层出现，因此各层 distinct 数及 repeat 数不能直接相加成全局值。

| 层 | distinct Query | 未见于 Task64 | occurrence 重复数（超过首次） |
|---|---:|---:|---:|
| `direct_name` | 50 | 33 | 22 |
| `bilingual_or_synonym` | 52 | 41 | 20 |
| `ambiguous_name` | 53 | 40 | 19 |
| `raw_vs_prepared` | 47 | 21 | 25 |

单进程每项 `total_elapsed_ms`（候选检索/构建 + mapper；按 nearest-rank）：

| 方案 | p50 | p95 | max |
|---|---:|---:|---:|
| LEGACY | 1.089 ms | 1.387 ms | 3.005 ms |
| RAG | 6.503 ms | 9.095 ms | 1632.052 ms |

RAG 最大值包含首次 lazy model/index 加载；本次是 host-Python 单进程测量，不是 packaged EXE 冷启动、20 次 RAM 测试或新增包体验证。Task65 的资源门槛仍引用 [Task65 冻结实测](M14_TASK65_INGREDIENT_RAG_IMPLEMENTATION.md)，本任务未重测这些资源，也未因结果调 K、候选排序、mapper 或查询集。

## 原始产物与可复核性

以下原始 JSONL、manifest 与 metrics 均位于 Git ignored 的 `output/m14-task66-1/`，不提交。SHA-256：

| 文件 | SHA-256 |
|---|---|
| `freeze_manifest.json` | `4F9460198029AB630BA818ABC7FA38C6352F52B2243B1BF21AA2F7B754970C27` |
| `manifest.json` | `9E076F9175FF4C27458003893A890B5EC59401B0D096E1D65A9EE29282579E16` |
| `legacy_results.jsonl` | `21FBC96EFE5CF32766028C9F1930980337C5A8BBC76F0B5C921CCFD8E650BE44` |
| `rag_results.jsonl` | `340E127A01DEF015F9BF6370932CBB93A8BCEAF0FC209803891ED5F266415118` |
| `jev.jsonl` | `78DF56A1C0829F88EA2B13301EC33AEBA47DB9CAE466B058CA0D954F73BCADF4` |
| `metrics.json` | `5922CC249754B1DB8DAA8D53ABF1D60146AF2C4DBBA28444B4243247072C4CB2` |

Task64/66 历史文件的逐文件 SHA 在运行 manifest 中保存，并在两侧执行和 metrics 复算时重核；没有覆盖或修改旧输入/结果。产品代码、catalog、默认 selector、API/UI/schema 与 fixture/Gold 均未因结果变化。

## 验证记录

- `python -m pytest backend/tests/tools/test_m14_ingredient_holdout.py backend/tests/tools/test_m14_ingredient_comparison.py -q -p no:cacheprovider --basetemp output/m14-task66-1/pytest-focused`：**19 passed**。覆盖冻结样本校验、盲化请求、exact-state 复用、版本漂移停止、固定菜品分母与 Recall@5、LEGACY/RAG 实际候选来源。
- `python -m ruff check scripts/evaluate_ingredient_holdout.py backend/tests/tools/test_m14_ingredient_holdout.py`：通过。
- `python -m py_compile scripts/evaluate_ingredient_holdout.py backend/tests/tools/test_m14_ingredient_holdout.py`：通过。
- `python scripts/evaluate_ingredient_holdout.py validate-fixture`：通过，复核 96/288、四层各 24、142 个 distinct normalized Query、Task64 未见 112 个、中英 192/96、288 个 Gold ID 均可用。
- `git diff --check`：退出码 0；Git 仅提示 `.gitattributes` 与主 Agent 所有的 `STATUS.md` 将在后续 Git 写入时做 LF→CRLF 转换，没有 whitespace error。
- 完成后再次核对 fixture SHA、Git blob SHA 与全部六个 ignored 结果/manifest SHA，均与上表冻结值一致；以上验证不运行映射、不请求 JEV，也未改写原始结果。
