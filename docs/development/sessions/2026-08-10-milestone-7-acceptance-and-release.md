# Session｜Milestone 7 全量验收与 v1.0.0 Release

| 字段 | 值 |
|---|---|
| session_id | `2026-08-10-milestone-7-acceptance-and-release` |
| session_type | `milestone-7-full-acceptance-and-release` |
| status | `in_progress`（release 触发后关闭） |
| owner | 包工（Claude Code 主会话） |
| started_at | `2026-08-10` |
| acceptance_contract_id | `mvp-m7-full-acceptance-v1` |

## 用户验收结论（2026-08-10）

用户经 fresh-install 全新安装验证后确认：

- **Task 22（应用身份与 Gus icon）**：通过。
- **Task 23（per-user installer）**：通过（安装无 UAC、图标/版本身份、开始菜单、卸载保留数据）。
- **Task 24（GitHub Release）**：本次以真实发布流程验证。
- **Task 25（双语 UI 与 Settings locale）**：通过（Settings 语言切换、持久化、新稿 POST `language`）。
- **Task 26（双语生成与图像 prompt）**：通过（en-US 全链路英文 + zh 回归）。

本地构建产物：`dist\installer\PelicanTownSpecials-Setup-v1.0.0.exe`（SHA-256
`372A94EE19B810B798F417CF0E8DA701A62BFF01B78483DD3E92ED00FF9725B5`，含 Gus icon 门禁、
版本身份门禁、content gate；前端 bundle 确认含 `pts-locale` 语言切换）。

## Release 执行（用户已授权 push）

1. push `feat/mvp-implementation`（Task 22–26 全部本地 focused commit + 控制面记录）。
2. `git tag v1.0.0` → push tag → 触发 `release.yml`（`on: push: tags: 'v*'`）。
3. GitHub Actions 在 Windows runner 从源码全量重建：ruff/mypy/pytest/文案与多语言门禁/
   前端单测/lint/build/Playwright E2E → onedir bundle → Inno Setup 安装器 → smoke →
   版本漂移门 → 便携 ZIP → RELEASE_NOTES → SHA256SUMS → 创建 GitHub Release v1.0.0。

## 验收限制

- 发布产物由 GitHub runner 重建，SHA-256 与本地构建不同（正常）；本地安装包仅作预览。
- Task 23 记录的双路径 workspace（`%LOCALAPPDATA%\PelicanTownSpecials\PelicanTownSpecials\workspace`）
  保留为候选后续项，不阻塞本次发布。
