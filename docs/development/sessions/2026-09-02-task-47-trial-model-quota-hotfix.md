# Session｜Task 47 公共试用模型与额度热修复

| 字段 | 值 |
|---|---|
| session_id | `2026-09-02-task-47-trial-model-quota-hotfix` |
| status | `auto_accepted`（detector PASS，用户已预授权双分支推送与 Release） |
| session_type | `product_patch` |
| owner | Codex 主 Agent（`luna_worker` 实施，`detector` 独立审阅） |
| started_at | `2026-09-02` |
| user_authorization | `2026-09-02 用户要求公共试用 image model 改为 gpt-image-2、试用总额度提高至 5，并同步 main/MVP、推送及更新最新 Release` |
| base_commit | `573afbc docs: close v1.5.2 error localization release` |
| acceptance_contract_id | `mvp-task-47-trial-model-quota-v2`（用户在提交前改为所有旧用户一次性重置至完整 5 次） |
| revise_round | `1` |
| context_packet | `docs/plans/2026-09-02-task-47-trial-model-quota-packet.md`（gitignored） |

## 目标与边界

仅修改公共试用隐藏档案：图像模型由 `gpt-image-2-max` 改为 `gpt-image-2`，本机试用总额度由 2 提高到 5。个人 Provider 的默认值、用户已保存设置、试用 Key、扣次时机、失败不扣次、偏好切换、M8/M9/M10 及 API schema 均保持不变。

## 迁移裁决（2026-09-02 用户修订）

- `trial-state.json` 从 schema v2 升级为 v3；首次读取任意合法 v1/v2 状态时，将 `consumedAttempts`、`reservations` 与 `committedAttempts` 清空并原子写回 v3，使所有旧用户获得完整 5 次。
- 保留旧状态的 `enabled`；v2 的 `providerPreference` 也原样保留。写成 v3 后不再重置，因此后续成功消费会正常持久化，不会在每次启动恢复为 5。
- 只改 `TRIAL_IMAGE_MODEL`，不改个人服务的 `ProviderSettings.image_model` 默认值 `gpt-image-2-max`，避免覆盖用户个人配置。
- 本 Task 不调用真实 Provider，不轮换或读取试用 Key；发布工作在本 Task PASS/commit 后进入独立 v1.5.3 Release Session。

## Acceptance Ledger

- **T47-001**：公共试用 gateway 使用 `gpt-image-2`，不再使用 `gpt-image-2-max`。
- **T47-002**：公共试用总额度为 5；新状态和 API status 返回 `limit=5`、`remaining=5`。
- **T47-003**：所有合法 v1/v2 旧状态一次性迁移到 schema v3 并清零历史消费/预留/commit 快照，迁移后 `limit=5`、`remaining=5`；保留 enabled 和 v2 providerPreference；v3 重启不得再次重置。
- **T47-004**：并发 reservation/commit/release、完整成功才扣次、失败不扣次、R-09 与个人偏好语义保持不变。
- **T47-005**：个人 Provider 默认 image model 及已保存配置不变；不改变 API schema、Key 注入、遥测或 Canonical 行为。
- **T47-006**：focused tests、相关 trial/generation/API 回归、Ruff、mypy 与 diff-check 通过；不产生真实模型费用。

## 当前进度

- v1 合同曾按“保留历史消费、上限补至 5”完成 worker/detector PASS，但尚未 commit/push；用户随后明确改为“所有用户均重置到 5”，因此 v1 合同作废，不作为最终验收依据。
- v2 Context Packet 已重新冻结；新的 `luna_worker`（工具路由 `gpt-5.6-luna` / `max`）已完成实施并返回 `TASK_HANDOFF`：contract id 未变，五个修改文件均在 Packet 范围内，`implementation_scope_delta: none`、`scope_deviations: none`，未调用 Provider、未读取 Key、未 commit/push。
- 主 Agent复验：相关 trial/generation/API 回归 `79 passed`；Ruff、mypy 96 files、diff-check 全绿。Worker 环境中的 pytest 临时目录 ACL 失败已由主 Agent在真实 Windows 权限下成功重跑，不属于产品失败。
- 下一步：`detector` 按 v2 合同独立审阅。
- detector round 0 返回 `REVISE`，唯一 MUST_FIX 绑定 T47-003：合法 snake_case v2 payload 同时保留 `provider_preference` 并新增 `providerPreference`，会触发 StrictModel extra-forbid，导致迁移降级为全新 disabled 状态。最小修复为归一化后只保留一个偏好键，并补 snake_case v2 回归；无新设计、无范围扩张。
- Round 1 worker 已按最小范围修复：v2/v3 归一化写入 canonical `providerPreference` 后移除 `provider_preference`，新增 snake_case v2 迁移回归。主 Agent相关回归 `80 passed`；Ruff、mypy 96 files、diff-check 全绿，等待同一 detector 封闭复审。
- detector round 1 封闭复审 `PASS`：T47-003/T47-006 通过，`must_fix=[]`、`scope_delta=none`，实际路由为 implementer `gpt-5.6-luna/max`、review `gpt-5.6-sol/medium`。
- T47-001..006 全部满足；按普通 Task 自动路径进入 `auto_accepted`，准备创建一个产品+控制面 focused commit，不包含 Key、构建产物或历史未跟踪目录。
