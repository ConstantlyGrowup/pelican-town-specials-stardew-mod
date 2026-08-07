# Session｜2026-08-07-milestone-5-1-state-management-planning

| 字段 | 值 |
|---|---|
| `session_id` | `2026-08-07-milestone-5-1-state-management-planning` |
| `session_type` | planning（只产出需求定义与规划，不实施） |
| `state` | planned（2026-08-07 用户授权后转为 development：按 19.1→19.6 连续开发，用户本人统一验收，不走 Codex；控制面改动未提交） |
| `date` | 2026-08-07 |
| `task` | 定义 Milestone 5.1：生成状态管理（前后端）重构 |
| `acceptance_contract_id` | 未生成（各 Task 的 Context Packet 在开发授权后逐个生成） |
| `revise_round` | 不适用（无实施） |
| `base_commit` | `3817a10` |
| `review_route` | 用户明确指令：本轮由用户本人验收，**不通过 Codex 审阅** |

## 1. 触发：Milestone 5 验收结果（用户 2026-08-07 报告）

用户对 `2026-08-07-post-acceptance-slot-leak-fix` 的 3 项复验给出结果：

| 复验项 | 结果 | 用户原话要点 |
|---|---|---|
| ① 生成中切页→回草稿 | **部分通过** | 不再误报「开始生成」/busy，点击重新生成能正常启动；但**需求理解不全面** |
| ② 删除草稿后新建生成 | **未通过** | 删除生成中的草稿后，新任务仍报「当前已有一个生成任务在运行，请稍后重试。」 |
| ③ reload/重开 exe 自恢复 | 未单独报告 | 用户在 ① 中指出刷新后「所有状态消失了」，与预期不符 |

用户对 ① 的需求澄清（权威需求来源）：

> 我指的是我们进入生成阶段后，刷新/去其他页面，后面再返回这个草稿，都能回显当前的生成状态，**继承的是同一个生成任务**；而当前改成的是当我刷新后，所有状态消失了，但是我可以重新生成，不会阻塞，这和预期不符。

用户结论：

> 我认为当前系统的整体（前后端）的状态管理一直存在问题，还需要修复。

## 2. 根因诊断（包工已读代码确认）

两个现象不是独立缺陷，是同一条架构不变量缺失的两个表现：**生成状态的真相源在错误的位置。**

生成状态实际活在两个易失位置：前端模块内存（`frontend/src/features/generation/generationStore.ts` 的 `states` Map）和那条 HTTP NDJSON 流。持久化的 attempt 记录本身一直在写——`orchestrator.py:714` 每阶段 `self._attempts.save(self._advance_stage(...))` 落盘 `GenerationAttempt.current_stage`/`stages`/`status`——但**没有任何接口把它读出来**。`GenerationAttemptPublic`（`backend/src/pelican_town_specials/domain/draft.py:199`）已定义却全仓库零使用；`frontend/openapi.json` 中生成相关端点只有 `generate` 与 `cancel`。

### 2.1 现象①：刷新后状态消失 —— 断开被定义成了「取消」

`backend/src/pelican_town_specials/generation/orchestrator.py:716`：

```python
except GeneratorExit:
    # A client disconnect (abort / close / page nav) equals cancel
    self._rollback_cancelled(state, staged)
    raise
```

上一轮修复（`af08da4`）新增的 `_ClosingStreamingResponse`（`backend/src/pelican_town_specials/api/routes/generation.py:20`）还把这条断开路径做成了**确定性**触发。由此：

- SPA 内切页（不刷新）→ 模块 store 存活 → 进度保留（F19-2 生效，即用户 ① 中「通过」的部分）；
- 浏览器刷新 / 关标签重开 → fetch 连接销毁 → 后端判定断开 → draft 回滚 READY + 槽释放 → 状态全部归零，但可重新生成。

即：上一轮为治槽泄漏，把「客户端断开」钉成了权威取消语义，与用户「继承同一个生成任务」的要求方向相反。**生成任务的生命周期被绑在 HTTP 连接上，而不是绑在服务端。**

### 2.2 现象②：删除草稿完全没触达生成注册表

`backend/src/pelican_town_specials/application/drafts.py:551` `_delete_draft_record` 只做三件事：删独占资产、`self._attempts.delete_for_draft(draft_id)`、`self._drafts.delete(draft_id)`。而 `DraftService.__init__`（`drafts.py:401`）**没有** `AttemptRegistry` 或 orchestrator 引用——无 `request_cancel`、无 `release_slot`。

删除一个正在生成的草稿后：该 asyncio task 仍在跑并占着进程级单槽；流对象在模块级 store 中，导航到首页也不会断开；它下一次 `control_write` 会在已删除记录上抛 `FileNotFoundError`，而 `_rollback_cancelled`（`orchestrator.py:1094`）只捕 `RevisionConflictError`/`AttemptMismatchError`。槽由此永久挂住 → 后续所有生成返回 `PTS_GEN_BUSY`。

