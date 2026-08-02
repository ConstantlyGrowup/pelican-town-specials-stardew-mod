# React 前端骨架与生成式 API Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** 建立一个可测试、可构建的 React + TypeScript + Vite 前端壳层，渲染冻结的产品首屏，并通过 OpenAPI 生成类型调用 same-origin health API。

**Architecture:** frontend 是根 pnpm workspace 中的独立 Vite 应用。App 保持可直接渲染的纯首屏组件；main.tsx 在正常浏览器启动时调用 typed health probe，再用 Providers 挂载 App。API 类型只来自 frontend/openapi.json，apiClient 使用 openapi-fetch 并保持空 baseUrl。

**Tech Stack:** React、TypeScript、Vite、TanStack Query、openapi-fetch、openapi-typescript、Vitest、Testing Library、MSW、Playwright、ESLint、pnpm。

## Global Constraints

- 本 Session 只处理 MVP Task 3：React/Vite/TypeScript 前端骨架、OpenAPI 生成类型、same-origin typed client、正式产品首屏和 GET /api/v1/health 启动检查；同时纳入已验收的后端标准 ASGI 启动入口、开发依赖兼容性和回归测试，不改变路由或 OpenAPI 契约。
- 正式产品名必须是“鹈鹕镇新菜单”；主宣传语必须是“把你做的菜，写进鹈鹕镇的下一张菜单。”。
- apiClient 必须使用 openapi-fetch<paths>，baseUrl 必须为空字符串；不得手写重复的 HealthResponse DTO。
- schema.d.ts 必须由 openapi-typescript openapi.json -o src/api/generated/schema.d.ts 生成。
- App 的冻结渲染测试必须可以直接调用 render(<App />)，不要求 QueryClient 或网络。
- 启动 health probe 失败不能阻塞首屏，也不能伪装成业务状态。
- 不实现草稿、料理蓝图、收集品、菜单打包、游戏安装、认证、CSRF store、真实模型调用或 Task 4+。
- uv 不是 Task 3 的启动前置；不提交 Python lockfile 或后端 Python 虚拟环境配置；前端依赖使用 pnpm，并允许生成前端依赖锁文件。
- 保护现有未提交控制面文档；实现 Agent 不得覆盖或重写它们。
- 按 TDD 先写并观察首屏测试失败，再创建 App 等产品代码；配置文件和生成文件属于 TDD 允许的前置例外。
- 按项目 AGENTS.md，用户验收前不创建 commit；实现 Agent 完成后保留工作树变更供只读 Review 和主 Agent 验收。

---

### Task 1: MVP Task 3 前端骨架、typed client 与启动探针

