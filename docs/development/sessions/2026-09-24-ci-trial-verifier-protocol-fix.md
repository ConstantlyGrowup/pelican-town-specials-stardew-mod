# Session｜最近 CI：试用网关原料核验协议补齐

| 字段 | 值 |
|---|---|
| session_id | `2026-09-24-ci-trial-verifier-protocol-fix` |
| status | `committed` |
| session_type | `implementation` |
| owner | Codex 主 Agent |
| base_commit | `9807a5a` |
| acceptance_contract_id | `ci-trial-verifier-protocol-fix-v1` |
| revise_round | `0` |
| planning_status | `READY_FOR_IMPLEMENTATION` |

## 失败证据与冻结边界

最新远端 push CI run `35978864894`（commit `7b45e1a`）仅 `backend-fast` 失败；`frontend-fast` 成功，PR/main integration 按分层规则跳过。失败步骤为 `python -m mypy backend/src`，精确报错 `api/app.py:570`：`TrialSafeGateway` 缺少 `ModelGateway.verify_ingredient_candidates`，因此返回类型不兼容。Ruff 已通过，后续 backend 单测因 mypy 失败未执行。先前 run `35864006596` 成功。本次只补 Task67 新协议在试用安全网关上的转发及脱敏测试，不改 CI 分层或用户默认链路。

## Context Packet

```yaml
task_id: CI-trial-verifier-protocol-fix
base_commit: 9807a5a
planning_status: READY_FOR_IMPLEMENTATION
acceptance_contract_id: ci-trial-verifier-protocol-fix-v1
revise_round: 0
objective: 修复最新 push CI 的 ModelGateway 结构化协议不兼容，并保持试用网关脱敏边界。
user_visible_contract: 无新增 UI/API/设置、试用扣次或默认链路变化；显式 RAG 经过当前试用网关时仍只调用同一内层 Provider 一次并保护试用内部诊断。
planning_rulings:
  - conflict: Task67 给 ModelGateway 新增原料核验方法，但 TrialSafeGateway 仍只转发旧方法。
    sources: [CI run 35978864894 backend-fast mypy, providers/contracts.py, application/trial.py]
    decision: 为 TrialSafeGateway 增加与现有方法同型的单次转发及 AppError details 清空；不另选 Provider，不增加重试。
    rationale: 最小补齐协议并延续现有安全语义。
    user_visible_delta: none
contract_delta:
  documents: [docs/development/STATUS.md, 本 Session]
  domain: []
  persistence: []
  application_api: [TrialSafeGateway 内部方法]
architecture_budget:
  allowed: [一个转发方法、必要 DTO 导入、focused fake 测试]
  forbidden: [修改 RAG 决策、Provider 重试、试用额度、默认开关、CI workflow、付费 API 调用、真实用户数据]
allowed_files:
  - path: backend/src/pelican_town_specials/application/trial.py
    action: modify
    reason: 实现 ModelGateway 新方法并复用试用错误脱敏
    criterion_ids: [CCI-01, CCI-02]
  - path: backend/tests/application/test_trial.py
    action: modify
    reason: 新方法的结果透传、AppError 详情脱敏及非 AppError 透传回归
    criterion_ids: [CCI-01, CCI-02]
acceptance_ledger:
  - criterion_id: CCI-01
    source: CI run 35978864894 的 mypy 失败
    requirement: `python -m mypy backend/src` 不再报告 TrialSafeGateway 缺少 verify_ingredient_candidates；本地 scoped/all mypy 通过。
  - criterion_id: CCI-02
    source: 现有 TrialSafeGateway 安全协议及 Task67 单次核验边界
    requirement: 新方法只转发一次；成功结果原样返回；AppError 保留 code/message/http_status/retryable 但清空 details；非 AppError 原样传播。focused tests 覆盖。
  - criterion_id: CCI-03
    source: 用户要求修复最近 CI 并提交推送
    requirement: Ruff、focused application/Provider/generation 回归及 Git diff check 通过；只改允许的产品/测试文件和控制面，后由主 Agent 做单独 focused commit、推送并核验新 CI。
out_of_scope: [JEV/Provider 真实请求、默认 RAG 切换、Release、CI 层级重构、原料算法调整]
test_commands: [python -m mypy backend/src, python -m ruff check backend/src/pelican_town_specials/application/trial.py backend/tests/application/test_trial.py, python -m pytest backend/tests/application/test_trial.py backend/tests/application/test_trial_generation.py backend/tests/providers/test_ingredient_verifier.py backend/tests/generation/test_rag_provider_verifier.py -q -p no:cacheprovider, git diff --check]
```

主 Agent 拥有 STATUS/Session，实施子代理只改两份代码/测试文件；独立只读 detector 复核后由主 Agent 提交并依用户本轮授权推送。最终增量文档状态更新发生在 CI 修复推送与核验之后，不与本次 focused commit 混合。

## 实施交接

指定 `luna_worker`（`gpt-6-luna` / `max`）只修改 `application/trial.py` 与 `tests/application/test_trial.py`：新增 `verify_ingredient_candidates` 单次内层转发，沿用 `_trial_safe_error` 清空 `AppError.details`，成功结果原样返回，其他异常原样传播。测试先 RED：新增覆盖在实现前因缺方法出现 3 个 `AttributeError`；修复后冻结四文件测试 **78 passed**，`python -m mypy backend/src` **107 source files PASS**，目标 Ruff 与 `git diff --check` PASS。普通权限下 pytest 的临时目录遇 Windows ACL 错误，按最小权限重跑通过，未改 ACL。无真实 Provider/JEV、无提交推送；独立 detector 仍在复核，当前为 `verification`。

## 独立复核与提交授权

只读 `detector`（`gpt-6-sol` / `medium`）按 `CCI-01..03` 返回 PASS，无 must-fix/scope delta；它独立确认 mypy 107 source files、Ruff 和 diff check 通过，代码仅两份允许文件。其独立 pytest 复跑被本机 temp `WinError 5` 阻断，故不伪称独立跑过 78 项，实施者的最小提升测试结果保留为证据。用户本轮已授权修复后提交推送；Session 经 verification 按自动收口路径进入 committed，主 Agent 创建单独 focused commit，和先前纯文档提交一起推送开发分支。新远端 CI 成功与否另行核验；不触发 Release、默认切换或模型请求。
