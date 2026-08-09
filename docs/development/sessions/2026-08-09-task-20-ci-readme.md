# Session｜2026-08-09-task-20-ci-readme

| 字段 | 值 |
|---|---|
| `session_id` | `2026-08-09-task-20-ci-readme` |
| `session_type` | milestone-6-task-20（CI/README/发布检查） |
| `state` | auto_accepted（Codex PASS，本地 focused commit，未 push） |
| `date` | 2026-08-09 |
| `task` | Milestone 6 Task 20：建立 Windows CI、用户 README、.env 参考与发布内容检查门禁 |
| `acceptance_contract_id` | `mvp-task-20-ci-readme-v1`（`docs/plans/2026-08-09-task-20-ci-readme-packet.md`，gitignored） |
| `revise_round` | 0（REVISE，2 项 MUST_FIX）→ 1（PASS） |
| `base_commit` | `74e0c4e` |

## 任务范围

按 `docs/plans/MVP_IMPLEMENTATION_PLAN.md` Task 20：新增 `.github/workflows/ci.yml`、
`.env.example`、`scripts/check_openapi_drift.ps1`、`scripts/check_product_copy.py`、
`tests/repo/test_product_copy.py`、`tests/repo/test_release_contents.py`；重写 `README.md`
为完整用户指南。**不改变领域、API 或 Mod 协议；Task 21 明确不实施。**

## 实施（产品 commit `33ab7f1`，8 文件 +435/-3）

- `README.md`（重写）：开始使用 / 首次设置 / 两种创作模式 / 收集品 / Pack the Menu /
  Bring It In-Game / 隐私与 Key / 系统要求 / 开发环境 / 测试 / Windows 构建 / 贡献。
  冻结产品名「鹈鹕镇新菜单」「Pelican Town Specials」与宣传语；不含「StarValley Cook Agent」。
- `.env.example`：只含空值与说明，不含任何真实 token。
- `.github/workflows/ci.yml`（19 步，windows-latest）：checkout → Python 3.13 →
  pnpm 11 → Node 24 → `pip install --group dev -e .`（backend 目录）→
  `pnpm install --frozen-lockfile` → OpenAPI drift → ruff/mypy → 全量 pytest →
  product copy gate → 前端 test/lint/build → Playwright chromium + fake E2E →
  build_windows.ps1 → smoke → 上传 release candidate artifact。
- `scripts/check_openapi_drift.ps1`：再生成 OpenAPI + 前端类型并 `git diff --exit-code`。
- `scripts/check_product_copy.py`：命名与 README 锚点检查的唯一实现源（pytest 复用）。
- `tests/repo/test_product_copy.py` + `test_release_contents.py` + `__init__.py`。

## planning_rulings

- mypy 以当前实测为准（87 source files，0 错误），CI 直接用 `python -m mypy backend/src`。
- 命名门禁扩展为同时校验引导锚点，使 stub README 形成红→绿。
- release 内容门禁基于 `git ls-files`，允许任意路径 `.env.example`（含已跟踪的
  `samples/yibu-api-probe/.env.example`），拒绝其它 `.env*`、设计文档、workspace、日志、
  source map 与 build 产物。
- 依赖安装用 `pip install --group dev -e .`（PEP 735，pip 25.2 实测可用），不引入 uv/lockfile。

## Codex 审阅（gpt-5.6-luna / max effort，独立 thread）

- round 0 **REVISE**（2 项 MUST_FIX）：
  - T20-CI-001：根目录 `pip install --group dev -e ./backend` 因 cwd 无 pyproject 失败
    → 改为 `working-directory: backend` + `-e .`（README 开发命令同步修正）。
  - T20-NAME-002：README 隐私表述自相矛盾（「图片不离开电脑」vs「模型分析照片」）
    → 改为明确「仅在主动生成请求时向配置的 Provider 发送照片与必要上下文；
    Key 只用于请求鉴权，不写入本地 JSON/日志/诊断包」。
- round 1 **PASS**（无 MUST_FIX；两项修复验证通过，无回归）。

## 验证证据（全部通过）

- `python -m pytest tests/repo -q`：**8 passed**（红→绿）。
- `python -m pytest backend/tests tests/repo tests/integration -q`：**666 passed / 2 skipped**。
- `python -m ruff check backend`、`python -m mypy backend/src`：clean（87 source files）。
- `pnpm --dir frontend test:run`：**94 passed**；lint clean；`build` OK。
- `pnpm --dir frontend e2e`：**10 passed**（Playwright 假流）。
- `pwsh -File scripts/check_openapi_drift.ps1`：OK（openapi.json/schema.d.ts 同步，无 git diff）。
- `python scripts/check_product_copy.py`：OK。
- `pwsh -File scripts/build_windows.ps1`：exit 0（PyInstaller onedir + release content gate）。
- `pwsh -File scripts/smoke_windows_bundle.ps1`：exit 0（Phase A health+首页，Phase B 自检退出 0）。
- `.github/workflows/ci.yml`：YAML 解析有效（19 步），`git diff --check` clean。
- Codex 额外核验：repo pytest 8 passed、copy gate 0、ruff/mypy 0、pnpm install 0、
  OpenAPI drift 0、lint 0；host ACL 阻塞全量后端/前端 build 时以 foreman 证据补足，非断言失败。

## 范围说明

- Task 21（视觉精修、无障碍、最终验收 `mvp_acceptance.ps1`）未实施，待用户授权。
- 未修改 `build_windows.ps1` / `smoke_windows_bundle.ps1` / 既有控制面。
- 非阻塞观察（Codex OPTIONAL_HARDENING）：T20-CONTENT-001 措辞未含「tests」（计划 prose 提及
  release bundle 不得含 tests，已由 build_windows.ps1 bundle gate 覆盖）；`.env.example` 空值断言
  可选加强。均非 MUST_FIX，留作后续。

## 遗留

无。Task 20 本地 focused commit 创建后未 push；推送待 Milestone 6 全量用户验收后统一授权。
