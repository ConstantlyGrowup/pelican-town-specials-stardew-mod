# Session｜Milestone 7 Task 25 Bilingual UI and Settings locale

| 字段 | 值 |
|---|---|
| session_id | `2026-08-10-milestone-7-task-25-bilingual-ui` |
| session_type | `milestone-7-task-25-implementation` |
| status | `auto_accepted`（round-1 Codex PASS，本地 focused commit，不 push） |
| owner | Codex 主会话（Claude Code 主会话实施 + Codex 独立审阅） |
| started_at | `2026-08-10` |
| user_acceptance | `pending`（Milestone 7 全量验收时统一） |
| base_commit | `529981a feat: add GitHub Release auto-publish workflow (tag/manual, checksum, notes)` |
| acceptance_contract_id | `mvp-m7-task-25-i18n-v1` |

## 任务范围

按 `docs/plans/2026-08-10-milestone-7-refine.md` Task 25：把当前中文 copy 体系整理为
typed zh-CN / en-US catalog，设置页提供语言切换控件；默认 `zh-CN`，切换立即更新整个
用户界面并在刷新后保持；新建草稿发送当前 locale；静态 copy gate 阻止重新引入
`PRODUCT_COPY.zh` 直读与散落用户文案。**不实现 Task 26 的双语生成与图像 prompt。**

Context Packet：`docs/plans/2026-08-10-task-25-bilingual-ui-packet.md`（gitignored），
`planning_status: READY_FOR_IMPLEMENTATION`，4 条 planning_rulings，acceptance_ledger
M7-T25-I18N-001..005，`revise_round: 0`。

## 规划裁决（包工冻结，实施时全部应用）

- **M7-D03 / R-01（locale 默认与存储）**：默认 `zh-CN`，语言偏好存 `localStorage` key
  `pts-locale`；首次访问、非法值与清空值回退 `zh-CN`。
- **R-02（模块级文案）**：`providerForm.ts` 改 `createProviderFormSchema(copy)` 工厂；
  `generationStore.ts` 的 fallback 错误文案参数化（`GenerationFallbackMessages`），
  `useGeneration` 用 `useCopy()` 注入当前 locale。
- **R-03（copy gate）**：`scripts/check_frontend_locale.py` 全 src 禁 `PRODUCT_COPY`
  令牌；`features/components/app` 目录（排除 `.test.*`）禁止直接 import `i18n/copy`
  模块与散落 CJK/全角字符（`/assets/game/` 资源路径行豁免）。
- **R-04（数据语言不随 UI 改写）**：Pack/Cookbook 默认文案来源来自 catalog（挂载时
  `useCopy()`），用户编辑不被 locale 切换覆盖；`ExportSpec.language` 保持 `zh-CN`
  不变（内容包语言属 Task 26）；新建草稿 POST `language` = 当前 locale，已有草稿/
  归档记录的 `source.language` 与数据不因 UI 切换改写。

## 实现

- **`frontend/src/i18n/copy.ts`（重写）**：typed 双语 catalog。导出 `LOCALE_STORAGE_KEY`
  （`pts-locale`）、`SUPPORTED_LOCALES`、`Language`、`DEFAULT_LOCALE`（`zh-CN`）、
  `isLanguage()`、`catalogs: Record<Language, Copy>`，`Copy` 类型派生自 zh 目录。
  约 160 个文案键；插值占位符（`{name}`/`{count}`/`{category}`/`{zh}`/`{en}` 等）用
  `.replace()` 填充。不再导出 `PRODUCT_COPY` 常量。
- **`frontend/src/i18n/locale.tsx`（新建）**：`LocaleProvider`/`useLocale`/`useCopy`
  + `useSetLocale`。`LocaleContext` 默认值为 `{locale: zh-CN, setLocale: noop}`，
  裸渲染（无 Provider 的测试）安全落到 zh-CN；`readStoredLocale()` try/catch 读取
  localStorage；`useEffect` 同步 `document.documentElement.lang`；`setLocale` 持久化
  到 localStorage。
- **设置页语言切换**：`SettingsPage.tsx` 新增 LANGUAGE 区块，`role="radiogroup"` +
  radio 按钮（`aria-checked`/`aria-label`），箭头键/Home/End 导航包裹循环；语言名
  （中文/English）按自身语言显示（`copy.languageChinese`/`copy.languageEnglish`）。
- **全部页面/组件 useCopy 化**：`AppShell`、`router`、`PixelModal`、`DownloadableImage`、
  `DishSlot`、`HomePage`（含 `formatUpdatedAt(locale)`）、`CreateDishPage`
  （POST `language: locale`）、`PackMenuPage`、`BringInGamePage`、`ValidationIssues`、
  `GenerationProgress`、`GenerationError`、`CookbookPage`、`CookbookDetailPage`、
  `AskGusReviewPage`、`BlueprintEditorPage`、`pickers`（双语食材名模板）。散落
  CJK/全角（`：`/`；`/`（）`/`＋`）全部收编进 catalog，用模板键
  （`draftSubtitleLine`/`blueprintSubtitleLine`/`ingredientRowLabel`/`tagJoiner`/
  `categoryChipLabel`/`draftTerminalStatusLine`）表达。