**Files:**
- Create: \`pnpm-workspace.yaml\`
- Create: \`frontend/package.json\`
- Create: \`frontend/eslint.config.js\`
- Create: \`frontend/vite.config.ts\`
- Create: \`frontend/tsconfig.json\`
- Create: \`frontend/index.html\`
- Create: \`frontend/src/app/App.test.tsx\`
- Create: \`frontend/src/app/App.tsx\`
- Create: \`frontend/src/app/providers.tsx\`
- Create: \`frontend/src/main.tsx\`
- Create: \`frontend/src/api/client.ts\`
- Generate: \`frontend/src/api/generated/schema.d.ts\`
- Modify: \`backend/pyproject.toml\`
- Modify: \`backend/src/pelican_town_specials/api/app.py\`
- Modify: \`backend/tests/api/test_health.py\`
- Create: \`frontend/src/i18n/copy.ts\`

**Interfaces:**
- Consumes: \`frontend/openapi.json\`，其中包含 \`GET /api/v1/health\` 和 \`HealthResponse\`。
- Produces: \`apiClient\`、\`PRODUCT_COPY\`、可构建的 \`frontend/dist\`，以及供根脚本调用的 frontend package scripts。

- [x] **Step 1: 建立 workspace、package manifest 和固定 scripts**

在仓库根目录创建 \`pnpm-workspace.yaml\`：

\`\`\`yaml
packages:
  - frontend
\`\`\`

创建 \`frontend/package.json\`，先写入以下固定字段和 scripts，依赖随后由 pnpm 写入：

\`\`\`json
{
  "name": "pelican-town-specials-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "test": "vitest",
    "test:run": "vitest run",
    "build": "tsc --noEmit && vite build",
    "lint": "eslint .",
    "contract:generate": "openapi-typescript openapi.json -o src/api/generated/schema.d.ts",
    "e2e": "playwright test"
  }
}
\`\`\`

在 \`frontend\` 目录添加运行时依赖：

\`\`\`powershell
pnpm --dir frontend add @tanstack/react-query openapi-fetch react react-dom react-hook-form react-router-dom zod
\`\`\`

添加开发依赖：

\`\`\`powershell
pnpm --dir frontend add --save-dev @eslint/js @playwright/test @testing-library/jest-dom @testing-library/react @types/node @types/react @types/react-dom @vitejs/plugin-react eslint globals jsdom msw openapi-typescript playwright typescript typescript-eslint vite vitest
\`\`\`

这些命令使用当前 pnpm registry 的稳定兼容版本，并由生成的 lockfile 固定解析结果；不要手工添加第二套依赖管理配置。

- [x] **Step 2: 建立 Vite、TypeScript 和 ESLint 配置**

创建 \`frontend/vite.config.ts\`，使用 \`defineConfig\`、React 插件和 Vitest jsdom 配置；开发服务器固定在 5173，并把 \`/api\` 代理到 \`http://127.0.0.1:8000\`：

\`\`\`ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
\`\`\`

创建严格的 \`frontend/tsconfig.json\`，至少包含 \`target: ES2022\`、\`module: ESNext\`、\`moduleResolution: Bundler\`、\`jsx: react-jsx\`、\`strict: true\`、\`noEmit: true\`，并包含 \`src\` 和 \`vite.config.ts\`，类型包含 \`vite/client\` 和 \`vitest/globals\`。

创建 \`frontend/eslint.config.js\`，使用 \`@eslint/js\`、\`typescript-eslint\` 和 \`globals\`，对 TypeScript/TSX 启用推荐规则，忽略 \`dist\` 和 \`src/api/generated\`，并提供 browser 与 node 全局变量。不要为生成 schema 引入手工 lint 规则。

创建 \`frontend/index.html\`，设置 \`lang="zh-CN"\`、标题 \`鹈鹕镇新菜单 · Pelican Town Specials\`，并提供 \`<div id="root"></div>\` 与 \`/src/main.tsx\` module script。

- [x] **Step 3: 安装依赖并确认 lockfile 边界**

从仓库根目录运行：

\`\`\`powershell
pnpm install
\`\`\`

预期生成根目录 \`pnpm-lock.yaml\`，workspace 包为 \`frontend\`。确认没有生成 \`Python lockfile\`、\`frontend/.venv\`、\`backend/.venv\` 或其他 Python 虚拟环境目录。若 pnpm 在 workspace 下产生不同的 lockfile 位置，停止并报告，不要同时保留根和 frontend 两份 lockfile。

- [x] **Step 4: 写首屏失败测试（RED）**

先创建 \`frontend/src/app/App.test.tsx\`，内容如下；只额外导入 jest-dom matcher，不添加网络 mock，因为 App 必须是纯首屏：

\`\`\`tsx
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { App } from "./App";

it("renders the frozen product name and tagline", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: "鹈鹕镇新菜单" })).toBeVisible();
  expect(screen.getByText("把你做的菜，写进鹈鹕镇的下一张菜单。")).toBeVisible();
});
\`\`\`

- [x] **Step 5: 运行 RED 测试并确认失败原因**

运行：

\`\`\`powershell
pnpm --dir frontend test:run -- src/app/App.test.tsx
\`\`\`

预期测试以失败结束，原因是 \`./App\` 尚不存在或正式文案尚不存在；不是依赖安装错误、配置解析错误或测试语法错误。若失败原因不是缺少功能，先修正测试/配置并重复运行，直到得到正确的 RED。

- [x] **Step 6: 实现正式文案和最小 App（GREEN）**

创建 \`frontend/src/i18n/copy.ts\`：

\`\`\`ts
export const PRODUCT_COPY = {
  zh: {
    productName: "鹈鹕镇新菜单",
    tagline: "把你做的菜，写进鹈鹕镇的下一张菜单。",
    askGus: "问问 Gus",
    blueprint: "料理蓝图",
    cookbook: "收集品",
    packMenu: "打包菜单",
    bringInGame: "带进游戏",
  },
} as const;
\`\`\`

创建 \`frontend/src/app/App.tsx\`，导出 \`App\` 函数组件；使用 \`PRODUCT_COPY.zh\` 渲染一个语义化欢迎区，至少包含 \`main\`、一个可访问 heading、冻结产品名和主宣传语，并显示英文品牌标识 \`Pelican Town Specials\`。不要加入业务导航按钮或领域数据。

立即重跑：

\`\`\`powershell
pnpm --dir frontend test:run -- src/app/App.test.tsx
\`\`\`

预期测试通过且没有 React/Testing Library 警告。

- [x] **Step 7: 生成 OpenAPI schema**

在 \`App\` 的 RED/GREEN 已完成后运行：

\`\`\`powershell
pnpm --dir frontend contract:generate
\`\`\`

确认生成 \`frontend/src/api/generated/schema.d.ts\`，包含 \`paths\` 和 \`/api/v1/health\` 的 GET 类型。不得手工复制或修改 \`HealthResponse\`；生成文件只由当前 \`frontend/openapi.json\` 决定。

- [x] **Step 8: 实现 same-origin typed client**

创建 \`frontend/src/api/client.ts\`：

\`\`\`ts
import createClient from "openapi-fetch";
import type { paths } from "./generated/schema";

export const apiClient = createClient<paths>({
  baseUrl: "",
});
\`\`\`

保持导出的名称 \`apiClient\` 和类型参数 \`paths\` 不变。Task 3 只有 GET health 请求，不实现修改请求、认证会话或 CSRF store。

- [x] **Step 9: 建立 Providers 边界**

创建 \`frontend/src/app/providers.tsx\`，导出 \`AppProviders\`，使用 \`PropsWithChildren\` 和 \`QueryClientProvider\`。QueryClient 在模块范围内只创建一次，并将 query retry 设为 \`false\`，避免壳层测试或本地启动对失败请求自动重试：

\`\`\`tsx
import type { PropsWithChildren } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
});

export function AppProviders({ children }: PropsWithChildren) {
  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
}
\`\`\`

- [x] **Step 10: 实现启动 typed health probe 和入口挂载**

创建 \`frontend/src/main.tsx\`。正常浏览器启动时先使用 \`apiClient.GET("/api/v1/health")\` 发起请求，再挂载 \`AppProviders\` 和 \`App\`。健康检查失败只通过 \`console.warn\` 记录，不能阻塞或替换首屏：

\`\`\`tsx
import { createRoot } from "react-dom/client";
import { apiClient } from "./api/client";
import { App } from "./app/App";
import { AppProviders } from "./app/providers";

void apiClient
  .GET("/api/v1/health")
  .then(({ error }) => {
    if (error) {
      console.warn("Pelican Town Specials health probe failed", error);
    }
  })
  .catch((error: unknown) => {
    console.warn("Pelican Town Specials health probe failed", error);
  });

createRoot(document.getElementById("root")!).render(
  <AppProviders>
    <App />
  </AppProviders>,
);
\`\`\`

不要在 \`App.tsx\` 中调用 health；这样 \`render(<App />)\` 测试保持无网络依赖。不要显示“业务可用”徽章或保存健康响应。

- [x] **Step 11: 运行完整前端测试和静态检查**

依次运行：

\`\`\`powershell
pnpm --dir frontend contract:generate
pnpm --dir frontend test:run
pnpm --dir frontend lint
pnpm --dir frontend build
\`\`\`

预期：所有命令成功；生成 schema 通过 TypeScript 编译；测试覆盖正式产品名和主宣传语；\`frontend/dist\` 生成且包含正式产品名。若 generated schema 触发 lint，修正 ESLint ignore，不修改生成文件。

- [x] **Step 12: 执行后端回归与文档边界检查**

使用当前 Python 环境运行后端测试和仓库检查（uv 可选，不是前置条件）：

\`\`\`powershell
python -m pytest backend/tests -q
pwsh -File scripts/verify_local_docs_ignored.ps1
git diff --check
\`\`\`

如果后端依赖在当前环境不可用，记录确切错误，不为 Task 3 增加 Python lockfile 或 .venv；前端测试和构建仍必须完成。

- [x] **Step 13: 手工验证同源 health 请求**

分别启动后端和 Vite：

\`\`\`powershell
python -m uvicorn pelican_town_specials.api.app:app --app-dir backend/src --host 127.0.0.1 --port 8000
pnpm --dir frontend dev
\`\`\`

在浏览器打开 \`http://127.0.0.1:5173\`，确认：

1. 页面显示“鹈鹕镇新菜单”、主宣传语和 \`Pelican Town Specials\`；
2. Network 中出现 \`GET /api/v1/health\`；
3. 请求地址是 Vite 本机同源路径，不访问外部域名；
4. 后端返回 \`status=ok\` 时页面仍只显示壳层，不误报业务功能已完成。

- [x] **Step 14: 实现 Agent 自审并交付 Review**

运行 \`git status --short\`、\`git diff --check\`，确认只包含 Task 3 前端文件、pnpm workspace/lockfile 和必要控制面记录；没有 Python lockfile、虚拟环境、真实模型请求或 Task 4+ 代码。实现 Agent 在报告文件记录：

- 修改文件；
- RED 与 GREEN 命令及结果；
- 契约生成、lint、build、后端回归和人工验证结果；
- 已知限制；
- 明确不要 commit（项目规则要求用户验收后才提交）。

完成后保持工作树变更，不创建 commit，返回 DONE 或 DONE_WITH_CONCERNS。

## 验收与提交边界

主 Agent 会基于本计划和实现报告生成只读 Review 包，先完成规格符合性与代码质量 Review，再复跑命令。验证通过后 Session 进入 verification → awaiting_user_acceptance；用户明确接受后才创建唯一 focused commit：

\`\`\`
feat: add React application shell
\`\`\`

提交范围为 Task 3 的前端文件、pnpm workspace/lockfile、已验收的后端标准 ASGI 启动入口/开发依赖/回归测试，以及对应控制面记录；不提交后端缓存、Python lockfile 或临时报告。

## 计划自审

- 规格覆盖：Task 1 的步骤 1–3 覆盖 workspace、依赖、Vite/TS/ESLint 和 lockfile；步骤 4–6 覆盖 TDD RED/GREEN 和正式文案；步骤 7–10 覆盖生成 schema、typed client、Providers 和启动 health probe；步骤 11–13 覆盖自动化与人工验收；步骤 14 覆盖 Review 交接。
- 设计决策一致：App 不依赖网络，health probe 只在 main.tsx；apiClient 的 baseUrl 为空；generated schema 不手写；没有修改请求或 CSRF store。
- 计划与正式实现计划的 lockfile 预期一致：通过 pnpm-workspace.yaml 让 frontend 成为根 workspace 包，生成根 pnpm-lock.yaml；不产生第二份 frontend lockfile。
- 约束扫描：未将 uv 作为必需工具，也没有引入 .venv、真实模型、领域页面或 Task 4+；没有预先 commit，遵守项目验收规则。
- 类型一致：PRODUCT_COPY、apiClient、AppProviders 和 main.tsx 中的名称/签名与设计规格一致；generated paths 由 OpenAPI 命令提供。
- 步骤均包含实际命令、断言或配置内容，没有 TBD、TODO 或泛化的“自行实现”占位。
