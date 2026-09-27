# Session｜JEV 评测视频本地网页

| 字段 | 值 |
|---|---|
| session_id | `2026-09-25-temp-jev-video-web` |
| status | `committed` |
| session_type | `implementation` |
| owner | Codex 主 Agent |
| base_commit | `4919b3e` |
| acceptance_contract_id | `temp-jev-video-web-v1` |
| revise_round | `1` |
| planning_status | `READY_FOR_IMPLEMENTATION` |

## Context Packet

```yaml
task_id: TEMP-JEV-VIDEO-01
base_commit: 4919b3e
planning_status: READY_FOR_IMPLEMENTATION
acceptance_contract_id: temp-jev-video-web-v1
revise_round: 0
objective: 在 temp-for评测视频 目录实现可点击开始、实时展示过程并可复算结果的本地 JEV 文本评测网页。
user_visible_contract: 页面准确区分参考答案、JEV 选择和是否判对；显示真实运行时间、费用完整性和结果；可停止与导出；浏览器刷新不重复计费。
planning_rulings:
  - conflict: 现有 Gold ID 只标可接受映射，非 Gold ID 不能自动作为语义负例。
    sources: [TASK_PLAN.md 第 3 节, M14 人审报告]
    decision: 只把已核对的明显不相关目录对应物标为负例；数据 manifest 显示负例构造方式和难度界限。
    rationale: 避免把不完整 Gold 当成 JEV 错误。
    user_visible_delta: none
  - conflict: TASK_PLAN.md 记录的发布 Session 已结束且 v1.5.7 已正式发布。
    sources: [STATUS.md, 2026-09-24-v1-5-7-release Session]
    decision: 本任务独立实施，不修改发布控制面与产品代码。
    rationale: 当前已无修改型活动 Session。
    user_visible_delta: none
contract_delta:
  documents: [本 Session, docs/development/STATUS.md, temp-for评测视频/README.md]
  domain: []
  persistence: [temp-for评测视频/data, temp-for评测视频/runs]
  application_api: [本地独立 FastAPI 网页与运行接口]
architecture_budget:
  allowed: [本地 FastAPI、静态 HTML/CSS/JS、线程池并发、既有 JEV typed Choice 协议、JSONL 持久记录]
  forbidden: [修改产品主链路、改写旧评测输出、接入公网服务、预制结果冒充真实 API、未经授权主动调用付费 API]
allowed_files:
  - path: temp-for评测视频/prepare_cases.py
    action: create
    reason: 冻结正负样本与清单
    criterion_ids: [JV-01, JV-02]
  - path: temp-for评测视频/server.py
    action: create
    reason: 本地运行、计时、结果、进度和导出
    criterion_ids: [JV-01, JV-03, JV-05]
  - path: temp-for评测视频/static/
    action: create
    reason: 可视化桌面网页
    criterion_ids: [JV-04, JV-05]
  - path: temp-for评测视频/README.md
    action: create
    reason: 本地启动与视频录制步骤
    criterion_ids: [JV-04, JV-06]
  - path: temp-for评测视频/tests/
    action: create
    reason: 验证评分、负例标签和一次性请求边界
    criterion_ids: [JV-01, JV-02, JV-03, JV-05]
  - path: docs/development/STATUS.md
    action: modify
    reason: 唯一活动 Session 与后续状态
    criterion_ids: [JV-06]
  - path: docs/development/sessions/2026-09-25-temp-jev-video-web.md
    action: create
    reason: 接受合同与独立复审记录
    criterion_ids: [JV-06]
acceptance_ledger:
  - criterion_id: JV-01
    source: 用户本轮请求及 TASK_PLAN.md
    requirement: JEV 选择与事前冻结的语义标签同集计分；无效、无法判断、失败留在全集分母；请求字段不含标签。
  - criterion_id: JV-02
    source: TASK_PLAN.md 第 3 节
    requirement: 固定 120 菜/360 项正例及经明确语义规则核对的负例；处理 Wheat Flour 翻译并公开负例难度界限；输入与目录 hash 可复算。
  - criterion_id: JV-03
    source: 用户要求展示并发与速度及 TASK_PLAN.md 第 4 节
    requirement: 并发 1/8 可选择，同集实测无结果复用；总耗时、单项耗时、吞吐、usage.cost 与费用覆盖可查看；无真实请求时不展示假成绩。
  - criterion_id: JV-04
    source: 用户强调视频网页可读性
    requirement: 一键开始、清晰进度和表格；区分“不合理”判定与“判错”；桌面录屏可读，并可筛选、分页、查看详情与总结。
  - criterion_id: JV-05
    source: TASK_PLAN.md 第 5 至 8 节
    requirement: 重复点击与刷新不重复请求，停止派发，持久记录与导出可复算；API Key 不进入浏览器；不调用真实 API 做开发验证。
  - criterion_id: JV-06
    source: 用户限定临时目录与 AGENTS.md
    requirement: 产品实现仅放临时目录，现有仓库代码及历史输出不改；复核与控制面状态完整。
out_of_scope: [Git push, Release, 产品 UI/API 修改, 录制视频成片, 付费 JEV 实跑]
test_commands: [python -m pytest temp-for评测视频/tests -q, python -m ruff check temp-for评测视频, git diff --check]
```

