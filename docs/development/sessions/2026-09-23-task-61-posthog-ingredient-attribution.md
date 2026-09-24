# Session｜Task 61 PostHog 原料问题指标与三看板联动

| 字段 | 值 |
|---|---|
| session_id | `2026-09-23-task-61-posthog-ingredient-attribution` |
| status | `auto_accepted` |
| session_type | `implementation` |
| owner | Codex 主 Agent |
| started_at | `2026-09-23` |
| base_commit | `21905b2` |
| acceptance_contract_id | `m14-task61-v1.3` |
| revise_round | `0` |
| planning_status | `READY_FOR_IMPLEMENTATION` |

局部生成器交付使用子合同 `m14-task61-fixture-v1`（最终 `revise_round=1`），范围仅 `scripts/telemetry/m14_seeded_events.py` 与 `backend/tests/tools/test_m14_seeded_events.py`，继承本 Session 的 R61-01..03、C61-01/C61-02 和隐私/数据完整性边界。该子合同不替代 Task 61 总合同 `m14-task61-v1.3`；worker handoff 已确认 `implementation_scope_delta: none`，独立 detector 首轮 REVISE、修复轮 PASS。

## 目标与用户可见合同

在已核对的 PostHog US Cloud 项目 `583351` 中，用一批可复算、无个人信息的预置事件驱动三张现有看板的数据联动变化：User volume `2045232`、Core usage `2045233`、Quality and canonical memory `2045234`。Core usage 为重点更新指标/图表的看板；另外两张保留结构但验证数值随同一事件流变化。不删除项目、原始事件库、其他看板或既有事件。

预置事件在底层以 `pts_data_origin=m14_seeded_v1` 标识，开发记录保留构造方法；看板不放永久来源说明。后续真实事件仍进入同一项目/看板，真实使用归因与预置演示数据必须按来源/时间分开计算。用户已提供“原料定位不准”的调研结论，但现有事件无原料质量或成功草稿放弃字段；不得把预置数据说成真实用户行为或原料错误的因果证明。

## 可实施性闭包

- PostHog 组织 `Pelicant new dish`、项目 `Starvalley Cook`/`583351`、三张看板 ID 和管理权限已只读确认。
- 现有事件为 `app opened`、`generation started`、`generation finished`、`dish archived`、`menu export finished`；字段从项目事件 Schema 与本地 `domain/telemetry.py` 核对。最近 30 天旧看板有 19 次 generation finished（11 成功、6 失败、2 取消），成功→存档漏斗因仅 1 个安装而显示 100%，不代表每次生成的接受率。
- PostHog 官方 Capture/Batch API 使用 US Cloud `https://us.i.posthog.com/batch/` 和项目公开 token；当前连接提供读写看板/Insight 工具，但不提供事件 capture 工具，故批量预置走已核对的公共采集端点。
- 当前工作树存在用户和前序规划修改，Task 61 不清理、覆盖或纳入无关文件。

## Planning rulings

| ID | 冲突 | 依据 | 裁决 | user_visible_delta |
|---|---|---|---|---|
| R61-01 | M14 v1.2 要求预置数据不区分来源并按真实使用基线消费，与用户后续确认相冲突 | 用户本轮确认；M14 v1.3 §1/§3 | 后续用户确认优先：底层逐条标源，开发记录留方法，看板无永久说明，分析按来源分开；旧 v1.2 表述废止 | none |
| R61-02 | 用户先选仅替换 Core usage，随后澄清三看板数据联动 | 用户本轮最新澄清；PostHog 已有三张 Dashboard | 单批写入共用事件流使三张数据变化；Core usage 重点调整图表，其余结构保留 | none |
| R61-03 | 现有匿名事件无 draft ID/放弃原因，安装级漏斗不能直接说明原料问题 | M10 事件协议；PostHog Schema/现有看板核查 | 使用生成成功、安装级存档转化、重生成和试用行为作为问题定位旁证；直接原因来自已提供反馈，准确率效果交由 Task 64/66 | none |

## Architecture budget 与文件范围

允许：标准库确定性预置数据生成/校验、项目已有 PostHog 事件类型、仅限目标项目的 `/batch` 事件预置、已确认看板/Insight 的最小必要更新、Task 61 方法与控制文档。禁止：产品遥测 schema 或发布包改动、新服务、个人资料/图片/菜品文本/Provider/业务 ID 采集、伪造用户反馈事件、删除或覆盖原始事件、改变另两张 Dashboard 定义、模型调用或发布。

本地允许文件：

- `scripts/telemetry/m14_seeded_events.py`（创建；C61-01/C61-02）
- `backend/tests/tools/test_m14_seeded_events.py`（创建；C61-01/C61-02）
- `docs/development/sessions/2026-09-23-task-61-posthog-ingredient-attribution.md`（创建/追加；C61-03/C61-04/C61-05）
- `docs/development/M14_TASK61_METRIC_CONTRACT.md`（创建；C61-02/C61-04）
- `docs/development/STATUS.md`（更新状态；C61-05）
- `docs/development/CONSTRAINTS.md`、`AGENTS.md`、`docs/plans/2026-09-23-milestone-14-ingredient-rag-evaluation.md`、规划 Session（同步用户最新裁决；C61-05）

## Acceptance Ledger

