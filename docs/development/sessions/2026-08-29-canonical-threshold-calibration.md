# Session｜Canonical 发布阈值校准为 0.80

| 字段 | 值 |
|---|---|
| session_id | `2026-08-29-canonical-threshold-calibration` |
| status | `auto_accepted / committed next` |
| date | `2026-08-29` |
| owner | Codex 主 Agent（`luna_worker` 实施 / `detector` 独立审阅） |
| base_commit | `11cb287 release: bump version to 1.4.0 for M9 and M10` |
| acceptance_contract_id | `m9-canonical-threshold-080-release-v1` |
| revise_round | `0` |

## 用户授权

用户在 v1.4.0 push/tag 前明确要求把 `CANONICAL_MATCH_THRESHOLD = 0.80` 纳入发布版，以在当前没有额外命中率优化时提高召回；用户接受相对 0.90 更高的误命中风险。该指令覆盖此前“隔离现有 canonical.py 0.80 改动”的发布边界。

## 冻结范围

- 命中边界改为包含式 `confidence >= 0.80`；`0.80` HIT，低于 `0.80` MISS。
- 更新直接锁定阈值的 domain/application tests，以及正式 M9 技术设计、详细计划、MVP 设计/计划和开发状态口径。
- 不改变 `CANONICAL_MIN_VALID_COUNT = 2`、Top 5、同语言/现实原料候选、补充要求冲突、合法 candidate ID、完整重新生成/Blueprint 排除、HIT 复用或调用次数。
- 不 push、不 tag、不发布；PASS 和 focused commit 后恢复 v1.4.0 Release Session。

## 验收

- `M9-THRESHOLD-001`：发布源码常量为 `0.80`。
- `M9-THRESHOLD-002`：合法最高候选置信度恰为 `0.80` 时 HIT，`0.799` 时 MISS。
- `M9-THRESHOLD-003`：N=2、Top 5、候选合法性、冲突 context 和 fail-open 回归不变。
- `M9-THRESHOLD-004`：所有现行正式设计/计划和开发控制面不再把 0.90 描述为当前发布阈值；历史变更记录可保留并明确已由 0.80 校准取代。
- `M9-THRESHOLD-005`：用户其他文件和无关产品行为零改动。

## 实施与主 Agent 验证

- `luna_worker`（自定义角色，配置为 `gpt-5.6-luna` / `max`）在冻结范围内完成测试和正式口径同步；`implementation_scope_delta: none`，未提交、push、tag 或发布。
- 源码常量沿用用户明确指定的 `CANONICAL_MATCH_THRESHOLD = 0.80`；domain test 锁定 0.80。
- application test 将包含式边界改为合法候选 `0.80` HIT，新增合法候选 `0.799` MISS，并把冲突补充要求的 fake matcher 降为 `0.799`，继续验证冲突必须 miss。
- 正式 M9/MVP 技术设计与计划、CONSTRAINTS/STATUS 的当前阈值均同步为 0.80；历史 0.90 仅作为被 2026-08-29 校准取代的记录保留。
- 主 Agent RED 基线：旧锁定测试 `2 failed / 21 passed`，失败精确为常量仍期待 0.90、冲突 fake 0.899 在新阈值下成为 HIT。
- 主 Agent GREEN（沙箱外隔离 temp，绕开已知 Windows ACL）：focused `24 passed`；generation + registration + registry 回归 `114 passed`；Ruff PASS；mypy `96 source files` PASS；`git diff --check` PASS（仅 CRLF 提示）。
- detector round 0 `REVISE`：M9-THRESHOLD-001..004 与阈值行为均通过；唯一 must-fix（M9-THRESHOLD-005）是主 Agent 为标记暂停修改了不在 Packet allowed_files 的 Release Session。已按最小修复撤销该文件变化；没有产品代码返工。
- detector round 1 封闭复核 `PASS`：Release Session 相对 HEAD 零 diff；tracked 产品/控制面差异与 gitignored 正式设计/计划均在 Packet allowed_files 内；focused `24 passed`、diff-check PASS；`must_fix: []`、`optional_hardening: none`、`new_design: none`、`scope_delta: none`。
- actual models：implementer `gpt-5.6-luna/max`（自定义 `luna_worker`）；review `gpt-5.6-sol/medium`（自定义 `detector`）；主 Agent为当前 Codex 会话。
- 本 Task 进入 `auto_accepted`，创建单独 focused commit 后恢复 v1.4.0 Release Session。
