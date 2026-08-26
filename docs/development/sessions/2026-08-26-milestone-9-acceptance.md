# Session｜Milestone 9 用户验收与推送

| 字段 | 值 |
|---|---|
| session_id | `2026-08-26-milestone-9-acceptance` |
| status | `accepted` |
| session_type | `milestone-acceptance-and-push` |
| owner | Codex 主 Agent |
| accepted_at | `2026-08-26` |
| implementation_tip | `3c3496b test: verify Milestone 9 canonical memory end to end` |
| user_acceptance | `验收通过。可以推送` |

## 验收范围

用户统一验收 Milestone 9 Task 31–36：SQLite Canonical Registry、正式 Ask Gus 归档登记、候选/matcher、Canonical HIT 复用、耗时/Gus 叙事，以及全链路/并发/隐私/Windows bundle 与 installer 验收。

## 用户真实对照

| 场景 | A 成本 | B 成本 | 平均成本 | A 耗时 | B 耗时 | 平均耗时 |
|---|---:|---:|---:|---:|---:|---:|
| 未命中 | `$0.447442` | `$0.549836` | `$0.498639` | `192s` | `190s` | `191s` |
| 命中 | `$0.432888` | `$0.443720` | `$0.438304` | `156s` | `119s` | `137.5s` |

- 两组均表现为命中后成本与耗时下降。
- 均值成本下降 `$0.060335`（约 `12.1%`）；均值耗时下降 `53.5s`（约 `28.0%`）。
- A 组成本/耗时约下降 `3.3% / 18.8%`；B 组约下降 `19.3% / 37.4%`。
- 样本量只有 `n=2`，且 Provider 单次消费与延迟存在外部波动；这些数据只作为本次 Milestone 的正向实测信号，不构成稳定节省、命中率或未来成本承诺。
- 未记录或提交原图、控制台凭据、完整响应、菜品内容或 Provider 配置。

## 推送边界

- 用户授权统一 push；`7addfb8..3c3496b` 已推送到 `origin/feat/mvp-implementation`，本验收控制面记录随后同步至同一分支。
- 用户已有未跟踪 prototype、samples、Claude/review/pytest 临时目录未纳入提交。
- 本次授权不包含版本提升、tag、GitHub Release 或 M10 实施。

## 最终状态

Milestone 9 进入 `accepted / pushed`。正式发布版本仍为 v1.3.0；后续发布或开始 M10 均等待用户新的明确授权。
