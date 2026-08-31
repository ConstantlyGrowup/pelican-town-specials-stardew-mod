# Session｜Task 44：试用不可用时放弃草稿并返回主页

| 字段 | 值 |
|---|---|
| session_id | `2026-08-31-task-44-trial-error-discard-draft` |
| status | `verification_complete`（detector PASS，等待 M11 统一人工验收） |
| session_type | `implementation` |
| owner | Codex 主 Agent（M11 全量接管） |
| started_at | `2026-08-31` |
| user_authorization | `2026-08-31 用户要求试用暂时不可用的反馈页面支持直接删除草稿并回到主页，与正常生成任务一致` |
| base_commit | `1ad271a docs: close v1.4.0 release session`（叠加当前未提交 M11 修复与 Task 43） |
| acceptance_contract_id | `mvp-m11-task-44-trial-error-discard-draft-v1` |
| revise_round | `0` |
| context_packet | `docs/plans/2026-08-31-task-44-trial-error-discard-draft-packet.md`（gitignored） |
| focused_commit | pending |

## 目标与边界

在 Ask Gus 与料理蓝图的 `PTS_TRIAL_SERVICE_UNAVAILABLE` 反馈区提供“放弃草稿并返回主页”入口。入口必须复用各页面已有的不可恢复操作确认弹窗、`POST /discard`、CSRF/同源请求、失败提示与成功后 `navigate("/")`；不得一点即删，不新增后端接口。

## 冻结 Acceptance Ledger

- **M11-T44-001**：试用暂时不可用时，Ask Gus 与 Blueprint 错误反馈区均显示明确的放弃草稿并返回主页操作。
- **M11-T44-002**：点击只打开各页面既有确认弹窗；取消不请求、不跳转，确认后只调用一次既有 discard API，204 后回主页。
- **M11-T44-003**：删除失败保留当前页面并显示各页面既有失败提示；CSRF 与 same-origin 合同不变。
- **M11-T44-004**：该入口只出现在 `PTS_TRIAL_SERVICE_UNAVAILABLE`；其他 GenerationError、重试、个人服务接管/配置与正常底部操作不退化。
- **M11-T44-005**：不改后端/API/OpenAPI/试用计数/生成状态；中英文文案和 focused 页面/组件测试、TypeScript、ESLint、diff-check 全绿。

## 当前进度

- 已确认两个页面均有可复用的 discard 处理和确认弹窗，后端无需变化。
- `luna_worker` 已在 7 个允许文件内完成实现，`implementation_scope_delta: none`；主 Agent 复跑三个 focused 文件 `71 passed`，TypeScript、ESLint、diff-check 全绿。
- 正式 TASK_HANDOFF 已落入 Context Packet；等待只读 detector 独立审阅。
- detector 返回 `PASS`：M11-T44-001..005 全部满足，`must_fix=[]`、`optional_hardening=[]`、`scope_delta=none`，未授权 commit/push。
