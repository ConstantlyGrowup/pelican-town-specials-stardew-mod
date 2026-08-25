# Session｜第三期全局生成记忆规划

| 字段 | 值 |
|---|---|
| session_id | `2026-08-16-phase-3-global-memory-planning` |
| status | `accepted / closed` |
| session_type | `milestone-9-10-planning` |
| owner | Claude Code 主会话（包工） |
| started_at | `2026-08-16` |
| implementation_started | `false` |
| user_acceptance | `accepted（2026-08-25）` |
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

Milestone 9/10 规划已于 2026-08-25 获用户统一验收，本规划 Session 关闭。用户同时明确授权开始 Milestone 9，并要求按 Milestone 粒度自治开发、非必要不打断、仅在 M9 完成或协议允许的阻塞/人工介入时通知。下一步创建 Task 31 Context Packet 与独立实施 Session；Milestone 10 保持 `accepted / awaiting_implementation_authorization`。

**2026-08-16 追加**：用户明确指令“实现完 task30 并更新相关文档”，覆盖本 Session 记录的 Task 30 deferred 决定。Task 30（新手试用入口）已恢复实施并完成实现（Session `2026-08-16-task-30-trial-entry-impl`，Context Packet `mvp-task-30-trial-entry-v1`），不属于第三期；本 Session 第三期需求发现仍保持暂停/等待确认。

**2026-08-25 恢复**：Task 30 已验收、提交、推送并随 v1.3.0 发布；发布后维护修复也已推送至 `7addfb8`。本 Session 恢复为当前唯一规划活动，继续确认“本机共享 Registry + 生成前局部命中/复用”的已冻结边界与未决机制；仍不修改产品源码。

**2026-08-25 需求确认完成**：用户确认全局有效 Canonical 数量达到 `N=2` 后才启动召回；仅正式保存的 Ask Gus 成品写入；完整重新生成不直接复用；补充要求参与匹配且冲突即 miss；仅召回同语言记录。候选先按现实语义原料等字段低成本缩小，再由紧凑模型节点选择最高置信度结果，只有 `>=90%` 才命中；命中复用完整结构化词条和像素图标，最终预览仍用本次原图生成。效果只以单次生成耗时和单次任务成本衡量，不把模型调用数或生成步骤数列为正式指标。产品机制现已闭合，等待技术设计。

**2026-08-25 Milestone 9 规划完成**：建立 `PHASE_3_CANONICAL_MEMORY_TECHNICAL_DESIGN.md` v1.0 和 `2026-08-25-milestone-9-canonical-memory.md` v1.0；Milestone 9 拆为 Task 31–36，严格串行完成 SQLite/自有图标、正式存档登记与启动修复、Top 5 + 90% matcher、Orchestrator hit/miss 复用、双模式耗时/Gus 叙事、全链路/打包/耗时与单次成本验收。规划裁决包含 internalName 自动唯一化、Archive 成功优先+启动修复、Recall 作为 GAMEPLAY_DESIGN 内部节点和 Registry 自有图标。未创建 Context Packet、未修改产品源码，等待用户验收规划。

**2026-08-25 Milestone 10 规划完成**：用户要求在 EXE 可能长期作为最终产品形态时建立真实发行量化能力。新增 `RELEASE_TELEMETRY_TECHNICAL_DESIGN.md` v1.0 与 `2026-08-25-milestone-10-release-telemetry.md` v1.0，拆为 Task 37–40。第一版选择 PostHog Cloud 只写 capture/batch + 后端人工类型化事件 + 随机安装 ID；首次透明说明确认前零发送，默认参与但可当场和设置页关闭；personless 事件、项目级 IP discard，禁止用户内容、Provider/模型、路径、设备指纹、业务 ID、异常正文、自动点击与录屏。有界内存 dispatcher 故障不影响业务；GitHub 下载量仅作旁证。M10 与 M9 无硬依赖，默认仍按 M9 后 M10；如需提前必须由用户明确重排。未创建外部项目、Repository Variables、Context Packet 或产品源码，现等待用户统一验收 M9/M10 规划。

**2026-08-25 用户验收与实施授权**：用户明确验收 Milestone 9 Task 31–36 与 Milestone 10 Task 37–39 的现行技术设计/实施计划；同时授权开始开发 M9，严格按 `31 → 32 → 33 → 34 → 35 → 36` 串行执行。普通 Task 走 Context Packet → 新 implementer → Codex 独立 Review → PASS auto_accept → 本地 focused commit，不逐 Task 打断；M9 全量完成后统一通知并等待 Milestone 验收/push 授权。M10 仅规划验收，尚未授权实施。

**2026-08-25 Milestone 10 减负修订**：用户明确 M10 仅用于项目自身统计，要求开发前后用户体验无差别，不设计用户可见说明、确认或关闭能力，并删除“新版本采用比例”。据此将 M10 技术设计/详细计划升至 v1.1，压缩为 Task 37–39：后端统计核心、业务事件接线、Release 配置/看板/全链路验收。配置完整的 Windows Release 自动启用；不新增前端、Settings、公开 API、OpenAPI 或用户文档入口；不记录应用版本。保留最小字段 allowlist、不上传用户创作内容和采集故障绝不影响业务两项技术边界。旧 v1.0 规划仅作为本 Session 的历史决策记录，不再是现行方案；仍未实施源码或外部配置。
