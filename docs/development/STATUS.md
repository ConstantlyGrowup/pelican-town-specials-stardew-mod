# Pelican Town Specials｜开发状态

> 本文件是开发状态唯一真源。设计内容回查正式技术设计，文档索引回查项目设计源索引；本文件只回答“当前哪个 Session、做到哪里、下一步是什么”。

## 当前状态

| 字段 | 值 |
|---|---|
| overall_state | milestone_7_accepted_and_released |
| project_phase | Milestone 7（Refine）完成并发布；Task 22–26 全部通过验收；v1.1.0（双语 UI + 双语生成前后端）已发布到 GitHub Release；Task 24 经真实发布流程验证 |
| product_implementation_started | true |
| active_session_id | `2026-08-10-milestone-7-acceptance-and-release` |
| active_session_state | accepted + released（M7 五 Task 用户验收通过；v1.1.0 已由 GitHub Actions release.yml 实际发布并核验产物） |
| active_session_type | milestone-7-full-acceptance-and-release |
| current_task | M7 验收与 v1.1.0 Release 收尾：状态记录同步；等待用户对 v1.1.0 发布版 fresh-install 复验 |
| blocker | 无 |
| next_action | 用户复验 GitHub Release v1.1.0 安装版（含双语功能）；如需修正则按验收即发布流程重发；无新工作则 M7 关闭 |
| collaboration_model | 主会话（Claude Code）直接实施 + 自动验证；Codex MCP 独立审阅（gpt-5.6-luna/max，新 thread）；PASS → auto_accepted → 本地 focused commit；里程碑粒度不打断 |

## 当前 Git 状态事实

| 项目 | 当前值 |
|---|---|
| 仓库 | 已在当前目录初始化 |
| 当前分支 | feat/mvp-implementation |
| origin | https://github.com/ConstantlyGrowup/pelican-town-specials-stardew-mod.git |
| 初始提交 | 517f844 chore: add serial agent handoff control plane |
| 最新提交 | `b39b50d fix: CI ignore gate on fresh checkout and bump release version to 1.1.0` |
| 远端操作 | Milestone 7 已推送至 `b39b50d`（`feat/mvp-implementation`）；tag `v1.1.0` 已推送并触发 `release.yml` 成功；GitHub Release **v1.1.0** 已发布（setup.exe + 便携 ZIP + SHA256SUMS + 中文 release notes，run 31394532120 success）。旧 v1.0.0 tag 留在远端但无 Release 产物（首次发布因 ignore gate 失败后弃用）。 |
| 当前工作树范围 | M7 全部提交完成，tracked 工作树干净（仅保留用户已有的 prototype、official-assets、samples、`.pytest_tmp/`、`.review_tmp_task20_workspace/` 等未跟踪文件）。 |

## 当前 Milestone 7 Task 23 实施 Session（auto_accepted）

- `2026-08-10-milestone-7-task-23-installer`：本 Session 只处理 Task 23（Windows per-user installer）。Context Packet：`mvp-task-23-installer-v1`（`docs/plans/2026-08-10-task-23-installer-packet.md`，gitignored），base_commit `4333267`。
- 实现（commit `5f54516`，10 文件 +753/-29）：`packaging/installer/PelicanTownSpecials.iss`（per-user、无管理员、`x64os`、Gus icon、start-menu 必建/desktop 可选、无 `[UninstallDelete]`）；`scripts/release_content_gate.ps1`（共享 `Test-ReleaseContent` + `*.map` + Root 绝对化）；`scripts/install_innosetup.ps1`（6.7.3 固定 + SHA-256 校验 + `/CURRENTUSER`）/`find_iscc.ps1`/`build_installer.ps1`（内容 gate + Gus icon 像素 hash + 版本身份 gate）/`smoke_installer.ps1`；`build_windows.ps1` 改接共享 gate；`tests/repo/test_installer.py`；`ci.yml`（安装 Inno Setup、构建/冒烟/上传 installer artifact）；`packaging/release/README.txt` 安装/卸载说明。
- 审阅：Codex（gpt-5.6-luna/max，新 thread）round 0 REVISE（2 项 MUST_FIX：INSTALL-002 快捷方式未真正演练、INSTALL-003 固定 marker 可能覆盖用户文件）→ 修复 → round 1 **PASS**（5/5 criterion，无 MUST_FIX）。OPTIONAL_HARDENING 2 项非阻塞（setup log 固定路径、README 隐私措辞）。
- 规划裁决 `R-06`（workspace 路径准确性）：实测 platformdirs 4.10.0 将 `user_data_dir("PelicanTownSpecials")` 展开为双重路径 `%LOCALAPPDATA%\PelicanTownSpecials\PelicanTownSpecials\workspace`（appauthor 默认取 appname），即 app 冻结的真实默认 workspace；Task 23 不改 app 路径（R-01）。smoke 经 `_default_workspace_path()` 探测真实路径放置 marker；README 改引用 app 数据目录 `%LOCALAPPDATA%\PelicanTownSpecials`。双重路径记录为候选后续项，M7 验收时向用户呈现。
- 验证：`tests/repo` 22 passed；全量 backend+repo+integration **680 passed/2 skipped**；ruff/mypy clean；`smoke_installer.ps1` 全流程通过并返回干净机器状态（无残留 marker、install 目录/快捷方式消失、真实用户 workspace 保留）；Inno Setup 6.7.3 构建的 setup exe Gus icon hash 匹配、ProductName 校验通过。
- 范围：Task 24（GitHub Release）、Task 25/26（双语）未实施；未改 backend/API/Mod 协议、未改变 app 运行时或 workspace 逻辑。

## 当前 Milestone 7 Task 24 实施 Session（auto_accepted）

- `2026-08-10-milestone-7-task-24-release`：本 Session 只处理 Task 24（GitHub Release 自动发布）。Context Packet：`mvp-task-24-release-v1`（`docs/plans/2026-08-10-task-24-release-packet.md`，gitignored），base_commit `2d1f926`。
- 实现（commit `529981a`，7 文件 +479/-98）：`build.yml`（可复用 verify-and-build，`workflow_call` + 漂移门 + 便携 ZIP + release notes + 4 artifact 上传）/`ci.yml`（薄调用方，永不发布）/`release.yml`（v* tag + manual；resolve-version；create-release job-scoped `contents: write`，`sha256sum` + `gh release create`，`GH_REPO` 显式，create-if-absent/update-if-present 可复现）；`scripts/check_release_version.ps1`（漂移门）；`scripts/generate_release_notes.ps1`（版本化中文 notes）；`tests/repo/test_release.py`（6 条门禁）；`test_installer.py`（断言迁移到 build.yml）。
- 审阅：Codex（gpt-5.6-luna/max，新 thread）round 0 **REVISE**（2 项 MUST_FIX：RELEASE-001 create-release 无仓库上下文 → 设 `GH_REPO`；RELEASE-002 重复运行已创建 tag 不可复现 → create-if-absent/update-if-present + 新增 `test_release_repeatable_and_repo_scoped`）→ round 1 **PASS**（4/4 criterion，无 MUST_FIX，scope_delta none）。OPTIONAL_HARDENING：本机无 gh CLI，未做真实 GitHub 命令。
- 验证：`tests/repo` **28 passed**；全量 backend+repo+integration **686 passed/2 skipped**；ruff/mypy clean；workflow YAML 有效；漂移门 1.0.0/v1.0.0 过、2.0.0 明确报错；notes 生成器正常；本地 dry-run 发布产物 `sha256sum -c` 对 installer（565cd414…）与 ZIP（0488798e…）均 OK，产物名全链路一致。
- 范围：未创建真实 GitHub Release；未改 app/backend/frontend/installer 逻辑；Task 25/26（双语）未实施。

## 当前 Milestone 7 Task 25 实施 Session（auto_accepted）

- `2026-08-10-milestone-7-task-25-bilingual-ui`：Task 24 已 auto_accepted（`529981a`）；本 Session 只处理 Task 25（双语 UI 与 Settings locale）。Context Packet：`mvp-m7-task-25-i18n-v1`（`docs/plans/2026-08-10-task-25-bilingual-ui-packet.md`，gitignored），base_commit `529981a`，4 条 planning_rulings，验收 M7-T25-I18N-001..005。
- 实现（37 文件修改 + 4 新建，约 +1126/-417）：`frontend/src/i18n/copy.ts` 重写为 typed zh-CN/en-US catalog（约 160 键，无 `PRODUCT_COPY` 导出）；新建 `frontend/src/i18n/locale.tsx`（`LocaleProvider`/`useLocale`/`useCopy`/`useSetLocale`，localStorage key `pts-locale`，非法/空值回退 zh-CN，`document.documentElement.lang` 同步）；SettingsPage 语言 radiogroup（aria-checked/aria-label/箭头键导航）；全部页面/组件 useCopy 化；`providerForm` 改 `createProviderFormSchema(copy)`；`generationStore` fallback 文案参数化；CreateDishPage POST `language` = 当前 locale；新建 `scripts/check_frontend_locale.py` + `tests/repo/test_frontend_locale.py` + build.yml 步骤（PRODUCT_COPY 令牌/i18n-copy 直 import/散落 CJK 三规则）。
- 测试：新建 `locale.test.tsx`（6 条）、Settings 语言切换（3 条）、CreateDishPage locale→language（1 条）+ 既有用例补 language 断言；13 个测试文件 `PRODUCT_COPY.zh` → `catalogs["zh-CN"]`。
- 审阅：Codex（gpt-5.6-luna/max，新 thread）round 0 **REVISE**（3 项 MUST_FIX：I18N-003 剩余英文直写未进 catalog、I18N-001 瞬态消息存渲染字符串不随 locale 重本地化、I18N-004 Settings radiogroup 无 roving tabIndex/focus）→ round 1 修复（catalog 新增约 36 键×2 收编全部 eyebrows/counters/stamps/status/severity 渲染；7 个页面瞬态消息 state 改为 catalog key 联合类型并 `{copy[key]}` 渲染；SettingsPage roving focus + 新增 `document.activeElement` 测试）→ round 1 **PASS**（5/5 criterion，无 MUST_FIX，scope_delta none；1 条 OPTIONAL_HARDENING 非阻塞：Settings 字段级校验消息留存期切 locale 不重渲染）。
- 验证：前端 Vitest **19 files / 116 passed**；lint clean；`pnpm build` clean；copy gate OK；grep 扫描确认无残留 raw eyebrow/field-counter/export-stamp/detail-badge、raw `{draft.status}`、raw `{issue.severity}`、`alt="Gus"`、`aria-label="mode"`、`set*Error(copy.*)`；全量 backend+repo+integration **690 passed / 2 skipped**。
- 范围：未实现 Task 26（双语生成与图像 prompt）；`ExportSpec.language` 保持 zh-CN；未改后端/API/Mod 协议/持久化；切换 UI 语言不改写旧草稿/归档数据。

