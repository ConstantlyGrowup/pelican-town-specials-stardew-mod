# Session｜M14 Task 65 本地原料 RAG 实现

| 字段 | 值 |
|---|---|
| session_id | `2026-09-23-task-65-ingredient-rag-implementation` |
| status | `committed` |
| session_type | `implementation` |
| owner | Codex 主 Agent |
| started_at | `2026-09-23` |
| base_commit | `7175d9c` |
| acceptance_contract_id | `m14-task65-local-ingredient-rag-v1` |
| revise_round | `1`（首轮 detector `REVISE` 后；原冻结 Packet 仍为 round 0） |
| planning_status | `READY_FOR_IMPLEMENTATION` |

## Objective 与边界

实现 Task63 选定的本地逐原料检索：静态原版目录条目向量、E5 小模型通用 CPU INT8、词面与语义融合 Top5、mapper 前去除本菜已用 ID、兼容校验及安全退回旧检索。Task65 只完成接线、离线及打包/资源/回归验证；同集 JEV 主质量结论留给 Task66。用户 2026-09-23 明确不引入整道菜联合选择；同日明确将后续主指标改为固定集“菜品全部合理率”。不修改 Task64 历史输出或先验宣称 RAG 优于旧链路。

## planning_rulings

- `R65-01`：M14 v1.3 计划和 Task63 设计曾把逐项非兜底合理率列为主指标；用户已明确改为“菜品全部合理”。同步 ignored 计划/设计的 Task66 gate，保留 Task64 历史报告；Task65 不进行付费 JEV 同集质量判定；`user_visible_delta: none`。
- `R65-02`：逐项检索已满足多原料场景；保持 `GeneratedDishCore.ingredients` 每项独立 Top5，按顺序逐项映射，不引入联合选择、整菜向量或新的 Provider 调用；`user_visible_delta: none`。
- `R65-03`：Task66 尚未证明质量 gate，Task65 的生产默认必须保持旧 backend。允许仅内部 selector 在测试/评测中启用 RAG；打包可携带候选模型和索引用于离线验证，但不可未经 Task66 改变普通用户默认映射；`user_visible_delta: none`。
- `R65-04`：模型与索引需要复现和 Windows 发布包验证；可在最小依赖闭包内修改构建脚本、PyInstaller spec、依赖/许可清单及新增检索模块、索引构建脚本和测试。模型、索引、性能原始输出可放 ignored 路径，源码必须记录固定 revision/hash/生成方法及可审计资源结果；`user_visible_delta: none`。
- `R65-05`：所有索引/模型/编码/目录异常只降级检索器到原有 `_build_candidates`，仍经原 mapper 校验。不得把失败混同于原料目录 fallback，也不得暴露 Query 文本、Embedding、Key 或远端事件；`user_visible_delta: none`。

## Context Packet

