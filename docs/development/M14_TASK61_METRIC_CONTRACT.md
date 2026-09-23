# M14 Task 61｜PostHog 指标口径与来源分区

项目：PostHog US Cloud `583351`（`Australia/Sydney` 时区）。同一事件流驱动 User volume `2045232`、Core usage `2045233`、Quality and canonical memory `2045234` 三张现有看板。Core usage 是本 Task 指标改造重点。

## 证据边界

用户调研已给出“菜品原料定位不准”的反馈。这是问题假设的直接来源。PostHog 当前事件能观察使用路径，但没有原料质量、草稿 ID、成功草稿被放弃或放弃原因字段；因此无法凭当前埋点证明“原料不准导致放弃”。预置记录只用于验证看板口径与展示路径，不充当真实用户行为证据。真实原料准确率由 M14 Task 64/66 的冻结 Query 与 JEV 同集评测给出。

所有预置事件带 `pts_data_origin=m14_seeded_v1`；正式应用事件没有此标记。来源分区必须同时使用属性和时间：标记为预置的事件属预置；`2026-09-23T02:50:48Z` 前的无标记事件属历史未核实；该切点之后的无标记正式应用事件才可进入后续真实行为口径。指标复算至少提供预置、历史未核实、后续真实、合计四种口径。看板不放永久来源说明，因为后续真实事件会继续进入同一看板；分析和结果文档必须写清采用的来源口径。现有三张看板默认图表显示合计，不能直接解释为真实用户样本，且预置数据最终会随滚动时间窗自然退出。

## 指标定义

| 指标 | 分子/分母或查询 | 单位 | 可解释性与限制 |
|---|---|---|---|
| 活跃匿名安装 | 窗口内有 `app opened` 的唯一 `distinct_id` | 安装数，按日/周/月 | `distinct_id` 是随机安装 ID，不等于自然人。预置与真实要分区。 |
| 生成成功率 | `generation finished` 中 `outcome=succeeded` / 全部 `generation finished` | attempt 比例 | 说明技术链路是否成功，不代表结果被接受。 |
| 成功生成→存档转化 | 先有 `generation finished` 且 `outcome=succeeded`，14 天内同一匿名安装出现 `dish archived` 的安装数 / 出现成功生成的安装数 | 安装比例 | 最接近“结果使用意愿”的现有指标；**不是逐草稿接受率**，也不能单独归因于原料准确率。小样本同时报告人数分子/分母。 |
| 生成类型分布 | `generation started` 按 `generation_kind` 分组计数；重点关注 `full_regenerate`、`retry_failed_stage` | attempt 数/占比 | 重生成增多可能提示结果不满意，也可能是正常编辑或失败重试；只能作为辅助定位信号。 |
| 试用路径使用 | `generation started` 中 `trial_used=true` / 全部 `generation started` | attempt 比例 | 不等于额度消耗；失败不扣次规则保持。预置数据每安装 `trial_used=true` 的开始次数不超过 5。 |
| 终态与 Canonical | `generation finished` 按 `outcome`、`memory_outcome` 分组 | attempt 数 | Quality 看板保留其原目的，不把 Canonical 命中当作原料映射质量。 |

不建立“成功草稿被放弃率”“原料错误率”或“因原料不准取消率”的假指标；当前事件缺少计算所需的草稿关联或原因字段。后续若要直接测量，应作为独立埋点设计并经产品范围审阅。

## 复算与核验

预置前最近 30 日的现有事件为 5 次 `app opened`、19 次 `generation started`、19 次 `generation finished`（11 `succeeded`、6 `failed`、2 `cancelled`）、9 次 `dish archived`、4 次 `menu export finished`，均来自同一个安装；成功→存档安装级漏斗为 1/1，显示 100%。该值说明样本过小，不是高逐草稿接受率。

2026-09-23 单批写入后，来源标记分区为 12 次 `app opened`、42 次 `generation started`、42 次 `generation finished`、4 次 `dish archived`、3 次 `menu export finished`，共 103 条、12 个匿名安装。预置分区的成功→存档安装级转化为 4/12=33.33%；此前历史未核实安装为 1/1。原看板合计转化为 5/13=38.46%，不能报告成 13 位真实受访用户的行为或归因结论。User volume 的 DAU/WAU/MAU 刷新后分别为 12/13/13；Core usage 的成功率合计为 55.7377%；Quality 看板的终态合计 succeeded 34、failed 13、cancelled 8、interrupted 6。所有合计图默认混合来源，仅适合看板交互验证；正式分析须按上方来源分区复算。预置记录绝不能在“后续真实”分区出现。
