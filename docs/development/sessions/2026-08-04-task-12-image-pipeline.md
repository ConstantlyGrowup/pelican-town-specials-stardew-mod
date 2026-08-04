# Session｜2026-08-04-task-12-image-pipeline

| 字段 | 值 |
|---|---|
| `session_id` | `2026-08-04-task-12-image-pipeline` |
| `session_type` | `implementation` |
| `state` | `committed` |
| `date` | `2026-08-04` |
| `task` | MVP Task 12：图片归一化、图标与预览合成 |
| `acceptance_contract_id` | `mvp-task-12-145e164-20260804-final-v1` |
| `revise_round` | `1`（第一轮 REVISE 4 项已修复；第二轮 PASS） |
| `owner` | Codex Main Agent 规划与审阅；Claude Code Implementer 执行；Review Subagent（gpt-5.6-luna/max） |
| `base_commit` | `145e164` |

## 实际模型与 effort

```yaml
actual_models:
  main: gpt-5.6-sol / effort: high
  review: gpt-5.6-luna / effort: max
  implementer: deepseek-v4-flash / effort: default
```

## 目标

建立完全本地、确定性、无模型费用的图片管线：收敛 Task 9 上传归一化边界（`images/input_normalizer`），生成 16×16 RGBA 游戏图标（`icon_pipeline`），并用版本化模板、登记资源与结构化菜品字段合成可由 golden hash 锁定的预览 PNG（`preview_compositor`）。

## 不包含

Ask Gus/Blueprint 生成编排（Task 13/14）、Provider 调用（Task 11）、Content Patcher 编译、导出/发布、前端页面、数据库、把生成结果写入 AssetStore/VisualSpec/DraftRecord、联网下载官方素材。

## planning_rulings（已应用）

`T12-RULING-001` 至 `T12-RULING-009` 全部按 Packet 应用。关键裁决：上传归一化收敛到 `images/input_normalizer`（AssetService 委托）、Noto Sans SC 2.04 字体逐字节收录（hash `76314658...`）、`build_preview_resources.py` 生成占位模板并登记 provenance、根 `resources/provenance.json` 独立于 Task 8 catalog provenance、Pillow 固定 12.3.0、图标 14×14 居中留边、预览文字坐标/数值冻结。

## 实现证据

- `images/`：input_normalizer（EXIF/模式/元数据/重编码/bomb 边界）、icon_pipeline（16×16 RGBA）、preview_compositor（960×540 合成 + 结构化文字）。
- 资源：`resources/templates/preview-v1/{layout,frame.png,parchment.png}`、`resources/fonts/NotoSansSC-VF.ttf`、`resources/provenance.json`、`THIRD_PARTY_NOTICES.txt`（SIL OFL 1.1）。
- 验证：`backend/tests/images` 16 passed；资产上传回归 20 passed；全量 404 passed/2 skipped；Ruff、mypy（64 源文件）、`build_preview_resources.py --check`、`git diff --check` 通过。

## Review 结果

- 第一轮（revise_round=0，gpt-5.6-luna/max）：`REVISE`，4 项 MUST_FIX（metadata 清除、bomb Warning 映射、预览文字截断、samples 归属）。均已修复并补测试。
- 第二轮（revise_round=1，gpt-5.6-luna/max）：`PASS`，无 MUST_FIX、无 OPTIONAL_HARDENING、无 NEW_DESIGN；`scope_delta: none`。
- 修复后验证：images 20 passed；全量 408 passed/2 skipped；资源 `--check`、Ruff、mypy（64 源文件）、`git diff --check` 通过；golden 已重新生成。

## 当前状态

- `state`: `committed`
- `next_action`: Task 12 Review PASS 后 auto_accepted + 本地 focused commit（不 push）；按里程碑粒度继续 Task 13（Ask Gus 生成 Orchestrator）。
