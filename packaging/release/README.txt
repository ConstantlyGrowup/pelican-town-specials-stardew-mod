鹈鹕镇新菜单 · Pelican Town Specials
=====================================

感谢使用「鹈鹕镇新菜单」！这是一个本地运行、为《星露谷物语》生成自定义食谱
内容包的桌面工具。

开始使用
--------

1. 解压本发布包到你选择的文件夹（例如 `C:\PelicanTownSpecials`）。
2. 双击 `PelicanTownSpecials.exe`。应用会打开浏览器进入本地界面。
   - 首次启动会自动创建默认工作区（位于
     `%LOCALAPPDATA%\PelicanTownSpecials\workspace`）。
   - 若浏览器未自动打开，请访问界面中显示的本地地址。
3. 在「设置」页填入你的 Provider API Key（保存到当前 Windows 用户环境变量
   `PTS_OPENAI_API_KEY`，不会写入任何 JSON 或日志）。
4. 上传菜品照片，使用「问问 Gus」或「料理蓝图」生成食谱，加入「收集品」，
   然后「打包菜单」并「带进游戏」。

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

- 若双击后浏览器未打开或界面异常，请删除
  `%LOCALAPPDATA%\PelicanTownSpecials\workspace\app-state` 下的
  `launcher-error.log` 后重试，并查看该日志内容。
- 卸载：直接删除本文件夹即可；工作区数据位于 `%LOCALAPPDATA%\PelicanTownSpecials`。

第三方许可请见 `THIRD_PARTY_NOTICES.txt`。
