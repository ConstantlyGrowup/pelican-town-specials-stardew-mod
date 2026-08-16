# Session｜Task 30 新手试用入口实施

| 字段 | 值 |
|---|---|
| session_id | `2026-08-16-task-30-trial-entry-impl` |
| status | `active` |
| session_type | `task-30-implementation` |
| owner | Codex 主会话（包工） |
| started_at | `2026-08-16` |
| implementation_started | `true` |
| user_acceptance | `pending` |
| base_commit | `b6df1f3 docs: record v1.2.0 release published and artifacts verified` |
| acceptance_contract_id | `mvp-task-30-trial-entry-v1` |
| revise_round | 0 |

## 目标

用户 2026-08-16 明确指令“实现完 task30 并更新相关文档”，覆盖此前 deferred 状态。实现 Settings“**不想配置，先试试效果**”入口：独立隐藏试用档案 + `app-state/trial-state.json` 本机软额度（N=2）+ 首次可能付费 Provider 调用前原子 claim + 保存个人 Provider 参数/Key 自动退出（不重置次数）+ `PTS_TRIAL_LIMIT_REACHED` + CI Secret 注入试用资源。

## 冻结裁决

- R-01 N=2；R-02 试用 preset 为后端常量、Key 为 gitignored 资源；R-03 惰性 gateway 在首次 Provider 调用点 claim（Ask Gus `DISH_ANALYSIS` / Blueprint `ICON_GENERATION`），`INPUT_VALIDATION` 失败不扣；R-04 `PTS_TRIAL_LIMIT_REACHED`/`PTS_TRIAL_UNAVAILABLE`（409）与 `recommended_action` 分支；R-05 保存（PUT provider / PUT key）退出试用，DELETE key 不退出；R-06 试用 Key 由 build.yml 从 `secrets.PTS_TRIAL_API_KEY` 注入并 gitignore，本地/测试只用 fake；R-07 耗尽后 enabled 保持 true、claim 返回 False → 精确额度错误；R-08 试用模型放 `application/trial.py`，不进 domain。
- 详情见 `docs/plans/2026-08-16-task-30-trial-entry-packet.md`（gitignored）。

## 实施与验收记录（追加式）

- 实施子代理交付 `TASK_HANDOFF`（base `b6df1f3`）→ 包工复核全部实现 diff 并完成“更新相关文档”（STATUS、本 Session、AGENTS.md、CONSTRAINTS.md、MVP 计划/技术设计、顶层规划）→ 桥接 Codex（gpt-5.6-luna/max，新 thread）独立只读审阅。
- **round 0 REVISE**（2 项 MUST_FIX + 1 项阻塞门禁，均为真实缺陷，包工逐项核证）：
  1. **T30-TRIAL-006（MUST_FIX）**：build.yml 只声明 `workflow_call.inputs`、未声明 secret，ci.yml/release.yml 调用也未转发 `secrets:` → 可复用 workflow 内 `secrets.PTS_TRIAL_API_KEY` 恒为空 → 注入步骤 `if` 永不触发，发布包永远没有试用 Key。
  2. **T30-TRIAL-001（MUST_FIX）**：试用 provider `AppError.details.providerError`（仅截断 200 字符、未脱敏）经 `attempt.failed` NDJSON 事件（`ErrorPayload.from_app_error` 逐字复制 details）流向前端；若 provider 回显试用 URL/模型/Key 会泄漏。
  3. **阻塞门禁（同根）**：`tests/repo/test_release.py` 禁止 workflow 出现任何 `secrets.`，注入步骤已使其翻红（CI “Backend, repo and integration tests” 会失败）→ 须放行试用 Key 转发、仍禁个人 Key。
- **round 1 已派发**新实施子代理：FIX 1 workflow secret 转发（build.yml `workflow_call.secrets` + ci/release 显式转发，保留无 secret → 无资源 → available=false）；FIX 2 test_release.py 门禁改写（禁 PTS_OPENAI_API_KEY/SUPER_SECRET，正向断言试用 Key 声明与转发，权限断言不变）；FIX 3 试用 gateway 边界脱敏（`TrialSafeGateway` 实现 ModelGateway 三方法，捕获 AppError 以空 details 重抛，个人路径不动）+ 回归测试。
- **round 1 实施完成**（新实施子代理，scope_delta none，仅 round-1 allowed_files）：build.yml 声明 `workflow_call.secrets.PTS_TRIAL_API_KEY`（required: false）+ ci/release 转发；test_release.py 门禁放行试用 Key 转发仍禁个人 Key；`application/trial.py` 增 `TrialSafeGateway`/`_trial_safe_error`，`app.py` 试用 gateway 工厂包一层；test_trial.py 增 3 条单元测试（全协议方法：AppError details 剥空、happy path 透传、非 AppError 透传），test_trial_generation.py 增回显错误不泄漏集成测试（`attempt.failed` details=={}，个人路径零调用）。
- **包工复跑验收（round 1）**：focused 39 passed；repo 36 passed；全量 backend **708 passed / 2 skipped**；ruff clean；mypy clean（88 files）；`git diff --check` exit 0。→ 桥接 Codex round-1 复审（新 thread，gpt-5.6-luna/max）。

## 不做

- 不接触真实试用 Key（实现/测试/交接只用 fake，如 `sk-test-trial`）。
- 不扫描/重写/删除用户草稿；不修改 Draft/Cookbook schema；不新增队列/数据库/账号/服务端代理。
- 不开发第三期全局生成记忆；`2026-08-16-phase-3-global-memory-planning` 保持暂停。

## 下一步

等待 REVISE round-1 实施子代理 TASK_HANDOFF → 包工复跑聚焦 + 全量 backend/repo/static 门禁 → 桥接 Codex round-1 复审（新 thread）→ PASS → auto_accepted → 本地 focused commit → 提示用户验收。
