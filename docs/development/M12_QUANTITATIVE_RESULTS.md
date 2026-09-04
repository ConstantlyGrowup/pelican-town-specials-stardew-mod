# Milestone 12 量化指标结果

更新时间：2026-09-04
范围：Task 50–55；当前源码基线为 Task 49 之后的工作树，Canonical 最终匹配阈值为 `0.85`，Top K 为 `5`。

用户已于 2026-09-04 完成 M12 整体验收并授权提交推送。

本文件随仓库保存；下文 `output/` 链接指向评测机器上保留的本地证据，按仓库规则不提交原始图片、Provider 输出或模型文件。远端阅读可直接使用本文完整指标、来源转录和计时边界。

这份文件是后续 follow/review 的稳定入口。可读版结论见 [`m12_final_summary.md`](../../output/evaluation-m12/m12_final_summary.md)，HTML 版见 [`m12_final_summary.html`](../../output/evaluation-m12/m12_final_summary.html)。

## 结论概览

| 指标 | 结果 | 口径 |
|---|---:|---|
| Ground Truth 已知同菜的最终命中成功率 | **59/60 = 98.33%** | Current 轻量召回；正例 Query 中最终选择正确 Canonical 的比例 |
| Current vs CPU Embedding 最终命中 | **59/60 = 98.33% vs 52/60 = 86.67%** | 同一 60 条正例、同一候选池、同一 `0.85` Matcher 门槛 |
| 平均单次召回耗时 | **0.2894648577 ms vs 14.3037390009 ms** | 700 次纯召回样本；Current 相对 baseline 减少 **97.9762993601%** |
| 700 次召回 + Embedding fresh-process 加载的组件重建值 | **0.2026254004 s vs 31.4756661005 s** | baseline 包含独立测得的 21.4630487999 s 加载；重建值相对减少 **99.3562474588%** |
| 20 组真实图片 E2E 人工通过率 | **19/20 = 95%** | 固定 20 组分母；19 个可审样本为 19/19 = 100% |
| 既有 Memory 优化：Token | **22.2471071295% 降低** | 用户提供的 A、D 完整配对 |
| 既有 Memory 优化：API 花费 | **10.3260869565% 降低** | 用户提供的 C、D、E、F 完整配对 |
| 既有 Memory 优化：整体耗时 | **30.4302203568% 降低** | 用户提供的 A、C、D、E、F 完整配对 |

## 1. 命中成功率

这里的“命中成功率”采用 Ground Truth 条件口径：在历史同一道菜身份已知的 Positive Query 中，只有当最终 `selected_id` 等于该 Query 的 `expected_canonical_id`，并且最终判定为命中时，才计为成功。

因此它回答的是“已知应该命中时，系统最终正确命中了多少”，不是线上自然流量的总体命中率，也不是所有新用户请求中会自然复用记忆的比例。

本轮 Current 轻量召回结果为 **59/60 = 98.33%**。唯一未命中为 Q036，最终置信度 `0.84`，低于固定阈值 `0.85`；这条结果没有因评测而改标签或调阈值。10 条 Negative Query 的误命中为 `0/10`，但样本量不足以证明线上误命中风险为零。

原始逐条结果：[`current_results.csv`](../../output/evaluation-m12/current_results.csv)；两侧统一汇总：[`retrieval_comparison.csv`](../../output/evaluation-m12/retrieval_comparison.csv) 和 [`retrieval_comparison.json`](../../output/evaluation-m12/retrieval_comparison.json)。

## 2. 召回策略对比

对照只改变召回器：Current 轻量字段评分与本地 CPU Embedding；两侧使用同一冻结候选池、同一批 Query、`zh-CN`、Top 5、`0.85` 最终 Matcher 门槛和同一 Matcher 配置。Task 52/53 的输入是已经冻结并核对过的结构化 DishAnalysis Query，因此这两项召回对照跳过 vision 分析；Task 54 才是使用真实照片和新分析 prompt 的 E2E。CPU Embedding 使用一个本地 multilingual MiniLM 模型，未进入生产包。

### 2.1 最终命中成功率

| 召回器 | 正例最终正确命中 | 最终命中成功率 | 正例进入 Top 5 |
|---|---:|---:|---:|
| Current 轻量方案 | 59/60 | **98.33%** | 60/60（100%） |
| 本地 CPU Embedding baseline | 52/60 | **86.67%** | 53/60（88.33%） |
| Current 相对 baseline | +7 条 | **+11.6666666667 个百分点** | +7 条 / +11.6666666667 个百分点 |