## 当前 Milestone 7 Task 26 实施 Session（auto_accepted）

- `2026-08-10-milestone-7-task-26-bilingual-generation`：Task 25 已 auto_accepted（`a435bc5`+`efd2e5b`）；本 Session 只处理 Task 26（双语生成与图像 prompt）。Context Packet：`mvp-m7-task-26-i18n-gen-v1`（`docs/plans/2026-08-10-task-26-bilingual-generation-packet.md`，gitignored），base_commit `efd2e5b`，4 条 planning_rulings，验收 M7-T26-GEN-001..005。
- 实现（commit `318e3cf`，12 文件 +924/-61）：analysis/ask-gus 英文 prompt 变体与语言选择函数；gateway 按 `request.language` 选 prompt/JSON 指令/修复指令/「Dish analysis：」前缀；tooltip/visual brief/icon prompt 增加 `language` 参数（默认 ZH_CN）与英文标签映射；orchestrator 视觉 prompt 传 `draft.source.language`、`_map_gameplay` 线程 language、provenance prompt_versions 语言后缀版本（`ask-gus-v3-zh`/`-en`、`visual-v3-multi-image-edit-zh`/`-en`、`analysis-v1-zh`/`-en`）；catalog 映射显示名按 language 选 zh/en（`item_id` 权威不变，`display_name_zh` 修正 Task 25「不中英混杂」一致化）。未新增翻译模型调用、未改 API/schema/编译/导出协议。
- 审阅（gpt-5.6-luna/max，新 thread）：round 0 **REVISE** 4 项 MUST_FIX（GEN-002 英文 tooltip 超 1500 契约 → 压缩模板至 1463/1258 + 英文最长回归测试；GEN-003 英文海鲜词不触发 R15 → 英文关键词 + casefold；GEN-005 analysis provenance 缺版本 → `analysis-v1-zh/en`、blueprint provenance visual 版本不可追溯 → `model_copy` 合并，保留字段权威与 cache_eligibility）→ 修复 → round 1 **PASS**（revise_round 1，无 MUST_FIX，scope_delta none，planning_rulings R-01..R-04 全部应用）。
- 验证：focused 测试（generation/providers/catalog）**165 passed**；全量 backend+repo+integration **705 passed/2 skipped**（含 2 个新回归测试）；ruff **All checks passed**；mypy 仅 3 处 HEAD 预存错误（`application/exports.py:194,226`、`api/app.py:356`，stash 基线确认与 Task 26 无关，未越界修复）。RED→GREEN 已确认（实施前 focused 20 failed/71 passed）。
- 范围：未实现导出语言、未翻译旧稿、未加服务端偏好 API、未调真实 provider。Task 22–26 至此全部 auto_accepted；Milestone 7 进入全量验证与用户验收（Task 74）。

## 当前 Milestone 7 Task 22 实施 Session（auto_accepted）

- `2026-08-10-milestone-7-task-22-app-identity`：用户 2026-08-10 确认开始 Milestone 7，协作模式切回「主会话实施 → Codex MCP 独立审阅（gpt-5.6-luna/max，新 thread）」，里程碑粒度不打断。本 Session 只处理 Task 22（Windows 应用身份与 Gus icon）。
- 实现（commit `7286c74`，8 文件 +364/-1）：`scripts/generate_app_icon.py`（确定性 ICO 生成 + `--check`，唯一实现源）；`packaging/assets/pelican-town-specials.ico`（16/24/32/48/64/128/256）+ `provenance.json`；`PelicanTownSpecials.spec` EXE `icon=`；`scripts/check_exe_icon.ps1`（构建后 EXE icon 像素比对 + 版本身份）；`build_windows.ps1` 接入 EXE icon gate；`tests/repo/test_app_icon.py`。
- 审阅：Codex（gpt-5.6-luna/max，新 thread）round 0 **PASS**（无 MUST_FIX，4/4 criterion）；OPTIONAL_HARDENING 就地处理（`--check` 补 `provenance.source_sha256` 校验；Session base_commit 改为 `b5bd03d`）。
- 验证：`tests/repo` 13 passed（8 存量 + 5 新增）；全量 backend **671 passed/2 skipped**；ruff/mypy clean；`build_windows.ps1` exit 0（EXE icon gate：reference hash `3FE51DEB...` == built exe；ProductName/1.0.0 校验通过；release content gate OK）；`smoke_windows_bundle.ps1` Phase A+B OK。
- 规划裁决 M7-D05：EXE icon canonical source 默认 `gus-portrait-1.png`（1254×1254 RGB 带边框，方形），确定性生成多尺寸 `.ico`，不在运行时裁剪 portrait。
- 范围：Task 23（installer）、Task 24（GitHub Release）、Task 25/26（双语）均未实施；未改 backend/API/Mod 协议。

## 已关闭 Milestone 7 Refine 规划 Session（planned → 已授权）

- `2026-08-10-milestone-7-refine-planning`：用户 2026-08-10 确认规划并授权开始 Task 22；规划阶段不创建实施 Packet、不修改产品代码，已完成使命。
- 规划文档：`docs/plans/2026-08-10-milestone-7-refine.md`；主计划已追加 Milestone 7 章节，版本更新为 v0.8。
- Task 拆分：**Task 22** Windows 应用身份与 Gus icon；**Task 23** per-user installer；**Task 24** GitHub Release 自动发布；**Task 25** 双语 UI 与 Settings locale；**Task 26** 双语生成与图像 prompt。
- 依赖：`22 → 23 → 24`，`25 → 26`；推荐串行执行 `22 → 23 → 24 → 25 → 26`。
- 规划裁决：保留 PyInstaller onedir；installer 默认 per-user 且不需管理员权限；卸载保留 workspace；Release 仅 tag/manual；默认 icon 使用 `gus-portrait-1.png`；locale 默认 `zh-CN` 并存于 localStorage；新稿使用当前语言、旧记录语言保持权威；M7 不默默加入第二次翻译模型调用。

## Milestone 6 Task 21 实施 Session（accepted，已推送）

- `2026-08-09-task-21-visual-refinement`：用户已解除 hold并授权直接实施 Task 21；2026-08-10 已按四轮反馈完成修订并通过用户本人验收，已授权提交与推送，不派发独立 Codex Review。
- Design System：`prototype pages design/design system.md`（201 行）；正式视觉源为 Warm Pelican 母主题 + Joja Blueprint 受控子主题 + Cookbook 最高原作浓度，派生页只继承系统。
- Context Packet：`docs/plans/2026-08-09-task-21-visual-refinement-packet.md`，合同 `mvp-task-21-visual-refinement-v1`，`planning_status: READY_FOR_IMPLEMENTATION`，当前执行授权已由用户明确给出。
- Baseline Matrix：`docs/plans/2026-08-09-task-21-visual-baseline-matrix.md`，定义 15 张 Windows/Chromium 1440×900 视觉基线、13 组无障碍场景、1024 最小桌面断言与最终验收门禁。
- 依赖闭包：补入原计划遗漏的 Home、Cookbook Detail、Picker、DownloadableImage、共享 Dialog/Slot、相邻测试、E2E fixture、批准资产与 provenance；不触及后端/API/状态机。
- 实施边界：不修改 backend/API/状态机/Mod 协议；不运行真实 Provider；完成后交用户人工验收，Task 21 不走独立 Codex Review。
- 已实施：Warm Pelican 母主题、Joja Blueprint 受控子主题、Cookbook 槽位系统、App Shell、共享 `PixelModal`/`DishSlot`、批准 UI 资产与 provenance；Home/Create、Ask Gus/Generation、Blueprint、Cookbook/Detail、Pack/Bring/Settings 均已完成视觉精修。
- 2026-08-10 反馈修订：接入用户提供的 Stardew 1.6.15 `springobjects.png` 与 `Cursors.zh-CN.png`，详情页原料/料理数据改用游戏图标；Cookbook 槽位与右侧预览按菜品详情动态对应，点击菜品可切换并可进入对应详情；首页将创建 CTA 收入 Hero；Gus 生成阶段改为用户可理解的中文名称并补充等待提示；Gus 结果页将菜品预览与 16×16 游戏图标拆分展示。
- 2026-08-10 第二轮反馈修订：详情页扩大左侧预览面板与预览图；Banner 移除创建组件并将创建 CTA 独立置于使用流程上方；Ask Gus 使用 Gus portrait，草稿未生成保留 `?`、已归档使用勾选状态；首页收集品/打包入口改用原版收藏袋与礼物图标；详情页饱腹度、生命恢复与售价改用 `Cursors.zh-CN.png` 中更匹配的原版图标。
- 2026-08-10 第三轮反馈修订：接入用户放置于 `Specific Icons` 的五份人工提取素材，替换饱腹度、生命恢复、售价、创建第一道菜和料理蓝图图标；Cookbook 标题使用收藏袋并移除误导性的 `已保存数量 / 24`；Gus 结果左侧预览取消固定高度裁剪，按回传图片原始比例自动撑开容纳区域。
- 2026-08-10 第四轮反馈修订：按用户视觉验收反馈修正详情页料理数据板块的图标映射；饱腹度显示紫色恢复图标，体力恢复显示绿色十字图标。`GameUiIcon energy` 实际为紫色图标，用户提供的 `SpecificIcon edibility` 实际为绿色十字。
- 已补齐：确认弹窗焦点管理、Escape/Tab 行为、跳过链接、表单语义、错误/进度 live region、确定性 E2E fixtures、视觉候选截图和 1024px 横向溢出断言。
- 验证结果（首轮）：TypeScript、ESLint、Vitest `17 files / 98 passed`、Playwright `21 passed`、Vite production build、OpenAPI drift、product-copy gate、Windows bundle build（backend `658 passed / 2 skipped`）与 bundle smoke 全部通过；浏览器核验覆盖 1440px 核心页面和 1024px 无横向溢出。
- 反馈修订验证（2026-08-10）：全量前端 Vitest `18 files / 105 passed`、ESLint、TypeScript、Vite production build、Playwright `26 passed` 全部通过；第三轮定向视觉 Playwright `12 passed`，覆盖人工提取图标、Cookbook 数量字段移除与 Gus 预览不裁剪。未改后端/API/状态机/Mod 协议。
- 第四轮小修复验证（2026-08-10）：全量前端 Vitest `18 files / 105 passed`、详情页定向 Vitest `10 passed`、详情页定向浏览器视觉回归 `2 passed`；未改后端/API/状态机/Mod 协议。
- 最终验收（2026-08-10）：用户确认此前未执行 `pnpm build` 导致的显示误判已解决，并宣布 Milestone 通过验收，授权提交与推送；当前仅剩本次 Git 操作。
- 验收限制：视觉截图作为候选输出，不冻结 tracked screenshot baseline；未运行真实 Provider、真实游戏写入或用户可见 API Key 流程。上述内容不阻塞用户对本 Milestone 的验收与提交推送授权。

