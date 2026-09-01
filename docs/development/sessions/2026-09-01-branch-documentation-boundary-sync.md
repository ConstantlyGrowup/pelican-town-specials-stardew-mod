# Session｜分支文档边界与过期说明同步

| 字段 | 值 |
|---|---|
| session_id | `2026-09-01-branch-documentation-boundary-sync` |
| status | `committed` / `pushed` |
| session_type | `documentation_maintenance` |
| owner | Codex 主 Agent |
| started_at | `2026-09-01` |
| user_authorization | `2026-09-01 用户要求更新过期文档，并明确 main 与 MVP 分支文档不应混淆` |
| user_acceptance | `2026-09-01 用户明确验收通过并授权提交推送` |
| base_commit | `3216fdf docs: sync M11 and v1.5.0 release facts into control plane` |
| product_code_changes | `none` |

## 目标与边界

更新 `docs/development/README.md` 中停留在 v1.3.0/v1.4.0 发布前的状态，并冻结分支文档边界。只修改 MVP 分支开发控制文档；不修改任何产品源码，也不修改 `main/README.md` 或 `feat/mvp-implementation/README.md`。

## 结论

- 当前正式版本为 v1.5.0，Task 1–44 与 M9–M11 已完成。
- `STATUS.md` 的 Git 事实已同步：本地最新提交为 `3216fdf`，MVP 远端仍停在 `0815b0f`。
- `main/README.md` 是普通用户手册；`feat/mvp-implementation/README.md` 是源码开发说明。
- 两份 README 只同步共同事实，不要求受众、章节和文案一致。
- 全仓库当前态扫描未发现其他需要改写的过期说明；命中的旧说法均位于历史 Session 或变更日志，继续保留。

## 验证

- `git diff --check`；
- 当前态关键词扫描；
- 两个分支根 README 内容与 Git 差异核对；
- 确认产品源码和两个根 README 均无本次差异。

## 当前状态

文档同步已获用户验收；本 Session 随 focused documentation commit 提交并推送至 `origin/feat/mvp-implementation`。