### 2.3 更底层：槽是一个无主布尔量

`backend/src/pelican_town_specials/generation/attempt_registry.py:16` 的 `self._occupied = False` 无归属信息，没人能回答「现在这个槽是谁的」。因此任何漏释放路径都无法自愈——上一轮加的三层兜底（`_generate` finally、`_SlotGuardedAsyncIterator.__del__`、路由 `aclose`）本质都是在给这个无主状态打补丁，而不是消除它。

## 3. 用户已确认的设计决策（2026-08-07）

| ID | 决策点 | 用户选择 |
|---|---|---|
| D5.1-1 | 刷新后前端如何恢复生成状态 | **只读进度端点 + 前端轮询**（不做可重连 NDJSON 流） |
| D5.1-2 | 改动范围 | **完整状态管理重构**（下述 6 处改动全做），作为 Milestone 5.1 |
| D5.1-3 | 生成期间无浏览器连接时的空闲退出 | **生成中视为活动，应用不退出** |
| D5.1-4 | 审阅路由 | 本轮由用户本人验收，不通过 Codex 审阅 |

## 4. Milestone 5.1 需求定义

### 4.1 需求（权威来源：用户 2026-08-07 消息）

- **R5.1-1｜生成任务服务端所有权与状态继承**：进入生成阶段后，刷新页面、切到其他页面、关闭标签再重开，返回该草稿都必须回显**同一个**生成任务的当前状态（继承，非重启）。客户端断开不得取消或回滚服务端生成。
- **R5.1-2｜删除即真正清除生成状态**：删除草稿必须真正清除其生成状态并回收生成槽；删除一个生成中的草稿后，新建生成不得报 `PTS_GEN_BUSY`。
- **R5.1-3｜状态管理不变量修正**：持久化的 attempt 记录成为生成状态唯一真相源，HTTP NDJSON 流与前端 store 降级为其视图/缓存；生成槽从无主布尔改为可归属、可对账、可自愈。

### 4.2 目标不变量

1. 生成任务的生命周期由服务端拥有，不由任何 HTTP 连接的存活决定。
2. 生成状态的唯一真相源是持久化 attempt 记录（含 `current_stage`、`stages`、`status`）。
3. 生成槽任一时刻可回答「被哪个 draft 的哪个 attempt 占用」，并能与持久化状态对账自愈。
4. 删除 draft（含收集品级联）在删记录之前必然取消并回收其在跑的 attempt。
5. 前端任何挂载路径的初始状态都从服务端 hydrate，模块 store 只做缓存。

### 4.3 用户可见契约变更（本 Milestone 明确改变已冻结行为）

必须显式记录，因为这反转了 Milestone 5 修复的一部分语义：

- **新增**只读进度端点（OpenAPI 契约新增路径），需再生成 `frontend/openapi.json` 与前端类型。
- **变更**：刷新/切页/重开标签后回显同一生成任务（原行为：状态归零）。
- **变更**：客户端断开不再回滚 draft，也不再取消生成（原行为：断开即取消，`orchestrator.py:716` + `_ClosingStreamingResponse`）。
- **变更**：删除生成中的草稿即时取消并释放槽（原行为：槽泄漏 → 永久 busy）。
- **变更**：生成期间应用不因空闲阈值退出（原行为：10 分钟空闲退出不区分是否在生成）。

## 5. Task 分解（6 个 Task，每个单独 Context Packet + 本地 focused commit）

**编号：** 使用 `19.1`–`19.6`。本 Session 初稿曾用 20–25，但 `docs/plans/MVP_IMPLEMENTATION_PLAN.md` 的 Task 20 / Task 21 已分配给 Milestone 6（CI/README、视觉精修与最终验收），故改为 19.1–19.6 并已按依赖顺序排列（顺序执行即满足依赖）。权威定义见该计划 v0.6 的 Milestone 5.1 章节。