## 当前 Milestone 6 Task 20 Session（auto_accepted）

- `2026-08-09-task-20-ci-readme`：Milestone 6 首个 Task（CI/README/发布检查）。用户授权本 Task 由包工直接实施 + Codex 独立审阅（`gpt-5.6-luna`/max，独立 thread）。Context Packet：`mvp-task-20-ci-readme-v1`（`docs/plans/2026-08-09-task-20-ci-readme-packet.md`，gitignored）。
- 实施（commit `33ab7f1`，8 文件 +435/-3）：`README.md` 重写为用户指南；`.env.example`（空值+说明，无 token）；`.github/workflows/ci.yml`（19 步 Windows CI）；`scripts/check_openapi_drift.ps1`；`scripts/check_product_copy.py`（命名门禁唯一实现源）；`tests/repo/test_product_copy.py` + `test_release_contents.py` + `__init__.py`。
- 审阅：round 0 REVISE（2 项 MUST_FIX：T20-CI-001 pip `--group dev -e ./backend` 根目录解析失败 → 改 `working-directory: backend` + `-e .`；T20-NAME-002 README 隐私矛盾 → 明确仅在主动生成请求时向配置的 Provider 发送照片与上下文，Key 只用于请求鉴权）→ 修复 → round 1 **PASS**（无 MUST_FIX，无回归）。
- 验证：`tests/repo` 8 passed（红→绿）；全量 backend+repo+integration **666 passed/2 skipped**；ruff/mypy clean（87 source files）；前端 **94 passed**/lint/build clean；E2E **10 passed**；OpenAPI drift OK；copy gate OK；`build_windows.ps1` exit 0；`smoke_windows_bundle.ps1` exit 0；ci.yml YAML 有效（19 步）。
- 范围：Task 20（CI/README/发布检查）的历史实施记录；Task 21 随后已完成并通过用户验收，未改领域/API/Mod 协议。
- Task 20 与 Task 21 已纳入 Milestone 6 的 `ae5b320` 提交并推送；本节保留当时的 Task 20 自动验收证据。

## 当前 Milestone 5.1 规划 Session（planned，等待开发授权）

- `2026-08-07-milestone-5-1-state-management-planning`：只产出需求定义与 Task 分解，**不实施**。用户明确本轮由用户本人验收，不通过 Codex 审阅。
- **触发**：Milestone 5 验收 ① 部分通过（不再 busy，但刷新后状态归零，与「继承同一个生成任务」不符）、② 未通过（删除生成中的草稿后新任务仍报 `PTS_GEN_BUSY`）。用户结论：整体（前后端）状态管理存在问题。
- **根因**：生成状态真相源位置错误。持久化 attempt 一直在写（`orchestrator.py:714` 每阶段落盘 `current_stage`/`stages`/`status`），但无任何读取接口（`GenerationAttemptPublic` 定义于 `domain/draft.py:199` 却零使用，OpenAPI 只有 generate/cancel）。状态实际活在前端模块内存与 HTTP 流两处易失位置。
  - ①：`orchestrator.py:716` `except GeneratorExit: self._rollback_cancelled(...)` 把客户端断开定义为权威取消，`af08da4` 的 `_ClosingStreamingResponse` 还使其确定性触发 → 生成生命周期绑在 HTTP 连接上而非服务端。
  - ②：`_delete_draft_record`（`application/drafts.py:551`）只删资产/attempt/记录；`DraftService.__init__`（`drafts.py:401`）无 `AttemptRegistry` 引用，无取消无释放槽。task 继续跑并占槽，其 `control_write` 在已删除记录上抛 `FileNotFoundError`（`_rollback_cancelled` 只捕 Revision/AttemptMismatch）→ 槽永久挂住。
  - 更底层：`attempt_registry.py:16` 的 `_occupied` 是无主布尔量，无法回答「槽属于谁」，故任何漏释放都不能自愈；`af08da4` 的三层兜底是补丁而非消除。
- **用户已确认决策**：D5.1-1 只读进度端点 + 前端轮询（不做可重连流）；D5.1-2 完整状态管理重构（6 处改动全做）；D5.1-3 生成中视为活动、应用不退出；D5.1-4 用户本人验收。
- **目标不变量**：生成生命周期由服务端拥有；持久化 attempt 为唯一真相源（流与前端 store 降为视图/缓存）；槽可归属、可对账、可自愈；删除 draft 前必先取消回收在跑 attempt；前端任何挂载路径从服务端 hydrate。
- **用户可见契约变更**（反转 Milestone 5 部分语义，须显式记录）：新增只读进度端点（OpenAPI + 前端类型再生成）；刷新/切页/重开标签回显同一任务；断开不再回滚或取消；删除生成中草稿即时释放槽；生成期间不因空闲阈值退出。
- **Task 分解**（编号 19.1–19.6，已按依赖顺序排列，顺序执行即满足依赖；各自独立 Packet 与本地 focused commit）：**19.1** 槽归属化与持久化对账自愈；**19.2** 服务端拥有的后台生成任务 + 断开改 detach；**19.3** 只读进度端点（复用 `GenerationAttemptPublic`）+ 契约再生成；**19.4** 删除/级联删除前取消回收 + 已删记录容错；**19.5** 前端 hydrate + 轮询 + store 降级为缓存；**19.6** 生成中计入活动 + startup sweep 收窄。
  - 编号说明：规划初稿曾用 20–25，但 Task 20/21 已被 Milestone 6（CI/README、视觉精修与最终验收）占用，故改为 19.1–19.6，以 `docs/plans/MVP_IMPLEMENTATION_PLAN.md` v0.6 为准。
- **规划期已识别将失效的旧语义测试**（改写属对应 Task 范围内）：`test_aclose_releases_slot_and_rolls_back`、`test_closing_streaming_response_closes_iterator_on_disconnect`、`test_cancel_orphaned_attempt_rolls_back`、`useGeneration.test.tsx` 取消/竞态用例、`e2e/generation.spec.ts`、`e2e/full-journey.spec.ts`。
- **范围外**：可重连 NDJSON 流、多并发生成、数据库/队列/事务日志、生成阶段与 prompt/图像/编译导出逻辑、已完成 Task 的回退。
- **`af08da4` 处理**：不回退。其「槽必被释放」目标由 Task 19.1 正式实现，其「断开即取消」语义由 Task 19.2 反转。
- **文档权威缺口**：本 Session 按用户指令只同步开发状态文档；`docs/plans/MVP_IMPLEMENTATION_PLAN.md`（gitignored，Task/里程碑边界权威源）尚未写入 Milestone 5.1，开发授权时须补齐。

## Milestone 5.1 实施完成（2026-08-07，awaiting_milestone_acceptance）

用户授权连续开发（D5.1-4 用户本人验收，不走 Codex）。6 个 Task 已按依赖顺序全部实施并创建本地 focused commit（不 push）：

| Task | commit | 内容 |
|---|---|---|
| 19.1 | `8bf2d8f` | 生成槽归属化与持久化对账自愈（`AttemptRegistry` 持有者记录 + 槽占用对账；`PTS_GEN_BUSY` 携带 `draftId`） |
| 19.2 | `8f8ac3c` | 服务端拥有生成任务，断开改为 detach（`_ServerOwnedStream` + 后台任务 + 队列；`GeneratorExit` 不再回滚） |
| 19.3 | `2a8f304` | 只读进度端点 `GET /api/v1/drafts/{draft_id}/generation`（复用 `GenerationAttemptPublic`）+ OpenAPI/前端类型再生成 |
| 19.4 | `24c9918` | 删除/级联删除前取消并回收在跑 attempt；`_rollback_cancelled`/`_finish_failed` 对已删记录容错 |
| 19.5 | `e1c9349` | 前端挂载从服务端 hydrate + 生成中轮询进度端点；`generationStore` 降级为缓存（终态 sticky） |
| 19.6 | `57b155f` | 生成中计入活动（空闲监控感知槽占用）；startup sweep 收窄为仅跨进程遗留孤儿 |

