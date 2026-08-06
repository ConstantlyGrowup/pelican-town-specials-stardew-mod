# Session｜2026-08-06-r17-gus-gameplay-pricing

| 字段 | 值 |
|---|---|
| `session_id` | `2026-08-06-r17-gus-gameplay-pricing` |
| `session_type` | acceptance-fix |
| `state` | committed |
| `date` | 2026-08-06 |
| `task` | R17：约束 Ask Gus 的原版风格金币定价 |
| `acceptance_contract_id` | `milestone4-r17-gus-gameplay-pricing-v1` |
| `revise_round` | 0 |
| `base_commit` | `324b509` |

## 用户确认的问题

- 当前玩法制定会给普通、甚至无 Buff 的菜设置明显偏高售价，例如 850g。
- 需要在 gameplay prompt 中按原版菜品经济尺度约束金币定价。
- 已验收的生图 prompt 不得修改。

## 本地原版数据基线

Stardew 1.6.15 `Category=-7` 共 85 项：中位数 200g、P90 400g；普通烹饪物最高 500g。仅 Oil of Garlic 1000g、Magic Rock Candy 5000g 两个特殊功能/传奇例外高于 500g。

## 实施边界

详见 `docs/plans/2026-08-06-r17-gus-gameplay-pricing-packet.md`。只做版本化 gameplay prompt、路由/provenance、测试和正式设计更新；不硬裁剪价格，不改变 schema/validator/编译器/生图管线，不调用真实 Provider。

## 当前进度

- Context Packet 已完成闭包检查。
- Implementer 按 TDD 完成 `ask_gus_v3`、provider 路由与 `ask-gus-v3` provenance；v1/v2 保留，v3 完整继承 v2 的 Buff 规则。
- 售价规则冻结为：普通菜 80..250g、精致菜 250..400g、明确高档或复杂菜 400..500g，多数结果 100..400g；普通或无 Buff 菜不得超过 500g，也不得用高价补偿无 Buff。超过 500g 仅限明确传奇或特殊功能性消耗品，并须在 `gusComment` 说明理由。
- 聚焦测试 49 passed；全量 backend 553 passed/2 skipped；Ruff、Mypy、diff-check 通过。独立只读 Review `PASS`，无 MUST_FIX。
- 生图 prompt、双图 EDIT 与图像管线未改动；未调用真实 Provider。产品 focused commit：`5905360`。

## 验收与遗留

- 按 Milestone 自动路径进入 `auto_accepted` 并创建本地 commit，未 push。
- 本次只收紧生成 prompt，不对 schema 或持久化结果硬裁剪；已有草稿不会被改价，实际模型分布需用户后续重新生成观察。
