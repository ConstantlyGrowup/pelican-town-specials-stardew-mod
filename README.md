# 鹈鹕镇新菜单 / Pelican Town Specials

把你做的菜，写进鹈鹕镇的下一张菜单。

**鹈鹕镇新菜单（Pelican Town Specials）** 是一个本地运行、为《星露谷物语》（Stardew Valley）生成自定义食谱内容包的桌面工具。上传一张菜品照片，选择创作模式，应用会为你设计玩法数值、生成图标与预览图，并把整道菜打包成 SMAPI + Content Patcher 内容包，让这道菜真正出现在鹈鹕镇的菜单上。

## 开始使用（普通用户）

本工具以 **Windows 发布包** 形式分发，不需要安装 Python 或 Node.js。

1. 解压发布包到你选择的文件夹（例如 `C:\PelicanTownSpecials`）。
2. 双击 `PelicanTownSpecials.exe`。应用会自动打开浏览器进入本地界面。
   - 首次启动会自动创建默认工作区（位于 `%LOCALAPPDATA%\PelicanTownSpecials\workspace`）。
   - 若浏览器未自动打开，请访问界面中显示的本地地址。
3. 进入「设置」配置自己的 Provider，或使用“不想配置，先试试效果”体验少量生成。

## 首次设置

1. 打开应用后进入「设置」页。
2. 填写你的 Provider 服务地址（Base URL）与文本 / 视觉 / 图像模型 ID。
3. 保存你的 API Key。Key 会写入当前 Windows 用户的用户环境变量（`PTS_OPENAI_API_KEY`），**不会**写入任何 JSON、日志或发布包。

如果暂时不会配置，可点击“**不想配置，先试试效果**”。应用会使用隐藏试用配置提供本机最多 2 次生成机会，不在页面回显试用服务地址、模型或 Key；以后保存自己的 Provider 参数或 Key 会自动退出试用。已经配置个人服务的用户有剩余试用次数时，也会优先使用试用额度。

## 两种创作模式

- **问问 Gus（Ask Gus）**：上传菜品照片，让模型分析照片并生成整套食谱（玩法数值、原料、Buff、图标与预览）。生成结果可「接受并加入收集品」、「完整重新生成」或「拒绝草稿」。生成中可随时取消；刷新或切换页面后仍会回到同一生成任务。
- **料理蓝图（Blueprint）**：从原始图片和基础模板开始创作。字段完全归你所有：设置名称、内部名称、分类、描述、标签与原料，再生成图标与预览。预览更新后才会允许进入下一步。

两种模式互相独立；收集品不会显示菜品的来源模式。

## Gus 的记忆与生成用时

当你正式保存过至少两道问问 Gus 的菜，之后遇到熟悉的菜品时，Gus 可能会更快认出它，并沿用已经确认过的菜品设定与像素图标；最终预览仍会根据这次上传的照片生成。问问 Gus 和料理蓝图的结果页都会显示本次生成用时。

## 收集品（Cookbook）

已接受的菜品进入「收集品」。收集品内容**不可编辑**，保持已验收时的数据不变。可从收集品列表进入详情页预览大图与像素图标（悬停预览图可点击「下载图片」）。

## 打包菜单（Pack the Menu）

1. 在「收集品」页勾选要打包的菜品。
2. 进入「打包菜单」，填写菜单名称、菜单标识与版本。
3. 点击「校验」确认无阻止性问题，再点击「打包菜单」。
4. 校验通过后即可下载 Content Patcher 内容包 ZIP。

## 带进游戏（Bring It In-Game）

1. 下载并安装 [SMAPI](https://smapi.io/)，然后安装 Content Patcher 2.9.0 或更新版本。
2. 把下载的 ZIP 解压到 Stardew Valley 的 `Mods` 目录，保持 `[CP]` 文件夹结构。
3. 使用 SMAPI 启动 Stardew Valley，等待内容加载完成。
4. 在 SMAPI 控制台查看 patch summary，确认菜品、配方与纹理已生效。
5. 在游戏里制作、取得并食用你的新菜——能量、生命、售价与 Buff 会按生成的数值生效。

## 隐私与 Key

- 应用在你自己的电脑上运行；草稿、收集品、导出记录与图片都保存在本机工作区。
- 只有你主动发起生成请求时，菜品照片与必要上下文才会被发送到你配置的 Provider 服务用于生成；
  Key 只用于该请求的鉴权，不会被写入任何本地 JSON、日志或诊断包。
- 应用「设置」页可随时更新或删除已保存的 Key。
- 新手试用使用项目方专用额度并受本机次数限制；主动删除应用数据可能重置本机计数，项目方同时在 Provider 控制台设置总消费上限。
- 诊断包只包含脱敏后的运行信息，不包含业务记录或密钥。

## 系统要求

- Windows 10 / 11（64 位）。
- 游戏目标：Stardew Valley 1.6.15 + SMAPI + Content Patcher 2.9.0。

## 开发环境

用于从源码构建与开发，普通用户不需要以下步骤。

**后端**

```powershell
python -m pip install --upgrade pip
cd backend
python -m pip install --group dev -e .
cd ..
python -m pytest backend/tests tests/repo tests/integration -q
python -m ruff check backend
python -m mypy backend/src
python -m uvicorn pelican_town_specials.api.app:app --port 8000
```

**前端**

```powershell
pnpm install --frozen-lockfile
pnpm --dir frontend contract:generate   # 从 backend OpenAPI 再生成类型
pnpm --dir frontend test:run
pnpm --dir frontend lint
pnpm --dir frontend build
pnpm --dir frontend dev                 # 开发服务器，代理 /api 到本机后端
```

## 测试

- 后端与仓库检查：`python -m pytest backend/tests tests/repo tests/integration -q`
- 前端单元测试：`pnpm --dir frontend test:run`
- Playwright 假流端到端（不调用真实 Provider）：`pnpm --dir frontend e2e`
- OpenAPI 契约漂移检查：`pwsh -File scripts/check_openapi_drift.ps1`
- 产品命名门禁：`python scripts/check_product_copy.py`
- 本地设计资料忽略检查：`pwsh -File scripts/verify_local_docs_ignored.ps1`

## Windows 构建

```powershell
pwsh -File scripts/build_windows.ps1     # 全门禁 + PyInstaller onedir
pwsh -File scripts/smoke_windows_bundle.ps1  # 启动 / health / 首页冒烟
```

发布包输出到 `dist/PelicanTownSpecials-windows-x64/`。

## 贡献

欢迎提交 issue 与 pull request。提交前请保证 `docs/development/REVIEW_PROTOCOL.md` 中的验收纪律与全部门禁通过；设计资料（`design docs/`、`docs/architecture/`、`docs/plans/` 等）不进入版本库。

第三方许可见发布包内的 `THIRD_PARTY_NOTICES.txt`。
