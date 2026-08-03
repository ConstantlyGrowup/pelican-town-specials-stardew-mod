# Session 2026-08-03｜Task 7 Launcher、会话安全、同源静态托管与空闲退出

## Session 元数据

| 字段 | 值 |
|---|---|
| session_id | 2026-08-03-task-7-launcher-security |
| task | MVP Task 7：Launcher、会话安全、同源静态托管、前端 bootstrap 与空闲退出 |
| state | committed |
| type | implementation |
| authorization | 用户已明确允许开始 Task7；设计补充方案已明确确认“可以按该方案继续” |
| owner | 主 Agent + 串行 implementer/reviewer Subagent |
| commit_policy | 用户验收前不创建 focused commit；推送需另行授权 |

## 目标

让普通 Windows 用户可以通过 Launcher 双击使用本地应用：服务只绑定 loopback，单实例打开浏览器，前端用一次性启动令牌建立受保护会话，FastAPI 同源托管 `frontend/dist`，并支持心跳、主动关闭和空闲退出。

## 范围

本 Session 包含：

- Launcher 单实例锁、运行记录、端口选择、health 等待和浏览器打开；
- 60 秒、单次消费、只存内存的 launch token；
- `HttpOnly`、`SameSite=Strict` 会话 Cookie，以及 Host/Origin/CSRF 校验；
- 同源静态托管、SPA fallback、前端 bootstrap 和内存 CSRF header；
- heartbeat、shutdown 和默认 600 秒空闲退出。

本 Session 不包含真实模型调用、Provider Gateway、业务草稿/菜品 API、登录账户、数据库、管理员权限、机器级环境变量或发布流水线。

## 已确认设计

- Uvicorn 只绑定 `127.0.0.1`，不注册 CORS；生产 Host 只允许 loopback。
- `POST /session/bootstrap` 接收 launch token，成功返回 204、设置 `PTS_SESSION` HttpOnly/SameSite=Strict Cookie，并通过 `X-PTS-CSRF` 响应头交给前端。
- 前端只在模块内存保存 CSRF 值；bootstrap 成功后用 `history.replaceState` 清理 `#launch` fragment。
- 业务 API 默认要求会话；修改请求额外要求匹配 Origin 和 CSRF。
- Launcher 不读取 API Key；token、Cookie、CSRF 和 API Key 不进入日志、响应正文或持久化文件。

## 记录

### planned → active｜2026-08-03

- 用户授权开始 Task7；读取 AGENTS.md、STATUS.md、CONSTRAINTS.md、正式技术设计、实施计划和项目设计源索引。
- 发现原 Task7 计划只列后端实现，未列正式技术设计要求的前端 fragment bootstrap；已向用户说明范围补充及其必要性，用户明确确认可以按该方案继续。
- 已写入并自审：`docs/superpowers/specs/2026-08-03-task-7-launcher-security-design.md`、`docs/superpowers/plans/2026-08-03-task-7-launcher-security.md`。
- 下一步：建立 SDD ledger，按 Task1 → Task5 串行实现，每项先观察失败测试，再进行独立只读复审。

## 验收记录

已完成 verification 和独立只读复审；用户已明确验收通过，Task7 focused commit 已创建，推送按已获授权继续执行。


### Task1 完成｜2026-08-03

- 实现 `SecurityState`、一次性 60 秒 launch token、会话 Cookie、CSRF header、Host/Origin/CSRF 校验和 `/api/v1` 会话保护。
- 通过四轮修复闭环：health Host 校验、错误 CSRF 不刷新会话、废弃 token 清理、当前端口精确匹配。
- 最终验证：安全/health/settings/app wiring 聚焦回归 21 passed；Ruff、mypy、`git diff --check` 通过；独立只读复审最终 PASS。
- 受限执行器默认 pytest 临时目录会触发 `WinError 5`，使用授权的 `C:\tmp` 临时目录完成最终回归；该限制不改变代码结果。
- Task2 已成为当前下一步；本 Session 仍未提交。
### Task2 完成｜2026-08-03