```yaml
task_id: M14-Task-65
base_commit: 7175d9c
planning_status: READY_FOR_IMPLEMENTATION
acceptance_contract_id: m14-task65-local-ingredient-rag-v1
revise_round: 0
objective: 实现并验证本地逐原料 RAG 候选检索、受控降级和 Windows 离线打包；质量对照在 Task66。
user_visible_contract: 普通用户默认仍走旧原料映射；API/UI/schema/试用/Canonical/Blueprint/Mod 导出及用户工作区不变。
planning_rulings: [R65-01, R65-02, R65-03, R65-04, R65-05]
contract_delta:
  documents: [Task65 Session/STATUS/实施与资源摘要, M14 ignored 计划/设计主指标口径]
  domain: []
  persistence: []
  application_api: [仅内部原料候选检索 selector 与 Ask Gus 接缝]
architecture_budget:
  allowed: [固定 E5 revision 与通用 CPU INT8 离线产物, 253 条只读 flat 索引和 manifest, 进程内惰性 ONNX 推理, 词面加语义 Top5, 完整旧链路降级, PyInstaller onedir 打包与许可, 定向和必要产品回归]
  forbidden: [独立向量数据库/ANN/服务, 整道菜联合优化, Runtime 下载或远端 Embedding, 新用户设置/API/schema, 修改冻结 Query/Gold/JEV 历史输出, 额外 Provider 调用, 用户数据迁移/删除, 自动启用未验证的 RAG, push/tag/Release]
allowed_files:
  - path: backend/src/pelican_town_specials/ingredient_rag/**
    action: create
    reason: 静态向量、校验、编码、检索与原因码实现
    criterion_ids: [C65-01, C65-02, C65-03, C65-04]
  - path: backend/src/pelican_town_specials/generation/orchestrator.py
    action: modify
    reason: 唯一 Ask Gus 候选接缝及内部 selector
    criterion_ids: [C65-02, C65-03, C65-05]
  - path: scripts/build_ingredient_rag.py
    action: create
    reason: 固定来源模型的可复现离线量化与索引构建
    criterion_ids: [C65-01, C65-04]
  - path: backend/pyproject.toml
    action: modify
    reason: 最小生产 CPU/tokenizer 依赖固定
    criterion_ids: [C65-01, C65-04]
  - path: packaging/pyinstaller/PelicanTownSpecials.spec
    action: modify
    reason: 包入唯一模型/tokenizer、索引与必要 runtime
    criterion_ids: [C65-04, C65-06]
  - path: packaging/release/THIRD_PARTY_NOTICES.txt
    action: modify
    reason: 新模型和运行依赖许可证说明
    criterion_ids: [C65-04]
  - path: backend/tests/ingredient_rag/**
    action: create
    reason: 构建/兼容/检索/降级/并发单元和回归测试
    criterion_ids: [C65-01, C65-02, C65-03, C65-05, C65-06]
  - path: backend/tests/generation/**
    action: modify
    reason: Ask Gus 逐项映射及三槽相邻回归
    criterion_ids: [C65-02, C65-05, C65-06]
  - path: docs/development/M14_TASK65_INGREDIENT_RAG_IMPLEMENTATION.md
    action: create
    reason: 模型 provenance、构建方法、实测资源与限制
    criterion_ids: [C65-01, C65-04, C65-06]
  - path: docs/development/sessions/2026-09-23-task-65-ingredient-rag-implementation.md
    action: modify
    reason: 主 Agent 记录合同、交接和审阅；worker 不拥有
    criterion_ids: [C65-07]
  - path: docs/development/STATUS.md
    action: modify
    reason: 主 Agent 保持唯一活动状态；worker 不拥有
    criterion_ids: [C65-07]
acceptance_ledger:
  - criterion_id: C65-01
    source: M14 Task63 设计 §3–5
    requirement: 固定官方 E5 40 位 revision/hash；从经验证目录构建每物品一向量的 253×384 有序 float32 flat 索引及严密 manifest；本地通用 CPU 动态 INT8 产物和可复现生成记录。
  - criterion_id: C65-02
    source: M14 Task63 设计 §2–3；用户逐项策略确认
    requirement: 语义原料逐项规范化，精确/别名优先并融合词面与本地向量 Top5，确定性 ID/分数排序，mapper 前排除已用 ID，保持鱼类守卫及 1–8 项约束；不做整菜联合选择。
  - criterion_id: C65-03
    source: M14 Task63 设计 §5–6
    requirement: catalog/model/tokenizer/index/manifest/shape/hash 错误或编码失败时安全降级原检索+原 mapper，仅内部非敏感原因码，无运行时网络、用户数据迁移或隐性费用；默认旧 backend。
  - criterion_id: C65-04
    source: M14 Task63 设计 §4–5、§7
    requirement: 生产依赖与 PyInstaller onedir 仅包含必要单一通用 CPU 模型/tokenizer/索引，记录许可证、锁定来源、hash、文件大小、模型/索引加载与 CPU/RAM/包体测量；不打包 PyTorch evaluation 栈。
  - criterion_id: C65-05
    source: M14 计划 Task65；MVP 现有合同
    requirement: Ask Gus 之外 Canonical HIT、Blueprint、试用、三槽和 Mod 导出不回归；RAG 故障不会绕开目录 ID/可用性校验或影响旧默认流程。
  - criterion_id: C65-06
    source: M14 Task63 设计 §7；M14 计划 Task65
    requirement: 定向/静态/相关回归和 Windows 离线 bundle smoke 实证；如冷加载≤5s、RAM≤256MiB、暖 p95≤100ms、新增发行文件≤180MiB 不能实测或未过，报告实情并保持旧默认，不伪称 gate PASS。
  - criterion_id: C65-07
    source: AGENTS.md 与 REVIEW_PROTOCOL.md
    requirement: 新 luna_worker 实施、独立 detector 审阅、主 Agent 核对及状态/本地 focused commit；push 另需授权。
out_of_scope: [Task66 JEV 同集复评与是否启用 RAG 的质量结论, 真实 Provider/照片测试, PostHog, main/tag/Release]
test_commands: [python -m pytest backend/tests/ingredient_rag backend/tests/generation/test_ask_gus.py backend/tests/generation/test_m8_concurrency.py -q -p no:cacheprovider --basetemp output/m14-task65/pytest-focused, python -m ruff check backend/src/pelican_town_specials/ingredient_rag backend/src/pelican_town_specials/generation/orchestrator.py backend/tests/ingredient_rag scripts/build_ingredient_rag.py, git diff --check, powershell -NoProfile -File scripts/build_windows.ps1, powershell -NoProfile -File scripts/smoke_windows_bundle.ps1]
```

