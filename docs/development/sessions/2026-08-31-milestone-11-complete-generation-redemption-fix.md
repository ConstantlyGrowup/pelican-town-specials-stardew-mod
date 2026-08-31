# Session｜M11 验收修复：完整生成后兑现试用

| 字段 | 值 |
|---|---|
| session_id | `2026-08-31-milestone-11-complete-generation-redemption-fix` |
| status | `verification_complete`（保留结果，纳入新增 UI Task 完成后的统一验收） |
| session_type | `acceptance-repair` |
| owner | Codex 主 Agent（M11 全量接管） |
| started_at | `2026-08-31` |
| implementation_started | `false` |
| user_authorization | `2026-08-31 用户实测发现公共服务中断仍扣次，并明确要求完整走完一次生成动作才算一次试用兑现` |
| base_commit | `c2fccdd feat: show confirmed trial usage on results` |
| acceptance_contract_id | `mvp-m11-complete-generation-redemption-fix-v1` |
| revise_round | `2` |
| context_packet | `docs/plans/2026-08-31-m11-complete-generation-redemption-fix-packet.md`（gitignored） |
| focused_commit | pending |

## 目标与边界

本 Session 只修正 M11 试用兑现时机：继续在首次 Provider 调用前按 attemptId 原子预留，但只有 generation attempt 的全部阶段成功、完整 Draft 已 promotion 并准备持久化成功终态时，才把 reservation 转为一次 consumed。任何中途 Provider/公共服务故障、后续阶段失败、校验失败、promotion 冲突或显式取消都释放 reservation，attempt 保持 `trialUsed=false` / `trialRemaining=null`。

保留 `TRIAL_GENERATION_LIMIT=2`、三路并发容量保护、v1/v2 状态迁移、TRIAL_FIRST/PERSONAL 路由、显式个人服务接管、Canonical/Blueprint/完整重新生成和 M10/M11 UI 结果事实。不得增加 Provider 调用、自动 fallback、远程额度服务、账号或新设置。

## 冻结 Acceptance Ledger

- **M11-FIX-001**：trial attempt 在首次真实 Provider 调用前只 reserve；任何 Provider 成功响应都不再提前 commit。
- **M11-FIX-002**：Ask Gus INITIAL、FULL_REGENERATE 与 Blueprint 仅在完整 generation 成功后 commit 一次，并持久化固定 `trialUsed=true` / `trialRemaining` 快照。
- **M11-FIX-003**：任一中途阶段失败（包括已有一次或多次 Provider 成功后公共服务不可用）均 commit=0、release=1、额度不变，失败 attempt 为 `false/null`。
- **M11-FIX-004**：显式取消、最终校验失败、promotion 冲突及意外异常均不得兑现；未确认 reservation 必须释放。
- **M11-FIX-005**：成功 attempt 的 commit/release 仍幂等；并发 `consumed + reservations <= N`，失败释放不影响其他 attempt。
- **M11-FIX-006**：失败提示继续脱敏并明确“本次未消耗”；个人服务路径零 reservation，未经点击不自动产生个人费用。
- **M11-FIX-007**：M10 `generation_finished.trial_used` 与成功 attempt 一致；失败为 false，成功为 true；不新增遥测字段或创作内容。
- **M11-FIX-008**：不增加或重排业务 Provider 调用；M8/M9/M10、trial-state v2、API/OpenAPI、前端结果卡与打包行为不退化。

## 当前进度

