# Pelican Town Specials｜开发状态

> 本文件是开发状态唯一真源。设计内容回查正式技术设计，文档索引回查项目设计源索引；本文件只回答“当前哪个 Session、做到哪里、下一步是什么”。

## 当前状态

| 字段 | 值 |
|---|---|
| overall_state | committed |
| project_phase | mvp-task-5-persistence |
| product_implementation_started | true |
| active_session_id | none |
| active_session_state | none |
| active_session_type | none |
| current_task | MVP Task 5：实现工作区、原子 JSON Repository 与 Asset Store，已验收并创建 focused commit |
| blocker | 无；Task5 已验收并提交，等待授权下一产品 Task |
| next_action | 等待用户授权开始 MVP Task 6 |

## 当前 Git 状态事实

| 项目 | 当前值 |
|---|---|
| 仓库 | 已在当前目录初始化 |
| 当前分支 | feat/mvp-implementation（正式实现功能分支，已推送） |
| origin | https://github.com/ConstantlyGrowup/pelican-town-specials-stardew-mod.git |
| 初始提交 | 517f844 chore: add serial agent handoff control plane |
| 最新提交 | MVP Task 5 focused commit；本地 HEAD 与 origin 状态以 Git 核验为准 |
| 远端操作 | Task4 focused commit 已创建；远端状态以 origin/feat/mvp-implementation 核验为准 |
| 当前工作树范围 | Task5 实现、测试、控制面、设计和计划文档已纳入 focused commit；工作树应保持干净 |

## 已关闭 Task 3 Session（committed）

- `2026-08-02-task-3-frontend-shell` 已完成 verification 并通过用户验收，范围严格限定为 MVP Task 3：React/Vite/TypeScript 前端骨架、OpenAPI 生成类型、same-origin typed client、正式产品首屏和启动健康检查。
- 用户明确反馈已手动启动 Vite 与后端，首页显示正常，Network 中 health 请求返回 200，并确认“task3可以验收通过了”。
- 本 Session 的 focused commit amend 边界包含前端壳层、标准 Uvicorn `app` 入口、开发依赖兼容性调整和启动回归测试；不改变 API 路由、不调用真实模型、不实现 Task 4 或后续领域页面。
- Task 3 未把 uv 作为启动前置，也未提交 Python lockfile 或虚拟环境；前端依赖使用 pnpm workspace 与根 pnpm-lock.yaml。

## 已完成 Task 4 Session（committed）

- 2026-08-02-task-4-domain-models 已获用户设计审阅通过，正式实施计划已写入 `docs/superpowers/plans/2026-08-02-task-4-domain-models.md`，实现、独立复审和最终验证已完成，并已创建 focused commit。
- 目标是实现技术设计 §9 的严格领域模型、错误协议、验证报告和 §11 的显式状态机；实现顺序为共享基础、菜品字段、草稿/存档/导出与组合验证、状态机。
- 本阶段不实现 API、Repository、工作区持久化、模型调用、前端页面或 Mod 导出；uv 不是 Task 4 前置，不提交 Python lockfile 或虚拟环境。
- 已完成证据：Task 1–4 implementer/reviewer 串行执行；全量 `python -m pytest backend/tests -q -p no:cacheprovider` 通过；Ruff、mypy、`git diff --check`、生产旧枚举扫描和文档忽略检查通过。Task4 已验收并创建 focused commit；推送结果以 Git 核验为准。

- uv 是否必需已完成本地评估：uv 不在 PATH，但现有 Python/FastAPI 依赖、pytest（2 passed）、ruff、mypy 和直接 Python/Uvicorn health 均通过；因此 uv 不属于产品运行或发布媒介。

## 当前 Task 5 Session（committed）

- 2026-08-02-task-5-persistence 已获用户授权启动，当前状态为 committed；实现、两轮独立复审和自动验证已完成，focused commit 已创建，当前等待下一 Task 授权。本 Session 只处理本地工作区、原子 JSON 写入、领域 Repository、Asset Store 与短期回收站。
- Task5 消费 Task4 的领域记录，建立 %LOCALAPPDATA%\\PelicanTownSpecials\\workspace 的可恢复持久化边界；实体记录与资产内容是真实来源，索引只作为可重建加速层。
- 本 Session 不实现 API、Secret Store、模型调用、前端页面、Launcher、数据库或 Mod 编译；uv 不作为前置工具，不提交 Python lockfile 或虚拟环境。
- 设计说明与实施计划：docs/superpowers/specs/2026-08-02-task-5-persistence-design.md、docs/superpowers/plans/2026-08-02-task-5-persistence.md。
- 范围边界：本 Session 按 Task5 实施计划完成；正式技术设计中更完整的 WorkspaceRecord 字段、应用根 bootstrap、进程锁、更强迁移恢复和统一异常层未在本 Task 扩展，若要求纳入需另行收敛设计和实现。
- 验收证据：持久化测试 21 passed；领域+持久化回归 107 passed；完整后端回归 109 passed；Ruff、mypy、git diff --check 均通过。默认 pytest 临时目录曾出现 WinError 5，使用全新 C:\tmp basetemp 后测试通过。
- focused commit 已创建；本次未 push，等待下一 Task 授权。
## 上一已关闭维护 Session 范围