验证证据：
- 全量 backend：**642 passed / 2 skipped**（ruff、mypy clean；mypy 仅剩 HEAD 预存 `app.py:326`/`exports.py` 错误，非本里程碑引入）。
- 前端：**92 passed**；lint/build clean；E2E **10 passed**（新增「刷新重挂载生成阶段」用例）。
- 发布包：`scripts/build_windows.ps1` 全门禁通过（backend 642 → frontend build → OpenAPI drift → PyInstaller → release content gate）；`scripts/smoke_windows_bundle.ps1` 两阶段通过（Phase A health + 静态首页；Phase B `--exit-after-health-check` 退出 0 + 无残留 runtime lock）。bundle 位于 `dist/PelicanTownSpecials-windows-x64/`，可直接启动复验。
- 环境性阻塞一次：构建时旧 bundle 的 `VCRUNTIME140.dll` 被外部进程（疑为 Windows Defender 扫描）锁住，`COLLECT` 清理失败；停止残留 `PelicanTownSpecials.exe` 并重命名锁定目录后重建成功。已锁定目录 `dist/PelicanTownSpecials-windows-x64.locked` 为 gitignored 残留，可待锁定释放后删除。
- OpenAPI 契约再生成（`fec69a4`）：Task 19.4 的 discard 路由 docstring 变更触发 drift 检查，已同步 `frontend/openapi.json` 与 `schema.d.ts`。

**用户交互验收（2026-08-07，四项全部通过）**：① 生成中刷新/切页回显同一生成任务进度 ✅；② 删除生成中的草稿后立即可新建生成 ✅；③ 生成期间无浏览器连接应用不退出 ✅；④ 重开 exe 无残留卡死 ✅。

**验收发现并已修复**（commit `d6aa3b4`）：刷新后阶段总数显示错误——"已完成 2/2 个阶段"应为"2/总阶段数"。根因：`attempt.stages` 是渐进式记录（只含已推进到的阶段），hydrate 路径误用 `stages.length` 当总数。修复：`GenerationAttempt`/`GenerationAttemptPublic` 新增 `total_stages`（orchestrator `_new_attempt` 按 `len(stage_order)` 落盘），前端 hydrate 改读 `totalStages`。验证：backend 642 passed、前端 92 passed、E2E 10 passed、ruff/mypy clean；发布包已重建（`build_windows.ps1` + `smoke_windows_bundle.ps1` 通过）。待用户确认此修复后再与用户一次性决定 Milestone 4 + 5 + 5.1 的统一 push。

## 当前文档冲突同步 Session（committed）

- `2026-08-08-docs-conflict-sync`：按用户 Brief `PelicanTownSpecials_文档冲突修改Brief_2026-08-08.md` 同步过时文档与产品描述冲突；**仅文档，不改业务代码/路由/UI**。
- 三项裁决已写入正式源：
  - **D-UI-01**：首页 `/` = 品牌叙事 + 草稿 Dashboard 单页；品牌 Hero 增强属 Milestone 6 FUTURE_TARGET，不得标为已完成。
  - **D-UI-02**：一级导航冻结 首页 / 开始创作 / 收集品 / 设置；「使用与安装说明」非一级导航。
  - **D-UI-03**：Ask Gus 结果页仅三操作（接受并存档、完整重新生成、拒绝）；无进入料理蓝图 / 无 Ask Gus→Blueprint 产品路径 / 无用户可达 `CONVERTED_TO_ADVANCED`；Blueprint 仅独立入口。
- 版本：P1D **v2.2**、P2D **v1.1**、TD0 **v1.5**、IP0 **v0.7**；CONSTRAINTS / 设计源索引 / 三期锚点「现行结论」已同步。
- HISTORICAL_KEEP：F19-3/F19-4 移除转换按钮（`ecfcf85`）、导航首页入口（`26c3044`）、历史 Session 与 convert 代码/测试——不改写、不删除代码。
- 代码残留仅报告：convert API/application/OpenAPI/tests 若仍存在，文档标注非用户可达；删除需另开授权 Task。
- 用户确认 Brief §10 后控制面 focused commit + push：`CONSTRAINTS.md`、`STATUS.md`、本 Session；设计源 gitignored。
- 详见 `docs/development/sessions/2026-08-08-docs-conflict-sync.md`。

## 预览图下载入口 Session（committed）

- `2026-08-09-downloadable-image-preview`：用户直接要求的前端小功能——为已生成的草稿预览图（蓝图编辑页 / Ask Gus 审核页）与已接受收集品详情页的预览大图增加 hover 下载按钮，替代右键另存为。用户本人验收，不走 Codex 审阅。
- 实施（commit `4fe7eca`，7 文件 +211/-3）：新增复用组件 `frontend/src/components/DownloadableImage.tsx`（hover 浮现下载按钮；点击 fetch 图片字节、按 MIME 探测扩展名，以 `{名称}-预览.<ext>` 下载）；接入三处预览图（BlueprintEditorPage / AskGusReviewPage / CookbookDetailPage）；`copy.ts` 新增 `downloadImage: "下载图片"`；`global.css` 加 hover 样式；新增组件聚焦测试 2 条。
- 验证：定向 **38 passed**；全量前端 **94 passed**（15 文件）、`tsc --noEmit` clean、eslint clean；发布包已重建并同步（`index-CgjeyN3b.js`），无需重打 exe（onedir 从磁盘读静态资源）。
- 范围说明：下载入口只加在预览大图；32px 像素图标未加，如需可后续追加。
- 用户验收通过（2026-08-09），授权提交并更新文档；本轮未授权 push。`frontend/dist`、`dist/` 为 gitignored 产物，不进提交。

## 导航栏首页入口 Session（committed，历史）

- `2026-08-08-nav-home-entry`：用户直接要求的前端 UI 小改动——主导航栏最左侧新增「首页」入口，指向 `/`（草稿首页仪表盘），解决用户在创建/收集品/设置页面无法回到首页、只能改 URL 的问题。
- 实施（commit `26c3044`，3 文件 +8/-0）：`copy.ts` 新增 `home: "首页"`；`AppShell.tsx` 导航栏最前加 `<NavLink to="/" end>`（`end` 防 `to="/"` 匹配所有路由导致始终高亮）；`router.test.tsx` 补断言。
- 验证：全量前端 **92 passed**、`tsc --noEmit` clean、eslint clean。
- **首次验收失败与重建**：用户贴出运行产物 HTML 无「首页」——源码改动未重建，发布包从 exe 旁 `frontend/dist` 读静态资源（旧构建）。修复：`pnpm --dir frontend build` 重建 + 同步 `index.html`/`assets` 进 `dist/PelicanTownSpecials-windows-x64/frontend/dist/`（onedir 静态资源从磁盘读，无需重打 exe）。用户复验通过（2026-08-08）。
- 已按用户授权提交并推送远端；`frontend/dist`、`dist/` 为 gitignored 产物，不进提交。本事实保留为 IMPLEMENTATION_FACT，不因文档同步改写。

## 当前 Task 19 Session（auto_accepted）

- `2026-08-06-task-19-pyinstaller`：Milestone 5 首个 Task。Context Packet：`mvp-task-19-pyinstaller-v1`（`docs/plans/2026-08-06-task-19-pyinstaller-packet.md`，gitignored）。
- 实现：`observability/`（redaction/logging/diagnostics）、只读诊断端点（会话门控）、PyInstaller onedir spec + build/smoke 脚本、安全回归（local API/SSRF/ZIP）、`frontend/e2e/full-journey.spec.ts` 全链路。
- 审阅：round 0 REVISE（4 项 MUST_FIX）→ 修复；round 1 残留缺口（嵌套键语义）补齐；round 2 REVISE（launchToken 大小写成员泄漏 dict）→ 修复 → 闭包验证 **PASS**。
- 验证：observability+security 57 passed、全量 backend 626 passed/2 skipped、前端 77 passed、E2E 1 passed、ruff/mypy/diff-check clean；build_windows.ps1 端到端通过（含发布文档门禁）；smoke 两阶段通过（Phase A 健康+首页、Phase B 自检退出 0 + 无残留 runtime.json）。
- auto_accepted，本地 focused commit（未 push）。

## 当前 Task 19* Session（auto_accepted）

- `2026-08-06-task-19star-frontend-state`：Milestone 5 第二个 Task。Context Packet：`mvp-task-19star-frontend-state-v1`（`docs/plans/2026-08-06-task-19star-frontend-state-packet.md`，gitignored）。修复用户报告的 5 项问题。
- 实现（commit `ecfcf85`，19 文件 +1102/−188）：F19-1 `/cancel` 改为等待回滚（`AttemptRegistry.await_task` shield+timeout、orchestrator `await_cancelled`、`GenerationService.cancel` async、路由 async 202 在回滚后返回；`_generate` finally `inner.aclose()` 使断流 GeneratorExit 同步触发 `_run` 的 `_rollback_cancelled`）；前端 `cancelStream` 先 await 后端再 abort + 单飞 + 捕获 controller 守卫。F19-2 模块级 `generationStore.ts`（per-draftId + `_snapshot`），切页不丢流、重挂载恢复。F19-3/F19-4 `AskGusReviewPage` 移除「进入料理蓝图」按钮/handler 与 `noGameplayYet` 块，copy 键同步移除。F19-5 `CookbookService.delete` 级联 `delete_archived_by_dish` + `list_drafts` 孤儿 ARCHIVED 过滤 + 共享 `_delete_draft_record`（资产引用保护）。`ndjson.ts` 新增结构化错误包络解析（`GenerationRequestError`/`GenerationCancelError`）。
- 审阅：round 0 REVISE（2 项 MUST_FIX，均 F19-1-001——/cancel 202 未等回滚、cancelStream 过期 finally 杀新生成）→ 修复（round 1：async cancel 路由 + API 集成回归测试；前端单飞 + controller 守卫 + 竞态回归测试）→ round 1 闭包验证 **PASS**（无 MUST_FIX；实施期「send 边界」观察经核对由 GeneratorExit 回滚覆盖，判非缺陷）。
- 验证：全量 backend 616 passed/2 skipped、前端 86 passed、E2E 9 passed（spec 未改，仅断言「进入料理蓝图」count 0）、ruff/mypy/lint/build/diff-check clean；无 OpenAPI/契约变化。
- auto_accepted，本地 focused commit（未 push）。真实用户交互复验留待 Milestone 5 全量验收。

