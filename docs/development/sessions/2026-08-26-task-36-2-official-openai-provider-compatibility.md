# Session｜Task 36.2 官方/非官方 OpenAI-compatible 端点适配补丁

| 字段 | 值 |
|---|---|
| session_id | `2026-08-26-task-36-2-official-openai-provider-compatibility` |
| status | `accepted / committed / push_authorized` |
| session_type | `task-implementation` |
| owner | Codex 主 Agent（临时全量接管） |
| started_at | `2026-08-26` |
| implementation_started | `true` |
| user_authorization | `2026-08-26 用户要求设计并实施 36.2；随后明确 36.1 与 36.2 联合验收` |
| joint_user_acceptance | `2026-08-27 用户明确验收通过、将 36.2 定义为官方/非官方端点适配，并授权两个任务推送` |
| base_commit | `e0a9509 docs: accept Milestone 9 results` |
| working_tree_dependency | `Task 36.1 verified/uncommitted changes retained` |
| acceptance_contract_id | `mvp-task-36-2-official-openai-provider-compatibility-v1` |
| revise_round | `1` |
| context_packet | `docs/plans/2026-08-26-task-36-2-official-openai-provider-compatibility-packet.md`（gitignored） |
| focused_commit | `bf3d1ed fix: adapt official and compatible OpenAI endpoints` |

## 目标

省略官方 `gpt-5.6` 不接受的固定 Chat `temperature=0` 与官方 `gpt-image-2` 不支持的 Images `response_format`；并修复官方多图 edit 必须使用 multipart `image[]` 数组字段的兼容缺口，同时保持单图 `image`、源图顺序、结构化输出、重试/错误归一化和中转站响应兼容。

本 Task 的正式名称为“官方/非官方 OpenAI-compatible 端点适配补丁”：官方端点按已确认契约发送请求；非官方兼容端点继续使用可配置 Base URL/模型 ID、Bearer 鉴权、结构化 fallback 以及 `b64_json`/URL 双响应解析。该命名不扩张实现范围。

## 冻结范围

- Acceptance Ledger：T36.2-001..008；planning rulings：T36.2-R01..R04。R03 仅保留为 round 0 历史，R04 是 revise round 1 的执行裁决。
- 产品写范围仅 `openai_compatible.py` 与对应 provider tests。
- 不改设置、frontend/API/OpenAPI/schema、generation orchestration、Canonical、试用、版本/发布或 M10；不调用真实 Provider。

## 联合验收裁决

Task 36.1 已完成主 Agent 全量验证和 detector PASS，用户明确将其验收延后并与 36.2 合并。36.1 Session 关闭为 `verification_complete / deferred_to_joint_acceptance`，其产品与控制面改动原样保留；本 Session 是唯一活动修改型 Session。36.2 通过 worker、主验收与 detector 后，统一进入 36.1 + 36.2 用户验收，不提前提交。

## 当前进度

- 用户 2026-08-27 的真实官方 API 联合验收在多图 edit 返回 HTTP 400：重复标量 `image` 不被接受，Provider 要求数组语法 `image[]`。这使 round 0 的联合验收失败并触发 revise round 1；未提交、未 push。
- 官方 Create image edit 文档的多图示例使用重复的 `image[]`；本轮冻结最小修复为：一张源图继续发送单个 `image`，两张及以上发送按输入顺序重复的 `image[]`，不增加请求或 Provider 分支。
- 以下 round 0 验证证据继续作为历史保留，但不代表 round 1 已完成；round 1 必须重新执行 worker、主 Agent 验收和 detector。
- round 1 `luna_worker`（gpt-5.6-luna/max）RED：两条聚焦 edit 请求测试为 `1 failed, 1 passed, 44 deselected`，多图断言观察到 `image[]` 为 0；GREEN：provider `46 passed`、Ruff PASS、diff-check PASS，改动仅两个 allowed files，scope delta `none`。
- round 1 最小实现：`image_field = "image" if len(source_images) == 1 else "image[]"`；循环和文件名不变，因此输入顺序不变，没有额外请求、Provider 分支或响应解析变化。
- 主 Agent round 1 独立复跑：provider `46 passed`；generation/trial/M9 `80 passed`；全后端 `781 passed, 2 skipped`（两条既有 duplicate-ZIP warning）；Ruff PASS；mypy 92 source files PASS；OpenAPI drift PASS；diff-check PASS。
- 主 Agent 沙箱内相关 pytest 与 OpenAPI 首次执行分别受 pytest basetemp 和应用工作区 Windows ACL 阻塞；获准在沙箱外使用同一测试/检查命令后通过，未改产品代码规避环境问题。
- `detector`（gpt-5.6-sol/medium，只读）round 1：`PASS`；T36.2-001..008 全部 PASS，R03 仅作为历史 superseded、R04 已应用；`must_fix: []`、`optional_hardening: []`、`new_design: []`、`scope_delta: none`。detector 独立复跑 provider `46 passed`、相关 `80 passed`、全后端 `781 passed, 2 skipped` 及全部静态/契约门禁。
- round 1 双重验证完成，当前重新进入 36.1 + 36.2 联合用户验收；尚未提交或 push。

