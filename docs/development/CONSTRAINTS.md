# Pelican Town Specials｜开发约束

本文是开发控制面的项目约束摘要。它不替代正式技术设计；如果摘要与用户后来确认的设计不一致，先停止当前 Session，报告冲突并同步正式设计、实施计划和项目索引。

## 权威文档

| 文档 | 权威范围 |
|---|---|
| `docs/architecture/MVP_TECHNICAL_DESIGN.md` v1.9 | 已发布本地版的运行形态、模块、数据模型、API、工作流、错误处理、Mod 编译协议和 Yibu API probe 结论；M8 已实现，Task 30 已实现并进入验收 |
| `docs/plans/MVP_IMPLEMENTATION_PLAN.md` v1.2 | 已完成 MVP/M8 与 Task 30 的文件、依赖、Task、测试、人工验证、里程碑和提交边界；Task 30 已实施，不属于第三期 |
| `最初设计功能清点/StarValleyCook_项目顶层规划_v3.0.md` | 现行五期路线与阶段边界；第三期记忆、第四期在线后端、第五期管理端 |
| `最初设计功能清点/第三期-全局生成记忆与Canonical召回-规划锚点_v3.0.md` | 当前第三期需求发现真源；只冻结已确认范围，未决机制等待统一回答 |
| `design docs/PelicanTownSpecials_一期顶层设计_v2.2.docx` | 一期产品定义与 Ask Gus 三操作 / 并列入口（Git ignored） |
| `design docs/StarValleyCook_第二期产品体验与品牌化设计_v1.1.docx` | 二期体验、首页/导航与品牌叙事（Git ignored） |
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
- Task 30 新手试用入口已实施（用户 2026-08-16 指令覆盖 deferred，Session `2026-08-16-task-30-trial-entry-impl`）：独立隐藏试用档案 + `app-state/trial-state.json` 本机软额度（N=2）+ 首次 Provider 调用前原子 claim + 保存个人配置自动退出 + CI Secret 注入 gitignored 资源 Key；试用 Key 不进入 Git/API/前端/日志；仍不属于第三期。
- Milestone 8 将生成执行扩展为进程级固定 3 个并行运行槽；第 4 个请求在创建 attempt、改变草稿状态和调用 Provider 前返回 `PTS_GEN_BUSY`，提示最多同时运行 3 个任务并由用户稍后手动重试。
- 三个运行任务必须按 draftId/attemptId 隔离 owner、task、cancel、NDJSON 和进度；完成、失败、取消、删除或异常 cleanup 只释放自己的槽。
- M8 不实现 QUEUED 状态、排队、排位、自动补位或队列持久化。完整队列留到未来在线化或数据库/分布式消息队列/worker 架构时重新设计。
- 问问 Gus 结果页仅三操作：接受并存档、完整重新生成、拒绝；使用完整原子重生成；不提供进入料理蓝图。
- 料理蓝图仅从首页 / 开始创作等独立入口创建并加载基础模板；不提供 Ask Gus → Blueprint 产品转换路径；代码中历史 convert 端点若存在则不得在 UI 暴露。
- 一级导航冻结为 首页 / 开始创作 / 收集品 / 设置（`/` `/create` `/cookbook` `/settings`）；「使用与安装说明」不作为一级导航；Bring It In-Game 保持导出后流程页；Pack the Menu 由收集品驱动。
- 首页为单一 `/`：品牌叙事 + 创作入口 + 本地草稿 Dashboard；品牌 Hero 增强属于 Milestone 6，当前实现以 Dashboard 为主，不得标为已完成。
- 收集品不可编辑且不暴露来源模式。
- Mod 目标为 Stardew Valley 1.6.15、Content Patcher 2.9.0、纯 JSON/PNG 内容包；本地 Mods 路径只从 `PTS_STARDEW_MODS_DIR` 获取。
- `AuthorName` 在工作区首次创建时生成并持久化为 `D<YYYYMMDD>`；身份/账号策略后移第四期重新讨论。
- 第三期只规划并验证问问 Gus 的本地 Canonical 召回：可复用结构化词条与像素图标，但最终专属预览必须使用本次用户原图重新生成。
- 第三期不引入登录、云端工作区、Redis、Bloom Filter、夜间批处理、分布式队列、Gallery 或管理端；这些分别留到第四期/第五期规划。

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
