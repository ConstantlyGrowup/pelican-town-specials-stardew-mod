# Session｜Task 45 Blueprint 英文分类/标签与 v1.5.1 发布

| 字段 | 值 |
|---|---|
| session_id | `2026-09-01-task-45-blueprint-meta-localization-release` |
| status | `accepted` |
| session_type | `product_patch_release` |
| owner | Codex 主 Agent |
| started_at | `2026-09-01` |
| user_authorization | `2026-09-01 用户要求检查最新 Blueprint 改动，同步 main/MVP，并进入最新发布包` |
| base_commit | `9652a5f docs: sync branch documentation boundaries` |
| feature_commit_mvp | `9144848 fix: localize blueprint metadata choices` |
| feature_commit_main | `016fc5b fix: localize blueprint metadata choices` |
| release_version | `v1.5.1` |

## 目标与边界

英文界面的料理蓝图分类与标签使用英文显示和英文搜索，同时继续把既有中文 curated 值作为 canonical 数据提交给后端。同步到 `main` 与 `feat/mvp-implementation`，并以 patch 版本 v1.5.1 生成、测试和发布 Windows installer、portable ZIP 与 SHA256SUMS。

不改变分类/标签候选集合、后端 API、草稿 schema、生成 Prompt、中文界面、自由标签回退、试用额度、Canonical 召回或两个分支各自的 README 定位。

## Acceptance Ledger

- **T45-001**：英文 Blueprint 已选分类、已选标签和选择器选项显示英文标签。
- **T45-002**：英文搜索词可以筛选中文 canonical 值对应的英文标签。
- **T45-003**：保存草稿时仍提交中文 canonical category/tag 值，兼容既有后端、Prompt 与存档。
- **T45-004**：中文界面保持中文；未映射自由值保持原值；移除操作与无障碍名称使用当前显示语言。
- **T45-005**：同一产品补丁进入 main 与 MVP；两份根 README 均不被该产品补丁覆盖。
- **T45-006**：v1.5.1 版本链一致，完整测试、OpenAPI、Windows bundle/installer 和 smoke 门禁通过，Release 三项资产可核验。

## 已完成证据

- MVP feature commit `9144848`；main cherry-pick commit `016fc5b`。
- MVP focused Blueprint tests：`32 passed`；完整 frontend：`193 passed`。
- ESLint、TypeScript 与 Vite production build 通过。
- main 独立工作树 focused Blueprint tests：`32 passed`；README 无差异。

## 当前进度

v1.5.1 Release Candidate 已完成：

- MVP release commit `dce9909`；main release commit `73ee31a`，main 根 README 保持 `e237802` 的用户手册内容不变。
- release/version tests `11 passed`；完整 backend `889 passed / 2 skipped`；完整 frontend `193 passed`；ESLint、TypeScript/Vite、OpenAPI 与 release version gate 全绿。
- PyInstaller onedir 构建成功，EXE ProductVersion/FileVersion 均为 `1.5.1`；bundle health、首页、SQLite 与两次启动 smoke 通过。
- Inno Setup `PelicanTownSpecials-Setup-v1.5.1.exe` 构建成功；隔离安装、启动、覆盖重装、卸载与工作区保留 smoke 通过。
- 用户原始指令已明确授权同步 main/MVP 与最新发布包；下一步推送两分支和 `v1.5.1` tag，并核验 GitHub Actions/Release 资产。