## Worker ownership

`luna_worker` 拥有上述实现/测试/打包文件及 Task65 结果摘要，不拥有本 Session、STATUS 或 ignored 计划/设计。worker 不是代码库唯一使用者，不得覆盖或撤销他人改动；新增相邻闭包文件须按 `implementation_scope_delta` 记录。不得 commit、push、发布、编辑 Task64 冻结数据或发起 JEV 费用。

## 验收记录

### Worker 首轮交接（未验收）

- `luna_worker`（配置 `gpt-6-luna/max`）完成逐项 RAG、官方固定 E5 revision 的 MatMul+Gather 动态量化、同 revision SentencePiece、253×384 静态索引、旧 backend 默认与故障回退；未做 JEV、提交或推送。构建报告为 `docs/development/M14_TASK65_INGREDIENT_RAG_IMPLEMENTATION.md`。
- 首轮实施证据：focused `58 passed`、全量 backend `999 passed/2 skipped`、frontend `231 passed`、Ruff/mypy 通过；隔离 Windows onedir 与离线 smoke 通过。20 次 fresh-process 首检索中位数/最大值 `1178.337/1466.078 ms`，额外 RSS `188.348/188.602 MiB`，暖态 p95 `8.449 ms`；新增资源与 CPU runtime 文件树 `159,489,831 B`。这些是 worker 实测，不等于最终 Task 验收或 Task66 质量结论。
- Worker 的最小依赖闭包扩展：同固定 revision 的 SentencePiece 替代高 RSS 的官方 fast tokenizer（253 passage + 50 distinct 冻结 Query + 5 规范化边界样本 308/308 token IDs 一致；保留控制 token 字面量禁用 RAG 并走旧链路）；`scripts/build_windows.ps1` 和 `scripts/smoke_windows_bundle.ps1` 增加隔离路径、产物构建和 bundle 校验；无用户可见变化。

### 独立 Review round 0：REVISE

只读 `detector`（配置 `gpt-6-sol/medium`）核对 C65-01..07 与 R65-01..05，给出 `REVISE`，`revise_round=0`，两项 `MUST_FIX`，无新设计请求：

1. `C65-04/C65-06`：`.github/workflows/build.yml` 的干净 Release runner 只安装 `--group dev -e .`，而 `build_windows.ps1` 无条件运行依赖 `huggingface_hub`、`onnx`、`tokenizers` 的新构建脚本；本机共享环境的 build PASS 不能证明干净 runner 能打包。最小修复为在 reusable build 路径安装固定构建期依赖或改用已验证离线产物，仍不得打包评测栈。
2. `C65-03/C65-05`：默认 LEGACY 路径误对已用 ID 做预过滤，重复 `Egg` 的第二次映射可能从原 ID `176` 变成 `180`。最小修复为只在 RAG 路径排除已用 ID，旧默认及 RAG 降级路径保持原候选和 mapper 行为。

