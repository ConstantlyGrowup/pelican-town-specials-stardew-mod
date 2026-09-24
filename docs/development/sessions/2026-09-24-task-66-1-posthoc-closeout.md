# Session｜M14 Task66.1 事后翻译歧义结论收口

| 字段 | 值 |
|---|---|
| session_id | `2026-09-24-task-66-1-posthoc-closeout` |
| status | `accepted` |
| session_type | `documentation_maintenance` |
| owner | Codex 主 Agent |
| source_task | `2026-09-23-task-66-1-expanded-ingredient-holdout`（已完成且已提交） |

## 用户确认与边界

用户确认原版物品 `246` 的英文原名 `Wheat Flour` 与中文显示名 `大麦粉` 构成评测歧义：现实语义原料 `Wheat Flour` / `小麦粉` 非兜底映射到此 ID，应判为合理。用户接受以两侧统一的事后修正分析和 96 菜扩样结果收口当前 Task。本 Session 只更新报告与开发状态，不改冻结 Query/Gold、JEV 原始记录、评测代码、产品目录或默认链路；不执行 API 调用、推送、tag 或 Release。

## 只读复算与结论

从 ignored `output/m14-task66-1/metrics.json` 逐项复算：原始 JEV 判否而符合上述规则的 LEGACY 12 项、RAG 15 项；固定 96 菜全合理由原始 `41/96`→`59/96`，在相同修正规则下为 `48/96`→`71/96`，配对 23 改善/0 退步/73 持平。原始主指标不覆写；修正只能标为观察结果后的事后分析。旧 24 菜 `14/24`→`18/24` 不在本次重算范围，也不与 96 菜生成修正后累计指标。两组均为策划题集，非真实用户总体推断。

## 文档范围与验证

- `docs/development/M14_TASK66_1_EXPANDED_HOLDOUT.md`：增加修正规则、两侧复算和解释边界。
- `docs/development/STATUS.md`、`AGENTS.md`、原 Task66.1 Session：同步已收口状态，并保留历史记录。
- 本文件记录独立的文档维护提交，避免把原 Task66.1 focused commit 改写为两个实施提交。
- 验证：逐项只读复算、目录 `246` 名称核对、`git diff --check`；不重跑映射/JEV，不改 ignored 原始文件。
