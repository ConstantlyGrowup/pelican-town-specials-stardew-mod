# Session｜Task 30 新手试用入口规划

| 字段 | 值 |
|---|---|
| session_id | `2026-08-16-task-30-trial-entry-planning` |
| session_type | `task-30-planning` |
| status | `closed / superseded-by-impl` |
| owner | Codex 主会话 |
| started_at | `2026-08-16` |
| implementation_started | `false` |
| user_acceptance | `pending` |
| base_commit | `b6df1f3 docs: record v1.2.0 release published and artifacts verified` |

## 目标

为不会配置中转站/API Key 的小白用户增加“**不想配置，先试试效果**”入口，同时使用足够轻量的本地软额度限制，避免扫描全部草稿或在生成每个阶段重复检查。

## 现状核对

- v1.2.0 与 Milestone 8 已发布并关闭，当前无产品实施 Session。
- Provider Settings 的非机密参数写入 `app-state/settings.json`；个人 Key 由 `PTS_OPENAI_API_KEY` 当前用户环境变量管理，Settings API 从不回显 Key。
- gateway 在每个 attempt 开始时由 `_gateway_factory` 使用最新个人设置构建，存在天然的一次性凭据选择边界。
- Draft 删除会删除记录，直接统计“当前生成草稿数量”可绕过，也无法区分个人/试用来源。
- 当前最多三路并发，因此任何试用额度领取都必须原子，避免多个请求同时越过 N。

## 推荐裁决

- 试用档案与个人档案完全分离，不写入/覆盖个人设置，所以不需要回收配置。
- 使用 `trial-state.json` 的 `claimedAttempts` 作为本机软限制；仅在启用按钮和第一次可能付费调用前检查。
- 推荐 N=2；本地输入失败不扣，进入 Provider 链路后无论最终成功与否计一次。
- 保存个人 Provider 参数或 Key 自动退出试用；已用次数不重置。
- 试用 Key 由 Release workflow secret 注入冻结后端资源，不进 Git/API/前端/日志；承认桌面包内 Key 可被有意提取，总消费上限由供应商控制台兜底。

## Task 边界

本次只新增一个 Task 30，不开启新队列/数据库/账号/设备指纹/在线额度服务。完整范围、文件预期和验收项见 `docs/plans/2026-08-16-task-30-trial-entry.md`（gitignored）。

## 当前不做

- 不创建 Task 30 Context Packet。
- 不修改 backend/frontend/packaging/workflow 产品实现。
- 不生成或读取真实试用 Key。
- 不运行产品测试/build，不 stage/commit/push/release。

## 下一步

原计划等待用户确认 N、本机软限制和桌面 Key 可提取边界。2026-08-16 用户将当前优先级切换到第三期全局生成记忆规划，因此本 Session 曾关闭为 `deferred`。

**2026-08-16 用户明确指令“实现完 task30 并更新相关文档”，覆盖 deferred 状态**：规划 §9 三项待确认（N=2、接受软限制可绕过、接受桌面 Key 可提取）均按计划推荐值接受，规划使命完成并关闭；实施交接至新 Session `2026-08-16-task-30-trial-entry-impl`（Context Packet `mvp-task-30-trial-entry-v1`）。
