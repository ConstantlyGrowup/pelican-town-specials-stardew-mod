# Session｜M14 CI Ruff 门禁修复

| 字段 | 值 |
|---|---|
| session_id | `2026-09-23-ci-m14-seeded-events-ruff-repair` |
| status | `auto_accepted` |
| session_type | `maintenance` |
| owner | Codex 主 Agent |
| started_at | `2026-09-23` |
| base_commit | `6e03557` |
| acceptance_contract_id | `m14-ci-seeded-events-ruff-repair-v1` |
| revise_round | `0` |
| planning_status | `READY_FOR_IMPLEMENTATION` |

## Objective 与证据

用户要求在 Task 64 前定位并修复近期推送触发的 CI 失败。GitHub Actions `ci` runs `35819558059`、`35820044923`、`35825084104`、`35825154949` 均在 `verify-and-build` 的 `Ruff lint` 步骤失败，OpenAPI drift 步骤通过，后续测试和打包均被跳过。最新 job `107065161438` 日志在 `backend/tests/tools/test_m14_seeded_events.py` 报 RUF100（多余 `# noqa: E402`）和两项 DTZ001（仅为日期比较却构造无时区 `datetime`）。这是现有 Task 61 测试的静态检查问题，非 M12 文档或 Task 62/63 设计导致；Node 20 deprecation 是非阻断警告。M12 原有文档改动已按用户授权独立提交 `6e03557`，不得混入本维护提交。

## planning_rulings

- `R-CI-01`：用 `date(2026, 9, 17)` 表示纯日历日期比较，去掉未启用的 `E402` noqa；不改事件夹具、日期门槛和业务断言，`user_visible_delta: none`。
- `R-CI-02`：GitHub 日志只证实 Ruff 当前阻断，其后续步骤没有运行，不能宣称整个 CI 已修好；本地尽量依 `build.yml` 执行后续检查。推送需独立授权，未经授权不创建远端 CI 运行，`user_visible_delta: none`。

## Context Packet

```yaml
task_id: M14-CI-MAINTENANCE
base_commit: 6e03557
planning_status: READY_FOR_IMPLEMENTATION
acceptance_contract_id: m14-ci-seeded-events-ruff-repair-v1
revise_round: 0
objective: 消除四次 CI 运行共同的 Ruff 阻断，验证相关测试和后续本地门禁。
user_visible_contract: none；不改变事件夹具、用户数据、产品行为或远端状态。
planning_rulings: [R-CI-01, R-CI-02]
acceptance_ledger:
  - criterion_id: CI-01
    source: GitHub Actions job 107065161438 Ruff lint 日志
    requirement: 清除 test_m14_seeded_events.py 的 RUF100 和两项 DTZ001，不改变测试语义。
  - criterion_id: CI-02
    source: .github/workflows/build.yml
    requirement: 本地 python -m ruff check backend 与专用测试通过，尽量执行 Ruff 后续门禁并记录未验证处。
  - criterion_id: CI-03
    source: AGENTS.md、REVIEW_PROTOCOL.md
    requirement: 新 worker 实施、独立 detector 只读审阅；主 Agent 记录真实证据、focused commit，不自动 push。
contract_delta:
  documents: [新增维护 Session，更新 STATUS]
  domain: []
  persistence: []
  application_api: []
architecture_budget:
  allowed: [修正 Task 61 测试文件的 Ruff 注释和纯日期构造；本地验证]
  forbidden: [修改事件数据、生成器、产品源码、CI workflow、依赖、发布配置、其他测试或远端]
allowed_files:
  - path: backend/tests/tools/test_m14_seeded_events.py
    action: modify
    reason: 唯一产生 CI Ruff 错误的文件；worker 所有。
    criterion_ids: [CI-01, CI-02]
  - path: docs/development/sessions/2026-09-23-ci-m14-seeded-events-ruff-repair.md
    action: create
    reason: 冻结合同与验证记录；主 Agent 所有。
    criterion_ids: [CI-03]
  - path: docs/development/STATUS.md
    action: modify
    reason: 唯一活动维护 Session；主 Agent 所有。
    criterion_ids: [CI-03]
out_of_scope: [Task 64, PostHog 数据, M12 内容再修改, GitHub push, release, 任意产品机制改动]
test_commands:
  - python -m ruff check backend
  - python -m pytest backend/tests/tools/test_m14_seeded_events.py -q -p no:cacheprovider --basetemp output/m14-ci-ruff/pytest-focused
  - git diff --check
```

