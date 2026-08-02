# Task 3 设计规格：React 前端骨架与生成式 API Client

状态：用户已审阅，实现与验证完成，已验收；focused commit 边界已确定
日期：2026-08-02
对应 Session：2026-08-02-task-3-frontend-shell

## 1. 目标

为 Pelican Town Specials 建立第一个可运行的 Web UI 壳层。Task 3 只负责让用户看到正式产品首屏，并为后续领域页面提供稳定的 React、TypeScript、OpenAPI 类型和 same-origin API 基础；它不实现业务闭环。

## 2. 当前基线与约束

- 后端 Task 2 已提供 FastAPI 应用和 GET /api/v1/health。
- frontend/openapi.json 已包含健康检查路径及 HealthResponse，它是本 Task 的唯一 API 类型输入。
- 技术设计规定 Web UI 使用 React + TypeScript + Vite，浏览器通过 same-origin HTTP 访问 FastAPI；开发服务器可将 /api 代理到后端。
- STATUS.md 是当前状态真源；不把可选开发工具误写成产品运行或发布依赖。

## 3. 范围与非目标

### 3.1 本 Task 交付

1. 可用的 Vite/React/TypeScript 前端工程配置和固定 npm scripts。
2. 由 openapi-typescript 从 frontend/openapi.json 生成的 schema.d.ts。
3. 基于 openapi-fetch<paths> 的 apiClient，baseUrl 使用空字符串保持浏览器 same-origin。
4. React Providers 入口，为后续 TanStack Query 等页面状态能力提供边界。
5. 首屏正式文案：
   - 产品名：鹈鹕镇新菜单
   - 主宣传语：把你做的菜，写进鹈鹕镇的下一张菜单。
6. 应用启动时通过 typed client 调用 /api/v1/health，用于确认前后端本地连接。
7. App 的渲染测试、契约生成检查和静态构建。
8. 为文档启动命令提供标准 Uvicorn module-level app 入口、开发依赖兼容性和回归测试；不改变既有路由或 OpenAPI 契约。

### 3.2 明确不做

- 不创建草稿、问问 Gus、料理蓝图、收集品、菜单打包或游戏安装页面。
- 不发送真实模型请求，不读取或保存 API Key，不引入认证、Cookie 会话或 CSRF store。
- 不修改 FastAPI 路由和 OpenAPI 契约；后端只补充标准 ASGI app 导出、开发依赖兼容性和回归测试；若契约不匹配，停止并报告，不在前端手写 DTO 掩盖问题。
- 不创建数据库、工作区、Mod、图片处理或领域校验代码。
- uv 不是 Task 3 的启动前置；不提交 Python lockfile 或后端虚拟环境配置。

## 4. 关键设计决策

### 4.1 App 与启动探针分离

App 保持一个可以直接由 Testing Library 渲染的纯首屏组件，因此冻结测试可以直接使用 render(<App />)，不依赖 QueryClient 或网络。main.tsx 在正常浏览器启动时负责调用 typed health probe，再把 App 放入 AppProviders。这样既保留最小首屏的可测试性，也能在浏览器 Network 面板验证 /api/v1/health。

健康检查失败不阻塞首屏渲染，也不把后端错误伪装成产品业务状态；启动探针只记录可诊断的失败结果，后续 Task 再设计统一错误界面。

### 4.2 API 类型单一来源

frontend/src/api/generated/schema.d.ts 只能由以下命令生成：

    openapi-typescript openapi.json -o src/api/generated/schema.d.ts

client.ts 通过 openapi-fetch<paths> 导出 apiClient，不手写 HealthResponse 或重复路径类型。baseUrl: "" 让生产静态资源和本地 Vite 代理都使用 /api/...；Vite 配置只负责开发时将 /api 转发到本机 FastAPI。

未来修改请求的会话和 CSRF 约束不在 Task 3 虚构实现；本 Task 只有 GET 健康检查，后续涉及写入时再由 session store 统一注入 X-PTS-CSRF。

### 4.3 文案集中管理

PRODUCT_COPY 放在 src/i18n/copy.ts，首屏只从该常量读取正式文案。导航或业务标签（如“问问 Gus”“料理蓝图”“收集品”“打包菜单”“带进游戏”）可以一并冻结为后续页面使用的中文 copy，但本 Task 不实现这些页面。

### 4.4 最小 Provider 边界

providers.tsx 提供 QueryClientProvider，并集中配置一个适合本地壳层的 QueryClient。Task 3 不借此实现业务查询；启动 health probe 仍在 main.tsx，避免 App 的冻结渲染测试被网络依赖绑住。

## 5. 文件职责

