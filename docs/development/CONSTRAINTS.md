# Pelican Town Specials｜开发约束

本文是开发控制面的项目约束摘要。它不替代正式技术设计；如果摘要与用户后来确认的设计不一致，先停止当前 Session，报告冲突并同步正式设计、实施计划和项目索引。

## 权威文档

| 文档 | 权威范围 |
|---|---|
| `docs/architecture/MVP_TECHNICAL_DESIGN.md` v2.8 | v1.5.0 已发布本地版协议，并链接 Milestone 9/10/11 与 Task 36.1/36.2 编码扩展 |
| `docs/architecture/PHASE_3_CANONICAL_MEMORY_TECHNICAL_DESIGN.md` v1.0 | Milestone 9 SQLite、领域/端口、候选算法、matcher、复用、登记、计时、失败与验收协议；用户已验收并授权实施 |
| `docs/architecture/RELEASE_TELEMETRY_TECHNICAL_DESIGN.md` v1.2 | Milestone 10 EXE 无感后台统计、PostHog sink、字段 allowlist、事件、性能与指标协议；已实施、独立审阅并随 v1.4.0 发布 |
| `docs/plans/MVP_IMPLEMENTATION_PLAN.md` v2.1 | 已完成并发布 Task 1–44，记录 Milestone 11 最终顺序、补丁与发布证据 |
| `docs/plans/2026-08-25-milestone-9-canonical-memory.md` v1.0 | Milestone 9 文件、依赖、Acceptance、测试、人工验收和 focused commit 计划；已验收并授权按 Task 31→36 实施 |
| `docs/plans/2026-08-25-milestone-10-release-telemetry.md` v1.2 | Milestone 10 Task 37–39 文件、依赖、Acceptance、测试、外部配置、打包和 focused commit 计划；已实施、验收并随 v1.4.0 发布 |
| `docs/plans/2026-08-26-task-36-1-source-referenced-icon.md` v1.0 | fresh/miss/full-regenerate/Blueprint 使用当前原图生成像素图标，Canonical HIT 复用历史图标；已验收并随 v1.4.0 发布 |
| `docs/plans/2026-08-26-task-36-2-official-openai-provider-compatibility.md` v1.0 | 官方/非官方 OpenAI-compatible 端点适配：省略官方不兼容参数、按单图 `image`/多图 `image[]` 编码，并保持非官方兼容端点回归；已验收并推送 |
| `docs/architecture/TRIAL_EXPERIENCE_TECHNICAL_DESIGN.md` v1.2 | Milestone 11 试用预留/完整成功确认、任意失败不扣、个人服务接管、结果快照及 Task 43/44；已随 v1.5.0 发布 |
| `docs/plans/2026-08-30-milestone-11-trial-experience.md` v1.2 | Task 40–44 的依赖、Acceptance、测试、统一验收与 v1.5.0 发布结果 |
| `最初设计功能清点/StarValleyCook_项目顶层规划_v3.0.md` | 现行五期路线与阶段边界；第三期记忆、第四期在线后端、第五期管理端 |
| `最初设计功能清点/第三期-全局生成记忆与Canonical召回-规划锚点_v3.0.md` v3.2 | 当前第三期产品/机制真源；Milestone 9 已验收并授权实施 |
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
- Task 30 新手试用入口已实施、验收并随 v1.3.0 发布（Session `2026-08-16-task-30-trial-entry-impl`）：独立隐藏试用档案 + `app-state/trial-state.json` 本机软额度（N=2）+ 首次 Provider 调用前原子 claim + 保存个人配置自动退出 + 已配置用户优先消耗试用额度 + CI Secret 注入 gitignored 资源 Key；试用 Key 不进入 Git/API/前端/日志；仍不属于第三期。
- Milestone 11 已完成、统一验收并随 v1.5.0 发布：不发送 `/models`、最小 Token query 或图像探测；每个试用 attempt 的首次真实 Provider 调用就是可用性检查。Task 40 把永久 claim 改为按 attemptId 预留，只有全部生成阶段与 Draft promotion 完整成功才确认，任一失败/取消均释放；Task 41 提供用户显式确认的个人额度接管，禁止无提示自动付费 fallback；Task 42 显示固定 `trialUsed/trialRemaining` 快照；验收补丁加入“直接重试”和试用 Key 轮换；Task 43 支持清空蓝图分类及逐个移除标签；Task 44 支持试用不可用时经确认放弃草稿并返回主页。
- Task 45 Blueprint 英文 metadata 补丁：curated 分类/标签继续以中文 canonical 值保存并进入后端、Prompt 与存档；`en-US` 只在前端显示英文标签并允许英文搜索，`zh-CN` 保持中文，未映射自由值原样回退。不得借此改变 API/schema、候选集合或根 README 的分支定位。
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
- Milestone 9 冻结（2026-08-29 阈值校准）：全局有效 Canonical 至少 N=2；同语言现实原料主导 Top 5；模型只选最高候选且 `>=0.80`（包含边界 `0.80` 命中、`0.799` miss）；仅正式 Ask Gus 存档写入；完整重新生成/Blueprint 不召回；效果只衡量总耗时和真实单次任务成本。此前 `>=90%` 的当前口径已由本次 0.80 校准取代。
- Task 36.1 冻结：Canonical HIT 直接复用历史 icon、零图标生成；Ask Gus INITIAL miss、FULL_REGENERATE 与 Blueprint 必须以当前 Draft 原图作为单图 edit 参考生成新 icon，再沿用现有背景透明化和 16×16 归一化。不得新增图片调用次数、设置项、前端/API/schema 或相似度模型。
- Task 36.2 冻结：面向官方与非官方 OpenAI-compatible 端点；官方 `gpt-5.6` 文本/视觉调用不得固定发送其不支持的 `temperature=0`，官方 `gpt-image-2` generation/edit 不发送 `response_format`，单图 edit 使用 `image`、多图使用有序重复 `image[]`；默认 `b64_json` 与兼容端点 URL 均继续解析。保持 Base URL/模型 ID 可配置，不新增 Provider SDK、设置项、API/schema、Provider 自动分支、额外调用或模型 fallback；真实 API 验证必须由用户明确授权。
- 第三期使用 Python 标准库 SQLite 和 Registry 自有图标目录，不要求用户安装数据库；调用/步骤数只用于正确性测试，不作为产品指标。
- 第三期不引入登录、云端工作区、Redis、Bloom Filter、夜间批处理、分布式队列、Gallery 或管理端；这些分别留到第四期/第五期规划。
- Milestone 10 统计口径冻结为“匿名活跃安装”，不宣称精确人数；随机 UUID v4 不与账号、机器指纹、用户名、路径或硬件绑定。
- M10 在配置完整的 Windows Release 中自动启用，不新增首次说明、用户确认、设置开关、前端页面、公开 API 或用户文档入口；开发、测试和缺少 Release 配置时使用 no-op。
- M10 只允许人工定义的模式/结果/耗时/试用/M9 命中枚举；不记录应用版本，也不统计新版本采用比例；禁止图片、菜品文本、用户输入、Key、Provider/模型、业务 ID、异常正文、IP/Geo、DOM、自动点击和 session replay。
- M10 第一版使用 PostHog Cloud personless capture（`$process_person_profile=false`）与项目级 IP discard；只用现有 `httpx`、进程内有界队列和可替换 `TelemetryRecorder`，采集故障不得影响业务。
- GitHub Release `download_count` 只作触达旁证，不等于安装或用户；M10 数据不用于计费、权限、安全审计或试用限额。

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
