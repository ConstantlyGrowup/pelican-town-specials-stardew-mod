# Session｜2026-08-07-post-acceptance-slot-leak-fix

| 字段 | 值 |
|---|---|
| `session_id` | `2026-08-07-post-acceptance-slot-leak-fix` |
| `session_type` | acceptance-fix |
| `state` | auto_accepted（待用户交互复验与 Milestone 统一 push） |
| `date` | 2026-08-07 |
| `task` | Milestone 5 验收未通过项修复：生成槽泄漏导致「有一个任务在运行」永久卡死 |
| `acceptance_contract_id` | 无（用户覆盖：本临时修复由用户直接验收，不走 Codex 审阅） |
| `revise_round` | 0（用户明确「不用通过 codex 审阅」） |
| `base_commit` | `febdef7`（Milestone 5 全量验证完成记录之后实施） |

## 任务范围

Milestone 5 一次性验收中用户报告 3 项未通过现象，全部由同一根因解释：

1. 进入生成阶段后，再进入原草稿，不显示当前生成阶段，默认显示「开始生成」；点击后提示「有一个任务在运行」——跨页进度保留（F19-2）没有生效。
2. 删除草稿后生成新草稿仍显示「当前已有一个生成任务在运行，请稍后重试。」——删除草稿没有打断原生成路径；关闭网页并重新打开 exe 后问题仍持续。
3. 模型侧控制台日志显示后续请求已停止，但系统卡在「当前已有一个生成任务在运行」。

用户指令：本修复由用户本人验收，**不通过 Codex 审阅**（用户明确确认的规则优先于所有项目文档）。

## 根因

Starlette 1.3.1 的 `StreamingResponse.__call__`（ASGI spec >= 2.4）在客户端断开时执行
`try: await self.stream_response(send) except OSError: raise ClientDisconnect()`，**从不调用
`body_iterator.aclose()`**。生成槽存放在 `_SlotGuardedAsyncIterator` 中——它只在
`aclose()`/迭代完成/异常时调用 `_release()`。因此：

- 断开后 body iterator 被 GC 终结，`_generate` 的 finally 通过 `inner.aclose()` 把 GeneratorExit
  传播进 `_run`，draft 回滚到 READY（所以 UI 显示「开始生成」）；
- 但 `_SlotGuardedAsyncIterator._release()` 从未运行 → `AttemptRegistry` 进程级单槽 `_occupied`
  永久为 True → 后续所有生成请求返回 `PTS_GEN_BUSY`「当前已有一个生成任务在运行」；
- 重开 exe 不恢复，因为槽是进程内状态；startup 只 `interrupt_running()` 打断 attempts，没有回滚
  draft / 释放孤儿槽，且没有新的 attempt 时孤儿 draft 保持 GENERATING 触发状态机 409。

三个用户现象（draft READY→「开始生成」、永久 busy、模型请求已停但系统卡死）均为该槽泄漏的直接后果。

## 实施（3 层修复）

- **槽在所有终止路径释放**（`orchestrator.py`）：`_generate` 的 `finally` 现在无条件
  `registry.release_slot()` + `unregister(attempt_id)`（先 `inner.aclose()` 回滚再释放）；
  `_SlotGuardedAsyncIterator.__del__` 作为 GC 兜底调用幂等 `_release()`（防 GC 路径只回滚不释放槽）。
- **路由级确定性关闭**（`api/routes/generation.py`）：新增 `_ClosingStreamingResponse(StreamingResponse)`，
  覆写 `stream_response` 以 `finally: await body_iterator.aclose()`，保证客户端断开/异常/正常完成都确定性地
  关闭迭代器（经 `getattr` 调用，兼容任意 AsyncIterable）。`generate_draft` 路由返回它。
- **孤儿 attempt 恢复**（`orchestrator.py` + `application/generation.py` + `api/app.py`）：
  - 新增 `GenerationOrchestrator.recover_interrupted(draft_id) -> bool`：读取 draft，若
    `active_attempt_id` 非空且 status ∈ {GENERATING, REGENERATING, STALE_PREVIEW} 则回滚
    （GENERATING→GENERATION_CANCELLED→READY、REGENERATING→REGENERATION_CANCELLED→REVIEWABLE、
    STALE_PREVIEW 保持），清除 `active_attempt_id`、写 `last_error=PTS_GEN_INTERRUPTED`，
    经 `control_write` 带 `expected_attempt_id` 写入，并把持久化 attempt 标记 `INTERRUPTED`；
  - `GenerationService.cancel` 改为：若 attempt 在本进程被跟踪（`AttemptRegistry.is_tracked`，
    `cancel()` 返回 True）则走原 `await_cancelled` 路径，否则对孤儿 attempt 直接
    `recover_interrupted`——使 `/cancel` 总能清掉卡死状态并释放槽；
  - lifespan startup 在 `interrupt_running()` 后新增 sweep：对所有带 `active_attempt_id` 且处于
    生成态的 draft 调用 `recover_interrupted`，重开 exe 时自愈。

## 验证证据

- 定向回归 10 passed：`test_aclose_releases_slot_and_rolls_back`（aclose 后 draft READY + attempt
  CANCELLED + 槽可用）、`test_recover_interrupted_rolls_back_generating_draft`（孤儿 GENERATING
  draft 回滚 + attempt INTERRUPTED）、`test_closing_streaming_response_closes_iterator_on_disconnect`
  （模拟 send 抛 OSError 后 probe.aclose 被调用）、`test_cancel_orphaned_attempt_rolls_back`
  （/cancel 清孤儿 GENERATING draft + 立即重新生成成功）。
- 全量 backend：**620 passed / 2 skipped**（92.77s，仅预存 zip 警告）。
- Ruff clean；Mypy clean（5 个改动源文件；app.py:326 与 exports.py 为 HEAD 预存错误，非本次引入，
  见下方「已知限制」）。
- 前端无改动：SPA 导航保留模块级 store（有既有单元测试覆盖）；reload 场景由后端自恢复
  （槽释放 + /cancel 孤儿回滚 + startup sweep）覆盖。未运行前端/E2E/重新打包。

## 验收与遗留

- 用户指令跳过 Codex 审阅，由用户本人交互复验：① 生成中切页→回到草稿后不再误报「开始生成」/busy；
  ② 删除草稿后生成新草稿不再 busy；③ reload/重开 exe 后系统可自恢复。
- 已知限制：本修复后端已通过全量自动测试；真实 exe 交互复验需要重新执行
  `scripts/build_windows.ps1` 生成新 bundle（本次未重新打包）；`api/app.py:326` 与
  `application/exports.py:194/226` 为 HEAD 预存 mypy 错误（stash 基线确认与本次无关）。
- 非阻塞观察：`recover_interrupted` 对 STALE_PREVIEW 保持原状态（回滚语义与其他生成态不同，
  属既有设计）；断开路径回滚消息使用 `PTS_GEN_INTERRUPTED`（区别于主动取消 `PTS_GEN_CANCELLED`）。