## Milestone 5 全量验证（2026-08-06）

- `scripts/build_windows.ps1` 全门禁复跑通过（exit 0）：backend 632 passed/2 skipped → frontend 86 passed → frontend build → **OpenAPI drift**（捕获 round-1 cancel docstring 描述变化，已再生成 `4b58f0f`）→ repo ignore policy → PyInstaller（PYZ/PKG/EXE/COLLECT）→ 发布文档复制 → bundle 结构与 release content gate。
- `scripts/smoke_windows_bundle.ps1` 两阶段通过：Phase A 正常启动 + HTTP health + 静态首页；Phase B `--exit-after-health-check` 退出 0 + 无残留 runtime lock。
- 产物：`dist/PelicanTownSpecials-windows-x64/`（onedir 发布包，本机已验证可启动服务）。
- Milestone 5 自动化门禁全部完成，但 **2026-08-07 用户交互验收未全部通过**（① 部分通过、② 未通过）→ 未进入 Milestone 5 accepted，统一 push 门保持关闭。后续状态见上方 Milestone 5.1 规划 Session。

## 当前验收修复 Session（auto_accepted，待用户复验）

- `2026-08-07-post-acceptance-slot-leak-fix`：Milestone 5 验收未通过 3 项的根因修复——Starlette 1.3.1 `StreamingResponse` 断开时不 `aclose` body iterator → 生成槽泄漏 → 永久 `PTS_GEN_BUSY`「当前已有一个生成任务在运行」。用户明确本修复由用户本人验收，不走 Codex 审阅。
- 三层修复：① `_generate` finally + `_SlotGuardedAsyncIterator.__del__` 保证所有终止路径释放进程级单槽；② 路由级 `_ClosingStreamingResponse` 确定性 `aclose` body iterator；③ 孤儿 attempt 恢复（`recover_interrupted`，`/cancel` + startup sweep 清扫，重开 exe 自愈）。
- 验证：定向回归 10 passed；全量 backend **620 passed/2 skipped**；Ruff clean；Mypy clean（5 个改动源文件，app.py:326 与 exports.py 为 HEAD 预存错误）。前端无改动。
- 发布包已重建：`build_windows.ps1` 全门禁通过（backend 636 passed/2 skipped、frontend 86 passed、OpenAPI drift/ignore policy OK、PyInstaller、release content gate）+ `smoke_windows_bundle.ps1` 两阶段通过；bundle 位于 `dist/PelicanTownSpecials-windows-x64/`。
- 待用户交互复验 3 项：生成中切页回到草稿不再误报「开始生成」/busy；删除草稿后生成新草稿不再 busy；reload/重开 exe 后系统自恢复。

## 当前 Milestone 3 验收 Session（accepted）

- `2026-08-05-milestone3-acceptance`：用户 2026-08-05 宣布 Milestone 3 验收通过（R1–R11 全部修复已本地提交）。验收范围：Task 11–15（OpenAI-compatible generation）+ 验收修复 R1–R11（含 provider 入参约束 16 倍数/最小像素、Stardew tooltip prompt 硬锚点、双图 EDIT 管线、Buff 逐行中文展示）。
- 本地 commits 等待用户授权统一 push 至 origin/feat/mvp-implementation。

## 当前 R17 Session（committed）

- `2026-08-06-r17-gus-gameplay-pricing`：按 Stardew 1.6.15 原版烹饪物价格分布约束 Ask Gus gameplay prompt；生图 prompt 保持不变。
- 实现（commit `5905360`）：新增版本化 `ask_gus_v3` 并保留 v1/v2；普通菜 80..250g、精致菜 250..400g、高档/复杂菜 400..500g，多数结果 100..400g；普通或无 Buff 菜不得超过 500g，不得用高价补偿无 Buff；超过 500g 仅限明确传奇/特殊功能性物品并须在 `gusComment` 解释玩法理由。
- 价格依据覆盖原料价值/稀有度、制作复杂度、恢复量、Buff 强度/持续时间和定位；Oil of Garlic 1000g 与 Magic Rock Candy 5000g 只作极少数原版例外校准。
- 验证：TDD RED→GREEN focused 49 passed；全量 backend 553 passed/2 skipped；Ruff、Mypy（15 源文件）、diff-check clean；独立只读 Review PASS，无 MUST_FIX。
- 无 schema/validator/compiler/API/frontend/图像链路变化，未调用真实 Provider；已有草稿不自动改价，等待用户重新生成观察。

## 当前 Task 16 Session（committed）

- `2026-08-05-task-16-mod-compiler`：Milestone 4 首个 Task（deterministic Content Patcher compiler）。Context Packet：`mvp-task-16-mod-compiler-v1`。实施子代理 TDD（红→绿 60 passed、回归 208 passed、全量 528 passed/2 skipped），Codex 审阅 **PASS**（round 0，14/14 criterion），本地 focused commit `1730578`（feat）+ `be6eb1b`/`fa34d5e`（docs），未 push。
- 闭包裁决 R16-1..6：author_name 注入编译器构造；`validate_export` 增 catalog 参数；Buff→Data/Objects.Buffs（Task 18 Spike 冻结）；i18n default/zh 一致；ExportArtifact/compile_to_bytes；staging 为调用方目录。

## 当前 R16 Session（committed）

- `2026-08-06-r16-gus-buff-latitude`：用户确认生图 prompt 已满意，仅要求适度放宽 Ask Gus gameplay prompt 的 Buff 推荐标准。
- 实现（commit `9d06e41`）：新增版本化 `ask_gus_v2` 并保留 v1；普通但有可信玩法关联的菜通常可获得 1 个温和 Buff，特征明确时最多 2 个互补属性；仅非常朴素且无可信关联时为 null；禁止无关或夸张 Buff。新调用路由 v2，provenance 记录 `ask-gus-v2`。
- 验证：TDD RED 2 个预期失败→GREEN focused 48 passed；全量 backend 552 passed/2 skipped；Ruff、Mypy（14 源文件）、diff-check clean；独立只读 Review PASS，无 MUST_FIX。
- 生图 prompt、双图 EDIT、图标与预览管线均无改动；未调用真实 Provider。技术设计已更新至 v1.3；等待用户重新生成验证模型分布。

## 当前 R12–R15 Session（committed）

- `2026-08-06-r12-r15-game-acceptance-fixes`：用户游戏内验收发现四项细节问题并授权修复——R12 图标黑底（确定性 Pillow 洪泛抠图 + 洋红背景 prompt，`5761e92`）、R13 Buff 游戏内不显示（Buff 内嵌 Data/Objects 条目、对齐官方 1.6.15 结构、Duration 游戏分钟，`886de32`）、R14 Edibility 偏高（prompt 原版取值带 + 官方换算公式 ceil/floor，`8589a3e`）、R15 材料不准（双 prompt 约束 + `ensure_main_protein` 主食材护栏，`8589a3e`）。
- 验证：全量 backend + 集成 565 passed/2 skipped；Ruff clean；mypy 仅剩 3 处 HEAD 预存错误（exports.py/app.py，stash 基线确认与本次无关）；diff-check clean；无契约/前端变化。
- 独立只读 Review Subagent **PASS**（无 MUST_FIX；本环境无 codex-mcp 通道，按回退路径执行，未冒充 Luna 路由）。auto_accepted，三个本地 focused commits（未 push）。
- Spike 结论已回写设计 §18.3 与变更记录 v1.2；待用户重新生成菜品并游戏内复验四项效果。

## 当前 Task 18 Session（game-acceptance-passed）

- `2026-08-05-task-18-game-validation`：Milestone 4 第三个 Task（真实 Stardew Valley 验证与 Spike 冻结）。Context Packet：`mvp-task-18-game-validation-v1`（R18-1..5，gitignored）。自动范围完成：`scripts/validate_mod_zip.py`、`scripts/deploy_local_mod.ps1`、`tests/integration/test_release_mod.py`（16 passed）、根级 `pytest.ini`（importlib 模式，Codex 验证接受的 scope_delta）。
- Codex：round 0 REVISE（T18-VALIDATOR-002 根孤儿未拒）→ round 1 修复 → round 2 **PASS**。包工复跑：集成 16 passed、combined 76 passed、全量 backend 538 passed/2 skipped、ruff/mypy/diff-check clean。auto_accepted，本地 focused commit（未 push）。
- **游戏验收（用户 2026-08-06 确认）**：打包验收成功，解压后游戏内找到对应物品。核心验收通过；8 项细节中的四项 API 调用问题已由 R12–R15 修复（见上方 Session），Spike 结论已回写设计 §18.3。

## 当前 Task 17 Session（committed）

- `2026-08-05-task-17-export`：Milestone 4 第二个 Task（Export API、Pack the Menu 与 Bring It In-Game）。Context Packet：`mvp-task-17-export-v1`（R17-1..7）。实施子代理 TDD 完成；Codex round 0 REVISE（T17-OPENFOLDER-001 生产装配未注入 os.startfile）→ round 1 修复（app.py `_default_open_folder()` win32→os.startfile + 新测试）→ round 2 BLOCKED（环境性：只读环境无法跑 pytest，无 criterion 失败）。
- 包工复跑闭合：全量 backend **538 passed/2 skipped**、前端 77 passed、E2E 8 passed、lint/build/ruff/mypy（79 源文件）/diff-check clean、契约已重生成。判定 auto_accepted。
- 实现：`ExportRecord`/`ExportStatus`/`ExportRecordView` + `ExportRepository`（幂等 add_or_get）；`ExportService` 同步状态机 VALIDATING→BUILDING→SUCCEEDED/FAILED（staging ZIP 永不可下载）；5 端点；前端 PackMenuPage/ValidationIssues/BringInGamePage + CookbookPage 打包入口 + 路由 + E2E。
- 非阻塞：download OpenAPI 声明 application/json（运行时 application/zip）、Idempotency-Key 标可选 —— 后续加固。
## 当前 Task 13 Session（committed）

