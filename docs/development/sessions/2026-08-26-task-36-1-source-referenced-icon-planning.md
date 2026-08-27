# Session｜Task 36.1 原图参考像素图标补丁规划

> Session ID：`2026-08-26-task-36-1-source-referenced-icon-planning`
> 状态：accepted / closed
> 类型：planning
> 基线：`e0a9509`

## 用户确认的产品要求

- 像素图标与原图差异过大会影响最终效果。
- 若 Canonical 命中并存在历史图标，直接复用历史图标。
- 若初次生成没有命中，则像素图标必须参考本次原图生成。

## 规划裁决

- 作为 M9 后的独立补丁插入，编号使用项目已有的小数插入惯例 `Task 36.1`，不重编号已经验收的 M10 Task 37–39。
- “像素图也要参考原图”适用于所有非 Canonical 复用路径：Ask Gus INITIAL miss、FULL_REGENERATE 与 Blueprint。
- fresh icon 从纯文本 `ImageOperation.GENERATION` 改为单原图 `ImageOperation.EDIT`；调用次数不增加。
- Canonical HIT 保持零 icon generation，继续导入历史 icon；最终 preview 仍使用当前原图和当前/复用 icon 的双图 edit。
- 无前端、OpenAPI、领域/持久化 schema、召回算法或发布配置变化。

## 当前状态

详细计划已建立：`docs/plans/2026-08-26-task-36-1-source-referenced-icon.md` v1.0。用户于 2026-08-26 明确要求查看现有计划并实施，视为规划验收和源码实施授权；本规划 Session 随即关闭，实施转入独立 Session `2026-08-26-task-36-1-source-referenced-icon-implementation`。

Context Packet：`docs/plans/2026-08-26-task-36-1-source-referenced-icon-packet.md`（gitignored）。规划阶段未调用真实 Provider、未提交或推送。
