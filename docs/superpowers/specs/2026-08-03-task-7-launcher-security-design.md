# Task 7：Launcher、会话安全、同源静态托管与空闲退出设计

## 1. 目标

把当前“开发者手动启动 Vite 与 FastAPI”的形态收敛为普通 Windows 用户可以双击使用的本地应用壳：应用只绑定 loopback，单实例启动后打开浏览器，前端用一次性启动令牌建立本地会话，业务 API 默认拒绝无会话请求，前端静态资源由 FastAPI 同源托管，并在无页面心跳且没有活动操作时自动退出。

## 2. 范围

本 Task 包含：

- Launcher 的单实例锁、运行记录、端口选择、启动 FastAPI、等待 health、打开浏览器和测试参数；
- 一次性 launch token、60 秒有效期、单次消费和内存清理；
- `HttpOnly`、`SameSite=Strict` 本地会话 Cookie；
- Host/Origin/CSRF 校验和统一 `PTS_AUTH_*` 错误；
- `frontend/dist` 的同源静态托管与 SPA fallback；
- 前端从 URL fragment 读取 launch token，调用 `/session/bootstrap`，读取 `X-PTS-CSRF` 响应头，随后清除 fragment；
- 心跳、主动关闭和 10 分钟空闲退出。

本 Task 不包含真实模型调用、Provider Gateway、业务页面、草稿/菜品 API、登录账户、远程服务、数据库、管理员权限或机器级环境变量。

## 3. 固定安全决策

### 3.1 网络边界

- Uvicorn 只绑定 `127.0.0.1`；Launcher 不提供公开网卡绑定参数。
- 生产请求只接受 `127.0.0.1` 或 `localhost` 的当前端口；测试通过显式注入 `testserver` 等允许 Host。Launcher 生产模式禁用 `/docs`、`/redoc`、`/openapi.json`，并对所有请求执行 loopback Host 校验。
- 不注册 CORS；同源静态资源和 API 使用浏览器默认 same-origin 规则。
- 健康检查、静态资源和会话引导不要求会话；其他 `/api/v1/**` 业务 API 必须有会话。

### 3.2 会话引导

Launcher 将随机 token 放在 `http://127.0.0.1:{port}/#launch={token}`，token 只保存在内存中，有效期 60 秒且只能消费一次。

前端通过 `POST /session/bootstrap` 发送 `{ "launchToken": "..." }`。成功响应为 204，设置：

- `PTS_SESSION`：随机会话值，`HttpOnly`、`SameSite=Strict`、`Path=/`；
- `X-PTS-CSRF`：随机 CSRF 值，作为响应头返回，不写入 Cookie、URL、日志或持久化文件。

前端只在当前页面内存保存 CSRF 值；修改请求通过 `X-PTS-CSRF` 发送。bootstrap 成功后使用 `history.replaceState` 清除地址栏 fragment。

### 3.3 修改请求

所有非安全方法的 `/api/v1/**` 请求必须同时满足：

1. Host 为允许的 loopback Host；
2. Origin 与当前 loopback origin 完全匹配；
3. `PTS_SESSION` 会话有效；
4. `X-PTS-CSRF` 与该会话绑定的 CSRF 值相同。

失败分别返回安全 ErrorEnvelope：`PTS_AUTH_HOST_INVALID`、`PTS_AUTH_ORIGIN_INVALID`、`PTS_AUTH_SESSION_REQUIRED`、`PTS_AUTH_CSRF_INVALID`。任何响应和日志都不得包含 launch token、Cookie 或 CSRF 值。

## 4. Launcher 与生命周期

Launcher 在应用数据目录保存运行锁和运行记录，不把 launch token 写入文件。运行记录只包含 pid、port、loopback URL 和启动时间。

启动流程：

1. 获取单实例锁；已有实例时读取运行记录并先调用 health，健康则只打开已有 URL；
2. 创建/恢复工作区并装配 `SecurityState`、`ActivityTracker` 和 FastAPI；
3. 从固定候选端口预留已绑定的 loopback socket，候选都冲突时请求系统空闲端口；启动时把同一个 socket 交给 Uvicorn，避免端口检查与真正绑定之间的竞态。
4. 生成 launch token，启动 Uvicorn，等待 `/api/v1/health` 返回 `status=ok`；
5. 打开带 fragment 的 loopback URL；
6. 服务退出或启动失败时清理运行记录和锁。

`--no-browser`、`--workspace`、`--port` 和 `--exit-after-health-check` 仅用于自动化或本地壳验证。Launcher 不读取或处理 API Key。

启动失败时，Launcher 写入工作区 app-state/launcher-error.log，仅包含稳定错误码和脱敏提示，并在可用的情况下输出日志路径；不得写入 launch token、Cookie、CSRF 或 API Key。SPA fallback 不接管 `/api`、`/app`、`/session` 或 `/docs`、`/redoc`、`/openapi.json` 等保留路径。

ActivityTracker 记录最近心跳和当前是否存在活动操作。超过 600 秒没有心跳且无活动操作时触发 Uvicorn 优雅退出；`POST /app/shutdown` 可由已认证会话主动触发退出。

## 5. 文件边界

- `backend/src/pelican_town_specials/api/security.py`：Host、Origin、token、session、CSRF 的内存状态和依赖；
- `backend/src/pelican_town_specials/api/routes/session.py`：bootstrap 路由；
- `backend/src/pelican_town_specials/api/routes/app_control.py`：heartbeat 和 shutdown 路由；
- `backend/src/pelican_town_specials/launcher/instance.py`：单实例锁和运行记录；
- `backend/src/pelican_town_specials/launcher/runtime.py`：端口、浏览器、health 等可注入 OS 适配；
- `backend/src/pelican_town_specials/launcher/main.py`：命令行参数和启动编排；
- `backend/src/pelican_town_specials/api/app.py`：安全依赖、静态目录和生命周期装配；
- `frontend/src/api/client.ts`：CSRF 内存状态和修改请求 header middleware；
- `frontend/src/main.tsx`：launch fragment bootstrap 和清理；
- 对应后端/前端测试只覆盖本 Task 的安全和启动行为。

## 6. 验收标准

- foreign Host、foreign Origin、无 Cookie、错误 CSRF、过期 token、token 重放均被拒绝；
- bootstrap 成功设置 HttpOnly 会话 Cookie、返回 CSRF header，且 token/CSRF 不出现在响应正文、日志或磁盘；
- settings API 在有效会话下可访问，现有 health API 继续返回 200；
- 第二个 Launcher 实例不会启动第二个服务，只复用健康的已有 URL；
- 静态目录缺失返回 `PTS_SYSTEM_WEB_ASSETS_MISSING`，存在时 `/` 和静态资源同源可访问；
- 心跳更新活动时间，主动 shutdown 返回 202，空闲 10 分钟后服务优雅退出；
- 前端有 launch fragment 时完成 bootstrap 并清除 fragment，无 token 的开发入口仍可显示现有首页和执行 health probe；
- 后端全量 pytest、Ruff、mypy、前端 test/build/lint 和 `git diff --check` 通过。

