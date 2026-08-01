# Pelican Town Specials｜开发状态

> 本文件是开发状态唯一真源。设计内容回查正式技术设计，文档索引回查项目设计源索引；本文件只回答“当前哪个 Session、做到哪里、下一步是什么”。

## 当前状态

| 字段 | 值 |
|---|---|
| `overall_state` | `committed` |
| `project_phase` | `mvp-m0-runnable-skeleton` |
| `product_implementation_started` | `true` |
| `active_session_id` | 无（`2026-08-01-control-plane-tooling-cleanup` 已 committed 关闭） |
| `active_session_state` | 无 |
| `active_session_type` | 无 |
| `current_task` | 无活动 Task；MVP Task 2 与控制面维护已完成并提交 |
| `blocker` | 无 |
| `next_action` | MVP Task 3（React 前端骨架与生成式 API Client）等待用户另行明确授权后，以新修改型 Session 启动 |

## 当前 Git 状态事实

| 项目 | 当前值 |
|---|---|
| 仓库 | 已在当前目录初始化 |
| 当前分支 | `feat/mvp-implementation`（正式实现功能分支，已推送） |
| `origin` | `https://github.com/ConstantlyGrowup/pelican-town-specials-stardew-mod.git` |
| 初始提交 | `517f844 chore: add serial agent handoff control plane` |
| 最新提交 | 控制面维护 focused commit：`chore: align agent control plane and remove uv lockfile`（feat/mvp-implementation） |
| 远端操作 | main 与 feat/mvp-implementation 的既有推送保持不变；本次维护未 push |
| 当前未提交变更 | 无（本次维护范围已进入上述 focused commit） |

## 本次维护 Session 范围

- 更新 `AGENTS.md`，纠正已完成 Task 2 与当前无活动产品 Session 的状态，并明确开发工具不等于产品功能。
- 同步 `README.md` 与 `docs/development/README.md` 的当前状态说明。
- 移除仓库中的 uv 专属依赖 lockfile `backend/uv.lock`；保留 `backend/pyproject.toml` 的依赖/构建声明与 `.gitignore` 的通用 `.venv/` 保护规则。
- 不修改业务实现、不启动 Task 3、不做真实模型调用。

## 已完成 Task 2 的验收证据

- [x] `uv sync --project backend --all-groups` 成功，生成 `backend/uv.lock` 无冲突（CPython 3.13.14）。
- [x] health 测试先确认失败（红：ModuleNotFoundError），实现后通过（绿：1 passed）。
- [x] `ruff check backend` 与 `mypy backend/src` 通过（0 issues，strict 亦验证通过）。
- [x] `frontend/openapi.json` 含 `/api/v1/health` 与 `HealthResponse`（camelCase `apiVersion`）。
- [x] Review Subagent 规格符合性与代码质量检查通过（PASS）。
- [x] 用户已验收 verification 结果（2026-08-01：“task2可以验收并推送”；用户已查看本地 /docs 与 health 响应）。
- [x] 已创建一个 focused commit（`feat: add FastAPI application shell`）并推送 feat/mvp-implementation。

## 本次维护检查

- [x] 未发现 `backend/.venv`、`backend/venv` 或 `backend/virtualenv` 目录。
- [x] `backend/pyproject.toml` 保留为后端依赖、构建和工具声明；未删除运行所需的 FastAPI/Uvicorn 等依赖。
- [x] 未修改业务源代码、测试或 OpenAPI 契约。
- [x] uv 相关内容仅在已关闭 Task 2 的历史验收记录中保留，未篡改历史证据。
- [x] 用户已明确验收本次控制面维护（2026-08-01：“当前验收通过”）。
- [x] 已创建 focused commit；本次未推送远端。

## 状态规则

修改型 Session 只能按以下顺序推进：

```text
planned → active → verification → awaiting_user_acceptance → accepted → committed
```

任何状态冲突、脏工作树、重复活动 Session 或缺失下一步都必须停下并报告。Session 历史见 `docs/development/sessions/`，不能用历史记录覆盖本文件的当前结论。
