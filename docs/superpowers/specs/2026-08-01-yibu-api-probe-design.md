# 一步 API 模型能力测试页设计规格

## 状态与范围

- 日期：2026-08-01
- 状态：已获用户设计确认，已实现；用户已报告真实 Yibu 核心链路成功，辅助 Session 仍等待验收
- 产物类型：`samples` 下的独立 provider smoke test
- 不属于 MVP Task，不修改正式前端、后端、领域模型、工作区或开发状态控制面

本样例用于记录一步 API 的两段能力链路：先用多模态文本模型根据用户图片和一句话生成可直接交给图像模型的编辑指令，再将 Prompt 与原图提交到已由用户手动走通的 `/images/edits` 图像编辑路径。当前成功案例使用 `gpt-image-2-max`；`/images/generations` 保留为可显式尝试的比较模式，不视为本次用户实测已经冻结的生产路径。

## 已确认的外部接口

中转站 Base URL 默认使用 `https://yibuapi.com/v1`，鉴权为 `Authorization: Bearer <API Key>`。

文本阶段使用 `POST /chat/completions`，请求包含 `messages`、多模态 `image_url` data URL 和 `reasoning_effort`。默认模型为 `gpt-5.6-luna`，默认推理强度为 `high`。

用户手动成功的图像阶段使用 `POST /images/edits`，通过 multipart 传入原图、Prompt 和模型参数。当前调用案例使用 `gpt-image-2-max`，并成功使用 `size=3840x2160`；OpenAI SDK 案例从 `data[0].b64_json` 解码结果图：

```python
result = client.images.edit(
    model="gpt-image-2-max",
    image=image_files,
    prompt=prompt,
    size="3840x2160",
)
img_data = base64.b64decode(result.data[0].b64_json)
```

当前样例的页面还提供 `quality`、`response_format`、`output_format`、尺寸档位和比例等参数变体；除用户报告的成功案例外，这些组合仍需逐项记录兼容性。样例记录含 `pro` 的图像模型会返回 500，因此不再把 `gpt-image-2-pro` 作为默认或 fallback。

图像编辑是当前推荐模式；失败必须原样展示脱敏后的供应商错误，不自动切换模型或伪造成功。`/images/generations` 仍可作为显式实验模式，但真实兼容性不能从图像编辑能力推断。

参考资料：

