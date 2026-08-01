# 一步 API 模型能力测试页

这是一个独立的本地 provider smoke test，不属于正式 MVP。它验证两段能力：

1. 上传图片和一句话 → `gpt-5.6-luna` 多模态 Chat Completions → 可编辑的图像 Prompt；
2. 原图 + Prompt → 图像模型 Images Edits → 结果图。

中转站只分流两个图像模型：`gpt-image-2` 与 `gpt-image-2-max`。**任何包含 `pro` 的模型名都会直接返回 500**，所以页面下拉框只提供这两个，不出现 `gpt-image-2-pro`。图生图走 `POST /images/edits`（multipart），请求携带 `response_format=url` 与 `quality=high`（参考用户给出的调用样例）。

## 启动

在 PowerShell 中运行：

```powershell
Set-Location 'G:\AI-attempt\starvalley-cook\samples\yibu-api-probe'
.\run.ps1
```

脚本会隐藏读取 API Key，然后打开本地服务。浏览器访问：

```text
http://127.0.0.1:8765
```

如果 PowerShell 禁止执行脚本，可以只对当前命令临时放宽：

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

Key 会暂存在执行 `run.ps1` 的 PowerShell 进程环境，并被 Python 子进程继承；脚本结束时会清除当前 PowerShell 环境中的 Key。不要在共享终端中使用真实 Key，也不要把 Key 填入 `index.html`、`.env.example` 或任何请求 URL。

## 默认 API 配置

| 配置 | 默认值 |
|---|---|
| Base URL | `https://yibuapi.com/v1` |
| 文本模型 | `gpt-5.6-luna` |
| 推理强度 | `high` |
| 图像模型 | `gpt-image-2-max`（中转站支持的两个模型之一） |
| 图像端点 | `/images/edits`（图生图，multipart） |
| 输出尺寸 | `2560x2560`（2K · 1:1，可切换档位 1K/2K/4K 与比例 1:1/16:9/9:16/4:3/3:4） |
| 格式参数 | `response_format=url`（默认发，大图用 URL 比内嵌 base64 更稳） |
| `quality` | `high`（默认发，gpt-image-2 与 gpt-image-2-max 都支持） |

这些设置可在启动服务前通过 `PTS_` 环境变量覆盖。`.env.example` 只列出变量名称和默认值，不会被脚本自动读取，也不包含真实 Key。

### 尺寸与比例说明

页面把“分辨率档位”和“比例”分开选择，最终像素尺寸由两者换算：

- 分辨率档位（长边像素）：1K → 1280、2K → 2560（默认）、4K → 3840
- 比例：1:1（默认，方形）、16:9、9:16、4:3、3:4

换算规则：横向比例以档位为宽、按比例算高；竖向比例以档位为高、按比例算宽。16:9 行与历史上的 1K/2K/4K 值一致，其中 4K=3840x2160 已在成功案例实测合法：

- 2K · 1:1 → `2560x2560`（默认）
- 2K · 16:9 → `2560x1440`
- 4K · 16:9 → `3840x2160`
- 4K · 1:1 → `3840x3840`（总面积大于已实测的 4K 16:9，若报 “size not supported” 先降到 2K）

可用环境变量覆盖默认档位与比例：`PTS_IMAGE_SIZE_TIER`（1K/2K/4K）与 `PTS_IMAGE_ASPECT_RATIO`（1:1/16:9/9:16/4:3/3:4）。

### 格式参数说明（`PTS_IMAGE_RESPONSE_FORMAT`）

默认 `url`，即请求携带 `response_format=url`，中转站返回图片临时 URL。可选值：

- `url` / `b64_json` → 作为 `response_format` 发送；
- `png` / `jpeg` / `webp` → 作为 `output_format` 发送（GPT 图像模型风格）；
- `auto` → 不发送任何 format 参数（让服务端按默认返回，通常是 b64_json）。

请求中最多只会出现其中一个参数。

### 质量参数（`quality`，默认开启）

两个图像模型都支持 `quality` 字段，默认 `high`，每次请求都会发送。需要改时通过环境变量：

```powershell
$env:PTS_IMAGE_QUALITY = 'medium'   # 或 low / high
.\run.ps1
```

## 页面操作

1. 上传 PNG、JPEG 或 WEBP 图片；默认上限 10 MiB。
2. 写一句图片修改需求，选择文本模型推理强度，点击“生成编辑指令”。
3. 检查并按需修改 Prompt。
4. 选择图像模型（`gpt-image-2` / `gpt-image-2-max`）、输出尺寸（1K/2K/4K，默认 2K）、输出比例（默认 1:1）和模式（默认“图生图编辑”），点击“生成图片” → 原图、Prompt、quality=high 一起发到 `/images/edits`。
5. 如需测试纯文本生成（无原图参与），切换到“从文本生成”模式。

图生图请求是 multipart/form-data，包含 `model`、`prompt`、`image`（原图）、`size`、`n=1`、`response_format=url` 和 `quality=high`。结果以临时 URL 返回，页面直接展示。

## 注意事项

- 中转站只接受 `gpt-image-2` 与 `gpt-image-2-max`；含 `pro` 的模型名会直接 500，页面下拉框已排除。
- `quality=high` 默认发送，两个模型都支持；不需要时把 `PTS_IMAGE_QUALITY` 设为空串或 `auto` 行为由配置决定。
- 案例脚本支持一次最多 10 张图片；本页面当前是单图流程，多图整合可参考 `gpt-image-2-edit-multi*.py` 直接调用。
- 真实文本和图像调用可能产生费用；自动测试只使用 fake provider，不会访问中转站。
- 本地服务只监听 `127.0.0.1`。
- 图片、Prompt、结果 URL 和模型响应只在当前请求/页面内存中使用，不写工作区、不写日志、不保存历史。
- 这个样例没有 Credential Locker、登录、数据库、React、FastAPI 或正式 Model Gateway。