这是 30 条候选、60 条人工确认同菜正例和 10 条负例上的条件对照，不外推为大规模候选池或其他 Embedding 模型的结果。

### 2.2 整体批次时间口径

先区分两种时间：

| 时间项 | Current | CPU Embedding baseline | 是否是完整冷启动批次实测 |
|---|---:|---:|---|
| 从进程启动到 70 条 Query 全部结束 | **未记录** | **未记录** | 否，不能据现有文件恢复 |
| 700 次纯召回计时 | 0.2026254003867507 s | 10.012617300613783 s | 仅为召回组件实测 |
| fresh process 首次加载模型 | 无模型加载项 | 21.46304879989475 s | 单独的加载实测 |
| 700 次纯召回 + 一次模型加载的组件重建值 | 0.2026254003867507 s | 31.475666100508533 s | **重建值，不是完整冷启动实测** |

700 次是每侧 70 条 Query、每条重复计时 10 次的纯召回样本。baseline 的重建公式为：

```text
10.012617300613783 s（700 次 Embedding 召回）
+ 21.46304879989475 s（fresh process 模型加载）
= 31.475666100508533 s
```

以这组组件重建值计算，Current 相对 baseline 的时间减少为：

```text
(31.475666100508533 - 0.2026254003867507)
/ 31.475666100508533
= 99.3562474588%
```

该百分比不能标作“完整 70-query 冷启动批次节省”。本轮没有记录从 `0` 开始的完整批次墙钟时间，且上述组件计时没有包括候选编码、其他初始化、Registry 读取、Matcher、网络、模型下载或安装时间。因此，完整冷启动批次的实测减少率目前为“无记录”，组件重建值只用于说明已测到的本地召回和模型加载部分。

### 2.3 平均单次召回耗时

| 召回器 | 样本数 | 平均单次纯召回 | P50 | P95 |
|---|---:|---:|---:|---:|
| Current 轻量方案 | 700 | **0.2894648576953581 ms** | 0.2765499521046877 ms | 0.36895990488119407 ms |
| CPU Embedding baseline | 700 | **14.303739000876833 ms** | 12.835800007451326 ms | 24.605739972321306 ms |

按平均值计算：

```text
(14.303739000876833 - 0.2894648576953581)
/ 14.303739000876833
= 97.9762993601%
```

Current 的平均纯召回约为 baseline 的 `1/49.4144`，也就是约 49.4 倍快。该项包含 Embedding baseline 的每次 Query 编码；不包含 Matcher 和网络耗时。

### 2.4 本地资源与清理状态

Embedding 模型为 `paraphrase-multilingual-MiniLM-L12-v2`，revision 为 `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`，384 维，CPU 4 线程，最大 128 tokens。评测时记录到模型文件 `499557407` bytes（约 476.42 MiB），fresh-process 首次加载 21.4630487999 s，增量 RSS 755.828125 MiB。Current 的额外 RAM 没有单独测量，不能写成 0。

按用户授权，`output/evaluation-m12/model/` 中的 11 个模型文件已精确删除，共 `499557407` bytes；删除核验记录在 [`embedding_cleanup_manifest.json`](../../output/evaluation-m12/embedding_cleanup_manifest.json)。`embedding-resources/` 下的输入、资源和 provenance JSON，以及正式评测结果和复现脚本仍保留，用于审阅和追溯；没有卸载共享 Python 包。

## 3. 真实图片 E2E 人工通过率

Task 54 使用 20 张真实图片，走 production `create_app()` 和真实 asset/draft/generation API，使用 Task 49 后的新分析 prompt、`0.85` 阈值、Top 5、`gpt-5.6-luna` vision/text 与 `gpt-image-2` image 模型。20/20 例均执行并保留终态证据。

| 口径 | 分子 / 分母 | 比例 |
|---|---:|---:|
| 固定 20 组 E2E 人工通过率 | 19/20 | **95%** |
| 可审样本人工通过率 | 19/19 | **100%** |
| 完整生成终态 | 19/20 | 95% |

E2E-03 是真实的 `PTS_GEN_LOW_CONFIDENCE` 拒绝（分析置信度 0.28），没有可供人工审阅的生成物，因此保留在固定分母中，不把它伪装成一条人工失败样本，也没有重跑或替换图片。用户对其余 19 组逐组结果给出 ALL true。

证据：[`e2e_results.csv`](../../output/evaluation-m12/e2e_results.csv)、[`e2e-run/run.json`](../../output/evaluation-m12/e2e-run/run.json)、[`task54_e2e_review_report.md`](../../output/evaluation-m12/task54_e2e_review_report.md)。

