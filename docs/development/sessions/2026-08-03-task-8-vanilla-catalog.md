# Session 2026-08-03｜Task 8 Stardew 原版目录、恢复值与 Gameplay 校验

## Session 元数据

| 字段 | 值 |
|---|---|
| session_id | 2026-08-03-task-8-vanilla-catalog |
| task | MVP Task 8：建立 Stardew 1.6.15 原版目录、恢复值与 Gameplay 校验 |
| state | committed |
| type | implementation |
| authorization | 用户已明确要求 Task7 验收通过并开始下一个 Task；Task8 实施计划已确认并收到双语源文件 |
| owner | 主 Agent + 串行 implementer/reviewer Subagent |
| commit_policy | 用户已验收；Task8 focused commit 已创建并推送 |

## 目标

建立真实、版本化、可重复构建的 Stardew Valley 1.6.15 原版物品目录；让语义食材只能映射到目录内的有效 item ID；为数量、恢复值、Buff、售价和目录成员关系提供 Gameplay 校验。

## 范围

本 Session 计划包含：

- 真实 Data/Objects 导出登记、SHA-256 provenance 和确定性目录构建；
- VanillaCatalog 加载、require、固定搜索顺序和候选排序；
- 候选 ID 的安全映射，目录展示名和 catalogVersion 由程序事实源提供；
- RecoverySpec 派生值的复用、Gameplay 硬错误和版本化软警告；
- catalog 单元测试、重复构建检查、Ruff、mypy、后端回归和文档同步。

本 Session 不包含真实模型调用、Provider Gateway、业务 API、前端页面、数据库、Mod 编译或游戏内验证。

## 前置条件与待确认项

- 用户已提供真实的 Stardew 1.6.15 英文与中文导出：resources/catalogs/stardew-1.6.15/Objects.json 与 Objects.zh-CN.json；两者将按对象 Name/本地化 Key 合并。
- 中文导出已提供，英文名称来自 Objects.json 的 Name，中文名称来自 Objects.zh-CN.json 的 Name_Name key；不使用英文伪造中文。
- 正式设计给出了硬范围，但未给出软警告的数值阈值；计划建议使用显式版本化规则，并在未另行确认时以真实原版范围作为 warning-only 参考。

## 计划与控制面

- 实施计划：docs/superpowers/plans/2026-08-03-task-8-vanilla-catalog.md
- 设计依据：docs/architecture/MVP_TECHNICAL_DESIGN.md §6、§9.8–§9.11、§14.7、§17；docs/plans/MVP_IMPLEMENTATION_PLAN.md Task8
- 当前阶段为 committed；Task8 Task1–4 产品代码、测试、最终验证和独立总审阅已完成，focused commit 已创建并推送。
- 按 TDD 实施，Task1–4 已完成。edibility/sellPrice 使用真实目录观察范围；Buff duration 使用独立版本化 gameplay reference；均为 warning-only。

## 预期验收边界

- 目录可从真实源文件确定性重建，源哈希与 provenance 一致；
- item ID 256 可解析为 Tomato，-5 保留为 category；
- 目录外候选 ID 不能成为 GameIngredient；
- 模型返回的展示名不能覆盖目录事实；
- RecoverySpec 只由 edibility 派生能量和生命；
- 硬错误阻止验证，软警告只产生 WARNING；
- 生成文件不包含用户数据、Key、绝对路径或非 provenance 时间戳。
## 最终验证记录

- 真实 CLI 重建：`python scripts/build_vanilla_catalog.py --source resources/catalogs/stardew-1.6.15/Objects.json --output output/catalog-check.json`；与生产 vanilla-ingredients.json 比较结果为 identical。
- 目录事实：catalogVersion `stardew-1.6.15-v1`，808 条记录，85 个 named IDs，`256=Tomato`，`-5` 为 category。
- 聚焦目录测试：51 passed；全后端回归：254 passed、2 skipped。两个 skipped 仅因 Windows 无 symlink 权限，分别位于静态前端路径边界测试。
- 静态检查：Ruff、mypy（38 个源文件）、git diff --check 和本地文档忽略检查通过。
- 源哈希：Objects.json `6CBC66CAECFED0AAC884958E21834D572014DBF4E41E64A0AF1B190E8390FF90`；Objects.zh-CN.json `E51B2EF545E519E268A793BDB9EC0905B9ED6A3F7E1BFD7EEA84D5EE79051F07`。

## 当前用户验收门

- 状态为 `committed`；用户验收通过后已创建 Task8 focused commit 并推送。
