# Session｜Task 46 生成报错信息英文本地化与 v1.5.2 发布

| 字段 | 值 |
|---|---|
| session_id | `2026-09-01-task-46-generation-error-localization-release` |
| status | `released` |
| session_type | `product_patch_release` |
| owner | WorkBuddy 主会话（Codex 协作模式休眠，单会话直接实施） |
| started_at | `2026-09-01` |
| user_authorization | `2026-09-01 用户报告英文界面报错信息仍为中文并要求修复；随后要求把修复同步到当前 main/MVP 以及最新发布包` |
| base_commit | `73870ce docs: close v1.5.1 blueprint release` |
| feature_commit_mvp | `40b2a6e fix: localize generation error messages` |
| feature_commit_main | `23232cd fix: localize generation error messages` |
| release_version | `v1.5.2` |

## 目标与边界

英文界面下 Blueprint、Ask Gus 与系统级生成错误横幅改为显示英文提示；后端消息保持中文权威，前端按错误码映射本地化文案，未知错误码回退后端消息。同步到 `main` 与 `feat/mvp-implementation`，并以 patch 版本 v1.5.2 生成、测试和发布 Windows installer、portable ZIP 与 SHA256SUMS。

不改变后端 API/schema、错误码集合、错误 details、重试/接管/配置/放弃按钮逻辑、试用额度、Canonical 召回、分类/标签 canonical 值，以及两个分支各自的 README 定位。

## Acceptance Ledger

- **T46-001**：英文界面下 `GenerationError` 对全部固定消息生成错误码显示英文文案，不显示中文后端消息。
- **T46-002**：`PTS_PROVIDER_AUTH_FAILED` 与 `PTS_PROVIDER_UNAVAILABLE`（后端消息按失败模式变化）在英文界面显示合并后的英文提示；中文界面保留后端精确措辞。
- **T46-003**：未知错误码继续回退后端消息作为诊断兜底。
- **T46-004**：中文界面除 `PTS_PROVIDER_IMAGE_INVALID`（原样透传英文诊断文本改为友好中文）外行为不变。
- **T46-005**：同一产品补丁进入 main 与 MVP；两份根 README 均不被该产品补丁覆盖。
- **T46-006**：v1.5.2 版本链一致，完整测试、OpenAPI、Windows bundle/installer 门禁通过，Release 三项资产可核验。

## 已完成证据

- MVP feature commit `40b2a6e`；main cherry-pick commit `23232cd`，两分支该补丁内容 diff 为空。
- `GenerationError.test.tsx` 更新 1 个、新增 4 个用例；frontend 全量 `197 passed`。
- ESLint、TypeScript `--noEmit` 全绿；无 API 改动，OpenAPI 仅 `info.version` 随版本链更新。
- MVP release commit `d51164b`：版本链 13 文件同步 v1.5.2（workflows、app.py、diagnostics.py、version_info.txt、.iss、README.txt、notes/下载脚本、repo 门禁测试）。
- repo 门禁 `52 passed`；`scripts/build_windows.ps1` 全流程通过：backend `891 passed`、frontend `197 passed`、OpenAPI drift、ignore policy、telemetry dashboard contract、PyInstaller onedir、EXE 图标与版本身份（`1.5.2`）、bundle 结构与内容门全绿。
- 用户原始指令已明确授权同步 main/MVP 与最新发布包；两分支、tag、GitHub Actions 与 Release 资产核验均已完成。

## 发布结果

- `main` 已推送至 `14a3915`，`feat/mvp-implementation` 已推送至 `40466ef`；两分支根 README 保持各自用途。
- annotated tag `v1.5.2` 指向 `40466ef`；GitHub Actions run `33470806371` 全部成功。
- 正式 Release 包含 setup.exe（43,502,645 B）、portable ZIP（48,536,844 B）和 `SHA256SUMS.txt`。
- 独立下载核验：setup SHA256 `32390ec7d9411ad6489d06d362ce4aedbcd50077bbdb8cfa451dccda4c8990a5`；portable ZIP SHA256 `290bfc9c46248ddaa79fc6e6fe82e9590bbd46a9119779223168037d4f0b2632`，均与发布校验文件一致。