- `2026-08-04-task-13-generation-orchestrator` 已从上下文溢出后的部分工作树恢复，完成 Ask Gus 生成 Orchestrator、NDJSON 流式事件与完整重生成，独立只读 Review Subagent 首轮 `PASS`（无 MUST_FIX），auto_accepted 后创建本地 focused commit `5949516`（不 push）。
- 实现：`generation/orchestrator.py`（阶段循环、候选构建、原子 promote、取消/失败回滚、`_SlotGuardedAsyncIterator` 槽位释放）、`application/generation.py`、`api/routes/generation.py`、app.py 装配与 lifespan 启动恢复；依赖闭包含 repositories `control_write`/`promote`/attempt 仓库、domain errors/state_machine、providers ModelGateway Protocol、catalog mapping Protocol、error_handlers 共享 ErrorEnvelope。
- 验证：生成测试 10 passed；全量后端 420 passed/2 skipped；Ruff、mypy（68 源文件）、前端 contract:generate/build/lint/test（36 passed）、`git diff --check` 全部通过。
- 已消费 Task 11 建立的 `ModelGateway` 协议；测试全部使用 FakeGateway，不产生模型费用。

## 当前 Task 14 Session（committed）

- `2026-08-04-task-14-blueprint-preview` 采用「包工-子代理-Codex 审阅」新模式首次完整跑通：包工生成 Context Packet（`mvp-task-14-28db7a8-20260804-final-v1`），实施子代理 TDD 实现，包工桥接 Codex 独立审阅（round 1 REVISE 1 项 MUST_FIX → 修复 → round 2 PASS），本地 focused commit `daeacfd`（不 push）。
- 实现：`generation/blueprint.py`（6 阶段序列、确定性 brief、`run_blueprint_preview`）、orchestrator 的 BLUEPRINT_PREVIEW 分支（用户字段保护、provenance 保留、失败/取消保持 STALE_PREVIEW）、`application/generation.py` kind 解析、`domain/validation.py` scope delta（BLUEPRINT analysis 可选）。
- 验证：蓝图测试 8 passed；全量后端 428 passed/2 skipped；Ruff、mypy（69 源文件）clean；OpenAPI/前端契约无变化；`git diff --check` 通过。
- Task 14 不包含前端（Task 15）、真实模型调用；测试全部使用 FakeGateway。

## 当前 Task 15 Session（committed）

- `2026-08-04-task-15-generation-experience` 采用「包工-子代理-Codex 审阅」模式完成 Milestone 3 收尾：包工生成 Context Packet（`mvp-task-15-5df2352-20260804-final-v1`），实施子代理实现前端生成体验，Codex 独立审阅（round 1 REVISE 1 项 MUST_FIX → 修复 → round 2 PASS），本地 focused commit `038635a`（不 push）。
- 实现：`api/ndjson.ts`（NDJSON 流式解析 + streamGeneration）、`features/generation/`（useGeneration/GenerationProgress/GenerationError）、`AskGusReviewPage.tsx`（四操作）、`BlueprintEditorPage.tsx`（更新预览 + STALE_PREVIEW 阻止接受）、router 模式分发、`playwright.config.ts` + E2E fake flow。
- 验证：vitest 52 passed；Playwright E2E 7 passed；build/lint 通过；后端 428 passed/2 skipped（无后端改动）。
- 已知限制：后端 FAILED 重试未接线（`RETRY_FAILED_GENERATION` 已存在于状态机），FAILED ask-gus 草稿无操作入口；延后为单独后端 Task。
- **Milestone 3（Task 11–15）全部完成**：本地 commits（10aa141/9555a55/145e164、5949516/aca590b、daeacfd/5df2352、038635a）均已本地提交、未 push。

## 当前 R11 Session（committed）

- `2026-08-05-r11-min-pixels`：用户真实环境 Ask Gus 双图 EDIT 报 `total pixels must not be less than 655360 (got "752x672")`。方案选定：LANCZOS 放大为主、极端比例受控拦截兜底。修复（commit `8f36b6d`，4 文件 +107/-10）：`downscale_for_vision` 新增 `min_pixels`（默认 655,360）——缩放+16 倍数对齐后不足则 `_ceil_align_edge` 两轴放大到满足下限的最小尺寸（752x672→864x768=663,552、640x480→944x704=664,576）；放大后长边将超 2048（如 16x2048）抛 ValueError；orchestrator `_prepare_vision_input` 将 ValueError 转受控 `PTS_IMAGE_INPUT_UNSUPPORTED`（422 非重试），DISH_ANALYSIS 与 PREVIEW 统一使用。
- 验证：focused 32 passed、全量 backend **468 passed/2 skipped**、ruff/mypy/diff-check clean；Codex 审阅 **PASS**（round 0）；无契约变化。未 push。

## 当前 R10 Session（committed）

- `2026-08-05-r10-buff-tooltip-prompt`：按用户参考图将 Buff 从内部摘要改为逐行中文展示，持续时间改为 `H:MM`，并补充状态/时钟/金币像素图标与分隔线的最小布局要求；保持 R9 的 Stardew item hover tooltip 硬锚点。
- 实现（commit `732b3ac`）：12 个非零 Buff 属性固定中文映射与显式正负号；隐藏 Buff ID/内部键名；420→`7:00`、490→`8:10`；无 Buff 时省略 Buff 与持续时间；售价固定末行；Ask Gus/Blueprint 共用 builder。
- 验证：TDD RED 2 failed→GREEN focused 20 passed；全量 backend 465 passed/2 skipped；Ruff、Mypy、diff-check clean；独立只读 Review PASS，无 MUST_FIX。
- 实际 Review 为 `gpt-5.6-sol/max`；项目指定的 gpt-Luna 路由在当前工具面不可用，未静默冒充。真实模型视觉效果等待用户重测；未 push。

## 当前 R9 Session（committed）

- `2026-08-05-r9-prompt-anchor`：用户反馈 EDIT prompt 过强细节引导（羊皮纸/渐变/装饰角），要求按「硬锚点 + 少量版式约束 + 字段内容」重构，星露谷 item hover tooltip 为最高优先级。修复（commit `a727a8f`，4 文件 +123/-252）：新增公共 `build_full_tooltip_prompt`（Ask Gus/Blueprint 共用；锚点「Stardew Valley item hover tooltip」、非海报/菜单/网页卡/PPT/说明书/羊皮纸公告板；字段格式 标题：/类别：/描述：/能量：+N/生命：+N/售价：Ng）；删除 `clip_visual_brief`（visual_brief 不再进 prompt，`VisualSpec.visualBrief` 持久化不变）；`enforce_preview_prompt_budget` 保留为安全网；over-budget 端到端测试改为 budget 门单元测试（新 prompt 最大字段约 1190 < 1500）。
- 验证：focused 19 passed、全量 backend **464 passed/2 skipped**、ruff/mypy/diff-check clean；Codex 审阅 **PASS**（round 0）；无契约变化。

## 当前 R8 Session（committed）

- `2026-08-05-r8-prompt-quality`：用户观察词条卡稳定出现在食物居中上方，要求模型自主判断最佳位置（SKILL §3 自适应规则）+ 预览 EDIT 指定 `quality="high"`。修复（commit `787b82c`，4 文件 +13/-2）：两处 prompt（ask-gus/blueprint）加入自适应位置指令（优先背景留白/墙面/桌面/窗景，主体中下放上方、一侧放相反侧，不固定居中、不遮挡主体）；EDIT 请求加 `quality="high"`（icon 生成不加，保持已验收行为）；测试加 quality 与措辞断言（TDD 红→绿）。
- 验证：focused 19 passed、全量 backend **464 passed/2 skipped**、ruff/mypy/diff-check clean；Codex 审阅 **PASS**（round 0）；无契约变化。

## 当前 R7 Session（committed）

- `2026-08-05-r7-edit-edge-alignment`：用户真实环境 Ask Gus 超时，Provider 报 `invalid image size: edges must be multiples of 16 (got "990x1051")`。根因：`downscale_for_vision` 只保证长边 ≤2048，未对齐 16 倍数（缩放与不缩放两条路径）。修复（commit `90700b6`）：新增 `_align_edge`（向下取整 16 倍数、min 16 保护），缩放/不缩放路径统一对齐；新增 2 个红→绿测试（4032x2689→2048x1360、990x1051→976x1040）。同一函数服务 DISH_ANALYSIS，对齐无害且更合规。
- 验证：focused 9 passed、全量 backend **464 passed/2 skipped**、ruff/mypy/diff-check clean；Codex 审阅 **PASS**（round 0）；无契约变化。

## 当前 R6 Session（committed）

