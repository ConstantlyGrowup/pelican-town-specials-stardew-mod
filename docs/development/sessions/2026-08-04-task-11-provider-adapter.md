# Session｜2026-08-04-task-11-provider-adapter

| 字段 | 值 |
|---|---|
| `session_id` | `2026-08-04-task-11-provider-adapter` |
| `session_type` | `implementation` |
| `state` | `committed` |
| `date` | `2026-08-04` |
| `task` | MVP Task 11：OpenAI 兼容 Provider Adapter 与能力 Probe |
| `acceptance_contract_id` | `mvp-task-11-4b58be0-20260804-final-v1` |
| `revise_round` | `1`（第一轮 REVISE 5 项、第二轮 REVISE 2 项均修复；两轮上限已达，最终以自动测试验证收尾） |
| `owner` | Codex Main Agent 规划与审阅；Claude Code Implementer 执行；Review Subagent（gpt-5.6-luna/max） |
| `base_commit` | `4b58be0`（Milestone 2 推送后 HEAD） |

## 实际模型与 effort

```yaml
actual_models:
  main: gpt-5.6-sol / effort: high
  review: gpt-5.6-luna / effort: max
  implementer: deepseek-v4-flash / effort: default（Claude Code）
```

## 目标

实现严格类型化的 OpenAI-compatible Provider Gateway、结构化输出降级与一次 repair、有界自动重试、SSRF 安全的临时图片 URL 下载与显式 capability probe；默认测试完全使用 fake provider，不产生模型费用。

## 不包含

Ask Gus/Blueprint 生成编排（Task 13/14）、图片归一化/图标/预览管线（Task 12）、前端进度 UI（Task 15）、新公开 API、数据库、Provider Registry、Content Patcher、发布流水线、`gpt-image-2-pro` 默认/fallback。

## planning_rulings（已应用）

`T11-RULING-001` 至 `T11-RULING-012` 全部按最终 Context Packet 应用。关键裁决：contracts DTO 补齐、`GeneratedDishCore` 不含 GameIngredient（保留 Task 13 目录映射边界）、`generate_image` 显式 GENERATION/EDIT 端点、b64_json 优先 + capability 降级、仅瞬时故障网络重试、统一 X-Request-ID、SSRF 安全下载、无 Key 零网络 probe 报告。

## 实现证据

- `providers/` 包：contracts、openai_compatible gateway、structured_output、retry、safe_download、prompts/analysis_v1 + ask_gus_v1。
- `scripts/probe_provider.py`：读取 `PTS_OPENAI_BASE_URL`/`PTS_OPENAI_API_KEY`/`PTS_VISION_MODEL`/`PTS_TEXT_MODEL`/`PTS_IMAGE_MODEL`，输出 ignored `output/spikes/provider-capabilities.json`，无 Key 零网络。
- 测试：`backend/tests/providers/` 18 passed（Bearer/Base URL 不重复、requestId、json_schema 降级、一次 repair、401 不重试、429/500 有界重试、edits multipart、b64 解码、SSRF 下载、probe 无 Key 报告、结构化输出边界）。
- 全量后端 379 passed/2 skipped；Ruff、mypy（60 源文件）通过。

## 真实 capability probe 状态

- 实施环境的 Bash 沙箱无法访问真实外网（探针在沙箱中全部 capability 为 false、elapsedMs 0，属环境限制而非真实能力结论）。
- 用户已提供中转站 Key 与模型配置（Base `https://yibuapi.com/v1`、文本/视觉 `gpt-5.6-luna`、图像 `gpt-image-2-max`）。
- 真实 probe 需用户在本机 PowerShell 显式设置五个 `PTS_*` 环境变量后运行 `python scripts/probe_provider.py`；只有真实 probe 执行后才按脱敏事实更新 ignored 的技术设计 §18、实施计划与项目索引，不得猜测或伪造。

## Review 结果

- 第一轮（revise_round=0，gpt-5.6-luna/max）：`REVISE`，5 项 MUST_FIX（AppError details 类型、5xx 覆盖/网络重试、safe_download 缓冲/空 DNS、probe 未探 JSON-only、测试矩阵不足）。均已修复。
- 第二轮（revise_round=1，gpt-5.6-luna/max）：`REVISE`，2 项 MUST_FIX（safe_download 追加前大小检查、双图 multipart 顺序断言）。均已修复并由自动测试验证。
- 协议规定全局最多两轮 REVISE，不再开启第三轮审阅；最终以自动测试证据（providers 27 passed、全量 388 passed/2 skipped、Ruff、mypy 60 文件）+ 真实 probe 全绿收尾，进入用户决策。

## 真实 capability probe 状态（成功）

- 用户本机显式运行 `python scripts/probe_provider.py`（Base `https://yibuapi.com/v1`、文本/视觉 `gpt-5.6-luna`、图像 `gpt-image-2-max`），**五项 capability 全部 supported=true**：`chatMultimodal` 34s、`chatJsonSchema` 34s、`chatJsonOnly` 13s、`imageEdits` 51s、`imageGenerations` 24s。
- 修复过程中由用户日志定位的两个根因已修复：strict json_schema 需 `required` 覆盖全部属性（`quantityHint` 缺失 400）；图片总像素需 ≥ 655360（`256x256` 被拒），probe 改用 `samples/牛肉0.jpg`（4032×2689）+ `size=1024x1024`。
- 真实事实已按 T11-RULING-010 回写 ignored 技术设计 §18.2（脱敏，不含 Key/图片正文）。

## 当前状态

- `state`: `committed`（本地 focused commit `10aa141` + 修复 `9555a55`；不 push，Milestone 3 统一验收后推送）
- `next_action`: 用户确认 Task 11 验收后，按里程碑粒度继续 Task 12。