| 文件 | 职责 |
|---|---|
| frontend/package.json | 前端依赖和 dev、test、test:run、build、lint、contract:generate、e2e scripts |
| frontend/vite.config.ts | React 插件、开发端口和 /api → FastAPI 的本地代理 |
| frontend/tsconfig.json | 浏览器、React JSX 和严格 TypeScript 编译边界 |
| frontend/index.html | Vite HTML 入口和页面语言/元信息 |
| frontend/src/main.tsx | 启动 health probe、挂载 Providers 和 App |
| frontend/src/app/providers.tsx | QueryClientProvider 边界 |
| frontend/src/app/App.tsx | 语义化、可访问的最小产品首屏 |
| frontend/src/app/App.test.tsx | 冻结产品名和主宣传语的渲染契约 |
| frontend/src/api/client.ts | OpenAPI 生成类型绑定的 same-origin client |
| frontend/src/api/generated/schema.d.ts | 由 frontend/openapi.json 生成，不手工维护 DTO |
| frontend/src/i18n/copy.ts | 正式产品文案常量 |
| backend/pyproject.toml | 启动/测试所需的开发依赖兼容性声明 |
| backend/src/pelican_town_specials/api/app.py | 保留 create_app() 并导出标准 Uvicorn app |
| backend/tests/api/test_health.py | 健康契约与模块级 ASGI 入口回归测试 |

## 6. 用户可见行为

正常启动后的首屏必须包含一个可访问的 heading “鹈鹕镇新菜单”和主宣传语“把你做的菜，写进鹈鹕镇的下一张菜单。”。布局只需形成清晰的产品卡/欢迎区，不引入视觉精修或领域操作入口。

浏览器启动后应出现一个同源请求：

    GET /api/v1/health

请求失败时仍显示首屏；本 Task 不显示“业务可用”成功徽章，也不把健康检查响应保存为业务数据。

## 7. 测试驱动实施顺序

实施 Agent 必须先写并运行首屏失败测试，再写最小实现：

1. 在 App.test.tsx 写 heading/tagline 断言，运行 pnpm --dir frontend test:run -- src/app/App.test.tsx，确认因 App 或正式文案尚不存在而失败。
2. 建立配置、文案和 App 的最小实现，重复运行该测试确认通过。
3. 添加 Providers、typed client 和启动 probe；用测试替身隔离 fetch，避免单元测试依赖启动中的 FastAPI。
4. 运行契约生成，确认生成文件来自当前 OpenAPI；禁止手写同名响应模型。
5. 运行完整 Vitest、TypeScript/Vite build 和 lint；再做后端回归与浏览器手工检查。

## 8. 验收标准

- pnpm --dir frontend contract:generate 成功且生成 schema 可被 TypeScript 编译。
- pnpm --dir frontend test:run 全部通过，至少覆盖正式产品名和主宣传语。
- pnpm --dir frontend build 成功生成 frontend/dist，产物包含正式产品名。
- pnpm --dir frontend lint 成功。
- 后端现有 health 测试、标准 Uvicorn 启动命令和 scripts/verify_local_docs_ignored.ps1 不回归。
- 手工启动 Vite 与 FastAPI 后，首屏显示正式文案，Network 中 health 请求只访问本机 /api/v1/health。
- 后端直连与 Vite 代理的 /api/v1/health 均返回 status=ok、app=PelicanTownSpecials、apiVersion=v1。
- Task 3 范围内不提交 Python lockfile 或虚拟环境目录；真实模型调用和 Task 4+ 业务实现仍不在范围内。

## 9. 提交边界与后续

实现完成并通过独立只读 Review、主 Agent 验证和用户明确接受后，使用一个 focused commit：

    feat: add React application shell

该 focused commit 的 amend 边界包含 Task 3 前端文件、前端依赖锁文件、后端标准 ASGI 启动入口、开发依赖、回归测试，以及 Task 3/启动修复控制面记录；不包含 Python lockfile、虚拟环境或其他本地工具状态。本次 amend 与推送已获用户授权。

## 10. 自审结论

- 规格覆盖了用户已确认的 React/Vite/TypeScript 壳层、OpenAPI 生成类型、same-origin client、正式产品首屏和 health endpoint。
- 规格明确排除了领域功能、真实模型调用、Task 4+ 和非产品 Python 工具链配置，符合当前 Session 与 AGENTS.md。
- App 直渲染测试与启动健康检查的边界已显式解决，避免把网络依赖混入冻结首屏测试。
- 规格不替代后续实施计划；用户审阅通过后仍需按 TDD、implementer/reviewer 和 verification 流程执行。
