# Session｜2026-08-02-task-3-frontend-shell

| 字段 | 值 |
|---|---|
| session_id | 2026-08-02-task-3-frontend-shell |
| session_type | mvp-task-implementation |
| state | committed |
| date | 2026-08-02 |
| task | MVP Task 3：建立 React 前端骨架与生成式 API Client |
| owner | 当前主 Agent；Git 不记录 Agent 署名 |

## 授权与当前阶段

- 用户已明确授权将后端启动/环境配置改动纳入 `feat: add React application shell` 的 amend commit，并推送当前分支。
- Task 3 的高层设计范围和书面设计规格已获用户确认；本 Session 已从 planned 推进到 active。
- 已完成实施、启动问题修复、依赖补齐、任务级 Review、scoped re-review 和主 Agent verification；用户已明确验收，focused commit amend 边界为 `feat: add React application shell`，并包含后端启动闭环支持。

## 目标

在不引入业务领域页面的前提下，建立可运行的 React + TypeScript + Vite 前端壳层：

- 渲染冻结的正式产品名和主宣传语；
- 从 frontend/openapi.json 生成 API 类型；
- 暴露使用 openapi-fetch 的 same-origin typed client；
- 在应用启动时对既有 GET /api/v1/health 做类型化健康检查；
- 提供标准 Uvicorn pelican_town_specials.api.app:app 启动入口，并用回归测试锁定该入口；后端改动不改变路由或 OpenAPI 契约。
- 形成可测试、可构建的 frontend/dist 静态产物。

## 范围

计划涉及：

- frontend/package.json
- frontend/vite.config.ts
- frontend/tsconfig.json
- frontend/index.html
- frontend/src/main.tsx
- frontend/src/app/App.tsx
- frontend/src/app/providers.tsx
- frontend/src/app/App.test.tsx
- frontend/src/api/client.ts
- frontend/src/api/generated/schema.d.ts
- frontend/src/i18n/copy.ts
- backend/pyproject.toml
- backend/src/pelican_town_specials/api/app.py
- backend/tests/api/test_health.py
- docs/superpowers/plans/2026-08-02-startup-dependency-fix.md

不包含：

- 草稿、料理蓝图、收集品、打包菜单和“带进游戏”业务页面；
- 真实模型请求、API Key、认证会话或 CSRF store；
- 后端路由、OpenAPI 契约、数据库/工作区实现、Mod 编译；本 Session 只补充标准 ASGI 入口、开发依赖兼容性和回归测试；
- Task 4 及后续产品 Task；
- uv 不是 Task 3 的启动前置；不提交 Python lockfile 或其他 Python 虚拟环境配置。

## 设计闸门

- 书面设计规格：docs/superpowers/specs/2026-08-02-task-3-frontend-shell-design.md（已审阅）
- 规格状态：用户已审阅，实现与验证完成，已验收；focused commit 边界已确定。
- 实施计划：docs/superpowers/plans/2026-08-02-react-frontend-shell.md；implementer、独立只读 reviewer 和 scoped re-review 均已完成。

## 验收与实际验证

- `pnpm install --frozen-lockfile`、`pnpm --dir frontend contract:generate`、`pnpm --dir frontend test:run`（1 passed）、`pnpm --dir frontend lint`、`pnpm --dir frontend build` 均通过。
- `python -m pytest backend/tests -q` 通过（2 passed）；`pwsh -File scripts/verify_local_docs_ignored.ps1` 和 `git diff --check` 通过。
- `python -m ruff check backend`、`python -m mypy backend/src`、后端直连 health 和 Vite 代理 health 均通过。
- 用户手动启动 Vite 与后端，确认首页显示，Network 中 `/api/v1/health` 请求返回 200。
- Task 3 使用当前 Python 环境验证后端启动；未把 uv 作为前置工具，也未提交 Python lockfile 或虚拟环境配置。
## 提交边界

- Task 3 focused commit 边界：`feat: add React application shell`。
- 用户已授权本次 amend 与推送；a311e72 feat: add React application shell 已创建并推送，本地分支与 origin/feat/mvp-implementation 已核验一致。

## 精确下一步

Task 3 与后端启动闭环已通过用户验收，并已由 a311e72 feat: add React application shell 完成 focused commit、推送和远端状态核验；本 Session 已关闭。后续以 2026-08-02-task-4-domain-models 的 planned 设计阶段为准。