## 4. 引入 Memory 前后的 Token、费用与耗时

### 4.1 数据来源与责任边界

下表原始 A–F 数据来自用户提供的截图 [`memory_savings_user_source.png`](../../output/evaluation-m12/memory_savings_user_source.png)，SHA-256 为 `256CF266E49336A42BD558C9F5DB29C7FAA02DA4E413C1EF444D61C24F582FF4`。结构化转录见 [`memory_savings_user_data.csv`](../../output/evaluation-m12/memory_savings_user_data.csv)。

这些原始耗时、Token 和金额不是我重新调用 Provider 测得的。本报告中的合计、均值和降幅，是根据你提供的原始表按完整配对样本重新整理计算的；本轮没有追加新的 Memory 节省实验。截图没有逐行标记 prompt/阈值版本，因此这些历史数据按你的要求作为既有 Memory 优化证据使用，不标记为本轮新 prompt/`0.85` 配置的专门实测。

### 4.2 用户原始数据转录

| 组 | 未命中耗时 | 命中耗时 | 未命中 API 花费 | 命中 API 花费 | 未命中 Token | 命中 Token |
|---|---:|---:|---:|---:|---:|---:|
| A | 267 s | 132 s | — | — | 12.926K | 9.828K |
| B | — | 121 s | — | $0.18 | — | — |
| C | 143 s | 117 s | $0.18 | $0.17 | — | — |
| D | 161 s | 139 s | $0.48 | $0.44 | 16.543K | 13.085K |
| E | 192 s | 156 s | $0.447 | $0.432 | — | — |
| F | 190 s | 119 s | $0.549 | $0.443 | — | — |

`B` 缺少未命中侧原始值，所以不补零，也不加入任何降幅分母。

### 4.3 配对汇总与公式

统一使用同一指标中完整配对样本的总量公式：

```text
降低百分比 = (未命中总量 - 命中总量) / 未命中总量 × 100%
```

| 指标 | 完整配对 | 未命中合计 / 均值 | 命中合计 / 均值 | 降低百分比 |
|---|---|---:|---:|---:|
| Token | A、D（n=2） | 29.469K / 14.7345K | 22.913K / 11.4565K | **22.2471071295%** |
| API 花费 | C、D、E、F（n=4） | $1.656 / $0.41400 | $1.485 / $0.37125 | **10.3260869565%** |
| 整体耗时 | A、C、D、E、F（n=5） | 953 s / 190.6 s | 663 s / 132.6 s | **30.4302203568%** |

这解释了“是你提供的，还是我自己计算的”：原始样本和数值由你提供；本报告的汇总比例由我依据这些数值和上面的公式计算，既不是新的实测，也不是从 API 调用次数反推出来的。

## 5. 证据索引与限制

| 证据 | 用途 |
|---|---|
| [`retrieval_comparison.csv`](../../output/evaluation-m12/retrieval_comparison.csv) | Current / CPU Embedding 召回、700 次计时和资源数值 |
| [`metrics_update_verification.json`](../../output/evaluation-m12/metrics_update_verification.json) | 本次 700 samples、模型加载及降幅的机器核对值 |
| [`current_results.csv`](../../output/evaluation-m12/current_results.csv) / [`baseline_results.csv`](../../output/evaluation-m12/baseline_results.csv) | 70 条 Query 的逐条最终结果 |
| [`e2e_results.csv`](../../output/evaluation-m12/e2e_results.csv) | 20 组 E2E 的 completed / human_pass |
| [`e2e-run/run.json`](../../output/evaluation-m12/e2e-run/run.json) | E2E 配置、模型、阈值、设置保护和批次终态 |
| [`memory_savings_user_source.png`](../../output/evaluation-m12/memory_savings_user_source.png) / [`memory_savings_user_data.csv`](../../output/evaluation-m12/memory_savings_user_data.csv) | 用户独立统计原始来源和结构化转录 |
| [`embedding_cleanup_manifest.json`](../../output/evaluation-m12/embedding_cleanup_manifest.json) | CPU Embedding 模型文件精确删除与 SHA-256 清单 |

所有召回结果都是小规模条件评测：30 条候选、60 条正例、10 条负例、20 组真实 E2E；Memory 节省数据的样本数按指标为 n=2、n=4、n=5。它们用于定位当前实现的行为和资源口径，不外推为线上总体命中率、大规模候选池性能或稳定节省率。完整冷启动批次耗时尚无实测记录；新 prompt/`0.85` 配置下的 Memory 节省百分比也没有另行测量。