Worker 已按同一冻结合同进入 revise round 1 集中最小修复；审阅轮次不重置，修复后仅复查上述两项和直接回归。尚未 auto_accept、commit、push 或发布。

### Worker revise round 1 交接（待封闭复审）

- `C65-04/C65-06`：新增固定 `build` 依赖组（huggingface-hub、onnx、tokenizers），reusable `.github/workflows/build.yml` 在干净 Release runner 安装 `dev` 与 `build`；新 `test_build_contract.py` 锁定依赖版本、安装命令、runtime 不含构建依赖及 PyInstaller 排除。
- `C65-03/C65-05`：旧默认 `LEGACY` 保留原候选序列和重复 `Egg` 映射 ID `176`；仅成功且有候选的 RAG 分支排除本菜已用 ID；RAG 异常或去重后无候选均回到未过滤的旧词面 Top 5。
- TDD 红测复现两处问题及失败回退误过滤，修复后 scoped `62 passed`、7 条 targeted `passed`、Ruff/mypy（105 源文件）与 `git diff --check` 通过。pytest 临时目录遇 WinError 5，按此前项目先例仅对该受限命令使用最小提升后通过；未变更目录权限或清理其他工作区。
- 本次未重跑干净 GitHub Release runner 或修复后的 frozen exe build。此前隔离 onedir、全量门禁、资源测量均为修复前证据；不把配置审查当真实远端 CI success。新增 `.github/workflows/build.yml` 及定向契约测试属于 C65-04/C65-06 的最小依赖闭包，`user_visible_delta: none`。封闭独立复审正在进行，尚未验收或提交。

### 独立封闭 Review round 1：PASS 与主 Agent 收口

- 新只读 `detector`（配置 `gpt-6-sol/medium`）仅对 round 0 两项 MUST_FIX 和直接回归复审，合同 `m14-task65-local-ingredient-rag-v1`、`revise_round=1`，结论 `PASS`、`must_fix=[]`、`optional_hardening=[]`、`new_design=[]`；接受 `.github/workflows/build.yml` 与 build/smoke 脚本的无用户可见范围扩展。
- detector 查到 reusable build workflow 安装 pinned `build` 组，PyInstaller 排除 build-only 包；`orchestrator.py` 仅对成功 RAG 候选过滤已用 ID，LEGACY/失败回退保持未过滤的旧词面结果。其 targeted pytest `8 passed/28 deselected`、Ruff 与 diff check PASS；普通权限 broader pytest 因 Windows `WinError 5` 出现 34 项 fixture setup error，明确不是断言失败。主 Agent 采用 worker 已在最小权限提升下完成的 `62 passed` 作为完整 scoped 证据，不冒充 detector 独立完整重跑。
- 主 Agent 核对交接、Scope Delta、冻结设计与文件边界，接受 Task65 技术实现与资源/打包实证；普通用户默认仍走旧映射。新包离线 smoke 与资源测量是修复前记录，修复后的 clean GitHub runner 和 frozen exe 未重跑；Task66 需另行按固定 Query/JEV 菜品全合理率决定能否启用 RAG，现不启动、不宣称质量改善。
- Task65 按项目自治路径进入 `auto_accepted`，仅做本地 focused commit；不推送、不修改 main/tag/Release。运行时角色路由配置：implementer `gpt-6-luna/max`、review `gpt-6-sol/medium`，工具未向子代理暴露可核的运行时自报；主 Agent 自报亦未提供。

### 本地提交收尾

Task65 的 26 个精确文件已在 `feat/mvp-implementation` 创建本地 focused commit `635f4af`（`feat: add local ingredient RAG candidate backend`）。提交前 staged diff check 通过，提交后 tracked 工作树干净。未 push、未改 main/tag/Release。此段由后续纯控制面维护 Session 同步，不改变 Task65 实施合同或 Review 结论。