- [一步 API：gpt-image-2 示例页](https://yibuapi.apifox.cn/6547503m0)
- [一步 API：OpenAI Chat Completions 格式](https://yibuapi.apifox.cn/6777323m0)
- [一步 API：OpenAI Images 格式](https://yibuapi.apifox.cn/6777336m0)

## 用户实测记录（2026-08-01）

用户报告已在下午通过本地调用案例成功走通：

- OpenAI-compatible 多模态 Chat Completions；
- 原图 + Prompt → `gpt-image-2-max` `/images/edits`；
- 成功案例包含 `size=3840x2160`，并从 `b64_json` 取回结果图；
- 多图调用案例支持本地路径或 HTTP URL，最多 10 张。

该记录用于校准后续正式 Model Gateway 的请求形状，不冻结 MVP 最终模型、图像生成端点、JSON Schema、限流或费用策略。

## 方案选择

### 方案 A：纯 HTML 直接请求中转站

实现最少，但必须把 Key 放入浏览器输入框或前端代码；Key 会出现在浏览器进程、开发者工具和网络请求中，还依赖中转站 CORS。放弃。

### 方案 B：本地标准库 Python 代理 + 单页 HTML（采用）

HTML 只请求同源本地服务；本地服务从进程环境变量读取 Key，并负责请求格式转换、错误脱敏和图片响应归一化。无需安装依赖，适合一次性能力测试，也为未来正式 Model Gateway 保留清楚的边界。

### 方案 C：直接创建 MVP 的 FastAPI/React 骨架

与未来产品形态接近，但会启动正式产品实现、引入依赖和扩大本次验证范围，违反当前项目仍处于产品开发前的控制面约束。放弃。

## 文件边界

```text
samples/yibu-api-probe/
├─ index.html       # 单页 UI、样式与浏览器端交互
├─ server.py        # 无依赖本地代理和静态文件服务
├─ run.ps1          # 安全读取 Key，设置默认配置并启动 server.py
├─ .env.example     # 仅记录变量名和非机密默认值，不含真实 Key
└─ README.md        # 启动、配置、接口模式和费用提醒
```

不创建 `requirements.txt`、Node 工程、数据库、持久化工作区或正式 `backend/`、`frontend/` 目录。

## API Key 与配置

Key 只通过当前服务进程的 `PTS_OPENAI_API_KEY` 环境变量提供。`run.ps1` 使用 PowerShell `Read-Host -AsSecureString` 读取 Key，再转换为子进程可用的环境变量；服务退出后清除当前 PowerShell 环境中的 Key。HTML、仓库文件、URL、日志、响应和前端状态都不保存或返回完整 Key。

非机密配置使用项目约定的 `PTS_` 前缀：

| 变量 | 默认值 | 作用 |
|---|---|---|
| `PTS_OPENAI_BASE_URL` | `https://yibuapi.com/v1` | 中转站兼容 Base URL |
| `PTS_TEXT_MODEL` | `gpt-5.6-luna` | Prompt 生成模型 |
| `PTS_TEXT_REASONING_EFFORT` | `high` | 文本模型推理强度 |
| `PTS_IMAGE_MODEL` | `gpt-image-2-max` | 已实测编辑路径的默认候选模型 |
| `PTS_IMAGE_SIZE` | `3840x2160` | 文档示例尺寸 |
| `PTS_IMAGE_RESPONSE_FORMAT` | `url` | URL 或 `b64_json` 的显式返回形式 |
| `PTS_IMAGE_QUALITY` | 空 | 仅 max 模式可设置，例如 `high` |
| `PTS_CHAT_TIMEOUT_SECONDS` | `120` | 文本调用超时 |
| `PTS_IMAGE_TIMEOUT_SECONDS` | `600` | 图像调用超时 |
| `PTS_MAX_UPLOAD_BYTES` | `10485760` | 浏览器和代理的本地图片上限 |

代理允许在未配置 Key 时启动，以便页面显示连接状态和配置提示；真正调用 provider 前才校验 Key 并拒绝空鉴权请求。代理不调用 `/models`，避免把中转站的模型列表能力误当成兼容性证明。

## 页面结构与交互

页面分为四块：

1. **连接状态**：显示本地服务、Base URL、文本模型、图像模型、当前模式和 `apiKeyConfigured` 布尔状态；不显示 Key。
2. **输入区**：图片选择、图片预览和一句话编辑需求。接受 PNG/JPEG/WEBP，前端先检查 MIME 和大小。
3. **Prompt 区**：按钮“生成编辑指令”调用多模态文本阶段；生成后填入可编辑文本框，用户可以修改后再生成图片。显示本次调用耗时、模型和 usage（若供应商返回）。
4. **结果区**：模式选择默认为“图生图编辑”，另有“从文本生成”选项；显示阶段状态、结果图、临时 URL 提醒、revised prompt/usage 和脱敏错误详情。

默认工作流：

```text
上传图片 + 一句话
        │
        ▼
gpt-5.6-luna /chat/completions
        │  multimodal image_url + reasoning_effort=high
        ▼
可编辑的图像 Prompt
        │
        ├─ 图生图编辑（默认，已由用户实测）
        │       ▼
        │  gpt-image-2-max /images/edits
        │       │  原图 + Prompt + size=3840x2160
        │       ▼
        │  b64_json 结果图或供应商错误
        │
        └─ 从文本生成（显式实验）
                ▼
           <configured image model> /images/generations
                │  仅 Prompt
                ▼
           按实际兼容性展示结果或脱敏错误
```

Prompt 生成器的固定指令要求模型：理解原图、结合用户的一句话、保留未被要求修改的主体和构图、补全风格/光线/镜头/材质等视觉细节，并且只返回一段可直接用于图像模型的 Prompt，不返回解释或 Markdown 代码围栏。页面允许用户在第二阶段前修改该 Prompt。

## 本地代理 API

### `GET /api/health`

返回非机密运行状态：

```json
{
  "ok": true,
  "apiKeyConfigured": true,
  "baseUrl": "https://yibuapi.com/v1",
  "textModel": "gpt-5.6-luna",
  "imageModel": "gpt-image-2-max",
  "imageSize": "3840x2160",
  "imageResponseFormat": "url",
  "maxUploadBytes": 10485760
}
```

### `POST /api/prompt`

请求为本地 JSON：

```json
{
  "imageDataUrl": "data:image/png;base64,...",
  "userInstruction": "把背景改成黄昏，并保留主体",
  "reasoningEffort": "high"
}
```

代理把它转换为 OpenAI-compatible Chat Completions 请求。返回生成的 Prompt、模型、耗时和可用 usage；不返回完整上游响应中的私人内容。

### `POST /api/image`

请求为本地 JSON：

```json
{
  "imageDataUrl": "data:image/png;base64,...",
  "prompt": "<用户检查后的 Prompt>",
  "mode": "generate"
}
```

`mode=generate` 转成 `/images/generations` JSON；`mode=edit` 转成 `/images/edits` multipart。两种模式都固定 `n=1`。代理统一归一化 `data[0].url` 和 `data[0].b64_json`：前者返回临时 URL，后者返回内存中的 data URL；不写磁盘。

## 错误与安全处理

- Key 缺失：页面仍可打开并显示未配置状态；调用前提示设置 `PTS_OPENAI_API_KEY`，不向供应商发空鉴权请求。
- 400/401/403/408/429/5xx：保留供应商 HTTP 状态和脱敏错误正文；本样例不自动重试，避免测试中重复计费。
- 错误脱敏：过滤 `Authorization`、Bearer token、常见 `sk-...` 片段和环境变量值；不记录请求体、图片 data URL、完整 Prompt 或完整模型响应。
- 上传限制：仅允许 PNG/JPEG/WEBP，默认不超过 10 MiB；拒绝空图片、空指令和过长 Prompt。
- URL 结果：页面直接展示供应商返回的临时 URL，并明确提示有效期由供应商决定；本样例不把 URL 当作永久资产。
- 资源生命周期：图片和 Prompt 只存在于浏览器内存与当前 HTTP 请求，不写工作区、不写缓存、不生成诊断包。
- 本地服务默认只监听 `127.0.0.1`，不对局域网开放。

## 验证计划

### 不产生模型费用的自动检查

- `python -m py_compile samples/yibu-api-probe/server.py`
- 本地静态文件和路由检查：无 Key 时 `/api/health` 不泄露密钥；未知路径返回 404。
- 使用标准库 fake provider 验证：
  - 文本请求路径不重复 `/v1`；
  - 多模态 `image_url`、模型 ID 和 `reasoning_effort` 正确；
  - max 编辑请求包含 multipart 原图、Prompt、`size` 和 `n=1`；
  - format/quality 配置只在显式设置时发送，并记录真实兼容结果；
  - `url`/`b64_json` 两种响应都能归一化；
  - 供应商错误脱敏后不包含 Key、图片 data URL 或 Bearer token。

### 真实中转站人工验证

用户已报告使用本地 Key 启动 `run.ps1` 并成功完成：

1. 连接状态显示已配置但不显示 Key；
2. 上传一张测试图片并生成 Prompt；
3. max 模式编辑一张或多张原图，并得到结果图；
4. 记录 `size=3840x2160` 和 `b64_json` 返回路径；
5. 停止服务后确认 Key 环境变量被清除，并用 `rg` 检查样例目录没有真实 Key。

`/images/generations`、质量/格式组合和其他模型仍需未来显式验证；真实调用可能产生费用，自动测试不调用真实供应商。

真实调用可能产生费用；自动测试不调用真实供应商。

## 明确不包含的内容

- 不实现 MVP 的 FastAPI、React、Credential Locker、JSON 工作区、会话 Cookie、生成编排或正式 Model Gateway。
- 不保存用户图片、Prompt、模型结果、临时 URL 或调用历史。
- 不自动切换模型、不把失败模型静默替换为 `gpt-image-2-max`，不把图像编辑失败伪装成文生图成功。
- 不执行 Git push、自动发布或修改 MVP 设计/实施计划。

## 验收标准

当以下条件全部满足时，样例任务视为完成：

1. 按 README 的 PowerShell 步骤可以启动本地页面，Key 不进入仓库和 HTML。
2. 页面能完成上传图片 → 多模态 Prompt → 用户编辑 → max 图像编辑的闭环。
3. max 编辑请求参数与用户提供的成功案例一致，并能归一化 `b64_json` 结果。
4. quality/format/尺寸/比例是显式配置项，真实兼容结果不被猜测或静默 fallback。
5. `/images/generations` 作为单独实验路径真实报告供应商是否接受请求，而不是从编辑能力猜测兼容。
6. 自动检查通过，且真实人工验证的结果、费用风险和未支持能力在交付说明中明确记录。
