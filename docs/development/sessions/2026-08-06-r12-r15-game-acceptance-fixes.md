# 2026-08-06 R12–R15 游戏验收细节修复

## 背景

Task 18 游戏验收核心通过后（打包成功、游戏内找到物品），用户在真实游戏内发现四个 API 调用细节问题并授权修复。本 Session 为 Milestone 4 验收修复，延续 R1–R11 的编号与自治模式。

## 四个问题与修复

### R12 图标黑底（commit `5761e92`）

- 现象：模型生成的像素图标"透明底"实为不透明纯色底，游戏 UI 显示黑底方块。
- 根因：生成字节直接存为 ICON_SOURCE，全链无任何透明化处理；alpha 全 255 时 `build_icon_16` 的 bbox 框住整图，黑底原样保留。
- 修复：新增 `images/background_keying.py`（确定性 Pillow-only：边框近均匀 → 中位边框色为背景 → 4 连通洪泛去除，容差 40；已透明/非均匀边框/近全抠（>98%）三种情况原样保留，无新依赖）；orchestrator 图标阶段接入，keyed 结果存为 ICON_SOURCE（同时服务预览 EDIT 与 icon_16）；两处图标 prompt 增加"纯洋红色背景（#FF00FF）"指令提高可抠性。

### R13 Buff 游戏内不显示（commit `886de32`）

- 根因：编译器把 Buff 写成独立 `Data/Objects.Buffs` patch——该资产在游戏中不存在，补丁无效；且 `CustomAttributes` 误为字符串、`Duration` 误乘 60000。
- 修复：Buff 内嵌 `Data/Objects` 条目 `Buffs` 数组，结构逐字段对齐官方 1.6.15 Objects.json（`Id` 为 `"Food"`/`"Drink"`、`Duration` 为游戏分钟（与 domain `durationMinutes` 1:1）、`CustomAttributes` 为 18 键 float 对象）；golden content.json 重新生成；`.gitattributes` 固定 golden 为 LF（Windows stash/checkout 曾把 golden 转成 CRLF 导致字节比较失败）。

### R14 Edibility 偏高与换算公式（commit `8589a3e`）

- 根因：prompt 只给 0..500 上下限、无原版参照（官方菜品实测 20..105）；domain 派生公式 floor 近似与游戏显示差 1。
- 修复：prompt 冻结引导区间（普通 20..50、精致 50..90、极少超 100，附官方换算）；domain 派生改为官方公式 能量=ceil(edibility×2.5)、生命=floor(能量×0.45)（用户游戏内 135→338/152 实测验证）。

### R15 材料识别不准（commit `8589a3e`）

- 现象：鱼菜被映射成白藻/野山葵/蛋等无关材料（含静默 fallback 到 Egg）。
- 修复：analysis/ask_gus 双 prompt 约束（原料必须对应原版官方物品、主食材必须出现、鱼菜必须含鱼）；`catalog/mapping.py` 新增 `ensure_main_protein` 确定性护栏（菜名文本命中海鲜关键词但映射结果无鱼类 category `-4` 时，定向搜索插入最佳鱼类；满列表时替换第一个 fallback 材料；无关键词/已有鱼/满列表无 fallback 三种情况原样返回），接入 `_map_gameplay`。

## 验证

- 全量 backend 549 passed/2 skipped + 集成 16 passed（合计 565 passed/2 skipped）；Ruff clean；mypy 仅剩 3 处 HEAD 预存错误（exports.py/app.py，已 stash 基线确认与本次无关，疑为 mypy 版本漂移，留待工具链 Task 处理）；`git diff --check` clean。
- 独立只读 Review Subagent：PASS（无 MUST_FIX）。注：本环境无 codex-mcp 通道，按既有回退路径使用 Review Subagent，未冒充 Luna 路由。
- 非阻塞观察项（留档）：`_dish_text` 含 description/tags 可能低概率误触发插鱼；`_OPAQUE_ALPHA=250` 边缘；98–100% 抠除阈值边界未单测。
- 前端/契约：零改动（无 OpenAPI 变化）。

## 待用户下一轮游戏验收

- Buff 游戏内展示、Buff 持续时间、图标透明底视觉、Edibility 与材料合理性——需重新生成菜品并重新打包部署后确认。
- 既有草稿/图标资产不受影响（仅新生成生效）；完整重生成可刷新。
