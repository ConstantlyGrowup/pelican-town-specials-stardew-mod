# Session｜Milestone 7 Task 24 GitHub Release auto-publish

| 字段 | 值 |
|---|---|
| session_id | `2026-08-10-milestone-7-task-24-release` |
| session_type | `milestone-7-task-24-implementation` |
| status | `auto_accepted` |
| owner | Codex 主会话（Claude Code 主会话实施 + Codex 独立审阅） |
| started_at | `2026-08-10` |
| user_acceptance | `pending`（Milestone 7 全量验收时统一，不 push） |
| base_commit | `2d1f926 docs: record Task 23 installer acceptance and open Task 24 release session` |
| implementation_commit | `529981a feat: add GitHub Release auto-publish workflow (tag/manual, checksum, notes)` |

## 任务范围

按 `docs/plans/2026-08-10-milestone-7-refine.md` Task 24：为 GitHub Release 提供
自动发布入口（v* tag / manual dispatch 触发），生成 checksum、release notes，使用
最小写权限。**不实现 Task 23 的 installer 逻辑变更、Task 25/26 双语。**

## 协作模式

用户 2026-08-10 确认：主会话（Claude Code）直接实施 + 自动验证；完成后拉起
Codex MCP 独立审阅（`gpt-5.6-luna` / max effort，新 thread）；PASS → auto_accepted
→ 本地 focused commit；里程碑粒度不打断用户。

## Context Packet

- `mvp-task-24-release-v1`（`docs/plans/2026-08-10-task-24-release-packet.md`，gitignored）。
- 规划裁决 R-01..R-06：可复用 build.yml（`workflow_call`，version 默认 1.0.0，只读）；
  版本解析（tag/manual 去 v）+ 漂移门；便携 ZIP 由 build.yml 从已验证 bundle 生成；
  create-release 仅 job-scoped `contents: write` + `GH_TOKEN=${{ github.token }}`；
  checksum 在 create-release 对下载产物生成；release notes 由 Windows 作业生成并上传。

## 实施内容

- `.github/workflows/build.yml`（新增）：可复用 verify-and-build 管线（`on: workflow_call`，
  version input 默认 `1.0.0`，`permissions: contents: read`）；原 CI 全部步骤 + 版本漂移门
  （`check_release_version.ps1`）+ 便携 ZIP（Compress-Archive）+ release notes 生成 + 4 个
  artifact 上传（bundle / installer / portable ZIP / release notes，均 `if-no-files-found: error`）。
- `.github/workflows/ci.yml`（改写为薄调用方）：push（feat/mvp-implementation、main）+ PR
  触发，复用 build.yml，永不发布（无 `gh release create`）。
- `.github/workflows/release.yml`（新增）：v* tag push + workflow_dispatch（version 默认
  `v1.0.0`）；`resolve-version` 作业剥离 v 并输出 version/tag；`verify-and-build` 复用
  build.yml；`create-release` 作业（ubuntu，job-scoped `contents: write`，`GH_REPO` 显式）
  下载产物 → `sha256sum` 生成 `SHA256SUMS.txt` → `gh release create`（installer + portable
  ZIP + checksum + `--notes-file`）；create-if-absent / update-if-present
  （`gh release view` → `gh release edit` + `gh release upload --clobber`）保证重复运行可复现。
- `scripts/check_release_version.ps1`（新增）：版本漂移门，比对 `packaging/pyinstaller/version_info.txt`
  的 FileVersion，不匹配即 throw（M7-D04）。
- `scripts/generate_release_notes.ps1`（新增）：版本化中文 release notes（下载链接 + per-user
  安装步骤 + workspace 保留说明）。
- `tests/repo/test_release.py`（新增 6 条）：触发边界、管线复用、版本一致性、最小写权限与无
  secrets、产物/checksum/notes 一致性、可复现与仓库上下文（`gh release view`/`edit`/`upload --clobber`、`GH_REPO`）。
- `tests/repo/test_installer.py`（修改）：CI installer 构建断言迁移到共享 build.yml。

## 审阅

Codex（`gpt-5.6-luna` / max，新 thread）：
- round 0 **REVISE**（2 项 MUST_FIX）：
  - M7-T24-RELEASE-001：`create-release` 作业无 checkout / `GH_REPO` / `--repo`，`gh` 无仓库上下文 →
    修复：作业步骤 env 显式设置 `GH_REPO: ${{ github.repository }}`。
  - M7-T24-RELEASE-002：仅 `gh release create`，重复运行已创建 tag 不可复现 → 修复：
    create-if-absent / update-if-present（`gh release view` → `gh release edit` +
    `gh release upload --clobber`），并新增 `test_release_repeatable_and_repo_scoped` 门禁。
- round 1 **PASS**（4/4 criterion，无 MUST_FIX，scope_delta none）。OPTIONAL_HARDENING：
  本机无 gh CLI，未做真实 GitHub 命令。

## 验证

- `tests/repo` **28 passed**（含 6 条 release 门禁，round-1 新增 1 条）。
- 全量 backend+repo+integration **686 passed / 2 skipped**（round-0 后重跑，exit 0）。
- ruff / mypy clean（87 source files）；workflow YAML 全部有效。
- 漂移门：`-Version 1.0.0` 与 `v1.0.0` 通过，`-Version 2.0.0` 明确报错（exit 1）。
- release notes 生成器输出版本化中文 notes（`.pytest_tmp/release-notes.md`）。
- 本地 dry-run 发布产物：便携 ZIP `PelicanTownSpecials-windows-x64-v1.0.0.zip`
  （47,072,076 字节，内含 `PelicanTownSpecials-windows-x64/PelicanTownSpecials.exe`）；
  `sha256sum -c SHA256SUMS.txt` 对 installer（565cd414…）与 ZIP（0488798e…）均 OK；
  产物名与 build.yml 上传名 / release.yml 下载与 sha256sum / gh 资产名完全一致。

## 范围

- 未创建真实 GitHub Release（仅 workflow 就绪 + 本地 dry-run 验证）；未改
  app/backend/frontend/installer 逻辑；Task 25/26（双语）未实施。
- 里程碑粒度：本 Task `PASS` 已 auto_accepted 并创建本地 focused commit，不 push；
  M7 全量验收后统一 push。