- 已核对用户报告、现有适配层、fake-provider tests 与官方 OpenAI API 文档。
- 已确认两项最小修复：Chat 省略 `temperature`；GPT Image generation/edit 省略 `response_format`，保留 `b64_json`/URL 双解析。
- 详细计划与 Context Packet 已完成依赖闭包，状态为 `READY_FOR_IMPLEMENTATION`。
- `luna_worker`（gpt-5.6-luna/max）按测试先行完成两个获准文件；RED 为 provider `36 passed, 10 failed`，失败均精确对应旧请求仍含 `temperature` 或 Images `response_format`。
- 最小实现只删除三处固定字段：共用 Chat body 的 `temperature=0`、image generation/edit 的 `response_format=b64_json`；结构化 Chat 的 JSON Schema `response_format`、multipart 字段/顺序、`b64_json`/URL 解析及重试/错误逻辑保持不变。
- worker GREEN：provider `46 passed`；generation/trial/M9 相关 `80 passed`；Ruff、mypy、OpenAPI drift、diff-check 全绿；scope delta `none`。
- 主 Agent 独立复跑：provider `46 passed`；generation/trial/M9 相关 `80 passed`；全后端 `781 passed, 2 skipped`（仅两条既有 duplicate-ZIP warning）；Ruff clean；mypy 92 source files clean；OpenAPI drift PASS；`git diff --check` PASS。
- pytest 使用独立 `C:\\tmp` basetemp 避开既有 Windows 临时目录 ACL；未调用真实 Provider、未读取真实 Key、未产生费用。
- `detector`（gpt-5.6-sol/medium，只读）round 0：`PASS`；T36.2-001..008 与 T36.2-R01..R03 全部通过，`must_fix: []`、`optional_hardening: []`、`new_design: []`、`scope_delta: none`。
- detector 独立复跑 provider 为 `46 passed`；其组合回归受 Windows temp ACL 阻塞，但主 Agent 同组 `80 passed` 和全后端 `781 passed/2 skipped` 已使用独立 basetemp 成功，不构成产品失败。
- round 1 已完成双重验证并进入 36.1 + 36.2 联合用户验收。未提交、未 push、未提升版本、未 tag、未发布，也未开始 M10。
- 用户于 2026-08-27 明确联合验收通过并授权两个任务提交、push；仍未授权版本提升、tag 或 GitHub Release。
- focused product commit 已创建：`bf3d1ed`；控制面记录提交后与 36.1 一并 push。

## 联合人工验收

使用官方 Base URL、用户选定的文本/视觉模型和 `gpt-image-2` 完成一次 fresh Ask Gus：

1. 菜品分析与 Gus 结构化设计不再出现 `temperature` 参数 HTTP 400；
2. fresh icon 使用本次原图生成，16×16 轮廓、主色、摆盘与关键食材符合 Task 36.1 目标；
3. `gpt-image-2` icon/preview edit 不再因 `response_format` 被拒绝，任务能到达结果页；
4. 如方便，再用已有 Canonical 命中样本确认历史 icon 仍直接复用。

真实 API 运行由用户执行并承担费用；自动验收未读取 Key 或产生费用。用户明确接受后，主 Agent按两个 Task 的 focused commit 边界提交；push 仍需单独授权。