## 网页与服务端数据合同

- `GET /api/bootstrap` 返回 `dataset`（`dish_count`, `ingredient_count`, `case_count`, `positive_count`, `negative_count`, `unique_state_count`, `sha256`, `label_status`）、`model`、`api_key_available`、`active_run_id`。
- `POST /api/runs` 输入 `{concurrency:1|8, confirm:true}`，输出 `{run_id}`。仅一个活动真实 run；重复提交复用活动 run。
- `GET /api/runs/{run_id}` 返回全量快照：`run_id`, `status`, `concurrency`, `elapsed_ms`, `metrics`, `rows`, `started_at`, `finished_at`, `mode`。`rows` 带 `case_id`, `dish_zh`, `dish_en`, `ingredient`, `item_en`, `item_zh`, `item_id`, `gold_choice`, `gold_reason`, `decision`, `status`, `correct`, `latency_ms`, `confidence`。
- `GET /api/runs/{run_id}/events` SSE 快照流；`POST /api/runs/{run_id}/stop` 停止派发；`GET /api/runs/{run_id}/export` 导出持久 JSON。
- `metrics` 至少含 `total`, `done`, `valid`, `correct`, `positive_total`, `positive_correct`, `negative_total`, `negative_correct`, `undecidable`, `failed`, `cost_usd`, `cost_reported`, `cost_missing`, `throughput`。

指定 `luna_worker` 仅负责 `temp-for评测视频/static/index.html`、`app.js`、`styles.css`；主 Agent 负责准备数据、服务端、测试、README、Session/STATUS。worker 与主 Agent 共享目录，不得回退他人编辑。完成后交独立只读 `detector` 按 Ledger 复核。真实 JEV 请求只由后续用户在本地网页主动触发。

## 独立复核 round 0

实施者静态三件文件已交接；主 Agent 完成数据、服务、测试与 README。冻结样本为 720 条（正负各 360、唯一输入 720），主 Agent fake pytest `6 passed`、Ruff、Node 语法、diff check 通过；Chrome 本地 1920×1080 截图确认首屏控件、指标与表格区域可见。未点击开始或发真实 JEV 请求。

独立只读 `detector` 对 `JV-01..06` 返回 `REVISE`，仅 `JV-03` 一项 MUST_FIX：对照区使用请求模型通用名，可能把实际模型版本不同或混用的串行/并发结果称为“同模型”。最小修复：只在两轮各有一个相同的 `actual_models` 版本时计算加速比；缺失、混用或不同版本隐藏并说明。此项冻结合同不变，进入 revise round 1，仅修 `static/app.js` 并做定向复核。

## 独立复核 round 1 与交付状态

指定实施子代理仅修 `static/app.js`：历史记录保存服务端 `actual_models`；只有同一数据集下两轮各报告唯一且相同的实际模型版本，才显示串行/并发加速比。缺失、混用或不同版本时隐藏对照并解释，不回退请求模型名或旧缓存。独立只读 `detector` 按同一合同对 `JV-03`、`JV-05` 返回 `PASS`，无 MUST_FIX、范围增量或新设计；`node --check` 与 `git diff --check` 通过。

