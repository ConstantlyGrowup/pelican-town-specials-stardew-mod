# Session｜CI：Task64 本地历史产物测试边界

| 字段 | 值 |
|---|---|
| session_id | `2026-09-24-ci-task64-artifact-test-boundary` |
| status | `committed` |
| session_type | `implementation` |
| owner | Codex 主 Agent |
| base_commit | `18c7215` |
| acceptance_contract_id | `ci-task64-artifact-test-boundary-v1` |
| revise_round | `0` |
| planning_status | `READY_FOR_IMPLEMENTATION` |

## 失败证据与边界

push CI run `35986066650` 的 `frontend-fast` 成功，`backend-fast` 的 Ruff、mypy 及 1106 项单测通过，只有 `backend/tests/tools/test_m14_ingredient_comparison.py::test_task64_raw_outputs_match_frozen_input_hashes_and_historical_baseline` 失败：干净 runner 不含 Git ignored 的 `output/m14-task64/baseline_manifest.json`。该测试是历史原始产物审计，不应成为干净仓库单测的必需外部输入。存在部分文件或文件损坏时仍须失败，不得放宽哈希与历史结果检查。

## Context Packet

```yaml
task_id: CI-task64-artifact-test-boundary
base_commit: 18c7215
planning_status: READY_FOR_IMPLEMENTATION
acceptance_contract_id: ci-task64-artifact-test-boundary-v1
revise_round: 0
objective: 让干净 CI 跳过完全缺席的 Task64 本地历史产物审计，同时保留产物存在时的严格核验。
user_visible_contract: 无产品运行行为变化。
planning_rulings:
  - conflict: 历史原始输出按约定 Git ignored，但普通 push CI 无条件读取。
    sources: [CI run 35986066650 backend-fast, test_m14_ingredient_comparison.py, compare_ingredient_rag.py]
    decision: 仅当全部 Task64 原始产物缺席时跳过该历史审计；部分缺失或篡改继续失败。
    rationale: 干净 checkout 不依赖未提交数据，本地留存的历史审计仍可运行。
    user_visible_delta: none
contract_delta:
  documents: [docs/development/STATUS.md, 本 Session]
  domain: []
  persistence: []
  application_api: []
architecture_budget:
  allowed: [单个测试文件内的缺席判定、对应 hermetic 测试]
  forbidden: [改写冻结数据与哈希、提交原始 output、禁用全部测试、修改生产算法或 CI 层级]
allowed_files:
  - path: backend/tests/tools/test_m14_ingredient_comparison.py
    action: modify
    reason: 修正历史本地产物审计的 CI 边界
    criterion_ids: [CCI64-01, CCI64-02]
acceptance_ledger:
  - criterion_id: CCI64-01
    source: CI run 35986066650 的唯一测试失败
    requirement: 全部 Task64 原始产物缺席时，只有历史审计测试明确 skip；其余仓库单测继续运行。
  - criterion_id: CCI64-02
    source: Task64 冻结哈希与审计要求
    requirement: 任一原始产物存在时，仍调用原 verify_task64_artifacts，部分缺失或损坏不得静默跳过；本机完整产物继续核验原 72/71 与 14/24。
  - criterion_id: CCI64-03
    source: 用户要求修复最近 CI 并提交推送
    requirement: scoped pytest、Ruff、diff check 通过；独立只读 detector PASS；主 Agent 单独 focused commit、推送并核验新 CI。
out_of_scope: [付费 API、JEV 重跑、默认链路、Release、CI 工作流重构]
test_commands: [python -m pytest backend/tests/tools/test_m14_ingredient_comparison.py -q -p no:cacheprovider, python -m ruff check backend/tests/tools/test_m14_ingredient_comparison.py, git diff --check]
```

主 Agent 拥有 STATUS/Session；指定实施子代理仅拥有上述单测文件，且不得回退他人编辑。独立只读 detector 按冻结合同复核。最终增量文档更新仍在修复提交推送及 CI 核验之后。

## 实施与独立复核

指定 `luna_worker`（`gpt-6-luna` / `max`）仅修改冻结的测试文件：历史审计在四项命名原始产物全部缺席时 skip；任一项存在（含坏 symlink）仍进入原 `verify_task64_artifacts` 严格验证。新增 hermetic guard 测试覆盖全部缺席和部分存在。本机完整原始产物的既有哈希、72/71 行与 14/24 断言仍实际运行。聚焦 pytest `10 passed`，Ruff 和 `git diff --check` PASS；主 Agent 也独立复跑聚焦 pytest `10 passed`。尝试使用临时目录时遇已有 Windows ACL 限制，遗留一个 Git ignored 的不可访问临时目录；未清理或纳入提交。

只读 `detector`（`gpt-6-sol` / `medium`）按 `CCI64-01..03` 返回 `PASS`，无 must-fix、scope delta 或 optional hardening；独立聚焦 pytest `10 passed`、Ruff、diff check PASS。它未代替主 Agent 声称完成 commit、push 或远端 CI。按本轮用户授权进入提交与推送阶段；产品逻辑、原始评测产物与 CI workflow 均未修改。

## 提交、推送与远端验证

主 Agent 单独创建 focused commit `681d3c1` 并推送至 `origin/feat/mvp-implementation`，本地与远端同 SHA。对应 GitHub Actions [run 35987394616](https://github.com/ConstantlyGrowup/pelican-town-specials-stardew-mod/actions/runs/35987394616) 为 `success`：`backend-fast` 的 Ruff、mypy、仓库单测、遥测集成切片与两项文案门禁均通过；`frontend-fast` 的单测、lint、build 均通过；`pr-main-integration` 在普通分支 push 上按预定条件跳过。GitHub 仅给出旧版 Actions 的 Node 20 运行时弃用提醒，非本次失败项；没有据此扩大 CI 修复范围。最终增量文档状态由后续纯文档维护 Session 收口。