| Task | 目标 | 主要文件（预估，最终以各 Packet 的依赖闭包为准） |
|---|---|---|
| **19.1** | `AttemptRegistry` 槽归属化：`_occupied: bool` → 持有者记录（`draft_id`/`attempt_id`），与持久化 attempt 对账并自愈；busy 错误携带占用方 | `generation/attempt_registry.py`、`generation/orchestrator.py` |
| **19.2** | 生成改为服务端拥有的后台任务；断开语义由「取消」改为「detach」 | `generation/orchestrator.py`、`api/routes/generation.py`、`application/generation.py` |
| **19.3** | 新增只读生成进度端点，复用已存在未使用的 `GenerationAttemptPublic`；再生成 OpenAPI 与前端类型 | `api/routes/generation.py`、`application/generation.py`、`domain/draft.py`、`frontend/openapi.json`、`frontend/src/api/generated/schema.d.ts` |
| **19.4** | 删除/级联删除前取消并回收在跑 attempt；`_rollback_cancelled` 对已删除记录容错 | `application/drafts.py`、`application/cookbook.py`、`api/dependencies.py`、`api/app.py`、`generation/orchestrator.py` |
| **19.5** | 前端挂载时从服务端 hydrate；GENERATING/REGENERATING 期间轮询进度端点；`generationStore` 降级为缓存 | `frontend/src/features/generation/generationStore.ts`、`useGeneration.ts`、`AskGusReviewPage.tsx`、`BlueprintEditorPage.tsx`、`HomePage.tsx` |
| **19.6** | 生成中计入活动，空闲退出不在生成中途触发；startup sweep 收窄为只处理真正跨进程遗留孤儿 | `api/app.py`、`launcher/main.py` |

依赖：19.2 依赖 19.1 的可归属槽；19.4 依赖 19.1 + 19.2；19.5 依赖 19.3 的契约产出；19.6 依赖 19.1 的槽占用查询。

## 6. 已知会失效的既有测试（规划期已识别，非实施期意外）

以下测试编码了「断开即取消」的旧语义，Milestone 5.1 必须改写它们，而不是绕过：

- `test_aclose_releases_slot_and_rolls_back`（aclose 后期望 draft READY + attempt CANCELLED）
- `test_closing_streaming_response_closes_iterator_on_disconnect`
- `test_cancel_orphaned_attempt_rolls_back`
- 前端 `frontend/src/features/generation/useGeneration.test.tsx` 的取消/竞态用例
- E2E `frontend/e2e/generation.spec.ts`、`frontend/e2e/full-journey.spec.ts`

改写这些测试属于对应 Task 的验收范围内工作，不构成 scope 越界。

## 7. 范围外（明确不做）

- 可重连的 NDJSON 实时流（D5.1-1 已选轮询；若将来要做需另立 Task）。
- 多并发生成（仍是进程级单槽，只是变为可归属）。
- 数据库、队列、事务日志、sidecar 或跨进程状态存储。
- 生成阶段划分、prompt、图像管线、Mod 编译与导出逻辑的任何改动。
- Milestone 4 / Milestone 5 已完成 Task 的功能回退或重做。

## 8. 遗留与影响

- **Milestone 5 push 门保持关闭**：Milestone 4 + Milestone 5 本地 commits（含 `af08da4`）仍未 push。因 Milestone 5 验收未全部通过，统一 push 推迟到 Milestone 5.1 完成后与用户一次性决定。
- **`af08da4` 的处理方式**：不回退该 commit。其「槽必被释放」的目标由 Task 19.1 的归属映射 + 对账正式实现；其「断开即取消」的语义由 Task 19.2 反转。历史保留，行为演进。
- **预存 mypy 错误**：`api/app.py:326`、`application/exports.py:194/226` 仍未清（HEAD 预存，已用 stash 基线确认与槽泄漏修复无关）。Task 19.4/19.6 会触及 `app.py`，可顺带清理，但不作为本 Milestone 的验收项。
- **正式实施计划已补齐**（2026-08-07 同一 Session 内）：`docs/plans/MVP_IMPLEMENTATION_PLAN.md` 升至 v0.6，在 Milestone 5 与 Milestone 6 之间插入完整的 Milestone 5.1 章节（Task 19.1–19.6，含 Files/Interfaces/Steps/测试命令/commit 边界），并同步了 Plan Status、里程碑验收总表、设计覆盖与自审表、变更记录。文档权威缺口已消除。
- **技术设计文档未更新**：`docs/architecture/MVP_TECHNICAL_DESIGN.md`（gitignored，用户可见机制与错误协议的权威源）尚未写入本轮的 5 项用户可见契约变更（尤其「断开不再取消生成」与新增进度端点）。按 CONSTRAINTS「改变用户可见机制先更新设计并获得用户确认」，这属于开发授权前应补的一步；用户已在本 Session 明确确认这些行为变更，故不构成 `BLOCKED`，但设计文档需在 Task 19.2 / 19.3 实施前或同期回写。

## 9. 下一步

用户已授权（2026-08-07）连续开发 Milestone 5.1 全部 6 个 Task，仅需明确介入时停止；所有子任务完成后由用户本人统一测试验收（D5.1-4），不桥接 Codex 审阅。包工已生成 Task 19.1 Context Packet（`m5.1-task-19.1-slot-attribution-v1`，`docs/plans/2026-08-07-task-19-1-slot-attribution-packet.md`）。技术设计文档的契约回写建议与 Task 19.2 / 19.3 同期完成。
