# Session｜第三期全局生成记忆规划

| 字段 | 值 |
|---|---|
| session_id | `2026-08-16-phase-3-global-memory-planning` |
| status | `discovery / awaiting_user_confirmation` |
| session_type | `phase-3-requirements-planning` |
| owner | Codex 主会话 |
| started_at | `2026-08-16` |
| implementation_started | `false` |
| user_acceptance | `pending` |
| base_commit | `b6df1f3 docs: record v1.2.0 release published and artifacts verified` |

## 目标

依据 v1.2.0 已落地生成链路、旧顶层规划和用户 2026-08-16 的新阶段排序，先更新过时文档，再一次性确认第三期“全局生成记忆与 Canonical 召回”的产品与技术边界。

## 已确认裁决

- 第一期、第二期已经完成，v1.2.0 是当前本地发布基线。
- 第三期只做全局生成记忆及其本地可测试召回架构。
- Canonical 可候选复用结构化词条与像素图标；最终专属预览必须使用本次用户原图重新生成。
- 夜间批处理、Redis/Bloom Filter、热点 Key、逻辑过期与预热后移第四期。
- 登录、多用户、在线统一生成接口、队列/worker、云存储和后端优化后移第四期。
- 管理端与 Gallery 审核后移第五期；第四期和第五期在第三期完成后联合规划。
- Task 30 新手试用入口 deferred，不创建 Context Packet。

## 本 Session 范围

- 维护现行顶层规划、第三期发现锚点、设计索引与开发控制面。
- 从仓库核对现有生成阶段、字段、Repository、资产边界和测试能力。
- 给出 SQLite/MySQL/现有 JSON 的阶段化比较与推荐。
- 使用一次统一问题清单完成第三期需求发现。

## 不做

- 不修改产品源码、schema、API 或测试。
- 不创建开发分支、Context Packet、commit、tag 或部署。
- 不提前决定第四期/第五期技术选型。

## 下一步

等待用户一次性回答第三期问题清单。回答后先更新第三期产品/机制设计；技术设计与实施计划仍按“两步法”依次建立，并在实施前另行请求授权。

**2026-08-16 追加**：用户明确指令“实现完 task30 并更新相关文档”，覆盖本 Session 记录的 Task 30 deferred 决定。Task 30（新手试用入口）已恢复实施并完成实现（Session `2026-08-16-task-30-trial-entry-impl`，Context Packet `mvp-task-30-trial-entry-v1`），不属于第三期；本 Session 第三期需求发现仍保持暂停/等待确认。
