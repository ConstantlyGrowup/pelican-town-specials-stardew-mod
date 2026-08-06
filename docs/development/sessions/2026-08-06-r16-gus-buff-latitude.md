# Session｜2026-08-06-r16-gus-buff-latitude

| 字段 | 值 |
|---|---|
| `session_id` | `2026-08-06-r16-gus-buff-latitude` |
| `session_type` | acceptance-fix |
| `state` | committed |
| `date` | 2026-08-06 |
| `task` | R16：适度放宽 Ask Gus 的 Buff 推荐标准 |
| `acceptance_contract_id` | `milestone4-r16-gus-buff-latitude-v1` |
| `revise_round` | 0 |
| `base_commit` | `b7fa672` |

## 用户确认的目标

- 当前生图 prompt 的样式已经满意，本次不得修改。
- Ask Gus 玩法设计不应因标准过严而让大量菜品没有 Buff。
- 适度放宽而非无条件发放：普通但有鲜明玩法关联的菜可获得温和 Buff；仍保留合理性与平衡标准。

## 实施边界

详见 `docs/plans/2026-08-06-r16-gus-buff-latitude-packet.md`。本 Session 不改变领域/API/前端/编译器，不调用真实 Provider。

## 实现

- 新增 `ask_gus_v2`，完整保留 `ask_gus_v1` 作为历史版本。
- v2 明确：普通但有鲜明特点、且主食材/烹饪方式/风味/饮品特征/主题存在可信玩法关联时，通常推荐 1 个温和非零属性；只有两个效果明确互补时最多使用 2 个。
- 仍保留标准：非常朴素且无可信玩法关联时使用 `null`；禁止无关属性、夸张数值和夸张持续时间。
- Provider 新调用切换到 v2，新生成结果 provenance 记录 `ask-gus-v2`。
- 生图 prompt、双图 EDIT、图标与预览管线未修改。
- 正式技术设计 §18.3 与变更记录已更新至 v1.3。

## 验证与审阅

- TDD RED：2 个目标失败（v2 模块不存在、出站请求仍为 v1）。
- GREEN focused：48 passed。
- 全量 backend：552 passed、2 skipped。
- Ruff、Mypy（14 个源文件）、`git diff --check`：通过。
- 主会话 prompt 快照：`GAMEPLAY_PROMPT_OK chars=896`。
- 独立只读 Review：PASS，revise round 0，七项 criterion 全部通过，无 MUST_FIX。
- 未调用真实 Provider；实际 Buff 出现频率等待用户重新生成验证。

## 实际模型与路由

```yaml
actual_models:
  main: Codex GPT-5 family（精确型号与 effort 未暴露）
  implementer: GPT-5 Codex（继承 effort，标签未暴露）
  review: gpt-5.6-sol / max
review_route_note: 项目指定的 gpt-Luna 路由在当前工具面不可用；未静默冒充，实际审阅模型如上。
```

## 提交

- 本地 focused commit：`9d06e41 fix: relax ask gus buff recommendations`。
- 未 push；等待 Milestone 4 统一验收。
