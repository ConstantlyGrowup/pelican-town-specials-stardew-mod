# 鹈鹕镇新菜单 · Pelican Town Specials

[简体中文](README.md) | [English](README.en.md)

> 把你做的菜，写进鹈鹕镇的下一张菜单。

上传一张现实中的菜品照片，鹈鹕镇新菜单会把它变成《星露谷物语》里的新食物：菜名、描述、原料、数值、像素图标和预览图都准备好后，还能直接打包成 Content Patcher Mod。

整个工具在 Windows 本机运行。普通用户下载后即可使用，不需要安装 Python、Node.js 或其他开发环境。

## 下载与启动

前往 [Releases](https://github.com/ConstantlyGrowup/pelican-town-specials-stardew-mod/releases/latest)，选择一种方式：

- 下载 `PelicanTownSpecials-Setup-vX.X.X.exe`，按提示完成安装，然后从桌面快捷方式启动；
- 或下载 `PelicanTownSpecials-windows-x64-vX.X.X.zip`，解压后双击 `PelicanTownSpecials.exe`。

启动后，应用会自动打开浏览器。你的草稿、收集品、图片和导出记录会保存在本机工作区：

```text
%LOCALAPPDATA%\PelicanTownSpecials\workspace
```

## 先试用，或配置自己的 AI 服务

如果暂时不熟悉 API，可以在设置页点击「**不想配置，先试试效果**」。公共试用提供 2 次完整生成机会；只有生成完整成功才会扣除次数，结果页会显示剩余次数。

如果试用服务暂时不可用，可以直接重试，也可以切换到自己的服务继续，不会因此失去本次试用机会。

准备使用自己的服务时，打开「设置」，填写：

- **Base URL**：OpenAI 官方地址为 `https://api.openai.com/v1`；使用中转站时，以对方提供的地址为准；
- **API Key**：对应服务提供的密钥；
- **文本模型 ID、视觉模型 ID、图像模型 ID**：填写你的服务实际支持的模型名称。

例如，项目已验证过下面这组 OpenAI 官方配置：

```text
Base URL:     https://api.openai.com/v1
文本模型:     gpt-5.6
视觉模型:     gpt-5.6
图像模型:     gpt-image-2
```

不同服务支持的模型可能不同。如果你使用中转站，请直接采用中转站文档中的模型 ID。

![设置 AI 服务](docs/screenshots/01-provider-settings.png)

## 创建一道菜

上传照片后，可以选择「问问 Gus」或「料理蓝图」。两种模式都会生成像素图标和完整预览，但决定菜品内容的人不同。

![选择创作模式](docs/screenshots/02-create-mode-picker.png)

### 问问 Gus

适合想看看 Gus 会怎样理解这道菜的人。

1. 上传照片；
2. 可以补充一句背景，例如“这是妈妈每年冬至都会做的汤”；
3. 开始生成，等待 Gus 完成菜品分析、游戏化设计和视觉制作。

![问问 Gus 生成过程](docs/screenshots/03-ask-gus-progress.png)

生成完成后，你可以：

- **接受并加入收集品**：保存当前结果；
- **完整重新生成**：从头生成一套新结果；
- **拒绝草稿**：放弃这次创作。

![问问 Gus 结果](docs/screenshots/04-ask-gus-result.png)

生成任务由后端持续运行。刷新页面或暂时切到其他页面后，再回来仍能看到同一任务的进度。应用最多同时运行 3 个生成任务；达到上限时，等其中一个结束后再试即可。

### 料理蓝图

适合已经知道菜品应该叫什么、使用哪些原料和数值的人。

你可以自己填写名称、内部名称、分类、描述、标签、原料、恢复值、售价和饮品类型，再让 AI 根据这些信息和原图生成像素图标与预览图。

![料理蓝图编辑器](docs/screenshots/05-blueprint-editor.png)

修改菜品字段后，需要重新生成一次预览，让画面和最新内容保持一致。确认保存后，这道菜会进入收集品。

## 收集品

保存完成的菜都会出现在「收集品」中。

![收集品列表](docs/screenshots/06-cookbook-list.png)

点击菜品可以查看完整信息。已经进入收集品的菜品会保持定型；如果想尝试另一套设计，可以重新创建一份草稿。

![收集品详情](docs/screenshots/07-cookbook-detail.png)

## 打包菜单

想把菜品带进游戏时，在收集品中勾选一道或多道菜，然后点击「打包菜单」。

![打包菜单](docs/screenshots/08-pack-menu.png)

填写菜单名称、菜单标识和版本号，先运行校验，再开始打包。完成后会得到一个 Mod ZIP。

菜单标识使用英文字母、数字、连字符或下划线，例如：

```text
FamilyMenu
pelican-specials
```

## 带进游戏

开始前，请先安装：

- [SMAPI](https://smapi.io/)
- Content Patcher 2.9.0 或更新版本

然后按下面的步骤操作：

1. 下载刚刚生成的 Mod ZIP；
2. 将 ZIP 解压到 Stardew Valley 的 `Mods` 文件夹；
3. 确认解压后的 `[CP]` 文件夹直接位于 `Mods` 下，没有多套一层文件夹；
4. 通过 SMAPI 启动游戏。

![下载 Mod](docs/screenshots/09-bring-in-game-download.png)

![Mods 文件夹示例](docs/screenshots/10-bring-in-game-mods-folder.png)

进入游戏后，就可以制作、取得和食用自己的新菜品。能量、生命、售价和 Buff 会按照生成时保存的数值生效。

![游戏内物品效果](docs/screenshots/11-in-game-tooltip.png)

## 常见问题

### 生成失败会扣掉试用次数吗？

不会。只有整次生成完整完成后，试用次数才会减少。

### 公共试用暂时不可用怎么办？

可以直接重试，也可以前往设置配置自己的服务。已经配置个人服务的用户，可以在错误提示中切换后继续当前创作。

### 刷新页面会中断生成吗？

不会。重新打开草稿后，可以继续查看原任务的进度。

### 为什么料理蓝图提示预览需要更新？

因为菜名、原料或数值已经发生变化。重新生成预览后，就可以继续保存。

### API Key 保存在哪里？

Key 保存在当前 Windows 用户的环境变量 `PTS_OPENAI_API_KEY` 中，不会写入草稿、日志或诊断包。你可以随时在设置页更新或删除它。

### 支持哪些系统？

当前桌面版本支持 Windows 10 / 11 64 位。macOS 和 Linux 暂无本地安装包。

## 反馈问题

遇到问题时，可以在 [GitHub Issues](https://github.com/ConstantlyGrowup/pelican-town-specials-stardew-mod/issues) 中说明：

- 你正在进行哪一步；
- 页面显示的错误码或提示；
- 是否能够在设置页生成诊断包。

请不要公开粘贴 API Key。

第三方许可见发布包内的 `THIRD_PARTY_NOTICES.txt`。
