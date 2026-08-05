# Session｜2026-08-05-r7-edit-edge-alignment

| 字段 | 值 |
|---|---|
| `session_id` | `2026-08-05-r7-edit-edge-alignment` |
| `session_type` | milestone-acceptance-fix |
| `state` | committed |
| `date` | 2026-08-05 |
| `task` | Milestone 3 验收修复（R7）：预览双图 EDIT 输入 edges 对齐 16 倍数 |
| `acceptance_contract_id` | `milestone3-acceptance-fix-r7-16-alignment` |
| `revise_round` | 0（PASS） |
| `base_commit` | `fb40992` → `90700b6` |

## 实际模型与 effort

```yaml
actual_models:
  main/coordinator: deepseek-v4-flash / effort: max
  implementer: 包工直接实施（参照 R1–R4 验收修复先例，改动 2 文件）
  review: Codex gpt-5.6-luna / xhigh（经 codex-mcp 独立新 thread）
```

## 背景

用户真实环境运行 Ask Gus（R6 双图 EDIT 预览管线）时，Provider 控制台报错：`status_code=400, invalid image size: edges must be multiples of 16 (got "990x1051")`，生成挂起至超时。

根因：`downscale_for_vision`（`images/vision_input.py`）只保证长边 ≤2048，缩放与不缩放两条路径都**未对齐 16 倍数**；EDIT 请求的 `source_images[0]` 与 `size=` 参数（990x1051）因此违反 provider 约束被 400。

## 实现（commit `90700b6`，2 文件 +46/-7）

- `vision_input.py`：新增 `VISION_EDGE_MULTIPLE = 16` 与 `_align_edge(px)`（向下取整到 16 倍数，min 16 保护）；`downscale_for_vision` 缩放路径与不缩放路径统一——目标尺寸各自 `_align_edge`，与源尺寸不同才 LANCZOS resize（640x480 等已对齐输入保持原样不 resize）。对齐只让尺寸更小，不会超 max_side。
- 测试（TDD 红→绿）：`test_scaled_edges_are_multiples_of_sixteen`（4032x2689 → 2048x1360，先红 1366%16=6）；`test_unscaled_edges_are_aligned_to_sixteen`（990x1051 ≤2048 也对齐 → 976x1040，先红未对齐）。
- 同一函数同时服务 DISH_ANALYSIS（vision chat 输入）——对齐 16 倍数对其无害且更合规。

## 验证结果

- focused vision_input **9 passed**；全量 backend **464 passed / 2 skipped**；ruff、mypy（69 源文件）、`git diff --check` clean。
- Codex 独立审阅 **PASS**（round 0，must_fix 空；R7-ALIGN/R7-REGRESSION/R7-DISH/R7-CONTRACT/R7-VERIFY 全过）。
- 无 OpenAPI/契约/前端变化；R6 双图 EDIT 语义不变。
- 已创建本地 focused commit `90700b6`，未 push。

## 非阻塞观察

- 用户需重试 Ask Gus 确认 400 消失；若 provider 仍报尺寸/比例问题，检查 `size=` 参数语义（部分 provider 要求 size 与输入一致）。