- `2026-08-05-preview-pipeline-r6`：用户更新 SKILL——最终词条卡**必须由图像模型双图 EDIT 生成**（`source_images=[原图, 同一轮像素图标]`，图标优先 `iconSourceAssetId`），本地合成器/Pillow/Canvas/前端组件排版被明确列为错误做法；R5 本地合成方案推翻重做。同日用户澄清协作规则：codex-mcp 为通信桥接（非执行通道），codex 担任执行者仅限视觉/多模态 Task；审阅强度 GPT 5.6 Luna (xHigh)（`gpt-5.6-luna` + xhigh），memory 已同步。
- Packet：`docs/plans/2026-08-05-preview-pipeline-r6-packet.md`（`preview-pipeline-r6-8e5aaee-20260805-v1`）。
- 实现（commit `fb40992`，22 文件 +571/-767）：orchestrator PREVIEW 单次双图 EDIT（原图 `downscale_for_vision` ≤2048 + ICON_SOURCE，`size=原图尺寸`）；能力门 `_ensure_image_edit_capability`（不支持 → `PTS_PROVIDER_IMAGE_EDIT_UNSUPPORTED` 502 非重试，无回退）；prompt 重建（ask-gus `_preview_prompt` + `blueprint_preview_prompt` 含 gameplay 参数，字段逐字 + SKILL 视觉语言，`clip_visual_brief` 200 字符）；合成器及其独占资源/测试/golden/脚本/字体删除（scope_delta：`resources/provenance.json`、`THIRD_PARTY_NOTICES.txt` 一并清理）。
- round-1 修复（Codex REVISE 2 项 MUST_FIX）：最大合法字段下 prompt 超 1500 冻结契约 → 共享 `enforce_preview_prompt_budget`（Provider 调用前统一执行，超限受控 `PTS_PREVIEW_PROMPT_TOO_LONG` 422 非重试），TDD 红→绿；round 2 审阅 **PASS**。
- 验证：backend **462 passed/2 skipped**、frontend **71 passed**、E2E **7 passed**、ruff/mypy/build/lint/diff-check clean；无 OpenAPI/契约/前端变化。
- 非阻塞：真实 Provider 双图 EDIT 端到端未验证（下次用户验收确认模型渲染词条卡效果）；`build_blueprint_visual_brief` 措辞「菜品插画」已降级为氛围参考，改存储文本会变 API 可见字段留作加固。

## 当前 Preview Pipeline Session（committed）

- `2026-08-05-preview-pipeline-refactor`（R5）：用户反馈两问题——（1）三页只显示文案不渲染预览/图标（schema 有字段、端点已存在但无 `<img>`）；（2）orchestrator 预览阶段用 `ImageOperation.GENERATION` 生成整幅像素画，违反用户 skill `stardew-dish-card-overlay` 的「原图不可替换、只叠加词条卡」核心判定。
- 用户确认正确范式（`samples/image-edit/case/`）并要求实现走 codex-mcp（`gpt-5.6-luna`/xhigh）、主会话负责通信与验收。Context Packet：`docs/plans/2026-08-06-preview-pipeline-packet.md`（gitignored，`preview-pipeline-refactor-fd79f6a-20260805-v1`）。
- 实现（commit `8e5aaee`，17 文件 +363/-130）：合成器 `PreviewSnapshot` 改 `original_image + icon_16`、以原图为画布（保留尺寸/构图）、卡片自适应右上角、NEAREST 图标缩放、确定性文字；orchestrator PREVIEW 阶段删除模型调用，直接读原图 + icon_16 本地合成，`generatedArtAssetId` 新记录不再设置；前端三页（AskGusReviewPage/CookbookDetailPage/BlueprintEditorPage）经 `assetUrl()` 渲染 preview + icon，`imageRendering: pixelated`。
- 验证：backend **466 passed/2 skipped**、frontend **71 passed**、E2E **7 passed**、ruff/mypy/build/lint/资源检查/diff-check clean；无 OpenAPI/契约变化；包工人工核查 PREVIEW 阶段零 `ImageOperation.GENERATION`、`_read_source_image` 读 `original_image_asset_id`（skill 硬约束满足）。
- 非阻塞：真实 Provider 端到端预览视觉未验证（下次用户验收时确认）；卡片几何为确定性算法，产品侧如需微调可另立 Task。

## 当前 Milestone 3 验收修复 Session（committed）

- `2026-08-05-milestone3-acceptance-fixes` 两轮修复用户真实验证反馈：R1 `07652f6`（视觉降采样 ≤2048 + provider 错误脱敏摘要、Blueprint 生成入口覆盖 DRAFT/READY、首页草稿仪表盘）、R2 `949b762`（模型默认值 sample 配置 + 空模型守卫、FAILED 重试、草稿删除、recovery 派生字段 schema 剔除、Blueprint REVIEWABLE 重试门控）。
- 验证：R2 全量 backend **450 passed/2 skipped**、frontend **64 passed**、E2E 7 passed、ruff/mypy/build/lint/diff-check clean；无 OpenAPI/契约变化。
- 关键根因修复：`_model_schema` 剔除 `Field(frozen=True)` 派生字段解决 `recovery:value_error`（schema 曾强制模型返回只读派生字段）；`_resolve_kind` FAILED→INITIAL 解决 FAILED 重试 409。
- 非阻塞：HomePage 删除后 `list_drafts` 仍含 DISCARDED（过滤终态待用户确认）；`_strip_frozen_fields` 用 title 匹配可后续加固。

## 当前 Task 9 Session（committed）

- `2026-08-04-task-9-draft-cookbook-api` 已按最终 Context Packet（`mvp-task-9-rerun-15405d0-20260804-final-v1`）完成实现、自动验证与两轮 Review（第一轮 REVISE 4 项 MUST_FIX 已修复，第二轮 PASS），用户确认实验成功后创建本地 focused commit；工作树核验干净。
- domain 增加 `baseTemplateVersion`；persistence 扩展 asset UUID 查找与 Archive 幂等查询；application 新增 `AssetService`/`DraftService`/`CookbookService`/`Page`；api 新增 assets/drafts/cookbook 路由与 `dependencies.py` 装配。
- 验证：focused 125 passed、全量 334 passed/2 skipped、Ruff、mypy、前端 test/lint/build、`git diff --check` 与本地文档忽略检查全部通过。
- 用户已确认双 Agent 协作实验成功，后续采用里程碑粒度验收：普通 Task 的 PASS 自动进入 `auto_accepted` 并创建本地 focused commit，不在单个 Task 打断用户；Milestone 全量验证后统一验收与 push。

## 已关闭自治规则 Session（committed）

- `2026-08-04-dual-agent-autonomy-rules` 已完成规则落地、协议静态验证和旧 Task 9 产物清点；未修改 backend、frontend 或生成产品契约。
- Context Packet Schema、动态依赖闭包、技术冲突自治裁决、`BLOCKED` 边界、全局两轮 `REVISE` 上限、模型路由、Task 9 实验门和 Milestone push 门已写入控制面。
- Task 9 重做只可从新的最终 Context Packet 开始；Task 9 旧 Context Packet fixture 已移除，当前 schema 内的 rerun fixture 仅用于验证协议，不授权产品实现。

## 上一 Task 8 Session（committed）

- 2026-08-03-task-8-vanilla-catalog 已完成用户验收、focused commit 和推送。
- Task8 目标是把真实 Stardew 1.6.15 Data/Objects 变成可审计、可重复构建的原版目录，并提供安全映射与 Gameplay 校验。
- 计划文件为 docs/superpowers/plans/2026-08-03-task-8-vanilla-catalog.md；已保留用户提供的 Objects.json 与 Objects.zh-CN.json，并由构建脚本生成真实 vanilla-ingredients.json 与 provenance.json；不创建伪造的 objects-source.json。
- 已收到 Objects.json（SHA-256 6CBC66CAECFED0AAC884958E21834D572014DBF4E41E64A0AF1B190E8390FF90）和 Objects.zh-CN.json（SHA-256 E51B2EF545E519E268A793BDB9EC0905B9ED6A3F7E1BFD7EEA84D5EE79051F07）；中文名称通过 Name_Name 本地化 Key 合并。
- 最终验证已完成：真实重建与生产目录 identical；目录 808 条、85 个 named IDs，256 为 Tomato、-5 为 category；catalog 测试 51 passed，全后端 254 passed/2 skipped。两个 skipped 仅因 Windows 无 symlink 权限。

## 已关闭 Task 7 Session（committed）

- `2026-08-03-task-7-launcher-security` 已完成实现、全量验证和独立只读复审，用户已明确验收通过并创建 focused commit；Task7 设计补充和实施计划已写入并通过用户确认。
- 本 Session 只处理 Launcher 单实例启动、loopback 安全边界、一次性 launch token、HttpOnly 会话、Origin/CSRF 校验、同源静态托管、前端 bootstrap、心跳和 10 分钟空闲退出。
- Task7 不处理真实模型调用、Provider Gateway、业务草稿/菜品 API、登录账户、数据库、机器级环境变量或发布流水线。
- 设计说明：`docs/superpowers/specs/2026-08-03-task-7-launcher-security-design.md`；详细计划：`docs/superpowers/plans/2026-08-03-task-7-launcher-security.md`。
- Task1 已完成：安全测试先红后绿；当前主工作区最终安全回归 21 passed，Ruff、mypy、git diff --check 和独立只读复审均通过。修复了 health Host 校验、错误 CSRF 不续期、过期 token 清理和当前端口精确匹配。
- Task2 已完成：锁、运行记录、loopback URL、端口选择、浏览器打开和 health 探针已通过 15 项测试、Ruff、mypy、差异检查和独立只读复审；修复了总超时边界与端口 0。
- Task3 已完成：同源静态托管、SPA fallback、缺失资源安全错误、heartbeat、主动 shutdown 和生命周期 idle monitor 已通过 30 passed/1 skipped 的回归、Ruff、mypy、差异检查和独立只读复审；symlink 测试因当前 Windows 权限跳过，路径边界逻辑已覆盖。
- Task4 已完成：Launcher 主流程、CLI、动态端口、安全注入、单实例复用、health 等待、浏览器 fragment、no-browser/exit-after-health-check 和失败清理已通过 42 passed/2 skipped、Ruff、mypy、差异检查和独立只读复审；修复了站外 index symlink 预检旁路。
- Task5 已完成：前端 launch bootstrap、`X-PTS-CSRF` 内存 middleware、成功后 fragment 清除、30 秒 heartbeat 与 pagehide 清理已通过 9 项前端测试、lint、TypeScript/Vite build、差异检查和独立只读复审；实现过程中前端现有文件使用受控编辑完成，未创建提交。
- Task7 最终复验已完成：后端 201 passed, 2 skipped；前端 9 passed；Ruff、mypy、前端 lint/build、git diff --check 和本地文档忽略检查均通过；真实 no-browser Launcher smoke 在 127.0.0.1:43132 启动并完成 health 后正常退出，运行记录已清理。
- 独立只读总审阅已通过：端口预留竞态、可读失败反馈、异常清理覆盖缺口和 SPA fallback 文档路径边界均已修复并通过回归；剩余 P2 复用边界已记录为验收限制。Windows 无 symlink 权限的 2 项路径边界测试保留为 skipped；真实浏览器视觉流程仍需用户在本机确认。
- 当前下一步：完成最终验证证据、同步文档并进入用户验收准备。
## 已关闭 Task 3 Session（committed）

