# Session｜2026-08-08-nav-home-entry

| 字段 | 值 |
|---|---|
| `session_id` | `2026-08-08-nav-home-entry` |
| `session_type` | ui-fix |
| `state` | committed（2026-08-08 用户验收通过，创建本地 focused commit 并同步推送远端） |
| `date` | 2026-08-08 |
| `task` | 导航栏新增「首页」入口，使用户在任意页面可直接回到草稿首页，无需改 URL |
| `acceptance_contract_id` | 无（用户直接要求的前端小改动，用户本人验收，不走 Codex 审阅） |
| `revise_round` | 0 |
| `base_commit` | `0ffad8b`（Milestone 4+5+5.1 统一 push 之后） |

## 任务范围

用户反馈：主导航栏只有「创建 / 收集品 / 设置」，进入这些页面后无法跳回首页（草稿仪表盘），只能手动改 URL。
要求在最左侧新增首页入口，指向 `/`。

## 实施（commit `26c3044`，3 文件 +8/-0）

- `frontend/src/i18n/copy.ts`：新增 `home: "首页"` 文案。
- `frontend/src/app/layout/AppShell.tsx`：导航栏最前新增 `<NavLink to="/" end>`。`end` 为必要项——
  `to="/"` 默认匹配所有以 `/` 开头的路由，会导致首页链接在任意页面都处于高亮态。
- `frontend/src/app/router.test.tsx`：首页路由测试补一条断言，验证「首页」链接指向 `/`。

## 验证证据

- 定向测试（`router.test.tsx` + `App.test.tsx`）：8 passed。
- 全量前端：**92 passed**（14 文件）；`tsc --noEmit` clean；eslint（改动 3 文件）clean。

## 首次验收失败与重建（重要）

初轮通知用户复验时**验收不通过**——用户贴出的运行时导航栏 HTML 里没有「首页」。根因：
前端源码改动未重新构建，用户运行的发布包（`dist/PelicanTownSpecials-windows-x64/PelicanTownSpecials.exe`）
在运行时从 **exe 旁的 `frontend/dist`**（`_default_static_dir` frozen 分支）读取静态资源，那里仍是旧构建。

修复：
- `pnpm --dir frontend build` 重建 `frontend/dist`（新 bundle `index-BlryVRxK.js`，已验证含「首页」）；
- 清掉打包目录旧 `assets`，把新 `index.html` + `assets` 同步进
  `dist/PelicanTownSpecials-windows-x64/frontend/dist/`；
- PyInstaller onedir 模式下静态资源从磁盘读取、不嵌入 exe，故**无需重打 exe 包**。

## 用户复验结果（2026-08-08）

| 项 | 结果 | 说明 |
|---|---|---|
| 导航栏含「首页」 | **通过** | 重新启动发布包后，创建/收集品/设置任意页面最左侧出现「首页」，点击回到草稿列表 |

用户验收通过，授权提交并同步推送远端。`frontend/dist` 与 `dist/` 均为 gitignored 产物，不进提交。

## 遗留

无。
