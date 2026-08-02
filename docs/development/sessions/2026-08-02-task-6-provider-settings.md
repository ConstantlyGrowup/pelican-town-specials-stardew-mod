# Session｜2026-08-02-task-6-provider-settings

| 字段 | 值 |
|---|---|
| session_id | 2026-08-02-task-6-provider-settings |
| session_type | mvp-task-implementation |
| state | committed |
| date | 2026-08-02 |
| task | MVP Task 6：实现用户级环境变量 Secret Store、Provider Settings 与统一错误映射 |
| owner | 当前主 Agent；Git 不记录 Agent 署名 |

## 授权与当前阶段

- 用户已明确授权开始 Task6，并验收通过 Task6 设计说明。
- 用户确认优先易用性：应用直接维护当前 Windows 用户级环境变量 PTS_OPENAI_API_KEY，支持新增、更新和删除；不要求用户手动配置环境变量。
- 详细实施计划已写入 docs/superpowers/plans/2026-08-02-task-6-provider-settings.md。
- 用户已验收，focused commit 已创建并推送到 origin/feat/mvp-implementation；本 Session 已关闭。

## 目标

让普通 Windows 用户能够在应用设置流程中配置 Provider 和 API Key，不依赖手动环境配置；为后续一键启动和前端设置页面提供安全边界清晰的后端接口与统一错误响应。

## 已实现范围

- WindowsEnvironmentSecretStore：读取、新增、覆盖、删除当前用户级 PTS_OPENAI_API_KEY，并同步当前进程；包含失败回滚、读取/写入错误映射和测试注入适配器。
- ProviderSettings：非机密设置保存到工作区 app-state/settings.json，使用原子写入与备份恢复；Key 状态动态读取，不落盘。
- Settings API：GET/PUT /api/v1/settings/provider，PUT/DELETE /api/v1/settings/provider/key。
- 统一 ErrorEnvelope：AppError、请求校验错误和未预期异常统一返回 requestId、safe details 和 recommendedAction；异常消息和堆栈不进入响应或日志。
- create_app 生产装配：默认用户工作区、当前用户环境变量 Secret Store、Provider Settings 服务、Settings router 和统一异常处理器。
- 移除不再使用的 keyring 运行依赖；uv/lockfile/虚拟环境政策保持不变。

## 不包含

- 真实模型调用、Provider Gateway；
- Launcher、一次性启动令牌、HttpOnly 会话、CSRF；
- 前端设置页面；
- 多 Provider、多 Key 历史、Key 轮换、远程账户和机器级环境变量。

## 验证证据（截至当前）

- Secret Store focused：13 passed；Ruff、mypy 通过。
- Provider Settings focused：18 passed；Ruff、mypy 通过。
- Settings API、生产 app wiring、health、统一错误和日志脱敏：13 passed；Ruff、mypy 通过。
- 复审代理已检查 Secret Store、Provider Settings、Settings API 和 ErrorEnvelope；边界问题已补测试并修正。
- 全量验收已完成：backend/tests 152 passed；Ruff、mypy、git diff --check 通过；依赖与敏感配置扫描无 keyring、setx、机器级环境变量或 Credential Locker 实现；create_app 生产装配和 API 脱敏集成测试通过。
- focused commit：feat: configure provider settings and environment secrets，已推送到 origin/feat/mvp-implementation。

## 设计与下一步

- 设计说明：docs/superpowers/specs/2026-08-02-task-6-provider-settings-design.md。
- 实施计划：docs/superpowers/plans/2026-08-02-task-6-provider-settings.md。
- Session 已关闭；后续等待用户授权 Task7；Task6 已完成推送。