- `2026-08-02-task-3-frontend-shell` 已完成 verification 并通过用户验收，范围严格限定为 MVP Task 3：React/Vite/TypeScript 前端骨架、OpenAPI 生成类型、same-origin typed client、正式产品首屏和启动健康检查。
- 用户明确反馈已手动启动 Vite 与后端，首页显示正常，Network 中 health 请求返回 200，并确认“task3可以验收通过了”。
- 本 Session 的 focused commit amend 边界包含前端壳层、标准 Uvicorn `app` 入口、开发依赖兼容性调整和启动回归测试；不改变 API 路由、不调用真实模型、不实现 Task 4 或后续领域页面。
- Task 3 未把 uv 作为启动前置，也未提交 Python lockfile 或虚拟环境；前端依赖使用 pnpm workspace 与根 pnpm-lock.yaml。

## 已完成 Task 4 Session（committed）

- 2026-08-02-task-4-domain-models 已获用户设计审阅通过，正式实施计划已写入 `docs/superpowers/plans/2026-08-02-task-4-domain-models.md`，实现、独立复审和最终验证已完成，并已创建 focused commit。
- 目标是实现技术设计 §9 的严格领域模型、错误协议、验证报告和 §11 的显式状态机；实现顺序为共享基础、菜品字段、草稿/存档/导出与组合验证、状态机。
- 本阶段不实现 API、Repository、工作区持久化、模型调用、前端页面或 Mod 导出；uv 不是 Task 4 前置，不提交 Python lockfile 或虚拟环境。
- 已完成证据：Task 1–4 implementer/reviewer 串行执行；全量 `python -m pytest backend/tests -q -p no:cacheprovider` 通过；Ruff、mypy、`git diff --check`、生产旧枚举扫描和文档忽略检查通过。Task4 已验收并创建 focused commit；推送结果以 Git 核验为准。

- uv 是否必需已完成本地评估：uv 不在 PATH，但现有 Python/FastAPI 依赖、pytest（2 passed）、ruff、mypy 和直接 Python/Uvicorn health 均通过；因此 uv 不属于产品运行或发布媒介。

## 当前 Task 5 Session（committed）

- 2026-08-02-task-5-persistence 已获用户授权启动，当前状态为 committed；实现、两轮独立复审和自动验证已完成，focused commit 已创建，当前等待下一 Task 授权。本 Session 只处理本地工作区、原子 JSON 写入、领域 Repository、Asset Store 与短期回收站。
- Task5 消费 Task4 的领域记录，建立 %LOCALAPPDATA%\\PelicanTownSpecials\\workspace 的可恢复持久化边界；实体记录与资产内容是真实来源，索引只作为可重建加速层。
- 本 Session 不实现 API、Secret Store、模型调用、前端页面、Launcher、数据库或 Mod 编译；uv 不作为前置工具，不提交 Python lockfile 或虚拟环境。
- 设计说明与实施计划：docs/superpowers/specs/2026-08-02-task-5-persistence-design.md、docs/superpowers/plans/2026-08-02-task-5-persistence.md。
- 范围边界：本 Session 按 Task5 实施计划完成；正式技术设计中更完整的 WorkspaceRecord 字段、应用根 bootstrap、进程锁、更强迁移恢复和统一异常层未在本 Task 扩展，若要求纳入需另行收敛设计和实现。
- 验收证据：持久化测试 21 passed；领域+持久化回归 107 passed；完整后端回归 109 passed；Ruff、mypy、git diff --check 均通过。默认 pytest 临时目录曾出现 WinError 5，使用全新 C:\tmp basetemp 后测试通过。
- focused commit 已创建并推送到 origin/feat/mvp-implementation；Task5 已关闭.

## 已完成 Task 6 Session（committed）

- 2026-08-02-task-6-provider-settings 已获用户授权启动，设计说明和实施计划均已通过，自动验证已完成并通过用户验收，focused commit 已创建；本 Session 只处理用户级环境变量 Key、非机密 Provider Settings 和统一 ErrorEnvelope。
- 用户明确选择易用优先：应用直接新增、更新和删除当前 Windows 用户级 PTS_OPENAI_API_KEY，不要求用户手动配置环境变量；不写机器级变量，不实现 Credential Locker 作为默认持久化路径。
- Task6 设计说明：docs/superpowers/specs/2026-08-02-task-6-provider-settings-design.md；实施计划：docs/superpowers/plans/2026-08-02-task-6-provider-settings.md。
- 已实现文件：backend/src/pelican_town_specials/persistence/secret_store.py、application/settings.py、api/routes/settings.py、api/error_handlers.py，以及 api/app.py/config.py；对应 persistence/application/api 测试已补齐。
- 本 Session 不实现真实模型调用、Launcher、会话安全、CSRF、前端设置页面、数据库或 Mod 编译。
- 验收证据：全量 backend/tests 通过（152 passed）；Ruff、mypy、git diff --check 通过；依赖与敏感配置扫描无 keyring、setx、机器级环境变量或 Credential Locker 实现；生产 create_app 装配与 API 脱敏集成测试通过。
- focused commit：feat: configure provider settings and environment secrets；已推送到 origin/feat/mvp-implementation。

## 上一已关闭维护 Session 范围

- 更新 AGENTS.md，纠正已完成 Task 2 与当前无活动产品 Session 的状态，并明确开发工具不等于产品功能。
- 同步 README.md 与 docs/development/README.md 的当前状态说明。
- 移除仓库中的 uv 专属依赖 lockfile backend/uv.lock；保留 backend/pyproject.toml 的依赖/构建声明与 .gitignore 的通用 .venv/保护规则。
- 不修改业务实现、不启动 Task 3、不做真实模型调用；该 Session 已在 c4cedf0 提交并推送。

## 已完成 Task 2 的验收证据

- [x] uv sync --project backend --all-groups 成功，生成 backend/uv.lock 无冲突（CPython 3.13.14）。
- [x] health 测试先确认失败（红：ModuleNotFoundError），实现后通过（绿：1 passed）。
- [x] ruff check backend 与 mypy backend/src 通过（0 issues，strict 亦验证通过）。
- [x] frontend/openapi.json 含 /api/v1/health 与 HealthResponse（camelCase apiVersion）。
- [x] Review Subagent 规格符合性与代码质量检查通过（PASS）。
- [x] 用户已验收 verification 结果，并允许创建 focused commit。
- [x] 已创建一个 focused commit（feat: add FastAPI application shell）并推送 feat/mvp-implementation。

## 上一轮控制面维护检查

- [x] 未发现 backend/.venv、backend/venv 或 backend/virtualenv 目录。
- [x] 保留 backend/pyproject.toml 的后端依赖、构建和工具声明；未删除运行所需的 FastAPI/Uvicorn 等依赖。
- [x] 未修改业务源代码、测试或 OpenAPI 契约。
- [x] 已保留 Task 2 的 uv 历史执行证据；当前文档已将 uv 定位为可选开发便利，不作为产品运行、用户部署或产品 Task 前置。
- [x] 用户已明确验收本次控制面维护，并授权随后推送。
- [x] Task 3 与后端启动闭环已验收，统一纳入 `feat: add React application shell` 的 amend/push。

## Task 3 与本地启动闭环设计与验收边界

- 输入：现有 frontend/openapi.json，其中已冻结 GET /api/v1/health 与 HealthResponse。
- 产出：frontend/package.json、Vite/TypeScript 配置、React 入口与 Providers、apiClient、生成的 schema.d.ts、PRODUCT_COPY 和首屏测试；同时提供标准 Uvicorn `app` 入口、开发依赖兼容性配置和启动回归测试；构建产物为 frontend/dist。
- 首屏只显示正式中文产品名“鹈鹕镇新菜单”和主宣传语“把你做的菜，写进鹈鹕镇的下一张菜单。”；启动入口通过 typed client 发起 same-origin health probe。
- 不包含领域页面、草稿/收集品生命周期、真实模型调用、Mod 导出、认证会话或 Task 4+ 接口。
- [x] `pnpm install --frozen-lockfile`、`pnpm --dir frontend contract:generate`、`pnpm --dir frontend test:run`（1 file / 1 test）、`pnpm --dir frontend lint` 和 `pnpm --dir frontend build` 均通过。
- [x] `python -m pytest backend/tests -q` 通过（2 passed）；`pwsh -File scripts/verify_local_docs_ignored.ps1` 和 `git diff --check` 通过。
- [x] `python -m ruff check backend`、`python -m mypy backend/src`、Uvicorn 直连 health 和 Vite 代理 health 均通过；两端返回 `status=ok`、`app=PelicanTownSpecials`、`apiVersion=v1`。
- [x] 用户手动启动 Vite 与后端，确认首页显示以及 Network 中 `/api/v1/health` 返回 200；这补充了真实运行时联调证据。
- [x] amend 范围为前端文件、pnpm workspace/lockfile、后端标准 ASGI 启动入口、开发依赖、回归测试和两份 Task 3/启动控制面记录；不包含 Python lockfile 或虚拟环境。
- 已知限制：受限执行器曾对 Node 子进程报告 `spawn EPERM`；在真实 Windows 权限下的用户手动启动与浏览器联调已通过，不影响 Task 3 验收。

## 状态规则

修改型 Session 只能按以下顺序推进：

    planned → active → verification → awaiting_user_acceptance → accepted → committed

任何状态冲突、脏工作树、重复活动 Session 或缺失下一步都必须停下并报告。Session 历史见 docs/development/sessions/，不能用历史记录覆盖本文件的当前结论。
