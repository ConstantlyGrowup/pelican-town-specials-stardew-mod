# Session｜2026-08-04-foreman-collaboration-model

| 字段 | 值 |
|---|---|
| `session_id` | `2026-08-04-foreman-collaboration-model` |
| `session_type` | control-plane（协作模型变更） |
| `state` | committed |
| `date` | 2026-08-04 |
| `task` | 采纳「包工-子代理-Codex 审阅」协作模型并更新控制面文档 |
| `base_commit` | `aca590b`（Task 13 控制面记录） |

## 背景与用户决策

用户评估了「每个 Task 独占一个新 thread」方案：每次新 thread 都要重新分发文档、重建状态理解，这部分是可复用的；且单终端监控下多 thread 不便 tracking。因此改为：

- Claude Code 主会话提权为**包工/协调者**（常驻单会话）：持有状态真源，为每个 Task 生成 Context Packet，组装前置文档包并分发，桥接 Codex 审阅，编排返工与本地提交，在 Milestone 粒度下长时间自动开发，仅在 `BLOCKED`、需要人工介入或 Milestone 完成时打断用户。
- 每个 Task 使用**新的实施子代理**（干净上下文），只接收该 Task 的 Packet + 关键规则 + 相关设计/计划章节 + 测试命令，返回 `TASK_HANDOFF`，不提交。
- **Codex** 为审阅者，经 codex-mcp **新建独立 thread** 路由 `gpt-Luna`/`effort: max`，返回 `PASS` / `REVISE` / `BLOCKED`。

用户经 AskUserQuestion 确认两点：
1. Context Packet 由**包工生成**（Codex 只做实施后审阅）。
2. 更新 `AGENTS.md` 等控制面文档并提交。

## 修改文件

- `AGENTS.md`：当前工作模式改为 Milestone 3 + 包工-子代理-Codex 审阅；串行 Session、验收与提交规则、全局自治协议的 `Main Agent` 职责改由包工承担；Task 9 实验门标记为已成功。
- `claude-code/CLAUDE.md`：角色从「实现 Agent」改为「包工/协调 Agent」；新增「每个 Task 的编排流程」；模型路由改为 包工 / Codex luna-max（新 thread）/ 实施子代理；Git 与状态安全明确子代理不提交、包工负责控制面更新；Task 9 试运行范围标记为历史；全局自治执行补充对齐。
- `docs/development/REVIEW_PROTOCOL.md`：模型与路由相关表述由 `Main Agent`/`Review Subagent` 对齐为 包工 / Codex Review / 实施子代理；审阅机制（Acceptance Ledger 冻结、两轮 REVISE 上限、PASS/REVISE/BLOCKED 语义、BLOCKED 证据规则）保持不动；Task 9 实验门与 §13 模型路由更新。
- `docs/development/STATUS.md`：当前状态表新增 `collaboration_model` 行。
- `docs/development/sessions/2026-08-04-foreman-collaboration-model.md`：本记录。

## 验证

- `git diff --check` clean（仅 LF/CRLF 提示）。
- 控制面文档一致性人工核对：AGENTS.md 读取顺序、串行 Session 规则、验收与提交规则、全局自治协议与 claude-code/CLAUDE.md、REVIEW_PROTOCOL.md 的包工/Codex 路由表述相互一致；审阅机制核心未变。

## 实际模型

```yaml
actual_models:
  main: deepseek-v4-flash（Claude Code 主会话）
  review: 本变更纯控制面文档，未触发 Codex 审阅；由主会话人工核对
```

## 当前状态

- `state`: `committed`
- `next_action`: 按新协作模型继续 Task 14 规划（生成 Context Packet → 开实施子代理 → 桥接 Codex 审阅）。
