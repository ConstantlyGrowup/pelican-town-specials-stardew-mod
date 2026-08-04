# Session｜2026-08-04-task-9-draft-cookbook-api

| 字段 | 值 |
|---|---|
| `session_id` | `2026-08-04-task-9-draft-cookbook-api` |
| `session_type` | `implementation` |
| `state` | `committed` |
| `date` | `2026-08-04` |
| `task` | MVP Task 9：图片上传、Draft、Blueprint 转换、Archive 与 Cookbook API |
| `acceptance_contract_id` | `mvp-task-9-rerun-15405d0-20260804-final-v1` |
| `revise_round` | `1`（第一轮 REVISE 已修复；第二轮 PASS） |
| `owner` | Codex Main Agent 规划与审阅；Claude Code Implementer 执行；Review Subagent（gpt-5.6-luna/max） |
| `base_commit` | `15405d0` |

## 实际模型与 effort

```yaml
actual_models:
  main: gpt-5.6-sol / effort: high
  review: gpt-5.6-luna / effort: max
  implementer: deepseek-v4-flash / effort: default（Claude Code，按会话环境默认配置）
```

模型路由由 Codex Context Packet 与会话环境固定；实现不自行切换模型。

## 目标

实现不调用真实模型的图片上传、资产读取、Draft 创建/查询/编辑/转换/丢弃、Archive 接受，以及 Cookbook 查询/删除 API；复用现有严格领域模型、JSON 工作区、Task 8 原版目录与统一安全/错误边界，并导出可供前端生成类型的 OpenAPI 契约。

## 不包含

- 真实模型调用、Provider Adapter、capability probe；
- 前端产品页面、Blueprint editor、Cookbook UI；
- 数据库、队列、缓存、新事务/恢复协议；
- Launcher 安全重构、会话机制重做；
- Content Patcher 编译、Mod 导出、发布流水线；
- `draft generate/cancel`（归 Task 13）、`/exports/*`、`/workspace/migrate`、`/settings/provider/test`。

## planning_rulings（已应用）

`T9-RULING-001` 至 `T9-RULING-013` 全部按最终 Context Packet 应用。关键裁决：

- `T9-RULING-001`：`DraftRecord` 增加 `baseTemplateVersion` 持久化字段，`schemaVersion` 保持 1。
- `T9-RULING-003`：原始上传归一化（bomb 防护、EXIF 转置、元数据清除、PNG/JPEG 重新编码）在本 Task 的 `application/assets.py` 实现。
- `T9-RULING-004`：`FileAssetStore.open/stat` 支持按 UUID 查找并保留 AssetRef 兼容。
- `T9-RULING-007`：`ArchiveRepository` 增加按 `Idempotency-Key` 查询，支持安全重试与关联修复。
- `T9-RULING-011`：`api/dependencies.py` 作为 create 文件集中提供 app.state 类型安全依赖。
- `T9-RULING-012`：`AssetView`/`DraftView`/`DraftSummary`/`Page` 公开投影排除 `relativePath` 与来源字段。

## 实现证据

- domain：`DraftRecord.baseTemplateVersion` 及 mode 不变量；`tests/domain/test_models.py` 覆盖序列化与不变量。
- persistence：`FileAssetStore` UUID 查找/校验；`ArchiveRepository.get_by_idempotency_key`；persistence 测试 37 passed。
- application：`AssetService`、`DraftService`、`CookbookService`、`Page`；application 测试 57 passed。
- api：`assets`/`drafts`/`cookbook` routes、`dependencies.py`、`create_app` 装配；API 测试 68 passed/1 skipped（既有 symlink skip）。
- 契约：`python scripts/export_openapi.py` 成功；`frontend/openapi.json` 含全部 Task 9 schemas，Cookbook schemas 无来源字段；`pnpm --dir frontend contract:generate` 成功。

## 验证命令

- focused：`python -m pytest backend/tests/domain/test_models.py backend/tests/persistence/test_asset_store.py backend/tests/persistence/test_repositories.py backend/tests/application/test_assets.py backend/tests/application/test_drafts.py backend/tests/application/test_cookbook.py backend/tests/api/test_assets.py backend/tests/api/test_drafts.py backend/tests/api/test_cookbook.py backend/tests/api/test_task9_openapi.py backend/tests/api/test_app_wiring.py -q -p no:cacheprovider` → 121 passed
- 全量：`python -m pytest backend/tests -q -p no:cacheprovider` → 330 passed, 2 skipped（Windows 无 symlink 权限）
- `python -m ruff check backend` → All checks passed
- `python -m mypy backend/src` → Success: no issues found in 46 source files
- `pnpm --dir frontend test:run` → 9 passed；`pnpm --dir frontend lint` 通过；`pnpm --dir frontend build` 成功
- `pwsh -File scripts/verify_local_docs_ignored.ps1` → OK
- `git diff --check` → 通过

## Review 结果

- 第一轮（revise_round=0，gpt-5.6-luna/max）：`REVISE`，4 项 MUST_FIX——`gameplay.buff` 权属缺失、创建未校验 ORIGINAL_IMAGE kind、`contextText` 未在请求边界限长、Session 缺实际模型/effort 与 revise_round。均已修复并补测试。
- 第二轮（revise_round=1，gpt-5.6-luna/max）：`PASS`，无 MUST_FIX、无 OPTIONAL_HARDENING、无 NEW_DESIGN；`scope_delta: none`；`planning_rulings_checked: [T9-RULING-004]`。
- 修复后验证：focused 125 passed；全量 `python -m pytest backend/tests -q -p no:cacheprovider` → 334 passed, 2 skipped（Windows 无 symlink 权限）；Ruff、mypy、前端 test/lint/build、`git diff --check` 全部通过。

## 用户验收与提交

- 用户已确认 Task 9 双 Agent 协作实验成功，并授权创建本地 focused commit（不 push）；同时确认后续协作采用里程碑粒度验收：里程碑内的普通 Task 的 `PASS` 自动进入 `auto_accepted` 并创建本地 focused commit，不在单个 Task 打断用户。
- 已创建本地 focused commit（`feat: add draft and cookbook lifecycle APIs`）；工作树核验干净。
- 单个 Task 不 push；Milestone 2 全量验证后进入 `awaiting_milestone_acceptance`，用户一次性验收并授权统一 push。

## 当前状态

- `state`: `committed`
- `next_action`: 里程碑粒度协作已启用；继续 Milestone 2 中依赖满足的下一 Task（Task 10 前端页面），完成后进行 Milestone 全量验证与用户验收。