## Acceptance Ledger

| ID | MUST 验收项 |
|---|---|
| CI-01 | 修改仅清除三个 Ruff 错误，测试含义与夹具数据不变。 |
| CI-02 | `python -m ruff check backend`、专用 pytest 通过，后续本地门禁尽可能核验并如实标注范围。 |
| CI-03 | 新 worker、独立只读 detector 和主 Agent 核对；仅本地 focused commit，push/发布另需授权。 |

## Worker ownership

worker 仅拥有 `backend/tests/tools/test_m14_seeded_events.py`；主 Agent 拥有 Session、STATUS 和集成。所有角色共享工作树，不得撤销他人的改动。M12 提交 `6e03557` 与无关未跟踪资料不在维护范围。

## Worker handoff

- 仅修改 `backend/tests/tools/test_m14_seeded_events.py`：移除未启用 E402 的多余 noqa，日期门槛改为 `date(2026, 9, 17)`；未改夹具或断言含义，`implementation_scope_delta: none`。
- `python -m ruff check backend` exit 0，`All checks passed!`；受保护的无关目录有四条访问警告。focused pytest 在普通沙箱的 basetemp 建立/清理遇 WinError 3/5；同一命令在获准环境重跑 `10 passed in 0.06s`。`git diff --check` exit 0，测试文件改动为 4 insertions/4 deletions。
- worker 未提交或推送；后续 post-Ruff CI 门禁由主 Agent 整合核验。独立 detector 待复审。

## 独立复审与主 Agent 集成

- 新 `detector` 依合同 `m14-ci-seeded-events-ruff-repair-v1`、round 0 对 CI-01..03 和 R-CI-01/02 只读复审，结论 `PASS`；`must_fix=[]`、`optional_hardening=[]`、`new_design=[]`、`scope_delta=none`。detector `python -m ruff check --no-cache backend` 与 `git diff --check` 均 exit 0，确认日期断言语义与夹具未改。路由配置 worker `gpt-6-luna/max`、detector `gpt-6-sol/medium`，运行时没有独立自报模型。
- 主 Agent 的 post-Ruff 本地验证：`python -m mypy backend/src` 为 98 files PASS；`python -m pytest backend/tests tests/repo tests/integration -q -p no:cacheprovider --basetemp output/m14-ci-ruff/pytest-full` 为 `1016 passed / 2 skipped`、3 个重复 ZIP 名称测试警告；产品文案与前端 locale 门禁通过；frontend Vitest `23 files / 231 passed`、ESLint、TypeScript/Vite build 通过；Playwright fake E2E `39 passed`。前端 Vitest 普通沙箱因 esbuild 子进程 `EPERM` 未启动，获准环境重跑通过。
- `scripts/build_windows.ps1` 全流程通过：backend/integration `964 passed / 2 skipped`、frontend `231 passed`、OpenAPI drift、ignore policy、telemetry manifest、PyInstaller、EXE icon/version/content gate PASS。`scripts/smoke_windows_bundle.ps1` 通过两次干净启动、health/首页和 SQLite 持久化；`scripts/check_release_version.ps1 -Version 1.5.6` PASS。
- 本机没有 Inno Setup，因此未跑 installer 构建/安装器 smoke，也未形成新的 GitHub Actions CI 运行；远端全绿需要用户另行授权推送后观察。近期四次已失败的 run 不因本地修复自动变绿。Node 20 deprecation 与 Vite 大 chunk 只见警告，不是这四次运行的失败原因。
- 主 Agent 核对源文件/Session/STATUS 范围与 `git diff --check`；仅创建本地 focused commit，不推送、不发布、不启动 Task 64。

## 推送后远端核验

- 用户明确授权推送后，M12 澄清 `6e03557` 与本维护 focused commit `fc4a91b` 已推送 MVP 分支；`git ls-remote` 对应 `fc4a91be10e2b0b658c3eaf1309e9b66973602c5`。
- [GitHub Actions ci run 35827459734](https://github.com/ConstantlyGrowup/pelican-town-specials-stardew-mod/actions/runs/35827459734) 对该 SHA `completed/success`（2026-09-23T06:49:03Z）；先前 Ruff 阻断已消失，所有后续 job steps 包含 Windows installer smoke 和产物上传均成功。Node 20 deprecation 仅为非阻断注释；旧失败运行保留历史状态。未发布或启动 Task 64。