主 Agent 核对本地服务 `GET /api/bootstrap`：120 道菜、360 项原料、720 个固定题，正负各 360，数据 SHA-256 为 `5D847F6EF7593AC9BB4C953DFD4C9D766784B29F1FD76114A4B16B289EFC8A1E`，当前无运行记录。fake 测试 `6 passed`，Ruff、Node 语法、数据重生一致性及 1920×1080 本地页面截图检查均通过。未点击开始、未发送任何真实 JEV 请求，也未产生真实准确率、耗时或费用结果。

产品代码与历史评测产物未改。负例为明确跨类别的易例，不代表真实困难负例分布；一轮会产生最多 720 个计费请求，串行与并发各一轮最多 1440 个。当前因可见网页需要用户审阅，Session 从 `verification` 进入 `awaiting_user_acceptance`；不先行创建 focused commit、推送或发布。

## 用户审阅反馈与修订合同（2026-09-25）

用户尚未验收网页，明确提出三项需要修订的点：高并发速度展示、晦涩术语、仅有 8 行表格看不到整体评测完成过程。本次保留同一个未接受的 Session，将原待验收实现退回 `active`，按用户反馈补充验收项；不更改冻结样本、真实请求授权边界和已有历史产物。

- `JV-07`：提供并发 `1/8/32/64/128/720` 的固定档位，默认中等高速档。720 题同时派发是压力档而非保证最快；HTTP 客户端连接上限与选择同步，服务端拒绝未列档位。公开资料仅证实标准付费流量限流由提供方决定，未给 JEV 保证并发上限，因此界面不宣称最大可用并发；429/超时仍按失败计入，不在开发验证中发真实请求。
- `JV-08`：录屏主界面使用非专业观众能懂的中文表达，消除“标签口径”等晦涩主文案；必要的 Gold/翻译/样本构造限制留在说明中，但不能误导为真实世界全体准确率。
- `JV-09`：全部 720 项各有可见进度格，按等待、处理中、判对、判错、失败等状态实时变化，并能定位到详情；原 8 行表格仅作为逐题细读区，不得给人“只测 8 条”的观感。
- `JV-03` 增量：完成轮次的串行/并发对照允许并发档位大于 8，但仍需同一数据集和唯一相同的实际模型版本；显示所比档位与失败数，不能把限流导致的提前结束称为模型加速。

允许文件增量：`temp-for评测视频/server.py`、`static/index.html`、`static/app.js`、`static/styles.css`、`tests/test_demo.py`、`README.md` 及本 Session/STATUS。产品目录、现有 JEV 历史评测结果与 Release 仍禁止修改。指定 `luna_worker` 负责静态网页三件文件，主 Agent 负责后端、测试、README/状态；交接后另行独立只读复核。

## 修订验证与待验收

静态网页实施子代理按增量合同完成三件文件，主 Agent 同步后端连接上限、服务端档位校验、fake 测试和 README。主 Agent 在 Windows ACL 可用环境运行聚焦 pytest `7 passed`，Ruff、Node 语法及 diff check 均通过；本机 Chrome 1920×1080 首屏检查发现并修复一次 `caseGridTiles` Map 归属错误，复查页面正常打开。重启服务后 `GET /api/bootstrap` 为 720 题、Key 在服务端可用、运行记录 `0`；未点击开始，也未发送真实 JEV 请求。真实填充后的 720 格视觉效果尚未以付费请求验证，但静态代码与首屏布局已复核。

独立只读 `detector` 按 `JV-03/07/08/09` 返回 `PASS`，无 MUST_FIX 或范围增量。detector 自身默认沙箱 pytest 因既有 Windows 临时目录 ACL `WinError 5` 得 `6 passed/1 failed`，保留主 Agent 同命令可用环境的 `7 passed` 为测试结论。唯一未实测事项为 JEV/OpenRouter 实际限流和 720 档速度，不预称“最快”。用户可见网页需要明确验收；Session 从 `verification` 进入 `awaiting_user_acceptance`，仍不提交、推送或发布。

## 用户新增 32 题小批量试跑（2026-09-26）

