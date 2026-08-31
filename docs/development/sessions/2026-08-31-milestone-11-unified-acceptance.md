# Session｜Milestone 11 统一人工验收

| 字段 | 值 |
|---|---|
| session_id | `2026-08-31-milestone-11-unified-acceptance` |
| status | `accepted` |
| session_type | `milestone-acceptance` |
| owner | Codex 主 Agent（M11 全量接管） |
| started_at | `2026-08-31` |
| user_authorization | `M11 规划已授权；用户在最终验收前追加失败不扣次修复、直接重试、Key 轮换及 Task 43/44` |
| base_commit | `1ad271a docs: close v1.4.0 release session` |
| focused_commit | `3e59447 feat: complete milestone 11 trial recovery UX` |
| user_acceptance | `2026-08-31 用户明确反馈“验收完毕，已通过”，并授权推送与更新 Release 版本` |

## 本次统一验收范围

- 完整生成成功后才兑现试用，失败/取消不扣次；用户已实测核心失败不扣次通过。
- 试用暂时不可用的按钮文案为“直接重试 / Retry now”；新试用资源已进入 gitignored 本地资源并完成远端 Actions Secret 轮换。
- Task 43：料理蓝图已选分类可清空，标签可逐项移除，中英文无障碍名称完整。
- Task 44：Ask Gus 与 Blueprint 的试用不可用反馈区可发起放弃草稿，复用确认弹窗，成功删除后回主页。

## 自动验收证据

- M11 完整生成兑现修复：detector PASS；focused backend `106 passed`。
- Task 43：detector PASS；Blueprint focused `27 passed`；TypeScript、ESLint、diff-check 全绿。
- Task 44：detector PASS；GenerationError + Ask Gus + Blueprint focused `71 passed`；TypeScript、ESLint、diff-check 全绿。
- React 质量清单：组件职责、Hooks、可访问性、性能与 TypeScript 无 must-fix；原生按钮、动态 aria-label、装饰性 ×、页面持有副作用均符合现有模式。
- 最终完整门禁：backend/integration `889 passed / 2 skipped`；frontend `191 passed`；前端生产构建、OpenAPI drift、ignore policy、telemetry manifest、PyInstaller、EXE 图标/1.4.0 身份与内容门全部通过。
- Bundle smoke：递归 SQLite 扩展、健康页、静态主页、持久 Registry 和同一临时工作区二次启动全部通过。
- 最新验收 EXE：`dist/PelicanTownSpecials-windows-x64/PelicanTownSpecials.exe`；SHA256 `112C55A2A642BBE4FE38A7FDCC5D97E4A2A02AD442739DAAB14E18E2826AD30C`。
- Bundle 中试用资源存在、长度与本地一致且 SHA256 匹配；未读取或输出 Key 内容。本地验收构建遥测默认关闭，正式 Release 仍由 GitHub Actions Repository Variables 注入。

## 待用户人工检查

1. Blueprint 中点击分类或任一标签旁的 ×，确认可清除/逐项移除，并能重新选择。
2. 触发“试用功能暂时不可用”后，确认出现“放弃草稿并返回主页”；点击后先弹确认，取消保留草稿，确认才删除并回主页。
3. 可选复验“直接重试”和失败不扣次；这些链路已有自动与前次人工证据。

用户已明确验收并授权 push、版本提升、tag 与 Release。M11 focused commit `3e59447` 已创建，当前进入 v1.5.0 版本链与发布门禁。
