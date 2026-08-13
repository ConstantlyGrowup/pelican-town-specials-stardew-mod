# Session｜Milestone 7 全量验收与 v1.0.0 / v1.1.0 Release

| 字段 | 值 |
|---|---|
| session_id | `2026-08-10-milestone-7-acceptance-and-release` |
| session_type | `milestone-7-full-acceptance-and-release` |
| status | `closed`（2026-08-11 用户确认 v1.1.0 fresh-install 复验通过，M7 正式关闭） |
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

## v1.1.0 fresh-install 复验（2026-08-11，用户确认通过）

用户对 GitHub Release **v1.1.0** 发布版做 fresh-install 全新安装验收，结果通过（含双语功能），
并宣布 Milestone 7 正式关闭。Task 22–26、M7 全量验证、v1.1.0 发布与 fresh-install 复验全部完成。

## Release 执行（用户已授权 push）

1. push `feat/mvp-implementation`（Task 22–26 全部本地 focused commit + 控制面记录）。
2. `git tag v1.0.0` → push tag → 触发 `release.yml`。**首次 v1.0.0 run 失败**：根因为
   `scripts/verify_local_docs_ignored.ps1` 在全新 checkout（gitignored 设计目录未物化）上
   `git check-ignore` 无法匹配带尾斜杠的目录模式 → 误报「repo ignore policy」失败。
3. 按用户指令修复：目录条目加尾斜杠（`'design docs/'` 等）+ 回归测试
   `tests/repo/test_ignore_gate.py`；并按用户要求把「当前版本（含双语前后端）」作为 **v1.1.0**
   重新发布（应用版本全链路 bump，Mod/导出版本不动；重新生成 OpenAPI 契约；本地
   `build_windows.ps1` + `build_installer.ps1` 全量验证通过）。commit `b39b50d`。

## v1.1.0 Release 实际发布（2026-08-10，成功）

- push `feat/mvp-implementation`（`b39b50d`）；`git tag -a v1.1.0` → push tag。
- `release.yml` run `31394532120`（head `b39b50d`）：**completed success**（分支 CI run
  `31394509289` 亦 success）。
- GitHub Release **v1.1.0** 产物已核验：
  - `PelicanTownSpecials-Setup-v1.1.0.exe`（42,665,645 B）
  - `PelicanTownSpecials-windows-x64-v1.1.0.zip`（47,442,130 B）
  - `SHA256SUMS.txt`（212 B，覆盖以上两产物）
  - release notes：中文完整版（下载/安装/卸载保留数据说明），见 release body。
- 本地构建验证链（commit 后复跑）全部通过：backend **673 passed / 2 skipped**、frontend
  **116 passed** + build、OpenAPI drift OK、repo ignore policy OK、PyInstaller OK、
  EXE icon gate OK、EXE 版本身份 1.1.0 OK、content gate OK；installer 图标门/版本身份
  OK（SHA-256 `C4E5BBBC…`）。

## 验收限制

- 发布产物由 GitHub runner 重建，SHA-256 与本地构建不同（正常）；本地安装包仅作预览。
- 旧 `v1.0.0` tag 留在远端但无 Release 产物；如用户需要可另行授权删除远端 tag。
- Task 23 记录的双路径 workspace（`%LOCALAPPDATA%\PelicanTownSpecials\PelicanTownSpecials\workspace`）
  保留为候选后续项，不阻塞本次发布。
- 2026-08-11 用户 fresh-install 复验 v1.1.0 安装版通过（含双语功能），M7 正式关闭。
