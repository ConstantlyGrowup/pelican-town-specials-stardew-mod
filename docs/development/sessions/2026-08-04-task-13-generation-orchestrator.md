# Session｜2026-08-04-task-13-generation-orchestrator

| 字段 | 值 |
|---|---|
| `session_id` | `2026-08-04-task-13-generation-orchestrator` |
| `session_type` | `implementation` |
| `state` | `committed` |
| `date` | `2026-08-04` |
| `task` | MVP Task 13：Ask Gus 生成 Orchestrator、NDJSON 与完整重生成 |
| `acceptance_contract_id` | `mvp-task-13-5949516-20260804-final-v1` |
| `revise_round` | `0`（首轮独立 Review PASS，无 REVISE 轮次） |
| `owner` | Claude Code 主会话实现与协调；独立只读 Review Subagent 复审 |
| `base_commit` | `da62a1b`（Task 12）；本 Session 恢复自上下文溢出后的未提交工作树 |

## 实际模型与 effort

```yaml
actual_models:
  main/implementer: deepseek-v4-flash / effort: default
  review: Claude Code general-purpose Review Subagent
```

> 说明：本 Session 是用户直接驱动的 Claude Code 会话（非 Codex 主 Agent 协作）。实现、协调、验收证据与 focused commit 均由主会话完成；独立 Review Subagent 按 AGENTS.md 的只读复审协议执行并返回 PASS。

## 背景：上下文溢出恢复

上一 Task 13 尝试在生成 orchestrator 主流程时发生上下文溢出，工作树停留在部分状态：`generation/orchestrator.py` 已写主流程但有 18 处 mypy 错误且候选 draft 未在阶段中构建；`application/generation.py`、`api/routes/generation.py`、app.py 装配、OpenAPI 导出与 `tests/generation/` 均缺失。本 Session 从该未提交工作树继续，未丢失任何已验证工作。

## 目标

实现 Ask Gus 初始生成与完整重生成编排：阶段顺序执行、NDJSON 流式事件、单生成 semaphore（`PTS_GEN_BUSY`）、取消（attempt CANCELLED + 草稿回滚）、失败原子性（旧结果保持/新结果整体替换、revision +1）、启动恢复（遗留 RUNNING → INTERRUPTED）。

## 不包含

真实模型调用（Provider Gateway 已在 Task 11 建立，本 Task 只消费 `ModelGateway` 协议）、Blueprint 视觉更新与 `STALE_PREVIEW` 规则（Task 14）、Content Patcher 编译、导出/发布、前端页面、数据库。测试全部使用 FakeGateway，不产生模型费用。

## 实现证据

- `generation/`：`orchestrator.py`（阶段循环、候选构建、原子 promote、取消/失败回滚、`_SlotGuardedAsyncIterator` 槽位释放）、`events.py`（NDJSON 事件）、`attempt_registry.py`（单槽 + 取消状态）。
- `application/generation.py`：`GenerationService.begin_generation`（流式 NDJSON）+ `cancel`。
- `api/routes/generation.py`：`POST /drafts/{id}/generate`（`application/x-ndjson`）+ `POST /drafts/{id}/cancel`（202）；`app.py` 装配 orchestrator/gateway factory/attempt repository 与 lifespan 启动恢复；`dependencies.py` 新访问器。
- 依赖闭包：`persistence/repositories.py`（`control_write` 允许 `expected_attempt_id=None` 启动新 attempt、`promote` 原子 revision+1、`GenerationAttemptRepository` 含 `currentStage` 归一化）；`domain/errors.py`（`ErrorPayload`/`ErrorEnvelope`/`recommended_action`）；`domain/state_machine.py`（`GENERATION_CANCELLED`/`REGENERATION_CANCELLED`，revision 归持久化所有）；`providers/contracts.py`（`ModelGateway` Protocol）；`catalog/mapping.py`（`_SemanticIngredientLike` Protocol）；`api/error_handlers.py`（共享 ErrorEnvelope）；`images/preview_compositor.py`（mypy 1.20 新暴露的裸 `dict` 注解修复）；`config.py`（`ask_gus_min_confidence`）。
- 契约：`frontend/openapi.json` 与 `frontend/src/api/generated/schema.d.ts` 重新导出（新增 generate/cancel 路径）。
- 测试：`tests/generation/`（conftest + test_ask_gus + test_regeneration + test_cancellation）+ `tests/api/test_generation_stream.py`。

## 验证结果

- 新增生成测试：`backend/tests/generation` + `backend/tests/api/test_generation_stream.py` **10 passed**。
- 回归：`backend/tests/domain`、`persistence`、`providers`、`images` **177 passed**；全量后端 **420 passed / 2 skipped**。
- 前端：`contract:generate`、`build`、`lint`、`test:run`（36 passed）全部通过。
- 静态：Ruff（src + tests）、mypy（68 源文件）clean；`git diff --check` clean（仅 LF/CRLF 提示）。
- 人工验证：orchestrator 直接运行确认低置信度/失败/成功/取消路径，FakeGateway 调用计数与阶段预期一致。

## Review 结果

- 首轮（independent Review Subagent，只读）：`PASS`，无 MUST_FIX、无 NEW_DESIGN。
- 已核对 8 项冻结验收要求：阶段顺序、低置信度停止（`PTS_GEN_LOW_CONFIDENCE` 且不调用 gameplay/image）、完整重生成原子性（失败保持旧结果、成功替换全部核心字段与两类视觉资产 + revision +1）、单生成槽（`PTS_GEN_BUSY` + 释放）、取消回滚、启动恢复、API NDJSON 流/202、静态检查 clean。

## 非阻塞观察（记录为加固项，未进入本 Task）

- generate 端点在 OpenAPI 中的 200 响应 content type 声明为 `application/json`（空 schema），运行时 header 正确（测试已验证）；文档可后续精化。
- `interrupt_running` 把遗留 RUNNING 改为 INTERRUPTED，但草稿可能停留在 GENERATING/REGENERATING 且 `active_attempt_id` 未清；该草稿需人工重置后恢复生成。Task 13 冻结范围外。
- `save_candidate`/`get_candidate` 未被 orchestrator 调用（attempt record 每阶段落盘）；设计中的按阶段候选落盘非本 Task 验收要求。
- 无 `interrupt_running` 与 regeneration-cancel 回滚路径的自动化测试。
- 计划清单含 `generation/stages.py`；阶段执行收敛在 `orchestrator._execute_stage`，无功能影响。

## 当前状态

- `state`: `committed`
- `next_action`: Task 13 Review PASS 后 auto_accepted + 本地 focused commit（`5949516`，不 push）；按里程碑粒度继续 Task 14（Blueprint 视觉更新与用户字段保护）。
