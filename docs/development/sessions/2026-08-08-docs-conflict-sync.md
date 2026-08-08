# Session｜2026-08-08-docs-conflict-sync

| 字段 | 值 |
|---|---|
| `session_id` | `2026-08-08-docs-conflict-sync` |
| `session_type` | docs-sync |
| `state` | accepted → committing（用户确认 Brief §10 报告，授权控制面 commit + push） |
| `date` | 2026-08-08 |
| `task` | 按 `PelicanTownSpecials_文档冲突修改Brief_2026-08-08.md` 同步过时文档与产品描述冲突；仅文档，不改业务代码 |
| `acceptance_contract_id` | docs-conflict-sync-2026-08-08-v1（Brief D-UI-01/02/03） |
| `revise_round` | 0 |
| `base_commit` | `8343704`（nav home entry docs 记录之后） |

## 任务范围

用户提供 Brief，要求在当前项目空间同步过时文档与冲突描述。范围冻结为**文档同步 only**：

- 应用三项 2026-08-08 用户决策：D-UI-01（首页）、D-UI-02（导航）、D-UI-03（Ask Gus 三操作 / Blueprint 独立入口）。
- 不新增产品功能、不改业务代码/路由、不恢复已移除 UI、不发明 API 删除、不把 Milestone 6 品牌 Hero 标为已完成、不改写历史 Session。

## 三项裁决（写入正式源）

1. **D-UI-01**：首页 `/` = 品牌叙事 + 草稿 Dashboard 单页；不拆独立 Dashboard 顶级页；品牌 Hero 增强属 Milestone 6 FUTURE_TARGET，当前实现以 Dashboard 为主。
2. **D-UI-02**：一级导航冻结为 首页 / 开始创作 / 收集品 / 设置（`/` `/create` `/cookbook` `/settings`）；「使用与安装说明」非一级导航；Bring It In-Game 保持导出后流程；Pack the Menu 由收集品驱动。
3. **D-UI-03**：Ask Gus 结果页仅三操作——接受并存档、完整重新生成、拒绝；无「进入料理蓝图」、无 Ask Gus→Blueprint 产品路径、无用户可达 `CONVERTED_TO_ADVANCED`；Blueprint 仅从独立创作入口进入。

## 修改文件与版本

| 文件 | 版本变化 | 说明 |
|---|---|---|
| `design docs/PelicanTownSpecials_一期顶层设计_v2.2.docx` | v2.1 → **v2.2** | 三操作、并列入口、章节标题、CONVERTED 历史标注、修订摘要 |
| `design docs/StarValleyCook_第二期产品体验与品牌化设计_v1.1.docx` | v1.0 → **v1.1** | 首页品牌+Dashboard、导航四项、三操作、废止进阶转换文案 |
| `docs/architecture/MVP_TECHNICAL_DESIGN.md` | v1.4 → **v1.5** | 设计源、冻结表、convert 历史标注、§11.3、验收项、changelog |
| `docs/plans/MVP_IMPLEMENTATION_PLAN.md` | v0.6 → **v0.7** | Global Constraints、Task 15 三操作、验收项、Milestone 表、历史 convert 注记 |
| `docs/development/CONSTRAINTS.md` | 同步 | 权威版本表 + 产品冻结项（三操作/入口/导航/首页） |
| `StarValleyCook_项目设计源索引与状态快照.md` | → **v2.2** | 版本矩阵、§2.1/§3.3/§5、阶段矩阵、同步日志 |
| `最初设计功能清点/StarValleyCook_项目顶层规划_v2.0.md` | 锚点注记 | 文首「现行结论（2026-08-08）」 |
| `最初设计功能清点/第二期-产品体验升级与品牌化-规划锚点_v2.0.md` | 锚点注记 | 同上 |
| `最初设计功能清点/第三期-在线生产化与全局生成记忆-规划锚点_v2.1.md` | 锚点注记 | 同上 |
| `docs/development/STATUS.md` | 本 Session | active session 指向本文档同步 |
| 本 Session 文件 | 新建 | 追加式记录 |

辅助脚本（未跟踪、非产品）：`.pytest_tmp/update_p1d_docx.py`、`fix_p1d_residuals.py`、`update_p2d_docx.py`、`fix_p2d_residuals.py`、`apply_md_sync_2026_08_08.py`、`fix_index_2026_08_08.py` 等。

## HISTORICAL_KEEP（不改写）

- F19-3 / F19-4：Task 19* 已移除 Ask Gus「进入料理蓝图」UI（`ecfcf85`）——保留为 IMPLEMENTATION_FACT。
- 导航首页入口 Session `2026-08-08-nav-home-entry` 与 commit `26c3044`——保留历史，不改写。
- Task 9 convert 测试与 convert API/application 代码——保留为历史/兼容面；文档标注「非用户可达 / 不在 UI 暴露」，**本 Session 不删除代码**。
- 历史 Session 中四操作/转换叙述——HISTORICAL_KEEP，仅在现行正式源与 CONSTRAINTS 写现行结论。

## 代码残留（仅报告，本 Session 不改）

- 后端仍可能存在 convert / `CONVERTED_TO_ADVANCED` 应用层、OpenAPI 与测试；前端 Ask Gus 测试断言「进入料理蓝图」按钮 count 0。
- 文档已声明：历史端点若存在不得在 UI 暴露；删除 API 需另开授权 Task，不在本 Brief 范围。

## 明确非目标（已遵守）

- 不删除 conversion 业务代码；
- 不把 Milestone 6 首页 Hero 标为已完成；
- 不改写历史 Session 正文；
- 不恢复旧导航或转换按钮；
- 不扩展第三期范围。

## 验证

- 正式 MD 源头版本已核：TD0 v1.5、IP0 v0.7、CONSTRAINTS 权威表一致。
- 索引版本矩阵与 §5 模式契约已对齐三操作/并列入口。
- 工作树：控制面 `CONSTRAINTS.md` / `STATUS.md` / 本 Session 可提交；设计 DOCX/TD0/IP0/索引按约定 gitignored。

## 用户验收与提交

- 2026-08-08：用户确认 Brief §10 报告，并授权控制面 focused commit + push。
- 提交范围仅：`docs/development/CONSTRAINTS.md`、`docs/development/STATUS.md`、本 Session；设计源 ignored，不进 Git。
- 代码 convert 面清理若需要，另开产品/清理 Task 并获授权。
- Milestone 6 仍待用户授权，不因本文档同步自动启动。
