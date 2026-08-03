# Pelican Town Specials｜开发约束

本文是开发控制面的项目约束摘要。它不替代正式技术设计；如果摘要与用户后来确认的设计不一致，先停止当前 Session，报告冲突并同步正式设计、实施计划和项目索引。

## 权威文档

| 文档 | 权威范围 |
|---|---|
| `docs/architecture/MVP_TECHNICAL_DESIGN.md` v1.2 | MVP 运行形态、模块、数据模型、API、工作流、错误处理、Mod 编译协议和 Yibu API probe 结论 |
| `docs/plans/MVP_IMPLEMENTATION_PLAN.md` v0.5 | 文件、依赖、Task、测试、人工验证、里程碑和提交边界，以及 Yibu 证据如何进入 Task 11 |
| `StarValleyCook_项目设计源索引与状态快照.md` | 设计源索引、产品命名、阶段状态和文档同步线索；保持 ignored |
| `docs/development/STATUS.md` | 当前开发 Session、工作树事实、阻塞和下一步；是开发状态唯一真源 |
| `docs/development/sessions/` | 每个 Session 的追加式历史证据 |

## 产品与技术冻结项

- 中文正式名：`鹈鹕镇新菜单`；英文正式名：`Pelican Town Specials`。
- 功能命名：`问问 Gus / Ask Gus`、`料理蓝图 / Blueprint Mode`、`收集品 / Cookbook`、`打包菜单 / Pack the Menu`、`带进游戏 / Bring It In-Game`。
- 仓库：`pelican-town-specials-stardew-mod`；应用 Slug：`pelican-town-specials`；代码名：`PelicanTownSpecials`；环境变量前缀：`PTS_`。
- MVP 采用 Windows 本地 Web、React + TypeScript + Vite、FastAPI + Pydantic、PyInstaller onedir、JSON 工作区和 OpenAI-compatible gateway。
- 用户发布媒介冻结为 PyInstaller onedir：发布包自带 Python 运行时与依赖，普通用户不安装 uv、Python、Node.js 或包管理器。开发态使用 backend/pyproject.toml 和当前 Python 环境；uv 仅为可选开发便利，不作为产品或功能 Task 的依赖。
- 默认工作区为 `%LOCALAPPDATA%\\PelicanTownSpecials\\workspace`；浏览器不直接访问任意本地文件路径。
- 为降低小白用户配置门槛，应用维护当前 Windows 用户级环境变量 PTS_OPENAI_API_KEY；支持新增、更新和删除，不写机器级环境变量，不要求管理员权限。Key 不得进入 JSON、日志、错误正文、前端状态、测试快照、Context Packet 或 Git。
- MVP 使用同步请求和 NDJSON 阶段事件；不提前引入数据库、登录、队列、全局 Registry 或跨用户缓存。
- 问问 Gus 使用完整原子重生成；料理蓝图只复用原始图片和基础模板；收集品不可编辑且不暴露来源模式。
- Mod 目标为 Stardew Valley 1.6.15、Content Patcher 2.9.0、纯 JSON/PNG 内容包；本地 Mods 路径只从 `PTS_STARDEW_MODS_DIR` 获取。
- `AuthorName` 在工作区首次创建时生成并持久化为 `D<YYYYMMDD>`；第三期重新讨论身份策略。

## Yibu API 用户实测记录

2026-08-01 下午，用户报告已经通过本地调用案例成功走通 Yibu API 核心链路。当前只把它作为 Provider Adapter 的真实能力证据，不把它视为 MVP 已启动或最终模型选择：

- Base URL 候选：`https://yibuapi.com/v1`；鉴权使用 Bearer API Key。
- 文本/视觉候选：OpenAI-compatible `POST /chat/completions`，请求携带多模态 `image_url` data URL；案例使用 `gpt-5.6-luna` 和 `reasoning_effort=high`。
- 图像编辑成功路径：`POST /images/edits` multipart，案例使用 `gpt-image-2-max`、原图、Prompt 和 `size=3840x2160`；SDK 案例读取 `data[0].b64_json`。
- 当前样例同时记录 `gpt-image-2`、`gpt-image-2-max`、URL/`b64_json`、尺寸/比例和质量参数；这些参数变体不能全部视为已由真实 provider 单独验证。
- 当前样例记录含 `pro` 的图像模型会返回 500，因此 MVP 不默认使用 `gpt-image-2-pro`，也不做静默模型 fallback。
- 多图案例以本地路径或 HTTP URL 加载，最多 10 张；这是调用案例能力，不直接冻结正式 MVP 上传上限。
- `/images/generations`、JSON Schema、最终超时/限流、费用基线和正式产品模型仍需 Task 11 的显式 capability probe。

证据位置：`samples/gpt-image-2-edit-multi.py`、`samples/gpt-image-2-edit-multi-url.py`、`samples/yibu-api-probe/`、`docs/development/sessions/2026-08-01-yibu-api-probe.md`。不得把真实 Key、原图或完整模型响应写入这些文件或 Git。

## 编码与测试约束

- Python 内部字段和函数使用 `snake_case`；API 通过统一 alias generator 输出 `camelCase`；TypeScript 使用 OpenAPI 生成类型。
- 新功能必须先观察与目标一致的失败测试，再写最小实现，随后执行局部测试和相关回归测试。
- Task Subagent 不修改超出 Context Packet `allowed_files` 的文件，不处理未授权的未来里程碑。
- 真实模型、真实游戏和真实用户素材只在计划明确的人工验证中使用；默认测试不得产生模型费用。
- 发现需要改变用户可见机制或已批准接口时，停止当前 Task，先更新设计并获得用户确认。

## Git 与 Session 约束

- 控制面文件可提交；设计稿、技术设计、实施计划和项目索引按 `.gitignore` 保持本地。
- 一个 Task 对应一个串行修改型 Session；同一时间只能有一个活动修改型 Session。
- Session 状态必须遵循 `planned → active → verification → awaiting_user_acceptance → accepted → committed`。
- 默认必须等待用户验收后提交。纯后台且无功能变化的 Task，只有在自动测试和代码检查完全覆盖目标时才可自动审批；有疑问时升级用户 Review。
- 提交使用用户配置的 Git 身份，不添加 Agent 署名；推送必须另行获得授权。