用户在验收前要求新增“小批量测试”按钮，固定 32 道题，先检查系统设计再跑 720 道正式评测。原 Session 退回 `active`；这属于当前未验收网页的明确用户增量，不另开并发修改型 Session。

- `JV-10`：从现有 720 条冻结题中确定性抽取 32 条（参考答案“合理”与“不合理”各 16，尽量覆盖不同菜品），同一输入每次选到同一批；服务端明确保存与返回试跑范围和抽样摘要，导出可复核。
- `JV-11`：网页提供独立的“先测 32 题”按钮与“测全部 720 题”按钮；两者均须点击确认后才发真实计费请求，确认框准确显示本轮题数。试跑复用相同进度、表格、费用、停止与导出机制，但分母为 32，不混入 720 题主结果或正式串行/并发速度比较。仅一个活动 run，重复点击不重复派发。
- `JV-12`：小批量只用 fake 响应验证；本轮开发不主动触发任何付费 JEV 请求。保留上轮所有并发档位与主数据集不变。

允许文件增量：`temp-for评测视频/server.py`、`static/index.html`、`static/app.js`、`static/styles.css`、`tests/test_demo.py`、`README.md`、`TASK_PLAN.md` 及本 Session/STATUS。主 Agent 负责服务端、测试、文档及集成；新实施子代理只负责静态三件文件，完成后交独立只读 detector。不得修改正式产品链路、Git 历史或真实运行产物；无 commit/push/Release。

## 32 题试跑实施、验证与待验收

固定试跑从已有 720 条冻结题中按稳定顺序抽取 32 条，参考答案各 16 条，覆盖 32 道不同菜品；选择 SHA-256 `4CEDD3099A784DCDE678A91BF2BBAB64B9EFAE1370014C492A3559C1D82FCD73`。服务端新增 `scope=pilot32|full`，旧请求缺省为 full；试跑快照/历史/导出包含范围与选择摘要，实际同时请求数封顶为 32，独立按 32 计分。网页提供独立试跑和全量按钮，共用明确计费确认，32 题结果排除在正式 720 题速度比较之外。

主 Agent 最终 fake pytest `9 passed`，Ruff、Node 脚本语法、diff check 通过；本机 Chrome 1920×1080 只读页面截图确认新版双按钮在首屏、无可见运行错误。`GET /api/bootstrap` 返回 full `720`、pilot `32`（16/16、32 菜）、无 active run 和无历史运行。独立只读 `detector` 对 `JV-10/11/12` 及保留的 `JV-03/05` 返回 `PASS`，无 MUST_FIX、范围增量；其默认沙箱 pytest 有 2 项因 Windows TempDirectory ACL 失败，主 Agent 已在可用权限环境同套测试 `9 passed`。没有点击任一开始按钮、没有发 JEV/OpenRouter 计费请求。

预览旧版服务占用 `127.0.0.1:8765`，该端口 Python 进程当前权限下无法结束；为避免打开旧页面，主 Agent 在 `127.0.0.1:8766` 启动新版服务，并在 README 记载备用启动命令。未改旧进程或其运行数据。本任务仍属于用户可见网页，回到 `awaiting_user_acceptance`；不自动提交、推送或发布。

2026-09-26 用户已自行终止 8765 旧版服务，并明确以后以 8765 为准，要求主 Agent 停止 8766。主 Agent 向自己创建的 8766 Uvicorn 会话发送 Ctrl+C，复核 8765/8766 均无 `LISTENING`；残留的 TIME_WAIT/FIN_WAIT_2 仅为已关闭连接。服务未重启，下一次只在 8765 启动新版。待验收状态不变。

## 用户验收与交付（2026-09-27）

用户明确表示 JEV 评测演示网页通过验收，并授权提交与推送。冻结题集 720 条、其中固定 32 条试跑、单次确认后计费、进度与导出按上述合同交付。最终已有 fake pytest `9 passed`、Ruff/Node 语法/diff check 通过，以及独立 detector 对增量 `PASS` 的证据；未进行真实 JEV 付费试跑。focused commit 仅包含临时网页源代码、数据、测试、说明与本 Session/STATUS，排除 `runs/`、浏览器缓存、截图和测试临时目录。后续响应式布局为独立产品任务。
