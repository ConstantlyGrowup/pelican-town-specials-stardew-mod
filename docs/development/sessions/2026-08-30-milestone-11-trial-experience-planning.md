# Session｜Milestone 11 试用体验与可用性保护规划

| 字段 | 值 |
|---|---|
| session_id | `2026-08-30-milestone-11-trial-experience-planning` |
| status | `accepted / committed` |
| date | `2026-08-30` |
| scope | 只规划试用额度结果提示与公共试用服务可用性保护；不修改产品源码、不调用真实 Provider |
| base_commit | `1ad271a docs: close v1.4.0 release session` |

## 用户需求

- 问问 Gus 与料理蓝图的试用结果都显示本次消耗试用及剩余次数；
- 公共试用 Key 欠费/失效或网关关闭时，避免用户在没有得到结果前白白损失试用机会；
- 公共试用额度耗尽或服务关闭时，有自行配置能力的新用户必须能明确切换到自己的 Provider 与额度，不能被公共试用阻塞；
- 评估无 Token 探测、最小 Token query，以及每次试用/每应用 Session 探测一次的取舍；
- 当前只增加并规划两个 Task，不进入开发。

## 调研与现状证据

- OpenAI 官方 `GET /models/{model}` 不生成内容，但只返回模型基本信息与 permissioning；它不能证明生成余额、Chat/Images 真实链路或非官方兼容网关实现。
- 最小 Chat query 仍会增加费用与等待，也不能验证图像链路；任何前置探测都存在探测与真实调用之间再次故障的时间差。
- v1.4.0 `TrialAccessService.claim_attempt()` 在首个 Provider 调用前永久增加 `claimedAttempts`；Provider 首次调用失败仍扣次。
- 当前 Settings API 只有实时 `remaining`；Draft/GenerationAttempt 没有“该次是否确认消费、确认后剩余次数”的持久快照，前端不能可靠显示历史结果事实。

## 规划裁决

- 不采用 `/models`、最小 Token query 或图片请求作为独立探测；每个 attempt 原本就需要的第一次真实 Provider 调用即为探测，额外 Token 为零。
- 额度改为按 attemptId 的 `reserve → first-success commit / pre-success failure release`；首次成功后的后续失败不退还。
- `trial-state.json` schema v2 区分 consumed 与 reservations，v1 claimed 无损迁移；不增加远程服务、定时器或中大型架构。
- 正式实施顺序按依赖调整为 Task 40 后端可用性/确认扣次，Task 41 显式个人额度接管，Task 42 前端结果提示；全部需求均保留。
- 已配置个人服务的用户在公共试用首调用失败时先显示错误；用户点击“改用我的服务继续”后才持久切为 `PERSONAL` 并重试。未配置用户点击“配置我的服务”后切换偏好并进入 Settings。未经确认不得自动产生个人费用。

## 产出

- `docs/architecture/TRIAL_EXPERIENCE_TECHNICAL_DESIGN.md` v1.0；
- `docs/plans/2026-08-30-milestone-11-trial-experience.md` v1.0；
- 同步 TD0、IP0、顶层规划、索引、CONSTRAINTS、STATUS 与 AGENTS 当前入口。

## 下一步

2026-08-30 用户明确要求“看到当前 M11 规划，请按照规划进行开发”，视为规划验收与开发授权。本规划 Session 关闭；focused commit 为 `docs: accept milestone 11 trial experience plan`。下一步从该干净基线为 Task 40 创建独立 `READY_FOR_IMPLEMENTATION` Context Packet，严格按 Task 40 → 41 → 42 实施；不自动 push、提升版本、tag 或发布。