- 更新 AGENTS.md，纠正已完成 Task 2 与当前无活动产品 Session 的状态，并明确开发工具不等于产品功能。
- 同步 README.md 与 docs/development/README.md 的当前状态说明。
- 移除仓库中的 uv 专属依赖 lockfile backend/uv.lock；保留 backend/pyproject.toml 的依赖/构建声明与 .gitignore 的通用 .venv/保护规则。
- 不修改业务实现、不启动 Task 3、不做真实模型调用；该 Session 已在 c4cedf0 提交并推送。

## 已完成 Task 2 的验收证据

- [x] uv sync --project backend --all-groups 成功，生成 backend/uv.lock 无冲突（CPython 3.13.14）。
- [x] health 测试先确认失败（红：ModuleNotFoundError），实现后通过（绿：1 passed）。
- [x] ruff check backend 与 mypy backend/src 通过（0 issues，strict 亦验证通过）。
- [x] frontend/openapi.json 含 /api/v1/health 与 HealthResponse（camelCase apiVersion）。
- [x] Review Subagent 规格符合性与代码质量检查通过（PASS）。
- [x] 用户已验收 verification 结果，并允许创建 focused commit。
- [x] 已创建一个 focused commit（feat: add FastAPI application shell）并推送 feat/mvp-implementation。

## 上一轮控制面维护检查

- [x] 未发现 backend/.venv、backend/venv 或 backend/virtualenv 目录。
- [x] 保留 backend/pyproject.toml 的后端依赖、构建和工具声明；未删除运行所需的 FastAPI/Uvicorn 等依赖。
- [x] 未修改业务源代码、测试或 OpenAPI 契约。
- [x] 已保留 Task 2 的 uv 历史执行证据；当前文档已将 uv 定位为可选开发便利，不作为产品运行、用户部署或产品 Task 前置。
- [x] 用户已明确验收本次控制面维护，并授权随后推送。
- [x] Task 3 与后端启动闭环已验收，统一纳入 `feat: add React application shell` 的 amend/push。

## Task 3 与本地启动闭环设计与验收边界

- 输入：现有 frontend/openapi.json，其中已冻结 GET /api/v1/health 与 HealthResponse。
- 产出：frontend/package.json、Vite/TypeScript 配置、React 入口与 Providers、apiClient、生成的 schema.d.ts、PRODUCT_COPY 和首屏测试；同时提供标准 Uvicorn `app` 入口、开发依赖兼容性配置和启动回归测试；构建产物为 frontend/dist。
- 首屏只显示正式中文产品名“鹈鹕镇新菜单”和主宣传语“把你做的菜，写进鹈鹕镇的下一张菜单。”；启动入口通过 typed client 发起 same-origin health probe。
- 不包含领域页面、草稿/收集品生命周期、真实模型调用、Mod 导出、认证会话或 Task 4+ 接口。
- [x] `pnpm install --frozen-lockfile`、`pnpm --dir frontend contract:generate`、`pnpm --dir frontend test:run`（1 file / 1 test）、`pnpm --dir frontend lint` 和 `pnpm --dir frontend build` 均通过。
- [x] `python -m pytest backend/tests -q` 通过（2 passed）；`pwsh -File scripts/verify_local_docs_ignored.ps1` 和 `git diff --check` 通过。
- [x] `python -m ruff check backend`、`python -m mypy backend/src`、Uvicorn 直连 health 和 Vite 代理 health 均通过；两端返回 `status=ok`、`app=PelicanTownSpecials`、`apiVersion=v1`。
- [x] 用户手动启动 Vite 与后端，确认首页显示以及 Network 中 `/api/v1/health` 返回 200；这补充了真实运行时联调证据。
- [x] amend 范围为前端文件、pnpm workspace/lockfile、后端标准 ASGI 启动入口、开发依赖、回归测试和两份 Task 3/启动控制面记录；不包含 Python lockfile 或虚拟环境。
- 已知限制：受限执行器曾对 Node 子进程报告 `spawn EPERM`；在真实 Windows 权限下的用户手动启动与浏览器联调已通过，不影响 Task 3 验收。

## 状态规则

修改型 Session 只能按以下顺序推进：

    planned → active → verification → awaiting_user_acceptance → accepted → committed

任何状态冲突、脏工作树、重复活动 Session 或缺失下一步都必须停下并报告。Session 历史见 docs/development/sessions/，不能用历史记录覆盖本文件的当前结论。