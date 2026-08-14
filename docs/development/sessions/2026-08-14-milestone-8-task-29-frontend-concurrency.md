# Session｜Milestone 8 Task 29 前端提示与完整并发验收

| 字段 | 值 |
|---|---|
| session_id | `2026-08-14-milestone-8-task-29-frontend-concurrency` |
| session_type | `milestone-8-task-29-implementation` |
| status | `active` |
| owner | Claude Code 主会话（包工）+ 实施子代理 + Codex 审阅 |
| started_at | `2026-08-14` |
| base_commit | `d0a3701 docs: record M8 Task 28 auto_accepted` |
| acceptance_contract_id | `mvp-m8-task-29-frontend-concurrency-v1` |

## 范围与边界

本 Session 只处理 Task 29（M8 最后一个 Task）：前端 PTS_GEN_BUSY 双语上限提示（zh-CN/en-US，复用既有 GenerationError 横幅与重试按钮）、三草稿并行互不串线验证（hook 级 + E2E 多 page）、以及 frontend/backend/OpenAPI/E2E 全量回归与 Windows bundle/installer smoke。无后端/API/OpenAPI/领域改动；版本号不提升（验收即发布在用户 Milestone 验收后单独执行）。

## 验收项（来自 Context Packet `mvp-m8-task-29-frontend-concurrency-v1`）

- T29-001 zh-CN/en-US 下 PTS_GEN_BUSY 均显示明确上限提示（最多 3 个 + 等待后重试引导），草稿保持原状；非 busy 错误仍显示后端 message。
- T29-002 第 4 份草稿被拒绝后保留原状态；名额释放后「重试生成」可立即成功。
- T29-003 三份草稿同时生成互不串线（各自阶段/刷新恢复/取消独立）。
- T29-004 frontend Vitest/lint/build、E2E、backend 全量回归、OpenAPI drift 全部通过。
- T29-005 Windows bundle + installer 构建与 smoke 全流程通过，不调用真实 Provider。

## 规划裁决

- R-01 前端按 `error.code === "PTS_GEN_BUSY"` 分支显示本地化静态文案（copy key `generationBusyLimit`），不解析 details。
- R-02 复用 GenerationError 横幅与重试按钮，不新增组件/排位视觉。
- R-03 E2E 用 page.route 拦截（无后端/真实 Provider），三页并发用同一 test 内多 page。
- R-04 不重新生成 OpenAPI 契约（无 API 变更），drift 检查为回归门。
- R-05 版本号不提升；bundle/installer smoke 在本 Task 完成，Release 发布留待用户验收授权。

## 验证记录（实施后填写）

## 审阅记录（实施后填写）

## 结论（实施后填写）
