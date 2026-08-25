# Session｜Task 30 新手试用入口实施

| 字段 | 值 |
|---|---|
| session_id | `2026-08-16-task-30-trial-entry-impl` |
| status | `committed / released / closed` |
| session_type | `task-30-implementation` |
| owner | Codex 主会话（包工） |
| started_at | `2026-08-16` |
| implementation_started | `true` |
| user_acceptance | `accepted` |
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
- **Codex round-1 复审：PASS**（checked T30-TRIAL-006/001，无 MUST_FIX，optional_hardening/new_design none，scope_delta none，planning_rulings R-01..R-08 全过）。→ **auto_accepted** → 本地 focused commit `96e9988`（32 文件 +2286/−41，不 push）→ 进入 **awaiting_user_acceptance**。
- 建议提交边界：Task 30 实现（backend trial/errors/orchestrator/app/settings + 前端 SettingsPage/GenerationError/copy/OpenAPI/E2E + workflows + .gitignore + repo 测试）+ 控制面文档（STATUS/本 Session/AGENTS.md/CONSTRAINTS.md/三期 Session 追加）。用户明确验收后可授权 push。

## 验收阻塞解除：本地试用资源落地（2026-08-16）

用户验收时反馈"即使没有试用过控制台仍输出 `{"available":false,...}`"。该行为是设计的安全降级（R-06：无 key 资源 → `available=false`），并非缺陷；`dist/` 现 bundle 为 v1.2.0（Task 30 之前，无试用代码），用户跑的应是仓库内开发服务器。

解除步骤（本地环境，非代码改动）：
- 用户提供真实试用 Key 且已设额度兜底；按 CI 注入的同一机制把资源文件落到本地 gitignored 路径 `resources/trial/trial_api_key.txt`（ASCII、无尾随换行，51 字节）。
- `git check-ignore -v` 确认该文件被 `.gitignore:16` 忽略、`git ls-files resources/trial/` 为空——key 永不入库。
- 验证：全新 `FileTrialKeyProvider` + `TrialAccessService` 读取 → `{"available": true, "enabled": false, "claimedAttempts": 0, "limit": 2, "remaining": 2}`。
- 注意：`FileTrialKeyProvider` 首次读取后缓存，**正在运行的实例须重启**；当前无运行进程，下次启动即读到新资源。开发服务器读仓库根路径；本地 `build_windows.ps1`（spec datas 含整个 `resources/`）构建的安装包自动携带该资源；CI 构建由 `PTS_TRIAL_API_KEY` secret 注入（若发布 bundle 需用户在 GitHub 设该 secret）。

## 用户授权扩展：已配置用户优先试用（R-09 / T30-TRIAL-007，2026-08-16）

用户新增规则「当用户已经配置好了且有试用机会时，优先用掉试用机会」→ 作为 Task 30 合同的用户授权扩展（Context Packet 追加，base_commit `96e9988`，revise_round 0）。规划裁决 R-09 + 验收项 T30-TRIAL-007。

- **行为契约**：已配置个人 Provider 的用户自动优先消耗免费试用额度（`trial_opportunity()` = available && claimed < limit，无需点击 opt-in）；额度耗尽或并发 claim 竞争失败时**静默**回退个人 Provider（不报错）；未配置用户保持既有 opt-in 流程（`is_active()` 门 → claim → 耗尽抛 `PTS_TRIAL_LIMIT_REACHED`）。
- **实现（9 个 allowed_files）**：`application/trial.py` 增 `trial_opportunity()` 并放宽 `claim_attempt()` 的 `enabled` 门；`generation/orchestrator.py` `TrialAccess` Protocol 增方法 + `personal_configured` 构造参数 + `_ensure_gateway` 配置/非配置双路由；`api/app.py` `_personal_key_configured` 惰性回调接线；前端 SettingsPage 配置用户分支（priority status / exhausted status / 隐藏 opt-in 按钮）+ copy.ts zh/en 文案 + 单元/E2E 测试。
- **实施期 scope_delta 2 项（均 `user_visible_delta: none`）**：① `claim_attempt()` 不再要求 `enabled`——配置路径可在未 opt-in 服务上消耗额度，非配置路径仍在 `is_active()` 之后才 claim，opt-in 流程行为不变（真实服务测试证明未 opt-in 服务可被配置路径耗尽至 claimed==2）；② zh 文案由「已配置个人服务…」改为「个人服务已设置…」避免与 allowed_files 之外的 `full-journey.spec.ts:608` `getByText("已配置")` 子串断言冲突。
- **审阅**：Codex（gpt-5.6-luna/max，新 thread）round 0 **PASS**（checked T30-TRIAL-007 / R-05 / R-07 / T30-TRIAL-001，无 MUST_FIX，scope_delta none）。OPTIONAL_HARDENING 2 条非阻塞：全部门禁通过；STATUS 与 Session 状态措辞已在本记录中一致化。
- **验证（包工复跑）**：focused 33 passed；API+generation 回归 87 passed；前端 Vitest 131 passed（20 文件）；E2E 32 passed；ruff clean；`python -m mypy backend/src`（CI 命令）clean；product copy / locale / `git diff --check` clean。
- **状态**：**auto_accepted** → 本地 focused commit `9cb35a8`（9 个实现文件，不 push）+ 本控制面记录随 docs commit 提交。Task 30 整体（含 R-09）仍在 **awaiting_user_acceptance**。

