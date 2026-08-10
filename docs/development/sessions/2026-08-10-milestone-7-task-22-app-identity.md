# Session｜Milestone 7 Task 22 应用身份与 Gus icon

| 字段 | 值 |
|---|---|
| session_id | `2026-08-10-milestone-7-task-22-app-identity` |
| session_type | `milestone-7-task-22-implementation` |
| status | `auto_accepted`（Codex PASS，本地 focused commit，未 push） |
| owner | Codex 主会话（Claude Code 主会话实施 + Codex 独立审阅） |
| started_at | `2026-08-10` |
| user_acceptance | `pending`（M7 全量验收时统一） |
| base_commit | `b5bd03d docs: authorize Milestone 7 and open Task 22 app identity session` |
| product_commit | `7286c74 feat: add Gus portrait app icon and EXE identity gate` |

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

## 实施进度（全部完成）

- [x] 更新 STATUS.md / AGENTS.md / 规划 Session，反映授权与协作模式切换（控制面提交 `b5bd03d`）。
- [x] 生成 Context Packet `mvp-task-22-app-identity-v1`（planning_status: READY_FOR_IMPLEMENTATION）。
- [x] 实现：`scripts/generate_app_icon.py`、`packaging/assets/pelican-town-specials.ico`
      （16/24/32/48/64/128/256，确定性）、`packaging/assets/provenance.json`、spec `icon=`、
      `scripts/check_exe_icon.ps1`、`build_windows.ps1` 接入 EXE icon gate、
      `tests/repo/test_app_icon.py`。
- [x] 验证：见下方「验证证据」。
- [x] Codex 独立审阅（gpt-5.6-luna/max，新 thread）→ **PASS**（round 0，无 MUST_FIX）→
      auto_accepted → 本地 focused commit `7286c74`（8 文件 +364/-1）。
- [x] 更新本 Session 记录与 STATUS.md。

## Codex 审阅（gpt-5.6-luna / max effort，独立 thread）

- round 0 **PASS**（无 MUST_FIX；4/4 criterion checked，scope_delta none）。
- OPTIONAL_HARDENING（已就地处理，非 MUST_FIX）：
  - `--check` 增补 `provenance.source_sha256` 校验（M7-T22-ICON-004 直接要求）。
  - Session base_commit 改为实际基线 `b5bd03d`（原误写 `ae5b320`）。

## 验证证据（全部通过）

- `python -m pytest tests/repo -q`：**13 passed**（8 存量 + 5 新增 Task 22）。
- `python scripts/generate_app_icon.py --check`：OK（确定性、7 尺寸、provenance 一致）。
- `python -m pytest backend/tests tests/repo tests/integration -q`：**671 passed / 2 skipped**。
- `python -m ruff check backend`、`python -m mypy backend/src`：clean（87 source files）。
- `pwsh -File scripts/build_windows.ps1`：exit 0；EXE icon gate reference 32px hash
  `3FE51DEB...` == built exe hash；EXE version identity ProductName
  「Pelican Town Specials」/ 1.0.0；release content gate OK。
- `pwsh -File scripts/smoke_windows_bundle.ps1`：Phase A + Phase B OK，exit 0。
- Pillow ICO 确定性探针：7 frames（16..256），byte-identical 重生成。

## 范围说明

- Task 23（per-user installer）不实施；Task 24（GitHub Release）不实施；
  Task 25/26（双语）不实施。
- 不运行真实 Provider；icon 生成本地确定性完成。
