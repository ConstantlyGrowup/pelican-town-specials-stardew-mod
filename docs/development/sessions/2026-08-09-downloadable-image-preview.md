# Session｜2026-08-09-downloadable-image-preview

| 字段 | 值 |
|---|---|
| `session_id` | `2026-08-09-downloadable-image-preview` |
| `session_type` | ui-fix |
| `state` | committed（2026-08-09 用户验收通过，创建本地 focused commit，未 push） |
| `date` | 2026-08-09 |
| `task` | 前端为已生成的草稿预览图 / 已接受的收集品详情预览图增加 hover 下载入口，替代右键另存为 |
| `acceptance_contract_id` | 无（用户直接要求的前端小功能，用户本人验收，不走 Codex 审阅） |
| `revise_round` | 0 |
| `base_commit` | `f38f810`（docs-conflict-sync 控制面提交之后） |

## 任务范围

草稿（料理蓝图编辑页、Ask Gus 审核页）与收集品详情页三处的**预览大图**：
鼠标 hover 图片时右上角浮现小「下载」按钮，点击直接下载图片到本地，无需右键另存为。

## 实施（commit `4fe7eca`，7 文件 +211/-3）

- `frontend/src/components/DownloadableImage.tsx`（新增）：复用组件——包裹 `<img>`，
  hover/focus 时浮现圆形下载按钮；点击 fetch 图片字节 → 探测 MIME 决定扩展名
  （PNG/JPEG/WebP）→ 以 `{名称}-预览.<ext>` 下载。组件内做文件名净化与
  `revokeObjectURL` 延迟回收。
- `frontend/src/features/draft/BlueprintEditorPage.tsx`：预览图替换为 `DownloadableImage`。
- `frontend/src/features/draft/AskGusReviewPage.tsx`：同上。
- `frontend/src/features/cookbook/CookbookDetailPage.tsx`：同上。
- `frontend/src/i18n/copy.ts`：新增 `downloadImage: "下载图片"`。
- `frontend/src/styles/global.css`：`.downloadable-image` hover 浮现样式（默认透明，
  hover/focus-visible 显示）。
- `frontend/src/components/DownloadableImage.test.tsx`（新增）：聚焦测试 2 条。

## 验证证据

- 定向测试（组件 + 3 个受影响页面）：**38 passed**。
- 全量前端：**94 passed**（15 文件，新增组件测试文件）；`tsc --noEmit` clean；
  eslint（改动文件）clean。
- 发布包已同步：`pnpm --dir frontend build` 重建（`index-CgjeyN3b.js` /
  `index-BRK6cF7u.css`），清空并替换 `dist/PelicanTownSpecials-windows-x64/frontend/dist/`，
  已验证 bundle 含 `下载图片` 文案、`revokeObjectURL` 逻辑与按钮样式；PyInstaller
  onedir 从磁盘读静态资源，无需重打 exe 包。

## 范围说明

下载入口只加在「预览大图」上；32px 像素图标未加（非预览且尺寸过小）。如需图标也可
下载，属后续追加项。

## 用户验收结果（2026-08-09）

| 项 | 结果 | 说明 |
|---|---|---|
| 草稿预览图 hover 下载 | **通过** | 蓝图编辑页 / Ask Gus 审核页预览图右上角浮现下载按钮，点击下载 |
| 收集品详情预览图 hover 下载 | **通过** | 同上 |

用户验收通过，授权提交并更新相关文档；本轮未授权 push。`frontend/dist` 与 `dist/`
均为 gitignored 产物，不进提交。

## 遗留

无。