## 不做

- 不接触真实试用 Key（实现/测试/交接只用 fake，如 `sk-test-trial`）。
- 不扫描/重写/删除用户草稿；不修改 Draft/Cookbook schema；不新增队列/数据库/账号/服务端代理。
- 不开发第三期全局生成记忆；`2026-08-16-phase-3-global-memory-planning` 保持暂停。

## 用户验收与推送（2026-08-17）

用户 2026-08-17 明确「验收通过，可以push」，并在仓库设置中配置好试用 Key（`PTS_TRIAL_API_KEY` secret）。Task 30（含 R-09 扩展）整体进入 **accepted**；已授权 push 当前分支。本轮不自动构建新 installer/Release（tag 推送与 Release 发布需用户单独授权）。

## 推送、发布与核验（2026-08-17）

用户验收 Task 30（含 R-09）并授权 push + 发布 v1.3.0。实际执行：
- 推送 `feat/mvp-implementation` 至 `1a0c53a`（docs 记录验收与推送授权）。分支 CI（run 31952234049）曾因 **M8 并发 flaky 测试** `test_fourth_concurrent_generation_returns_409_busy_with_details` 失败一次（`AssertionError: assert 5 == 3`）。诊断：与 R-09 无关——该测试 fixture 用默认 `personal_configured=lambda: False`、无 trial access，R-09 双路由未进入；FakeGateway 在每次调用**开始**时记录调用，三个并发生成在 0.5s delay 内持续推进，快照后继续追加 design 调用 → 计数断言竞态。
- 版本提升 commit `4de82ad`（11 文件 +16/−15，v1.2.0→v1.3.0）；本地全量门禁全绿（build_windows.ps1 / build_installer.ps1 / smoke_windows_bundle.ps1：EXE+setup icon `3FE51DEB`、版本身份 1.3.0、installer SHA-256 `DC548314…`）。
- push branch + tag **v1.3.0** → release.yml run 31952659305 **success**（resolve-version → verify-and-build 10m48s → create-release 17s）。`gh release view v1.3.0` 核验：tag `v1.3.0`、非 draft/pre-release、产物 `PelicanTownSpecials-Setup-v1.3.0.exe` + `PelicanTownSpecials-windows-x64-v1.3.0.zip` + `SHA256SUMS.txt`。
- 用户最初报告「仍显示 1.2」系因检查时 verify-and-build 尚未完成（约需 10+ 分钟），并非发布失败。

## 维护修复：M8 并发 flaky 测试确定性化（2026-08-17）

分支 CI 曾因上文竞态失败一次，虽 release run 恰好通过，仍做确定性修复避免后续 CI 抖动：
- `backend/tests/generation/conftest.py`：FakeGateway 增可选 `hold: asyncio.Event | None = None`（默认 None 不影响既有测试）；`analyze_dish` 在记录 `analyze` 调用后、delay 前 `await hold.wait()`，可把在途生成冻结在首次 Provider 调用内。
- `backend/tests/api/test_generation_stream.py`：并发 409 测试设置 `hold`，冻结三个在途生成后快照；断言期间在途生成无法追加新调用，`len(calls) == calls_before` 由竞态变为确定；finally 先 `hold.set()` 再取消任务。
- 验证：generation + stream 全量 73 passed；flaky 测试连续 8/8 通过；全量 CI 命令 `python -m pytest backend/tests tests/repo tests/integration -q` 全绿。
- 状态：测试-only、无用户可见行为变化、测试全覆盖 → 按自动审批例外本地维护 commit（未 push）。

## 最终关闭（2026-08-25 状态核对）

- 维护修复已提交为 `e6582f7`，发布与修复收尾记录为 `7addfb8`；两者均已推送，当前分支与 origin 同位于 `7addfb8`。
- Task 30 已验收、提交、推送并随 GitHub Release v1.3.0 发布；本 Session 正式关闭，不再是当前活动 Session。
- 当前工作恢复到 `2026-08-16-phase-3-global-memory-planning`，仍只做需求发现，未授权第三期产品开发。
