# 鹈鹕镇新菜单 · Pelican Town Specials

> 把你做的菜，写进鹈鹕镇的下一张菜单。

## 关于这个工具

如果你今天做了一道拿手菜，想让它出现在《星露谷物语》的厨房里 ——

**鹈鹕镇新菜单** 是一款在你电脑上运行的 Windows 桌面工具。**上传一张菜品照片，它会把你的菜变成游戏里的真实道具**：给它取个游戏里的名字、设计能量与生命恢复数值、画出像素图标和预览图，最后打包成一个能直接放进游戏的 Mod。

做出来的菜可以自己吃、送朋友，或者作为一份独特的礼物。

## 开始使用

工具已经做好了 Windows 安装包，**你不需要装任何 Python、Node.js 或其他开发工具**。

1. 打开最新的 [Release 页面](https://github.com/ConstantlyGrowup/pelican-town-specials-stardew-mod/releases/latest)，下载 `PelicanTownSpecials-Setup-vX.X.X.exe` 安装包。
2. 双击安装包，选一个你想安装到的文件夹（默认 `C:\Program Files\PelicanTownSpecials`），完成安装。
3. 双击桌面上的「鹈鹕镇新菜单」图标。第一次启动会自动打开浏览器，并创建本机工作区（位于 `%LOCALAPPDATA%\PelicanTownSpecials\workspace`）。

如果你不想走安装流程，也可以下载 `PelicanTownSpecials-windows-x64-vX.X.X.zip`，解压后双击里面的 `PelicanTownSpecials.exe` 即可。

## 首次设置

第一次打开应用，会直接进入「设置」页面（路径：模型路由 / Provider 参数）。在这里配置你的 AI 服务：

![首次设置 · Provider 参数](docs/screenshots/01-provider-settings.png)

几个必填项：

- **Base URL**：你的 API 服务地址。用 OpenAI 官方填 `https://api.openai.com/v1`；用中转站就填中转站文档里给你的地址。
- **API Key**：在上一步「密钥 / API Key」里粘贴你的 Key。
- **文本模型 ID 与视觉模型 ID**：负责理解文字与图片的模型。**官方和中转站都推荐 `gpt-5.6-luna`**。
- **图像模型 ID**：负责生成像素图标与预览图的模型。**官方和中转站都推荐 `gpt-image-2`**。

填完点底部「保存设置」即可。**网络能直接访问 OpenAI 官方 API 的用户，用官方配置就能开跑；用中转站的用户填中转站给的地址和同样的模型 ID 也可以**。

### 没配置过 API？也能试

页面上有一个「**不想配置，先试试效果**」按钮。点它，应用会用一套隐藏的试用配置让你**生成 2 次菜** —— 用来确认这个工具是不是你想要的那个东西。试用不消耗你的 Key、不暴露服务地址，足够感受完整流程。保存自己的设置会自动退出试用；以后想再次体验，可以重新点这个按钮。

> 试用限制：本机软限制 2 次。删除应用数据会重置计数；试用服务在 Provider 控制台也设了总消费上限作为硬兜底。

## 两种创作模式

上传一张菜品照片后，你会看到这一步：

![创建一道菜 · 选择模式](docs/screenshots/02-create-mode-picker.png)

两种创作模式并列入口，**没有谁优谁劣 —— 它们解决不同的问题**：

- **问问 Gus**：把决定权完全交给 AI。它会分析你的照片，决定菜名、原料、Buff、能量数值，并生成图标与预览。适合「我想看看 AI 怎么理解我的菜」。
- **料理蓝图**：把决定权完全交给你。你自己填名称、内部名称、分类、描述、标签与原料，AI 只负责生成像素图标和预览。适合「我已经知道这道菜该怎么设计」。

两种模式互不干扰 —— 一个草稿属于且只属于一种模式。收集品里也不会显示这道菜当时是用哪种模式做的。

### 1. 问问 Gus（Ask Gus）

> 风格：上传照片 +（可选）一句背景描述 → AI 决定一切 → 你拍板。

**怎么用：**

1. 在「创建一道菜」页选「问问 Gus」。
2. 可选：在补充说明里写一句话，比如「这是妈妈每年冬至都做的汤」。
3. 点「创建草稿 →」，进入审核页。

![问问 Gus · 生成进度](docs/screenshots/03-ask-gus-progress.png)

生成过程是分阶段的（识别菜品、匹配原料、整理数据、画预览等），任何时候点「取消生成」都可以安全退出；刷新或切页再回来，也不会丢失当前任务。

![问问 Gus · 审核结果](docs/screenshots/04-ask-gus-result.png)

结果页能看到三件事：

- 左侧是按你的照片生成的预览图，下方是 16×16 像素图标。
- 右侧是 AI 给这道菜取的名字、描述、原料、Buff 与数值。
- 右上角会显示本次生成用时。

三个操作：

- **接受并加入收集品**：这道菜就定型了，以后不能改。
- **完整重新生成**：整道菜从头重做（不是局部修改）。
- **拒绝草稿**：不要这道菜，丢掉草稿。

### 2. 料理蓝图（Blueprint）

> 风格：你填全部字段 → AI 只生成图标与预览 → 你随时改。

**怎么用：**

1. 在「创建一道菜」页选「料理蓝图」。
2. 点「创建草稿 →」，进入编辑页。

![料理蓝图 · 编辑器](docs/screenshots/05-blueprint-editor.png)

右侧是字段表单 —— **所有字段都归你决定**：

- 名称（玩家在游戏里看到的名字）
- 内部名称（3-48 字符，英文/数字/下划线，例如 `PumpkinSoup`）
- 分类（必须选一个）
- 描述（一两句话介绍）
- 标签（可选）
- 原料（至少一个）
- 饱腹度、售价、是否饮品

左侧是预览区。填完点「生成预览」让 AI 画图标与预览图；**修改字段后必须重新生成预览，否则程序会阻止你进入下一步**。

保存并定型后，这道菜也进入收集品，同样不可修改。

## 收集品（Cookbook）

你所有「已经定型」的菜都在这里 —— 问问 Gus 接受并存档的、料理蓝图保存并通过校验的。

![收集品 · 列表](docs/screenshots/06-cookbook-list.png)

收集品的几个特点：

- **不可编辑**：每道菜定型后保持原样。
- **不显示来源**：你不会看到这道菜当时是 Gus 做的还是你自己做的。
- 点击菜品卡片可以看到完整数据：

![收集品 · 详情](docs/screenshots/07-cookbook-detail.png)

收集品页底部有「打包菜单」按钮 —— 勾选几道菜后就可以打包成 Mod。

## 打包菜单（Pack the Menu）

当收集品里有你想要放进游戏的几道菜，就可以打包了。

![打包菜单 · 校验与打包](docs/screenshots/08-pack-menu.png)

**步骤：**

1. 在收集品页勾选你要打包的菜（底部会出现「打包菜单 →」按钮）。
2. 进入「打包菜单」页，左侧确认勾选的菜。
3. 右侧填三个信息：
   - **菜单名称**（在游戏里显示的名字）
   - **菜单标识（Pack Slug）**：3-48 字符、英文/数字开头、含连字符下划线，例如 `FamilyMenu`。
   - **版本**（默认 `1.0.0`）。
4. 点「校验」让程序检查有没有阻止性问题。
5. 校验通过后点「打包菜单 →」开始打包，下载得到的 ZIP 文件就是你的 Mod。

## 带进游戏（Bring It In-Game）

把刚刚得到的 Mod 装进游戏：

![带进游戏 · 下载页](docs/screenshots/09-bring-in-game-download.png)

**步骤：**

1. 下载并安装 [SMAPI](https://smapi.io/)。
2. 继续安装 Content Patcher **2.9.0 或更新版本**。
3. 点「下载 Mod ZIP」拿到你的 Mod 文件。
4. 把 ZIP **解压**到 Stardew Valley 的 `Mods` 文件夹，保持解压后的 `[CP]` 目录结构（注意是直接放进去，不要再套一层）。「打开导出文件夹」按钮可以帮你直接跳到这个目录。

![带进游戏 · Mods 文件夹](docs/screenshots/10-bring-in-game-mods-folder.png)

5. 使用 SMAPI 启动 Stardew Valley。等内容加载完成后，SMAPI 控制台会显示 patch summary —— 这是确认菜品、配方与纹理已生效的地方。
6. 进游戏制作、取得并食用你的新菜。能量、生命、售价与 Buff 会按生成时的数值生效。

![游戏内 · 物品 tooltip](docs/screenshots/11-in-game-tooltip.png)

## 隐私与 Key

- 应用在你自己的电脑上运行；草稿、收集品、导出记录和图片都保存在本机工作区。
- 只有你主动发起生成请求时，照片和必要上下文才会被发送到你配置的 Provider；Key 只用于该请求的鉴权，**不会被写入任何本地 JSON、日志或诊断包**。
- 「设置」页可随时更新或删除你的 Key。
- 新手试用使用项目方专用额度，受本机次数限制；删除应用数据可能重置计数。
- 诊断包只包含脱敏后的运行信息，不包含业务记录或密钥。

## 系统要求

- Windows 10 / 11（64 位）。
- Stardew Valley 1.6.15 + SMAPI + Content Patcher 2.9.0（带进游戏时需要）。

## 开发环境

> 供从源码构建与二次开发用，普通用户不需要看这一节。

### 后端

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

### 前端

```powershell
pnpm install --frozen-lockfile
pnpm --dir frontend contract:generate   # 从 backend OpenAPI 再生成类型
pnpm --dir frontend test:run
pnpm --dir frontend lint
pnpm --dir frontend build
pnpm --dir frontend dev                 # 开发服务器，代理 /api 到本机后端
```

### 测试与门禁

- 后端与仓库检查：`python -m pytest backend/tests tests/repo tests/integration -q`
- 前端单元测试：`pnpm --dir frontend test:run`
- Playwright 假流端到端（不调用真实 Provider）：`pnpm --dir frontend e2e`
- OpenAPI 契约漂移检查：`pwsh -File scripts/check_openapi_drift.ps1`
- 产品命名门禁：`python scripts/check_product_copy.py`
- 本地设计资料忽略检查：`pwsh -File scripts/verify_local_docs_ignored.ps1`

### Windows 构建

```powershell
pwsh -File scripts/build_windows.ps1         # 全门禁 + PyInstaller onedir
pwsh -File scripts/smoke_windows_bundle.ps1  # 启动 / health / 首页冒烟
pwsh -File scripts/build_installer.ps1       # Inno Setup 安装包
```

发布包输出到 `dist/PelicanTownSpecials-windows-x64/` 与 `dist/installer/`。

## 贡献

欢迎提交 issue 与 pull request。提交前请保证：

- 所有测试、ruff、mypy、OpenAPI drift 门禁通过。
- 产品命名遵循「鹈鹕镇新菜单 / Pelican Town Specials」与冻结的功能标签（问问 Gus / 料理蓝图 / 收集品 / 打包菜单 / 带进游戏）。
- 设计资料（`design docs/`、`docs/architecture/`、`docs/plans/` 等）不进入版本库。
- 提交信息描述项目变更，不添加 AI 助手署名。

第三方许可见发布包内的 `THIRD_PARTY_NOTICES.txt`。