- **copy gate**：`scripts/check_frontend_locale.py`（PRODUCT_COPY 令牌 / `i18n/copy`
  直 import / 散落 CJK+全角三规则）+ `tests/repo/test_frontend_locale.py`（4 条）+ 
  `.github/workflows/build.yml` 新增 `Frontend locale gate` 步骤。
- **测试**：`frontend/src/i18n/locale.test.tsx`（6 条：默认 zh、非法回退、清空回退、
  持久化恢复、切换持久化+立即生效、`document.lang` 同步）；`SettingsPage.test.tsx`
  新增语言切换 3 条；`CreateDishPage.test.tsx` 新增当前 locale 作为草稿语言 1 条 +
  既有用例补 `body.language === "zh-CN"` 断言；13 个测试文件 `PRODUCT_COPY.zh` →
  `catalogs["zh-CN"]`。

## 验证

- 前端 Vitest：**19 files / 116 passed**（含新增 6+3+1 条 + round-1 新增 roving-focus 1 条）。
- ESLint：clean。
- `pnpm build`（tsc --noEmit + Vite production build）：clean。
- `python scripts/check_frontend_locale.py`：`OK: frontend copy stays in the typed catalog.`
- 全量 backend + repo + integration：**690 passed / 2 skipped**（`python -m pytest
  backend/tests tests/repo tests/integration -q -p no:cacheprovider`）。
- `tests/repo/test_frontend_locale.py` gate 测试本身：32 passed（含 4 条 gate 用例）。

## 审阅

### round 0（Codex gpt-5.6-luna / max，新 thread）→ `REVISE`（3 项 MUST_FIX）

- **I18N-003**：剩余用户可见英文直写（eyebrows、field-counters、export-stamps、
  raw `draft.status`、raw `issue.severity`、`alt="Gus"`、`aria-label="mode"`）未进
  catalog，en-US 下破坏「页面不出现中英混杂」合同。
- **I18N-001**：瞬态错误/状态消息以渲染字符串存入 `useState`，locale 切换不重本地化。
- **I18N-004**：Settings radiogroup 箭头键导航未实现 roving tabIndex + `focus()`。

三项均有可复现证据（file:line），属冻结验收合同内，进入 round 1。

### round 1 修复（本次）

- **I18N-003**：`copy.ts` 双目录新增约 36 键（eyebrows / counters / stamps / 状态地图
  复用 `draftStatusLabels`、`exportStatusLabels`、`validationSeverityLabels`）；
  全部页面/组件（Home、Create、AskGusReview、BlueprintEditor、PackMenu、
  BringInGame、CookbookDetail、Cookbook、PixelModal、ValidationIssues）改从
  catalog 渲染。grep 扫描确认无残留 raw eyebrow/field-counter/export-stamp/
  detail-badge、raw `{draft.status}`、raw `{issue.severity}`、`alt="Gus"`、
  `aria-label="mode"`、`set*Error(copy.*)`。
- **I18N-001**：`SettingsPage`/`CreateDishPage`/`AskGusReviewPage`/
  `BlueprintEditorPage`/`PackMenuPage`/`BringInGamePage`/`CookbookDetailPage`
  的瞬态消息 state 改为 catalog key 联合类型，渲染点 `{copy[key]}`。
- **I18N-004**：`SettingsPage.tsx` `radioRefs` + `onLocaleKeyDown` 调用
  `radioRefs.current[nextIndex]?.focus()`；radio 按钮 `tabIndex={selected ? 0 : -1}` +
  ref 回调；`SettingsPage.test.tsx` 新增 `document.activeElement` 断言用例。

### round 1（Codex gpt-5.6-luna / max，新 thread）→ `PASS`

- 仅核验 round-0 三项修复及回归（REVIEW_PROTOCOL §4 封闭范围）。
- `must_fix: []`；`scope_delta: none`；`planning_rulings_checked: [M7-D03/R-01..R-04]`。
- 1 条 OPTIONAL_HARDENING：Settings 字段级校验消息在校验时本地化，若错误留存期间
  切换 locale 不会重渲染——非阻塞，记录不改。

PASS → `auto_accepted` → 本地 focused commit（不 push）→ Task 26。

## 范围说明

- 未实现 Task 26（双语生成与图像 prompt）；`ExportSpec.language` 保持 `zh-CN`。
- 未改后端/API/Mod 协议/持久化 schema；未新增服务端用户偏好 API。
- 未自动翻译既有草稿、归档记录、Cookbook 图片或历史生成结果；切换 UI 语言不触发
  provider 调用、不改写旧数据。
- 默认语言名按自身语言展示（中文/English），不受当前 locale 影响。