- 实现单实例 `portalocker` 锁、原子运行记录、loopback URL 校验、偏好/系统端口选择、浏览器打开和 health 重试探针。
- 运行记录只保存 PID、端口、loopback URL 和启动时间；清理会核对完整实例归属，不会删除其他实例记录。
- 最终验证：Task2 聚焦测试 15 passed；Ruff、mypy、`git diff --check` 通过；独立只读复审最终 PASS。修复了 health 总超时和端口 0 边界。
- 当前下一步为 Task3：同源静态托管、heartbeat、主动关闭与空闲退出；本 Session 仍未提交。
### Task3 完成｜2026-08-03

- 实现配置 dist 的同源静态托管、SPA fallback、路径穿越/保留路径保护和 `PTS_SYSTEM_WEB_ASSETS_MISSING` 安全错误。
- 实现 `/app/heartbeat`、`/app/shutdown` 和可注入时钟/回调的 `ActivityTracker`；生命周期 monitor 会在 600 秒空闲且不 busy 时调用优雅关闭回调。
- 最终验证：Task3 聚焦与 API 回归 30 passed、1 symlink 测试 skipped；Ruff、mypy、`git diff --check` 通过；独立只读复审最终 PASS。
- 当前下一步为 Task4：Launcher 主流程与 CLI；本 Session 仍未提交。
### Task4 完成｜2026-08-03

- 实现 `launcher.main`：CLI、单实例复用、动态端口、安全端口注入、health 等待、内存 launch fragment、浏览器开关、no-browser/exit-after-health-check 和失败清理。
- Launcher 只把 PID、端口、loopback URL 和启动时间写入运行记录；静态资源预检拒绝缺失、非法和站外 `index.html`。
- 最终验证：Task4 聚焦与 Task1–3 启动器回归 42 passed、2 skipped；Ruff、mypy、`git diff --check` 通过；独立只读复审最终 PASS。
- 当前下一步为 Task5：前端 bootstrap、CSRF middleware 与文档同步；本 Session 仍未提交。
### Task5 完成｜2026-08-03

- 实现前端 launch fragment bootstrap、same-origin credentials、内存 CSRF、mutation middleware、成功后 fragment 清除和 30 秒 heartbeat/pagehide 清理。
- 保留无 fragment 的 health probe 与现有首页；bootstrap/CSRF 失败日志不回显敏感值。
- 最终验证：前端全量 9 passed；lint、TypeScript/Vite build、`git diff --check` 通过；独立只读复审最终 PASS。
- 当前下一步为 Task6：全量验证、文档同步和验收资料；本 Session 仍未提交。

### Task6 完成｜2026-08-03

- 全量后端回归：201 passed, 2 skipped；前端 Vitest：2 files / 9 passed；Ruff、mypy、前端 lint、TypeScript/Vite build、git diff --check 和本地设计/计划忽略检查均通过。
- 真实 Launcher 壳层 smoke 使用构建后的 frontend/dist 与临时 workspace，在 127.0.0.1:43132 启动服务、完成 health 检查并正常退出；退出后 runtime.json 不存在。端口预留 socket 已交给 Uvicorn，避免检查与绑定之间的竞态；第二实例复用、bootstrap、Host/Origin/CSRF、settings mutation 和 idle shutdown 由自动测试覆盖。
- 敏感配置扫描未发现 Task7 将 launch token、Cookie、CSRF 或 API Key 写入日志、响应正文或持久化运行记录；未引入 0.0.0.0、setx、机器级变量、注册表或 Credential Locker 路径。扫描命中的 Task6 用户级 Key 实现属于既有范围，不属于 Launcher。
- 独立只读总审阅已通过：P1 端口预留竞态、可读失败反馈、异常清理覆盖缺口和 SPA fallback 文档路径边界均已修复并通过回归。P2 启动窗口复用和新浏览器上下文重连边界保留为验收限制。2 项 symlink 路径边界测试因当前 Windows 权限跳过；真实浏览器视觉流程尚未由 Agent 手动操作，需用户在本机确认。
- Session 已关闭并进入 committed；用户已授权推送 Task7 focused commit，随后开始 Task8。
