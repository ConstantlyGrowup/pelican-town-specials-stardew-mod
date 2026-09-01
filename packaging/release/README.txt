鹈鹕镇新菜单 · Pelican Town Specials
=====================================

感谢使用「鹈鹕镇新菜单」！这是一个本地运行、为《星露谷物语》生成自定义食谱
内容包的桌面工具。

当前发布版本：v1.5.2

v1.5.2 / 报错信息本地化补丁
---------------------------

- 英文界面的生成报错信息（蓝图、问问 Gus 与系统级生成错误）现在会显示英文提示。
- 中文界面保持原有提示内容不变。
- 可先使用公共试用，也可以在「设置」页配置个人服务。

安装与启动
----------

推荐使用安装程序：双击 `PelicanTownSpecials-Setup-v1.5.2.exe` 完成安装。
- 应用安装到 `%LOCALAPPDATA%\Programs\PelicanTownSpecials`，无需管理员权限，
  不需要 Python、Node.js 或 Git。
- 安装会在开始菜单创建「Pelican Town Specials」快捷方式（可选择创建桌面快捷方式）。
- 也可以在「设置 → 应用」中卸载，或运行安装目录下的 `unins000.exe`。

也可使用便携版：解压 ZIP 到你选择的文件夹（例如 `C:\PelicanTownSpecials`），
双击 `PelicanTownSpecials.exe`。

启动后：
1. 应用会打开浏览器进入本地界面。首次启动会自动创建默认工作区（位于
   应用数据目录 `%LOCALAPPDATA%\PelicanTownSpecials` 下）。
   - 若浏览器未自动打开，请访问界面中显示的本地地址。
2. 你可以先使用公共试用；如果要使用自己的额度或服务，也可以在「设置」页配置个人
   Provider API Key（保存到当前 Windows 用户环境变量 `PTS_OPENAI_API_KEY`，不会写入
   任何 JSON 或日志）。
3. 上传菜品照片，使用「问问 Gus」或「料理蓝图」生成食谱，加入「收集品」，
   然后「打包菜单」并「带进游戏」。

卸载说明
--------

- 卸载会删除程序文件和快捷方式，但**保留**你的工作区与用户数据
  （`%LOCALAPPDATA%\PelicanTownSpecials`），重新安装后数据仍在。
- 便携版直接删除解压文件夹即可；工作区数据同样位于
  `%LOCALAPPDATA%\PelicanTownSpecials`。

隐私说明
--------

- 应用完全本地运行；你的图片、Key 与工作区数据不会离开这台电脑。
- 只有你主动请求的 Provider 生成请求会联网；Key 只用于该请求的鉴权。
- 应用「设置」页可随时更新或删除已保存的 Key。

系统要求
--------

- Windows 10/11（64 位）。
- 游戏目标：Stardew Valley 1.6.15 + SMAPI + Content Patcher 2.9.0。

发布包内容
----------

- `PelicanTownSpecials.exe`：主程序（含内置 Python 运行时，无需安装 Python）。
- `frontend/dist/`：本地界面资源。
- `resources/`：星露谷原版食材目录。
- `pelican_town_specials/` 等目录：内置 Python 运行库与依赖（请勿删除或修改）。
  运行库文件直接位于本文件夹下，没有 `_internal/` 子目录。

故障排除
--------

- 若双击后浏览器未打开或界面异常，请删除应用数据目录
  `%LOCALAPPDATA%\PelicanTownSpecials` 下工作区 `app-state` 文件夹中的
  `launcher-error.log` 后重试，并查看该日志内容。

第三方许可请见 `THIRD_PARTY_NOTICES.txt`。
