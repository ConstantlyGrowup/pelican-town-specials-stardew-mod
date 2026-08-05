# Session｜2026-08-05-r10-buff-tooltip-prompt

| 字段 | 值 |
|---|---|
| `session_id` | `2026-08-05-r10-buff-tooltip-prompt` |
| `session_type` | milestone-acceptance-fix |
| `state` | committed |
| `date` | 2026-08-05 |
| `task` | Milestone 3 验收修复（R10）：Buff 与持续时间改为游戏词条逐行样式 |
| `acceptance_contract_id` | `milestone3-acceptance-fix-r10-buff-tooltip-rows` |
| `revise_round` | 0 |
| `base_commit` | `a727a8f` |

## 用户确认的目标

- 非零 Buff 属性按图中样式逐行展示，例如 `速度 +1`、`幸运 +1`。
- Buff 行左侧使用匹配的星露谷式像素状态图标，不显示 Buff ID 或内部英文键名。
- Buff 存在时，在分隔线后用时钟图标显示 `持续时间：H:MM`；售价作为最后的金币图标行。
- 无 Buff 时，不生成 Buff 行和持续时间行。
- 保持 R9 的 Stardew item hover tooltip 硬锚点与低设计词密度。

## 实施边界

详见 `docs/plans/2026-08-05-r10-buff-tooltip-prompt-packet.md`。不改变领域、API、前端、持久化或 Mod 导出，不调用真实图像 Provider。

## 实现

- `build_full_tooltip_prompt` 为 12 个 Buff 属性提供固定中文显示名；只输出非零属性，并用显式正负号逐行表示。
- Buff ID 和 `speed`、`luckLevel` 等内部字段名不再进入 EDIT prompt。
- `durationMinutes` 确定性转换为 `H:MM`；420 分钟为 `7:00`，490 分钟为 `8:10`。
- prompt 仅补充必要的布局规则：恢复/Buff 行匹配像素状态图标、Buff 后分隔线、持续时间时钟图标、售价金币图标且售价为末行。
- 无 Buff 分支明确省略 Buff 与持续时间行；Ask Gus 与 Blueprint 仍共用同一个 prompt builder。

## 验证与审阅

- TDD RED：旧 prompt 在新增的 Buff/持续时间测试中 2 failed（暴露内部字段、分钟格式、无 Buff 省略规则不足）。
- GREEN focused：20 passed。
- 全量 backend：465 passed、2 skipped。
- Ruff、Mypy、`git diff --check`：通过。
- 主会话 prompt 快照：`BUFF_PROMPT_OK chars=525 order=luck,speed,duration,price`。
- 独立只读 Review：PASS，revise round 0，六项 criterion 全部通过，无 MUST_FIX。
- 未调用真实 Provider；最终视觉接近度等待用户重测。

## 实际模型与路由

```yaml
actual_models:
  main: Codex GPT-5 family（精确型号与 effort 未暴露）
  implementer: gpt-5.6-sol（继承 effort，标签未暴露）
  review: gpt-5.6-sol / max
review_route_note: 项目文档指定的 gpt-Luna 路由在当前工具面不可用；未静默冒充，实际审阅模型如上。
```

## 提交

- 本地 focused commit：`732b3ac fix: format buff rows in stardew tooltip prompt`。
- 未 push；等待 Milestone 统一验收。
