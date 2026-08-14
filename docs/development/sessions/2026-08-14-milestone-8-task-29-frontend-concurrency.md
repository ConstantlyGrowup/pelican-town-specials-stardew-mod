# Session｜Milestone 8 Task 29 前端提示与完整并发验收

| 字段 | 值 |
|---|---|
| session_id | `2026-08-14-milestone-8-task-29-frontend-concurrency` |
| session_type | `milestone-8-task-29-implementation` |
| status | `active` |
| owner | Claude Code 主会话（包工）+ 实施子代理 + Codex 审阅 |
| started_at | `2026-08-14` |
| base_commit | `d0a3701 docs: record M8 Task 28 auto_accepted` |
| acceptance_contract_id | `mvp-m8-task-29-frontend-concurrency-v1` |

## 范围与边界

本 Session 只处理 Task 29（M8 最后一个 Task）：前端 PTS_GEN_BUSY 双语上限提示（zh-CN/en-US，复用既有 GenerationError 横幅与重试按钮）、三草稿并行互不串线验证（hook 级 + E2E 多 page）、以及 frontend/backend/OpenAPI/E2E 全量回归与 Windows bundle/installer smoke。无后端/API/OpenAPI/领域改动；版本号不提升（验收即发布在用户 Milestone 验收后单独执行）。

## 验收项（来自 Context Packet `mvp-m8-task-29-frontend-concurrency-v1`）

- T29-001 zh-CN/en-US 下 PTS_GEN_BUSY 均显示明确上限提示（最多 3 个 + 等待后重试引导），草稿保持原状；非 busy 错误仍显示后端 message。
- T29-002 第 4 份草稿被拒绝后保留原状态；名额释放后「重试生成」可立即成功。
- T29-003 三份草稿同时生成互不串线（各自阶段/刷新恢复/取消独立）。
- T29-004 frontend Vitest/lint/build、E2E、backend 全量回归、OpenAPI drift 全部通过。
- T29-005 Windows bundle + installer 构建与 smoke 全流程通过，不调用真实 Provider。

## 规划裁决

- R-01 前端按 `error.code === "PTS_GEN_BUSY"` 分支显示本地化静态文案（copy key `generationBusyLimit`），不解析 details。
- R-02 复用 GenerationError 横幅与重试按钮，不新增组件/排位视觉。
- R-03 E2E 用 page.route 拦截（无后端/真实 Provider），三页并发用同一 test 内多 page。
- R-04 不重新生成 OpenAPI 契约（无 API 变更），drift 检查为回归门。
- R-05 版本号不提升；bundle/installer smoke 在本 Task 完成，Release 发布留待用户验收授权。

## 验证记录

- 实施子代理 TDD：RED 先行确认（GenerationError.test 2/4 失败——旧组件对 PTS_GEN_BUSY 逐字渲染后端 message；E2E busy 用例实现前 toBeVisible 超时）。
- GREEN（round 0）：frontend Vitest **20 files / 122 passed**（含 GenerationError 4 条 + useGeneration +2 条）；E2E **28 passed**（含 busy 提示与重试、三 page 并发 2 个新用例，既有 26 条零改动）；backend 全量（backend/tests + tests/repo + tests/integration）**724 passed / 2 skipped**（本 Task 无 backend 改动，回归为门禁；与 Task 28 记录的 674 差异系命令范围：后者只跑 backend/tests）；lint、build（tsc + vite）、ruff clean；check_openapi_drift.ps1 OK（schema.d.ts 无 diff）。
- 构建（round 0）：build_windows.ps1 全门禁通过（frontend build → backend 回归 → PyInstaller onedir → EXE icon gate hash 3FE51DEB… → 版本身份 1.1.0 未提升 → release content gate）；smoke_windows_bundle.ps1 Phase A+B OK；build_installer.ps1 OK（dist\installer\PelicanTownSpecials-Setup-v1.1.0.exe，SHA-256 4D8059DF…，setup icon gate OK）。
- round 1 修复（Codex 2 项 MUST_FIX 同一根因）：E2E route 处理 409 busy 分支前置，拒绝路径不调用 onGenerate；busy 用例新增草稿状态断言（409 后同一对象引用 + status 仍 DRAFT；重试成功仅经 200 路径 → REVIEWABLE；en-US 同断言）。重跑：busy 定向 E2E 1 passed、全量 Vitest 122 passed、全量 E2E 28 passed、lint/build/diff-check clean。
- 包工复跑：全量 Vitest + backend 全量（结果见后）+ E2E 全量；`git diff --check` clean。
- **唯一未过门禁（环境前置，需用户决策）**：smoke_installer.ps1 步骤 0 按设计拒绝——本机存在用户 2026-08-11 fresh-install 复验遗留的 v1.1.0 正式版安装（开始菜单快捷方式 → D:\ProgramTesting\PelicanTownSpecials\PelicanTownSpecials.exe；卸载注册表 DisplayVersion 1.1.0）。脚本保护既有用户数据；未卸载、未删快捷方式、未绕过。用户卸载该复验安装后重跑即可。

## 审阅记录

- Codex（gpt-5.6-luna/max，新 thread，只读）：round 0 **REVISE**（2 项 MUST_FIX，同一根因：E2E route 在 409 busy 分支判断前调用 onGenerate，busy 用例 mock 草稿在拒绝前已被推进，原状断言只验证前端缓存）→ round 1 修复（busy 分支前置 + 草稿对象引用断言）→ round 1 **PASS**（5/5 criterion，无 MUST_FIX，scope_delta none，R-01..R-05 全过）。
- OPTIONAL_HARDENING（非阻塞）：① Codex 只读沙箱无法复跑 Vitest/Playwright/Vite（EPERM）——包工已复跑确认；② smoke_installer 拒绝为环境保护非代码缺陷（验收说明项，交用户决策）；③ STATUS.md / MVP_IMPLEMENTATION_PLAN.md / 设计索引 M8 过期文本——由包工在 Task 29 完成后同步控制面。
- 结论：auto_accepted → 本地 focused commit（不 push）。Milestone 8 全部 Task（27/28/29）完成，进入全量验证与用户验收。
