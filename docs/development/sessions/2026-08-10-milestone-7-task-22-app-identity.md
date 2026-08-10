# Session｜Milestone 7 Task 22 应用身份与 Gus icon

| 字段 | 值 |
|---|---|
| session_id | `2026-08-10-milestone-7-task-22-app-identity` |
| session_type | `milestone-7-task-22-implementation` |
| status | `in_progress` |
| owner | Codex 主会话（Claude Code 主会话实施 + Codex 独立审阅） |
| started_at | `2026-08-10` |
| user_acceptance | `pending` |
| base_commit | `ae5b320 feat: implement Task 21 visual refinement` |

## 任务范围

按 `docs/plans/2026-08-10-milestone-7-refine.md` Task 22：从批准的 Gus portrait
生成确定性的多分辨率 Windows `.ico`，接入 PyInstaller EXE icon、文件属性与后续
installer shortcut。**不生成 installer、不改 GitHub workflow、不新增语言功能。**

验收条件（Acceptance Ledger，见 Context Packet `mvp-task-22-app-identity-v1`）：
- `M7-T22-ICON-001`：ICO 含 16/24/32/48/64/128/256 所需尺寸，透明/边缘无意外拉伸。
- `M7-T22-ICON-002`：Windows Explorer、EXE 文件属性和启动入口显示 Gus portrait；
  不是默认 PyInstaller 图标。
- `M7-T22-ICON-003`：现有 backend/frontend/build/bundle smoke 全部通过，icon 变化
  不改变启动和静态资源行为。
- `M7-T22-ICON-004`：icon 来源与生成方式可审计，不把临时截图、用户 workspace 或
  源设计包放进 release。

规划裁决 M7-D05：EXE icon canonical source 默认 `gus-portrait-1.png`
（1254×1254 RGB 带边框方形），确定性生成多尺寸 `.ico`，不在运行时裁剪 portrait。

## 协作模式

用户 2026-08-10 确认：主会话（Claude Code）直接实施 + 自动验证；完成后拉起
Codex MCP 独立审阅（`gpt-5.6-luna` / max effort，新 thread）；PASS → auto_accepted
→ 本地 focused commit；里程碑粒度不打断用户。

## 规划裁决

- 保留 PyInstaller onedir 架构；icon 只改变 EXE/快捷方式身份，不改变运行时。
- `.ico` 由 `scripts/generate_app_icon.py` 从 `frontend/public/assets/ui/gus-portrait-1.png`
  确定性生成（Pillow，多尺寸），产物 `packaging/assets/pelican-town-specials.ico`。
- `PelicanTownSpecials.spec` 增加 `icon=` 指向该 `.ico`；`version_info.txt` 身份校验
  作为 repo gate 的一部分。
- release 内容 gate 拒绝临时截图、源设计包、workspace 与样本素材。

## 实施进度

- [x] 更新 STATUS.md / AGENTS.md / 规划 Session，反映授权与协作模式切换（控制面提交）。
- [ ] 生成 Context Packet `mvp-task-22-app-identity-v1`（planning_status: READY_FOR_IMPLEMENTATION）。
- [ ] 实现：`scripts/generate_app_icon.py`、`packaging/assets/pelican-town-specials.ico`、
      spec `icon=`、repo/release gate 测试。
- [ ] 验证：icon 尺寸/内容、backend/frontend 回归、bundle build + smoke、copy gate。
- [ ] Codex 独立审阅（gpt-5.6-luna/max，新 thread）→ PASS → auto_accepted → 本地 focused commit。
- [ ] 更新本 Session 记录与 STATUS.md。

## 范围说明

- Task 23（per-user installer）不实施；Task 24（GitHub Release）不实施；
  Task 25/26（双语）不实施。
- 不运行真实 Provider；icon 生成本地确定性完成。