- 已复核当前状态、M11 技术设计/实施计划、Task 40 Session、试用状态服务、generation orchestrator 与相关回归测试。
- 根因确认：`_commit_trial_after_provider_success()` 在每个 Provider await 成功后被调用，第一次成功即 commit；后续失败进入 error path 时 reservation 已不存在，因而不会释放。
- 修复策略：移除 Provider 成功点的 commit，把 commit 集中到完整 Draft promotion 成功后的 terminal-success 边界；所有 terminal failure/cancel 路径释放 reservation。
- Round 0 `luna_worker` 在 permitted scope 内完成实现，focused `48 passed`；主 Agent focused `100 passed`、完整 backend/integration `883 passed / 2 skipped`，Ruff 与 mypy 全绿，无真实 Provider 调用。
- detector round 0 返回 `REVISE`：promotion 后本地 quota commit 返回 `None`/抛异常时，旧 `_finish_failed` 使用 promotion 前 revision/ownership 回滚失败，可形成成功 Draft 与 FAILED attempt 不一致；其余 M11-FIX-001..003/005..008 全部 PASS。
- Round 1 复用 worker 做唯一 must-fix：按 promoted revision、`active_attempt_id=None` 安全回滚到对应 generation kind 的失败/原状态，并增加 INITIAL/FULL_REGENERATE/BLUEPRINT × `None`/exception 的 fake accounting failure 回归。
- 主 Agent round 1：focused `106 passed`，Ruff、mypy 96 files、diff-check 全绿；worker `implementation_scope_delta: none`，未调用真实 Provider、未 commit/push。
- detector round 1 返回 `PASS`：M11-FIX-001..008 全部满足，`must_fix=[]`、`optional_hardening=[]`、`scope_delta=none`；独立 focused `106 passed`，Ruff、mypy 与 diff-check 全绿。
- 最终 Windows 构建门禁通过：backend/integration `889 passed / 2 skipped`，frontend `180 passed`，TypeScript/Vite、OpenAPI drift、ignore policy、telemetry manifest、PyInstaller、EXE 图标/1.4.0 身份与 bundle 内容门均 PASS。
- bundle smoke PASS：递归 `_sqlite3.pyd`、health、静态首页、非空 Registry SQLite、同一隔离工作区二次启动重开均正常。
- 新 EXE：`dist/PelicanTownSpecials-windows-x64/PelicanTownSpecials.exe`，SHA256 `B34B7B0A6721C8638A5A5BD93FD47F808D5C1E533FC89097B52CD4906963760A`；bundle 试用资源存在且长度 51，未读取或输出内容。
- 已把本机正式 `trial-state.json` 与 `.bak` 改名为 `pre-m11-redemption-retest-20260831-125753` 备份；下次启动默认 `consumedAttempts=0`、remaining=2。下一步等待用户用新 EXE复验并给出 M11 统一验收结论；未 commit、未 push、未提升版本或发布。
- 用户人工复验确认“无法完成的生成不消耗试用次数”，核心兑现修复通过；同时指出可点击动作“稍后重试”会立即重发请求，语义误导，要求改为“直接重试”或移除，并提供替换公共试用 Key（旧 Key 已无额度）。
- Revise round 2 冻结范围：仅把试用服务失败的可点击动作从 `retryLater/稍后重试/Try again later` 改为明确的 `retryNow/直接重试/Retry now`，点击行为不变；其他通用错误中的自然语言“稍后重试”不属于本问题。替换 gitignored 本地试用资源及 GitHub Actions `PTS_TRIAL_API_KEY` secret，不记录、回显或提交 Key；重建后再次重置本机试用状态。
- Round 2 worker 仅修改 `copy.ts`、`GenerationError.tsx` 与对应测试；主 Agent/独立 detector 均 PASS，GenerationError `10 passed`、TypeScript、ESLint、diff-check 全绿，`retryLater` 已完全移除，中文为“直接重试”、英文为“Retry now”，`onRetry` 行为不变。
- 新 Key 已通过隐藏输入写入 `resources/trial/trial_api_key.txt`，`git check-ignore` 确认为 `/resources/trial/trial_api_key.txt`；只核验长度 51 和指纹，不在日志/文档/差异中记录正文。尝试更新远端 Actions Secret 被安全审查拦截，需用户明确授权目标仓库 `ConstantlyGrowup/pelican-town-specials-stardew-mod` 的 Actions Secret `PTS_TRIAL_API_KEY` 后再执行。
- Round 2 最终构建：backend/integration `889 passed / 2 skipped`，frontend `180 passed`，TypeScript/Vite、OpenAPI、ignore policy、telemetry manifest、PyInstaller、图标/版本/内容门和 bundle Phase A/B smoke 全绿；bundle Key 与本地 Key 哈希一致。
- 本机试用状态已再次可恢复地改名备份为 `pre-m11-direct-retry-key-retest-20260831-172829`，下次启动 remaining=2。当前等待用户测试新 EXE、给出最终验收结论并明确决定是否授权远端 Actions Secret 更新；仍未 commit/push/提升版本/tag/发布。
- 用户随后明确授权把新 Key 写入 GitHub 仓库 `ConstantlyGrowup/pelican-town-specials-stardew-mod`；已通过标准输入更新 Actions Secret `PTS_TRIAL_API_KEY`，`gh secret list` 仅核验名称与更新时间 `2026-08-31T07:35:26Z`，未读取或输出 Secret 值。当前仅等待最新 EXE 的最终人工验收。
- 用户在最终验收前追加两个独立 UI 需求：蓝图分类/标签可直接移除，以及试用暂时不可用时可直接放弃草稿并返回主页。本 Session 的源码和验证结论保持冻结，不继续承载修改；状态收口为 `verification_complete`，待新增 Task 全部完成后统一人工验收。
