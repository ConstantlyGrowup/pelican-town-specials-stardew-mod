# Session｜Task 36.1 原图参考像素图标实施

| 字段 | 值 |
|---|---|
| session_id | `2026-08-26-task-36-1-source-referenced-icon-implementation` |
| status | `accepted / committed / push_authorized` |
| session_type | `task-implementation` |
| owner | Codex 主 Agent（临时全量接管） |
| started_at | `2026-08-26` |
| implementation_started | `true` |
| user_acceptance | `2026-08-26 用户确认现有 36.1 设计计划并明确要求实施` |
| joint_user_acceptance | `2026-08-27 用户明确验收 36.1 与 36.2 通过并授权推送` |
| base_commit | `e0a9509 docs: accept Milestone 9 results` |
| acceptance_contract_id | `mvp-task-36-1-source-referenced-icon-v1` |
| revise_round | `0` |
| context_packet | `docs/plans/2026-08-26-task-36-1-source-referenced-icon-packet.md`（gitignored） |
| focused_commit | `a2d3756 fix: generate fresh icons from the source photo` |

## 目标

Canonical HIT 继续复用历史 icon；Ask Gus INITIAL miss、FULL_REGENERATE 与 Blueprint 改为以当前 Draft 原图作为单图 edit 参考生成 fresh icon，并保持既有透明化、16×16 归一化、preview、失败与并发/试用语义。

## 冻结范围

- Acceptance Ledger：T36.1-001..008；planning rulings：T36.1-R01..R03。
- 只允许 Context Packet 列出的 generation 源码、测试与测试 harness；相邻依赖必须按 scope delta 记录。
- 不修改 frontend/API/OpenAPI/schema/Canonical recall/试用额度/发布配置；不增加 Provider 调用，不开始 M10。

## 当前进度

- 规划已获用户确认和实施授权。
- Context Packet 已完成依赖闭包并冻结为 `READY_FOR_IMPLEMENTATION`。
- `luna_worker`（gpt-5.6-luna/max）按测试先行完成六个获准文件：fresh icon 改为当前原图单图 EDIT；中英文 Prompt 保留主体轮廓、主色、摆盘与关键食材；Canonical HIT 和最终双图 preview 不变。
- RED：任务测试先出现 `7 failed, 31 passed`，失败对应旧 GENERATION/no-source/capability/prompt 行为；实现后 focused/provider 为 `83 passed`。
- 主 Agent 相关回归：generation + trial + M9 E2E `80 passed`；全后端 `780 passed, 2 skipped`，仅两条既有 duplicate-ZIP warning。
- Ruff clean；Mypy 92 source files clean；`scripts/check_openapi_drift.ps1` 在隔离 `PTS_WORKSPACE_PATH` 下 PASS；`git diff --check` PASS。
- 默认/工作区内 pytest 临时目录受 Windows ACL 影响会触发 `WinError 5`；验证使用获准的独立 `C:\\tmp` basetemp 完成。计划中的 `pnpm --dir frontend contract:check` 脚本名在项目中不存在，主 Agent改用仓库权威 `scripts/check_openapi_drift.ps1` 完成等价且更完整的契约检查。
- `detector`（gpt-5.6-sol/medium，只读）round 0：`PASS`；T36.1-001..008 与 T36.1-R01..R03 全部通过，`must_fix: []`、`optional_hardening: []`、`new_design: []`、`scope_delta: none`。
- 未调用真实 Provider；未修改 frontend/API/OpenAPI/schema/Canonical recall/试用/发布/M10；未提交或 push。

## 联合验收安排

- 自动与独立代码验收已通过。建议用户以同一张真实菜品原图生成 fresh icon，观察 16×16 主体轮廓、主色、摆盘和关键食材是否比补丁前更贴近原图。
- 用户于 2026-08-26 明确要求 36.1 与 36.2 一起验收；本 Session 不再占用活动修改型 Session，其已验证改动保持未提交，等待 36.2 PASS 后联合呈交。
- Task 36.2 已完成 worker 实施、主 Agent 全量门禁和 detector round 0 PASS；当前正式进入 36.1 + 36.2 联合用户验收。
- 联合验收明确接受后，仍建议保持 focused commit：`fix: generate fresh icons from the source photo`。
- push、版本提升、tag 与 GitHub Release 仍需单独授权。
- 2026-08-27 用户已明确联合验收通过并授权本 Task 与 36.2 提交、push；该授权不包含版本提升、tag 或 GitHub Release。
- focused product commit 已创建：`a2d3756`；控制面记录提交后与 36.2 一并 push。
