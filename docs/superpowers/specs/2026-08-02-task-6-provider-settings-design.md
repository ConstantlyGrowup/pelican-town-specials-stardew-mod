# Task 6：Provider 设置、用户环境变量密钥与统一错误响应设计

## 目标

让普通 Windows 用户可以在应用设置中直接配置 OpenAI-compatible Provider，不需要手动打开终端或设置环境变量；同时支持后续更新和删除 API Key，并让前后端使用统一、可安全处理的错误响应。

## 用户确认的取舍

本项目优先降低小白用户的配置门槛。API Key 由应用写入当前 Windows 用户级环境变量 PTS_OPENAI_API_KEY，并同步当前后端进程的环境视图，使保存后立即生效。

这里的“系统环境变量”采用当前用户范围，而不是机器范围：

- 不要求管理员权限；
- 不影响同一台机器上的其他 Windows 用户；
- 新启动的应用进程可以读取该变量；
- Key 会以明文存在用户环境配置中，应用在设置页面明确将其视为本地配置，不把它复制到工作区、日志、响应正文、测试快照或 Git。

环境变量仍是应用内部的唯一持久 Key 来源。应用不再依赖 Credential Locker 作为 Task 6 的默认写入路径；SESSION 仅表示可选的当前进程临时 Key。

## 方案与边界

### Secret Store

WindowsEnvironmentSecretStore 封装所有环境变量读写：

- 变量名固定为 PTS_OPENAI_API_KEY；
- get_api_key() 读取当前进程环境，并在需要时读取当前用户环境持久值；
- set_api_key() 同时更新当前用户环境和当前进程环境；
- delete_api_key() 清除当前用户环境和当前进程环境中的该变量；
- 写入失败转换为 PTS_WORKSPACE_SECRET_STORE_UNAVAILABLE，不得写入 JSON 作为备用；
- Key 的实际字符串只在 Secret Store、请求处理和后续 Provider 调用链路的内存中出现。

Windows 用户环境持久化使用用户范围的系统接口，不调用带命令行参数的 setx，避免 Key 出现在子进程命令行或命令历史中。当前进程同步更新，确保用户保存后无需重启即可使用。

### Provider 设置

非机密设置保存在 Task 5 工作区的 app-state/settings.json，使用既有原子 JSON 写入和备份恢复：

- providerKind 固定为 OPENAI_COMPATIBLE；
- baseUrl 默认 https://yibuapi.com/v1，保存时移除末尾 /；
- visionModel、textModel、imageModel 限制为 1–120 个字符；
- chatTimeoutSeconds 范围为 30–600；
- imageTimeoutSeconds 范围为 60–900；
- maxAutomaticRetries 范围为 0–3；
- apiKeyConfigured 与 apiKeySource 每次从 Secret Store 动态计算，不写入 JSON。

接口：

- GET /api/v1/settings/provider：返回非机密设置和 Key 状态；
- PUT /api/v1/settings/provider：校验并原子保存非机密设置；
- PUT /api/v1/settings/provider/key：接收用户输入并新增或覆盖当前用户环境变量；
- DELETE /api/v1/settings/provider/key：删除当前用户环境变量中的 Key。

Key 的 PUT 响应只返回配置状态和来源，不返回 Key；请求验证错误也必须脱敏。

### 统一错误响应

FastAPI 应用注册统一异常处理器：

- AppError 按自身 HTTP 状态和稳定错误码映射；
- 请求参数校验错误映射为安全的输入错误，不回显敏感输入；
- 未预期异常映射为 PTS_SYSTEM_UNEXPECTED，响应仅包含 requestId，堆栈不进入响应；
- 响应形状固定为：

    {
      "error": {
        "code": "PTS_WORKSPACE_SECRET_STORE_UNAVAILABLE",
        "message": "无法保存本机配置，请检查当前用户权限。",
        "retryable": false,
        "requestId": "uuid",
        "details": {},
        "recommendedAction": "CHECK_LOCAL_CONFIGURATION"
      }
    }

details 只允许既有安全标量，recommendedAction 由错误类型映射而来；任何 Key、堆栈、完整请求正文和供应商原始响应都不得出现。

## 不包含的范围

- 不调用真实模型、不实现 Provider Gateway；
- 不实现 Launcher、一次性启动令牌、HttpOnly 会话或 CSRF；
- 不实现前端设置页面；本 Task 先提供后端可供一键配置页面调用的接口；
- 不实现多 Provider、多 Key 历史、Key 轮换和远程账户管理；
- 不写机器级环境变量，也不要求管理员权限。

## 验收标准

1. 测试覆盖环境变量 Key 的读取、新增、覆盖、删除和当前进程立即生效。
2. 工作区所有文本和 JSON 中都找不到测试 Key。
3. Provider 设置保存后可重新读取，Base URL 和数值范围按约束规范化或拒绝。
4. Settings API 的任何响应、验证错误和异常响应都不包含 Key。
5. AppError、请求验证错误和未预期异常都返回统一 ErrorEnvelope。
6. Task 5 领域/持久化回归、Ruff 和 mypy 继续通过。
