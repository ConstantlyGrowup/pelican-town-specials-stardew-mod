# Session｜CI 分层工作流维护

| 字段 | 值 |
|---|---|
| session_id | `2026-09-23-ci-tiered-workflows` |
| status | `auto_accepted` |
| session_type | `maintenance` |
| owner | Codex 主 Agent |
| started_at | `2026-09-23` |
| base_commit | `082d629` |
| acceptance_contract_id | `ci-tiered-workflows-20260923-v1` |
| revise_round | `0` |
| planning_status | `READY_FOR_IMPLEMENTATION` |

## Context Packet

```yaml
task_id: CI-TIERED-WORKFLOWS
base_commit: 082d629
planning_status: READY_FOR_IMPLEMENTATION
acceptance_contract_id: ci-tiered-workflows-20260923-v1
revise_round: 0
objective: 将普通 push、PR/main 与 Release 分为快速验证、全量验证和 Windows 发布打包三层。
user_visible_contract: 不改变产品功能、发布资产名称或现有 Release 输入；普通 push 不打包、不上传发布资产。
planning_rulings:
  - conflict: 旧 repo 契约要求 CI 和 Release 同时复用完整 build.yml，与新三层要求冲突。
    sources: [用户 2026-09-23 指令, tests/repo/test_release.py, tests/repo/test_installer.py]
    decision: CI 脱离 build.yml；Release 继续调用 build.yml。更新旧契约测试与工作流注释。
    rationale: 保留发布链路与资产合同，同时缩短日常 push。
    user_visible_delta: none
  - conflict: 普通 push 的“部分 integration test”未指定用例。
    sources: [用户 2026-09-23 指令, tests/integration/]
    decision: 快速层执行 fake collector 远端遥测集成用例，PR/main 执行整个 tests/integration 加 Playwright fake E2E。
    rationale: 真实跨模块集成覆盖留在日常 CI，同时将完整集成留给高门禁。
    user_visible_delta: none
contract_delta:
  documents: [本 Session, STATUS]
  domain: []
  persistence: []
  application_api: []
architecture_budget:
  allowed: [调整 GitHub Actions 触发与任务, 更新旧流程合同测试]
  forbidden: [产品源码变更, 依赖升级, 变更 Release 标签/资产/密钥逻辑, 远端操作]
allowed_files:
  - path: .github/workflows/ci.yml
    action: modify
    reason: 日常快速层及 PR/main 加强层；worker 所有。
    criterion_ids: [CI-TIER-01, CI-TIER-02]
  - path: .github/workflows/build.yml
    action: modify
    reason: 更新过时的调用方描述；worker 所有，仅注释。
    criterion_ids: [CI-TIER-03]
  - path: .github/workflows/release.yml
    action: modify
    reason: 更新过时的调用方描述；worker 所有，仅注释。
    criterion_ids: [CI-TIER-03]
  - path: tests/repo/test_release.py
    action: modify
    reason: 锁定新的三层合同；worker 所有。
    criterion_ids: [CI-TIER-01, CI-TIER-02, CI-TIER-03]
  - path: tests/repo/test_installer.py
    action: modify
    reason: 旧 CI 安装器断言迁移到 Release；worker 所有。
    criterion_ids: [CI-TIER-03]
  - path: docs/development/STATUS.md
    action: modify
    reason: 当前状态；主 Agent 所有。
    criterion_ids: [CI-TIER-04]
  - path: docs/development/sessions/2026-09-23-ci-tiered-workflows.md
    action: create
    reason: 冻结合同与记录验证；主 Agent 所有。
    criterion_ids: [CI-TIER-04]
acceptance_ledger:
  - criterion_id: CI-TIER-01
    source: 用户普通 push 要求
    requirement: 所有分支 push 触发 lint、mypy、backend/repo unit、前端单测/lint/build 和指定部分 integration；不调用构建安装包流水线、不上传资产。
  - criterion_id: CI-TIER-02
    source: 用户 PR/main 要求
    requirement: PR 与 main push 在快速门禁后执行全量 integration 和 Playwright fake E2E；普通非 main push 跳过。
  - criterion_id: CI-TIER-03
    source: 用户 Release 要求、现有 release.yml 资产合同
    requirement: v* tag/manual Release 仍独占 PyInstaller、Windows bundle smoke、Inno Setup、installer smoke、ZIP 和 artifact；试用密钥、遥测与版本门禁不变。
  - criterion_id: CI-TIER-04
    source: AGENTS.md 与 REVIEW_PROTOCOL.md
    requirement: 新 worker 实施、独立 detector 审阅、主 Agent 记录证据并仅本地 focused commit；不推送或发布。
out_of_scope: [Task 64, PostHog, 产品功能, 依赖更新, push, main, tag, Release]
test_commands: [python -m pytest tests/repo/test_release.py tests/repo/test_installer.py tests/repo/test_task39_release_telemetry.py -q, git diff --check]
```

