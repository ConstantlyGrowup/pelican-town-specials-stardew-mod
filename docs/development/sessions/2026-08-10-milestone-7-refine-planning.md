# Session｜Milestone 7 Refine 规划

| 字段 | 值 |
|---|---|
| session_id | `2026-08-10-milestone-7-refine-planning` |
| session_type | `milestone-7-planning` |
| status | `planned → authorized`（2026-08-10 用户确认规划并授权开始 Task 22） |
| owner | Codex 主会话 |
| started_at | `2026-08-10` |
| implementation_started | `false`（本 Session 仅规划；Task 22 实施由新 Session 承担） |
| user_acceptance | `authorized` |
| base_commit | `ae5b320 feat: implement Task 21 visual refinement` |

## 目标

根据用户提出的 Milestone 7（refine）需求，维护项目控制面并完成可实施的 Task 拆分，不修改产品代码，不构建 installer，不创建 GitHub Release，不提交或推送。

## 用户需求映射

1. 当前版本可以打包为 Windows installer，并在 GitHub Release 提供给普通玩家下载。
2. EXE 应用图标改为 Gus portrait。
3. Settings 增加语言切换，提供英文 UI；英文新稿生成的图片词条也使用英文。

## 已完成的规划检查

- 已核对 `AGENTS.md`、`STATUS.md`、`CONSTRAINTS.md`、`REVIEW_PROTOCOL.md`、`CONTEXT_PACKET_SCHEMA.md`、MVP 技术设计、MVP 实施计划和项目设计源索引。
- 已核对当前 Git 基线：`HEAD` 与 `origin/feat/mvp-implementation` 均为 `ae5b320`；当前仅有用户/临时未跟踪目录，未清理。
- 已核对现有 Windows 运行链路：PyInstaller `onedir`、`build_windows.ps1`、bundle smoke、release README、CI artifact；确认目前没有 installer/release workflow。
- 已核对现有语言基础：后端 `Language` 已有 `zh-CN`/`en-US`，前端 copy 仍以中文为主，Create 请求语言硬编码中文，prompt 模板主要为中文。
- 已核对 Gus portrait 素材：`frontend/public/assets/ui/gus-portrait-1.png` 可作为默认 `.ico` 源；实现前保留用户覆盖选择权。

## Task 划分

| Task | 主题 | 依赖 | 规划状态 |
|---|---|---|---|
| 22 | Windows 应用身份与 Gus icon | Milestone 6 | planned |
| 23 | Windows per-user installer | 22 | planned |
| 24 | GitHub Release 自动发布 | 23 | planned |
| 25 | 双语 UI 与 Settings locale | Milestone 6 | planned |
| 26 | 双语生成与图像 prompt | 25 | planned |

推荐执行顺序：`22 → 23 → 24 → 25 → 26`。完整的文件预期、接口边界、规划裁决和验收条件见：

- `docs/plans/2026-08-10-milestone-7-refine.md`
- `docs/plans/MVP_IMPLEMENTATION_PLAN.md` 的 Milestone 7 章节

## 规划裁决摘要

- Installer 包裹现有 onedir，不替换 launcher 或 workspace 结构。
- 默认 per-user 安装，无管理员权限；卸载保留用户 workspace。
- Release 仅 tag/manual 触发，release job 使用最小写权限并生成 SHA-256。
- 默认 locale 为 `zh-CN`，使用 localStorage；新稿使用当前 locale，旧记录的 `source.language` 保持权威。
- M7 优先使用语言专用 prompt 模板和最终视觉 prompt，不默默引入第二次翻译模型调用。
- 英文显示名不能成为唯一存储身份；原版 catalog item identity、Gameplay 数值和 Mod 编译协议保持稳定。

## 当前不做

- 不创建 Task 22–26 的实施 Context Packet。
- 不修改 `frontend/`、`backend/`、`packaging/`、`.github/` 产品/发布实现文件。
- 不运行产品测试、build、installer 或 release workflow；规划阶段无新的测试证据。
- 不 stage、commit、push 或创建 GitHub Release。

## 下一步（2026-08-10 已确认）

用户确认 Task 拆分与规划裁决，并授权开始 Task 22；协作模式切回「主会话实施 → Codex MCP 独立审阅（gpt-5.6-luna/max，新 thread）」，按里程碑粒度推进。规划使命已完成，Task 22 实施由新实施 Session/Context Packet 承担，按 `22 → 23 → 24 → 25 → 26` 串行推进。若用户希望减少或合并 Task，可在实施前修改本 Session 和主计划，不带入代码实现。