| ID | 来源 | MUST 验收项 |
|---|---|---|
| C61-01 | 用户 10–15 人/最多 5 次试用要求；M14 v1.3 Task 61 | 确定性生成 12 个匿名安装的预置事件，每安装试用生成不超过 5 次，事件属性与现有 M10 枚举兼容、无敏感内容，三张看板所需事件均存在。 |
| C61-02 | 用户确认底层/开发记录保留来源 | 每条预置事件有同一来源标识；生成器可验证约束并复算；真实事件可按来源/时间与预置数据分开，Dashboard 无永久来源说明。 |
| C61-03 | 用户最新“三看板联动”要求 | 一批预置事件只写入项目 `583351` 一次；复查三张现有 Dashboard 数据均变化，并记录预置前后指标及数据窗口。 |
| C61-04 | 用户“寻找有解释性指标”；M10 事件协议 | Core usage 优先呈现成功生成后安装级存档转化等可解释指标；不得把安装级漏斗当作逐草稿弃用率或因果证明，不伪造缺失的放弃/原料原因埋点。 |
| C61-05 | 项目 Session/Review 协议 | 独立实施、验证与 Review；准确记录本地/远端改动、测试、限制；未获 Milestone 验收不 push/发布。 |

## out_of_scope 与测试

不做 Task 62–66、JEV/Embedding 调用、原料链路改造、真实用户反馈再收集、PostHog 项目/旧事件删除、另两张看板的结构替换。

预定验证：`python -m pytest backend/tests/tools/test_m14_seeded_events.py -q`；`python scripts/telemetry/m14_seeded_events.py --output <ignored output>`；PostHog `read-data-schema`、三张 `dashboard-insights-run` 与来源分组只读复查。具体执行证据在本 Session 后续追加。

## 执行与验证记录（2026-09-23）

- 实施子合同首轮独立 detector 为 `REVISE`：指出 41/42 对生成 `duration_ms` 与开始/结束时间差不一致、`retry_failed_stage` 可能跟在成功/取消后、CLI 测试使用固定路径。worker 仅在授权两文件中修复，第二轮封闭复审 `PASS`；detector 独立探针检查 42 对时长 mismatch=0、retry 状态转移有效，未发现新范围差异。
- 主 Agent 完整 focused pytest：`python -m pytest backend/tests/tools/test_m14_seeded_events.py -q -p no:cacheprovider --basetemp output/m14-task61/pytest-r1-20260923-c9` → `10 passed in 0.08s`。常规沙箱对 pytest 创建的临时目录返回 WinError 5，改在获准的本地执行环境复跑通过。
- 生成 `output/m14-task61/seeded_events.json`（Git ignored），103 条事件，SHA-256 `05C0385F7F755609F7CB8A772D73FF3D5ED55D94A8D7EFAEA70D53CAE83E7537`。12 个 UUIDv4 安装；12 `app opened`、42 `generation started`、42 `generation finished`、4 `dish archived`、3 `menu export finished`；每安装 2–5 个生成 attempt、最多 2 个 `trial_used=true`，全部事件有 `pts_data_origin=m14_seeded_v1`、关闭 person profile、固定 `$insert_id`。
- 仅一次 POST 至项目 `583351` 对应的 US Cloud `/batch/`，响应 HTTP 200 `{"status":"Ok"}`；没有重发。初次相同 SQL 文本命中旧/部分结果后，换新查询形状复核来源标记事件得到上述 12/42/42/4/3，总计 103，涉及 12 个安装。未删除旧事件。
- 三张原看板用 `force_blocking` 重新运行，均受同批事件影响。User volume：7 日活跃匿名安装 `0→12`、WAU `1→13`、MAU `1→13`。Core usage：生成开始 `19→61`；成功生成→归档安装级漏斗 `1/1=100% → 5/13=38.46%`，成功率当前合计 `55.7377%`，生成类型当前合计 initial 29/full_regenerate 18/retry_failed_stage 10/blueprint_preview 4。Quality and canonical memory：终态合计 succeeded 34/failed 13/cancelled 8/interrupted 6，较原 11/6/2/0 改变；记忆结果图亦随生成终态事件更新。
- Core usage 在原 insight `11443094`/tile `11489040` 上将 p50 时长图原位改为按 `generation_kind` 分组的生成类型图，保留 7 个 tile 和原 Dashboard ID；在原漏斗 insight `11443096` 上明确单位为安装且不作逐草稿/因果解释。User volume 与 Quality and canonical memory 的布局和 insight 定义未改。三张看板都没有加入预置来源说明。
- 来源/时间分区切点设为 `2026-09-23T02:50:48Z`（写入完成并复核之后；悉尼 `2026-09-23 12:50:48 +10:00`）。该时刻之前无来源标记的事件只列为历史未核实；该时刻之后且没有预置标记的事件才进入后续真实行为口径。看板默认合计仍包含预置事件，不得将其说成真实调研样本或原料不准的因果证明。
- Task 61 全范围独立 detector 在总合同 `m14-task61-v1.3`/round 0 判定 `PASS`，C61-01..05、R61-01..03 均通过，无 MUST_FIX、scope delta 或新设计。只读复核得到 103 个唯一 `$insert_id`、103/103 条 `schema_version=1` 和关闭 person profile；切点后 seeded=0、unmarked live=0，切点前无标记历史未核实事件=56；三看板图表/结构及无可见来源说明均确认。主 Agent 复核通过后进入 `auto_accepted`，按项目协议仅创建本地 focused commit；无 push、tag、Release 或 Task 62 工作。
- 实际运行时模型信息：主 Agent 未暴露可核实 model/effort；worker role 配置为 `gpt-5.6-luna/max`，实际运行时标识未暴露；detector role 为 `gpt-5.6-sol/medium`。
