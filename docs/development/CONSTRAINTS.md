# Pelican Town Specials｜开发约束

本文是开发控制面的项目约束摘要。它不替代正式技术设计；如果摘要与用户后来确认的设计不一致，先停止当前 Session，报告冲突并同步正式设计、实施计划和项目索引。

## 权威文档

| 文档 | 权威范围 |
|---|---|
| `docs/architecture/MVP_TECHNICAL_DESIGN.md` v1.0 | MVP 运行形态、模块、数据模型、API、工作流、错误处理和 Mod 编译协议 |
| `docs/plans/MVP_IMPLEMENTATION_PLAN.md` v0.2 | 文件、依赖、Task、测试、人工验证、里程碑和提交边界 |
| `StarValleyCook_项目设计源索引与状态快照.md` | 设计源索引、产品命名、阶段状态和文档同步线索；保持 ignored |
| `docs/development/STATUS.md` | 当前开发 Session、工作树事实、阻塞和下一步；是开发状态唯一真源 |
| `docs/development/sessions/` | 每个 Session 的追加式历史证据 |

## 产品与技术冻结项

- 中文正式名：`鹈鹕镇新菜单`；英文正式名：`Pelican Town Specials`。
- 功能命名：`问问 Gus / Ask Gus`、`料理蓝图 / Blueprint Mode`、`收集品 / Cookbook`、`打包菜单 / Pack the Menu`、`带进游戏 / Bring It In-Game`。
- 仓库：`pelican-town-specials-stardew-mod`；应用 Slug：`pelican-town-specials`；代码名：`PelicanTownSpecials`；环境变量前缀：`PTS_`。
- MVP 采用 Windows 本地 Web、React + TypeScript + Vite、FastAPI + Pydantic、PyInstaller onedir、JSON 工作区和 OpenAI-compatible gateway。
- 默认工作区为 `%LOCALAPPDATA%\\PelicanTownSpecials\\workspace`；浏览器不直接访问任意本地文件路径。
- API Key 默认进入 Windows Credential Locker，不得进入 JSON、日志、错误正文、前端状态、测试快照、Context Packet 或 Git。
- MVP 使用同步请求和 NDJSON 阶段事件；不提前引入数据库、登录、队列、全局 Registry 或跨用户缓存。
- 问问 Gus 使用完整原子重生成；料理蓝图只复用原始图片和基础模板；收集品不可编辑且不暴露来源模式。
- Mod 目标为 Stardew Valley 1.6.15、Content Patcher 2.9.0、纯 JSON/PNG 内容包；本地 Mods 路径只从 `PTS_STARDEW_MODS_DIR` 获取。
- `AuthorName` 在工作区首次创建时生成并持久化为 `D<YYYYMMDD>`；第三期重新讨论身份策略。

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
