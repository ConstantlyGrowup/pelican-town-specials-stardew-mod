# Session｜Milestone 10 验收与 v1.4.0 Release

| 字段 | 值 |
|---|---|
| session_id | `2026-08-29-milestone-10-acceptance-and-v1-4-0-release` |
| status | `release_in_progress` |
| date | `2026-08-29` |
| scope | M10 用户联合验收、v1.4.0 版本提升、本地干净构建验证、branch/tag push 与 GitHub Release 核验 |
| base_commit | `c4c1bcf test: verify release telemetry end to end` |

## 用户授权与统计口径

- 用户明确授权推送 M10 代码、提升版本并发布新的 GitHub Release。
- 下一功能版本采用 `v1.4.0`，发布范围包含已推送但尚未进入正式 Release 的 M9、Task 36.1/36.2，以及本地 M10 Task 37–39。
- 用户接受首次人工验收数据作为普通 personless 匿名事件参与聚合，不要求 Cohort 或测试渠道排除；该选择不改变事件 schema、运行配置或隐私 allowlist。
- GitHub Repository Variables 已由用户配置；不需要也不得把 PostHog Personal API Key 注入 Release。

## 发布边界

- 版本链同步：PyInstaller/installer、FastAPI/diagnostics、workflow defaults、release README、下载旁证默认 tag、锁定测试和生成 OpenAPI。
- 用户既有 `backend/src/pelican_town_specials/domain/canonical.py` 阈值 `0.90 → 0.80` 保持未暂存、未提交，不进入 v1.4.0。
- 本地发布候选必须从 committed HEAD 的干净 worktree 构建；本地 telemetry 使用 fake public config 验证包内容，不向真实 PostHog 发送事件。真实 Repository Variables 只由 GitHub Release workflow 注入。
- 发布产物必须包括 setup.exe、portable ZIP 和 SHA256SUMS.txt；workflow 与资产校验完成后再关闭本 Session。

## 进度

- 已开始同步 v1.4.0 版本链并重新生成 OpenAPI。
- 发布前全量验证、commit/push、tag 和 Release 结果待追加。