## Acceptance Ledger

| ID | MUST 验收项 |
|---|---|
| CI-TIER-01 | 所有普通分支 push 走轻量检查，不打包、不上传发布资产。 |
| CI-TIER-02 | PR/main 增加完整 integration 与 Playwright fake E2E；其它 push 不执行。 |
| CI-TIER-03 | Release 独占现有 Windows 打包和四类 artifacts，发布机密及版本合同不变。 |
| CI-TIER-04 | 独立复核并记录实际验证结果；仅本地 focused commit。 |

## Worker ownership

worker 仅拥有两个 CI/Release workflow 注释、`ci.yml` 实现及两个 repo 合同测试；主 Agent 拥有本 Session 和 STATUS。所有角色共享工作树，不得撤销他人的改动；既有无关未跟踪文件保留。

## Worker handoff

- `implementation_scope_delta: none`。`ci.yml` 已把所有分支 push 与 PR 的后端/前端快检拆成并行 job；PR/main 在快检通过后运行完整 `tests/integration` 与 Playwright fake E2E。`push.branches: ['**']` 排除 tag，不重复触发 Release 标签打包。
- `build.yml`、`release.yml` 仅更新过时的调用方注释；试用 Secret、遥测变量、版本输入、Windows bundle/installer smoke、ZIP 与 artifact 上传逻辑未改。旧 repo 合同断言已转为新分层断言。
- 指定三份 repo 合同测试在提升权限环境 `32 passed in 16.37s`；三个 workflow 经 PyYAML 解析成功；`git diff --check` exit 0。`actionlint` 本机未安装。初次普通沙箱运行 pytest 的临时目录被 WinError 5 拒绝，提升权限后同命令通过。
- 未提交、推送或触发 GitHub Actions。Worker 运行时未暴露准确模型自报，项目路由配置为 `gpt-6-luna/max`。worker 建立的受限临时目录 `.ci-tiered-pytest-1790147827247-252521` 保留在工作区，不纳入提交。

## 独立复审与主 Agent 集成

- 独立 `detector` 按同一合同 / round 0 复审 `CI-TIER-01..04`，结论 `PASS`，`must_fix=[]`、`new_design=[]`、`scope_delta=none`。审阅者核对了触发、job `needs`、Release-only 打包及 Secret/版本合同，三 YAML 解析和 `git diff --check` 通过。
- detector 普通沙箱的 9 个 `tmp_path` 测试在初始化阶段遭系统临时目录 WinError 5；其余 23 passed。worker 在可访问环境同一目标命令 32 passed，证明并非产品断言失败。`actionlint` 未安装，且没有远端 CI run，故实际触发与运行时间仍待推送后验证。
- 主 Agent 复核工作流差异：`build.yml` 与 `release.yml` 只有注释修改；`ci.yml` 使用分支通配符排除 tag；产品源码、发布输入及资产命名没有改变。按项目自动验收规则仅创建本地 focused commit，不推送或发布。
