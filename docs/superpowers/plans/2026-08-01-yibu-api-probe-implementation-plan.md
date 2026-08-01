# 一步 API 模型能力测试页 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `samples/yibu-api-probe/` 建立一个无外部依赖的本地测试页，记录 `gpt-5.6-luna` 多模态 Prompt 生成和用户已手动走通的 `gpt-image-2-max` 原图编辑接口，并保留可显式尝试的图像生成路径。

**Architecture:** 单页 HTML 只调用本机 `127.0.0.1` 的 Python 标准库 HTTP 服务；服务读取当前进程的 `PTS_OPENAI_API_KEY`，把本地请求转换成 OpenAI-compatible Chat Completions、Images Generations 和 Images Edits 请求，并在内存中归一化响应。默认路径使用用户实测的 `gpt-image-2-max` `/images/edits`，支持原图、Prompt、尺寸和质量/格式配置；`/images/generations` 只作为显式比较模式，不把 `gpt-image-2-pro` 作为默认或 fallback。

**Tech Stack:** Python 3.13 标准库（`http.server`、`urllib.request`、`unittest`）、单文件 HTML/CSS/JavaScript、PowerShell 启动脚本。

## Global Constraints

- 只创建 `samples/yibu-api-probe/` 和本设计/计划文件，并按项目规则同步本 Session 的状态记录；不创建正式 `backend/`、`frontend/`、Node 工程或 MVP Task 文件。
- API Key 只通过当前进程的 `PTS_OPENAI_API_KEY` 注入；不得写入 HTML、日志、响应、测试快照、Prompt、图片或 Git。
- 默认 `PTS_IMAGE_MODEL=gpt-image-2-max`，默认模式为 `/images/edits`；不要把 `gpt-image-2-pro` 作为默认或 fallback。
- 默认图像编辑请求必须为 multipart `/images/edits`、原图 + Prompt、`size`、`n=1`；`response_format`/`output_format`/`quality` 仅按显式配置发送。
- 文本请求使用 `gpt-5.6-luna`、多模态 `image_url` data URL 和 `reasoning_effort=high`。
- 本地服务只监听 `127.0.0.1`；图片和 Prompt 只留在内存，不写磁盘、不保存历史。
- 本样例不自动重试真实模型请求；自动测试使用 fake provider，不产生模型费用。
- 每个任务都运行自己的检查，但遵守项目规则：用户验收前不创建中间 Git commit；最终只创建一个 focused commit，不 push。

---

## 文件结构与职责

```text
samples/yibu-api-probe/
├─ index.html                 # UI、样式、浏览器端状态和 fetch 调用
├─ server.py                  # 配置、纯请求构造、provider client、HTTP 路由
├─ test_server.py             # 标准库单元/集成测试，动态加载 server.py
├─ run.ps1                    # 隐藏读取 Key，注入非机密配置并启动服务
├─ .env.example               # 变量说明，不含真实 Key
└─ README.md                  # 启动、费用和两种图像模式说明
```

`server.py` 对后续代码暴露这些稳定接口：

```python
@dataclass(frozen=True)
class AppConfig:
    base_url: str
    api_key: str | None
    text_model: str
    text_reasoning_effort: str
    image_model: str
    image_size: str
    image_response_format: str
    image_quality: str | None
    chat_timeout_seconds: float
    image_timeout_seconds: float
    max_upload_bytes: int

def load_config(environ: Mapping[str, str] | None = None) -> AppConfig:
    """Load non-secret settings and an optional in-process API key."""
    raise NotImplementedError

def parse_data_url(value: str, max_bytes: int) -> tuple[str, bytes]:
    """Decode one supported image data URL without writing it to disk."""
    raise NotImplementedError

def redact_text(value: str, secrets: Iterable[str]) -> str:
    """Remove API credentials and bearer tokens from provider text."""
    raise NotImplementedError

class ProviderClient:
    def create_prompt(self, image_data_url: str, user_instruction: str, reasoning_effort: str) -> dict:
        raise NotImplementedError

    def generate_image(self, prompt: str) -> dict:
        raise NotImplementedError

    def edit_image(self, image_bytes: bytes, mime_type: str, prompt: str) -> dict:
        raise NotImplementedError
```

## Task 1: 配置、data URL 校验与脱敏纯函数

**Files:**
- Create: `samples/yibu-api-probe/test_server.py`
- Create: `samples/yibu-api-probe/server.py`

**Interfaces:**
- Consumes: 进程环境变量映射。
- Produces: `AppConfig`、`load_config`、`parse_data_url`、`redact_text`，供 provider client 和 HTTP 路由复用。

- [ ] **Step 1: 写失败测试，锁定默认配置和密钥边界**

在 `test_server.py` 用 `importlib.util.spec_from_file_location` 动态加载带连字符目录中的 `server.py`，先写以下测试：

```python
def test_default_config_uses_max_high_quality_url_and_2k(server):
    config = server.load_config({"PTS_OPENAI_API_KEY": "sk-test"})
    assert config.base_url == "https://yibuapi.com/v1"
    assert config.text_model == "gpt-5.6-luna"
    assert config.text_reasoning_effort == "high"
    assert config.image_model == "gpt-image-2-max"
    assert config.image_size == "2560x2560"
    assert config.image_response_format == "url"
    assert config.image_quality == "high"

def test_max_quality_is_opt_in(server):
    config = server.load_config({
        "PTS_OPENAI_API_KEY": "sk-test",
        "PTS_IMAGE_MODEL": "gpt-image-2-max",
        "PTS_IMAGE_QUALITY": "high",
        "PTS_IMAGE_RESPONSE_FORMAT": "b64_json",
    })
    assert config.image_model == "gpt-image-2-max"
    assert config.image_quality == "high"
    assert config.image_response_format == "b64_json"

def test_missing_key_keeps_health_available(server):
    config = server.load_config({})
    assert config.api_key is None
```

由于仓库不预设 pytest 依赖，测试实现使用 `unittest`；测试模块在文件顶部定义 `SAMPLE_DIR = Path(__file__).parent`，并通过 `load_server_module()` 返回动态加载的模块对象 `server`。provider 调用在 `api_key is None` 时必须抛出清晰的配置错误，但配置加载本身不能阻止健康检查启动。

- [ ] **Step 2: 运行失败测试，确认接口尚不存在**

Run:

```powershell
python -m unittest discover -s samples/yibu-api-probe -p "test_*.py" -v
```

Expected: FAIL，`server.py` 中尚未提供 `load_config` 或 `AppConfig`。

- [ ] **Step 3: 实现最小配置加载和输入校验**

在 `server.py` 实现 `AppConfig` 和 `load_config`：

```python
def load_config(environ=None):
    values = os.environ if environ is None else environ
    api_key = values.get("PTS_OPENAI_API_KEY", "").strip() or None
    return AppConfig(
        base_url=values.get("PTS_OPENAI_BASE_URL", "https://yibuapi.com/v1").rstrip("/"),
        api_key=api_key,
        text_model=values.get("PTS_TEXT_MODEL", "gpt-5.6-luna"),
        text_reasoning_effort=values.get("PTS_TEXT_REASONING_EFFORT", "high"),
        image_model=values.get("PTS_IMAGE_MODEL", "gpt-image-2-max"),
        image_size=values.get("PTS_IMAGE_SIZE", "2560x2560"),
        image_response_format=values.get("PTS_IMAGE_RESPONSE_FORMAT", "url"),
        image_quality=values.get("PTS_IMAGE_QUALITY", "high").strip() or None,
        chat_timeout_seconds=float(values.get("PTS_CHAT_TIMEOUT_SECONDS", "120")),
        image_timeout_seconds=float(values.get("PTS_IMAGE_TIMEOUT_SECONDS", "600")),
        max_upload_bytes=int(values.get("PTS_MAX_UPLOAD_BYTES", "10485760")),
    )
```

`parse_data_url` 只接受 `image/png`、`image/jpeg`、`image/webp`，严格解码 base64 并检查字节数；`redact_text` 替换传入的 Key、`Authorization: Bearer <token>` 和 `sk-` 形式片段。

- [ ] **Step 4: 运行配置与校验测试**

Run:

```powershell
python -m unittest discover -s samples/yibu-api-probe -p "test_*.py" -v
```

Expected: 配置、缺 Key、无效 MIME、超限图片和脱敏测试 PASS。

## Task 2: OpenAI-compatible 请求构造与响应归一化

**Files:**
- Modify: `samples/yibu-api-probe/server.py`
- Modify: `samples/yibu-api-probe/test_server.py`

**Interfaces:**
- Consumes: `AppConfig`、`parse_data_url`。
- Produces: `ProviderClient.create_prompt`、`generate_image`、`edit_image`；返回包含 `model`、`elapsedMs`、`prompt` 或图片数据、`usage`、`revisedPrompt` 的 JSON-compatible 字典。

- [ ] **Step 1: 写 fake provider 测试，先锁定三类上游请求**

用 `unittest.mock.patch.object(server.urllib.request, "urlopen")` 返回 fake HTTP response，断言请求；下面代码中的 `fake_urlopen` 是该 patch context 提供的 mock：

```python
def test_prompt_request_is_multimodal_and_uses_reasoning(server, fake_urlopen):
    client = server.ProviderClient(server.load_config({"PTS_OPENAI_API_KEY": "sk-test"}))
    client.create_prompt(
        "data:image/png;base64,aGVsbG8=",
        "把背景改成黄昏",
        "high",
    )
    request = fake_urlopen.call_args.args[0]
    assert request.full_url == "https://yibuapi.com/v1/chat/completions"
    assert request.get_header("Authorization") == "Bearer sk-test"
    body = json.loads(request.data)
    assert body["model"] == "gpt-5.6-luna"
    assert body["reasoning_effort"] == "high"
    assert body["messages"][1]["content"][1]["type"] == "image_url"

def test_generation_sends_url_and_high_quality_by_default(server, fake_urlopen):
    client = server.ProviderClient(server.load_config({"PTS_OPENAI_API_KEY": "sk-test"}))
    client.generate_image("cinematic sunset")
    body = json.loads(fake_urlopen.call_args.args[0].data)
    assert fake_urlopen.call_args.args[0].full_url.endswith("/images/generations")
    assert body == {
        "model": "gpt-image-2-max",
        "prompt": "cinematic sunset",
        "response_format": "url",
        "size": "2560x2560",
        "n": 1,
        "quality": "high",
    }
    assert body["quality"] == "high"

def test_max_generation_includes_configured_quality(server, fake_urlopen):
    config = server.load_config({
        "PTS_OPENAI_API_KEY": "sk-test",
        "PTS_IMAGE_MODEL": "gpt-image-2-max",
        "PTS_IMAGE_QUALITY": "high",
        "PTS_IMAGE_RESPONSE_FORMAT": "b64_json",
    })
    server.ProviderClient(config).generate_image("pixel art")
    body = json.loads(fake_urlopen.call_args.args[0].data)
    assert body["model"] == "gpt-image-2-max"
    assert body["quality"] == "high"
    assert body["response_format"] == "b64_json"
```

同时覆盖 Chat Completion 的字符串 `message.content`、分段内容数组、空 choices；覆盖图片响应的 `url` 和 `b64_json`，以及上游 401/429/500 错误中 Key 被脱敏。

- [ ] **Step 2: 运行 fake provider 测试，确认先失败**

Run:

```powershell
python -m unittest discover -s samples/yibu-api-probe -p "test_*.py" -v
```

Expected: FAIL，`ProviderClient` 尚未发送规定的请求。

- [ ] **Step 3: 实现 ProviderClient 和统一 URL/错误处理**

实现以下行为：

1. `base_url.rstrip("/")` 后拼接 `chat/completions`、`images/generations`、`images/edits`，保证 Base URL 已含 `/v1` 时不重复。
2. 所有上游请求带 `Content-Type: application/json`（生成/聊天）或标准 multipart Content-Type（编辑）和 `Authorization: Bearer <key>`。
3. Chat system 指令要求只输出一段可直接给图像模型的 Prompt；user content 为文本 + `image_url`，`detail` 使用 `high`。
4. generation 和 edit 都根据显式 image configuration 发送 format/quality；默认样例配置为 max、url、high，且不使用 pro fallback。
5. edit 使用 multipart 的 `image`、`prompt`、`model`、`n=1` 和当前图像配置；不把原图写临时文件。
6. `normalize_chat_response` 抽取文本；`normalize_image_response` 处理 `data[0].url` 和 `data[0].b64_json`，b64 结果在内存中包装为 `data:image/png;base64,<encoded-image>`。
7. 上游网络错误和非 2xx 响应转换为包含 `status_code` 与已脱敏 `detail` 的 `ProviderError`；不重试。

- [ ] **Step 4: 运行 provider 测试并检查请求体无泄露**

Run:

```powershell
python -m unittest discover -s samples/yibu-api-probe -p "test_*.py" -v
rg -n "sk-[A-Za-z0-9_-]{8,}|Bearer\s+sk-" samples/yibu-api-probe
```

Expected: 所有 fake provider 测试 PASS；第二条命令无输出。

## Task 3: 本地 HTTP 服务和三个 API 路由

**Files:**
- Modify: `samples/yibu-api-probe/server.py`
- Modify: `samples/yibu-api-probe/test_server.py`

**Interfaces:**
- Consumes: `AppConfig`、`ProviderClient`。
- Produces: `GET /api/health`、`POST /api/prompt`、`POST /api/image`、`GET /`，只监听 `127.0.0.1`。

- [ ] **Step 1: 写路由失败测试**

使用标准库 `ThreadingHTTPServer` 启动 handler，注入 fake `ProviderClient`。在测试模块定义 `RunningApp.get(path)` 和 `RunningApp.post(path, payload)` 两个辅助方法：它们用 `http.client.HTTPConnection` 请求测试端口，返回包含 `status`、`text` 和 `json` 属性的响应对象。`start_test_server(config, provider)` 负责启动线程并在测试结束时关闭服务。测试以下合同：

```python
def test_health_never_returns_api_key(server, running_app):
    response = running_app.get("/api/health")
    assert response.status == 200
    assert response.json["apiKeyConfigured"] is True
    assert "sk-test" not in response.text

def test_prompt_route_returns_generated_prompt(server, running_app):
    response = running_app.post("/api/prompt", {
        "imageDataUrl": "data:image/png;base64,aGVsbG8=",
        "userInstruction": "把背景改成黄昏",
        "reasoningEffort": "high",
    })
    assert response.status == 200
    assert response.json["prompt"] == "fake image prompt"

def test_image_route_selects_generation_mode(server, running_app):
    response = running_app.post("/api/image", {
        "imageDataUrl": "data:image/png;base64,aGVsbG8=",
        "prompt": "fake image prompt",
        "mode": "generate",
    })
    assert response.status == 200
    assert response.json["imageUrl"] == "https://example.test/result.png"
```

覆盖空字段、非法 mode、超限请求、provider error 和未知路径 404。

- [ ] **Step 2: 运行路由测试，确认失败**

Run:

```powershell
python -m unittest discover -s samples/yibu-api-probe -p "test_*.py" -v
```

Expected: FAIL，HTTP handler 和路由尚未存在。

- [ ] **Step 3: 实现本地 server**

实现 `ProbeRequestHandler`：

1. `GET /` 从 `index.html` 读取字节并返回 `text/html; charset=utf-8`；其他静态路径返回 404。
2. `GET /api/health` 只返回非机密配置和布尔 Key 状态。
3. `POST /api/prompt` 解析 JSON，检查 `imageDataUrl`、`userInstruction` 和可选 reasoning effort，调用 `ProviderClient.create_prompt`。
4. `POST /api/image` 解析 JSON，检查 `mode`、Prompt 和图片；`generate` 调 `generate_image`，`edit` 先解析 data URL 再调 `edit_image`。
5. 所有成功响应使用 JSON；错误使用 `{ "error": { "code": "<error-code>", "message": "<sanitized-message>" } }`，message 经过 `redact_text`。
6. 主入口 `main()` 读取 `PORT`（默认 8765），使用 `ThreadingHTTPServer(("127.0.0.1", port), handler_factory)`，捕获 Ctrl+C 并正常关闭。

- [ ] **Step 4: 运行服务级测试和语法检查**

Run:

```powershell
python -m unittest discover -s samples/yibu-api-probe -p "test_*.py" -v
python -m py_compile samples/yibu-api-probe/server.py
```

Expected: 路由、fake provider、输入校验和响应脱敏测试 PASS。

## Task 4: 单页 HTML 工作流

**Files:**
- Create: `samples/yibu-api-probe/index.html`
- Modify: `samples/yibu-api-probe/test_server.py`

**Interfaces:**
- Consumes: 本地 `/api/health`、`/api/prompt`、`/api/image`。
- Produces: 无 Key 输入框的四区测试界面，默认选择 `generate` 模式。

- [ ] **Step 1: 写静态页面检查**

先添加一个标准库测试，读取 `index.html` 后断言关键元素和安全边界：

```python
def test_index_contains_workflow_and_no_key_input(server):
    html = (SAMPLE_DIR / "index.html").read_text(encoding="utf-8")
    for text in ("生成编辑指令", "按文档生成", "尝试图像编辑", "/api/prompt", "/api/image"):
        assert text in html
    assert 'name="apiKey"' not in html
    assert "PTS_OPENAI_API_KEY" not in html
```

- [ ] **Step 2: 运行静态检查，确认页面尚不存在**

Run:

```powershell
python -m unittest discover -s samples/yibu-api-probe -p "test_*.py" -v
```

Expected: FAIL，`index.html` 尚未创建。

- [ ] **Step 3: 实现最小可用页面**

在单文件内实现：

1. 连接状态卡片：加载后 `fetch('/api/health')`，显示 Base URL、模型、尺寸和 `apiKeyConfigured`，隐藏 Key。
2. 图片选择：`accept="image/png,image/jpeg,image/webp"`，用 `FileReader.readAsDataURL` 保存内存中的 data URL、预览原图和本地大小检查。
3. 一句话输入和 reasoning effort 下拉框，默认 `high`。
4. “生成编辑指令”按钮：要求有图片和一句话，POST `/api/prompt`，将返回的 Prompt 放入可编辑 textarea，并显示耗时/usage。
5. 模式选择：默认 `generate`，另一个值为 `edit`；“生成图片”按钮 POST `/api/image`，传入原图 data URL、Prompt 和 mode。
6. 结果显示：优先使用 `imageDataUrl`，否则使用 `imageUrl`；显示 revised prompt、usage、耗时和“临时 URL”说明。
7. 所有按钮有 loading/disabled 状态；所有异常显示在页面错误区，不用 `alert`，不把请求 JSON 打印到 console。
8. 样式使用内联 CSS，保持桌面和窄屏可读；不引入 CDN、字体、图片或 JavaScript 依赖。

- [ ] **Step 4: 运行页面静态检查**

Run:

```powershell
python -m unittest discover -s samples/yibu-api-probe -p "test_*.py" -v
```

Expected: HTML 关键元素、安全边界和页面路由测试 PASS。

## Task 5: 安全启动脚本、配置说明与最终验证

**Files:**
- Create: `samples/yibu-api-probe/run.ps1`
- Create: `samples/yibu-api-probe/.env.example`
- Create: `samples/yibu-api-probe/README.md`
- Modify: `samples/yibu-api-probe/test_server.py`
- Modify: `docs/development/STATUS.md` and the current Session record

**Interfaces:**
- Consumes: `server.py` 的 `main()`、项目已有 `.gitignore` 对 `.env` 的忽略规则。
- Produces: 一条命令启动方式、非机密配置模板和人工验证清单。

- [ ] **Step 1: 写启动脚本/文档检查**

先添加文本测试，锁定以下内容：

```python
def test_runtime_files_document_safe_configuration(server):
    example = (SAMPLE_DIR / ".env.example").read_text(encoding="utf-8")
    runner = (SAMPLE_DIR / "run.ps1").read_text(encoding="utf-8")
    readme = (SAMPLE_DIR / "README.md").read_text(encoding="utf-8")
    assert "PTS_OPENAI_API_KEY" in example
    assert "Read-Host" in runner and "AsSecureString" in runner
    assert "gpt-image-2-max" in readme
    assert "quality" in readme
    assert "不" in readme
```

- [ ] **Step 2: 运行检查，确认辅助文件尚不存在**

Run:

```powershell
python -m unittest discover -s samples/yibu-api-probe -p "test_*.py" -v
```

Expected: FAIL，启动脚本或文档尚不存在。

- [ ] **Step 3: 实现 `run.ps1`、`.env.example` 和 `README.md`**

`run.ps1` 需要遵循以下行为：

```powershell
$secureKey = Read-Host '请输入一步 API Key' -AsSecureString
$env:PTS_OPENAI_API_KEY = [System.Net.NetworkCredential]::new('', $secureKey).Password
$env:PTS_OPENAI_BASE_URL = if ($env:PTS_OPENAI_BASE_URL) { $env:PTS_OPENAI_BASE_URL } else { 'https://yibuapi.com/v1' }
$env:PTS_TEXT_MODEL = if ($env:PTS_TEXT_MODEL) { $env:PTS_TEXT_MODEL } else { 'gpt-5.6-luna' }
$env:PTS_TEXT_REASONING_EFFORT = if ($env:PTS_TEXT_REASONING_EFFORT) { $env:PTS_TEXT_REASONING_EFFORT } else { 'high' }
$env:PTS_IMAGE_MODEL = if ($env:PTS_IMAGE_MODEL) { $env:PTS_IMAGE_MODEL } else { 'gpt-image-2-max' }
$env:PTS_IMAGE_SIZE_TIER = if ($env:PTS_IMAGE_SIZE_TIER) { $env:PTS_IMAGE_SIZE_TIER } else { '2K' }
$env:PTS_IMAGE_ASPECT_RATIO = if ($env:PTS_IMAGE_ASPECT_RATIO) { $env:PTS_IMAGE_ASPECT_RATIO } else { '1:1' }
$env:PTS_IMAGE_RESPONSE_FORMAT = if ($env:PTS_IMAGE_RESPONSE_FORMAT) { $env:PTS_IMAGE_RESPONSE_FORMAT } else { 'url' }
$env:PTS_IMAGE_QUALITY = if ($env:PTS_IMAGE_QUALITY) { $env:PTS_IMAGE_QUALITY } else { 'high' }
try {
    python .\server.py
}
finally {
    Remove-Item Env:PTS_OPENAI_API_KEY -ErrorAction SilentlyContinue
}
```

README 必须说明：默认 max 编辑路径来自用户成功案例；切换尺寸、`quality`、`response_format` 或 `output_format` 时记录实际兼容结果；`/images/generations` 是显式实验，真实调用可能计费；不把 Key 填进 HTML 或 `.env.example`。

- [ ] **Step 4: 运行全套本地验证**

Run:

```powershell
python -m unittest discover -s samples/yibu-api-probe -p "test_*.py" -v
python -m py_compile samples/yibu-api-probe/server.py
git diff --check
rg -n "sk-[A-Za-z0-9_-]{20,}|Bearer\s+[A-Za-z0-9._~+/=-]{20,}" samples/yibu-api-probe -g "!test_server.py"
```

Expected: 测试全部 PASS，编译和 diff 检查成功，密钥扫描无输出；真实 Yibu 调用不由自动检查执行。

- [ ] **Step 5: 运行无 Key 的本地 HTTP smoke test**

在一个 PowerShell 窗口启动一个临时 fake provider 和样例服务，使用 `Invoke-WebRequest` 访问：

```powershell
Invoke-WebRequest http://127.0.0.1:8765/ -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:8765/api/health -UseBasicParsing
```

Expected: 首页返回 `200 text/html`；健康检查在无 Key 时返回 `apiKeyConfigured=false` 且不泄露任何 secret；未知路径返回 404。

- [ ] **Step 6: 进行用户本地的真实人工验证**

用户已报告在自己的终端执行 `run.ps1` 并提供 Key，成功完成：连接状态、Prompt 生成、max 图像编辑、`size=3840x2160`/`b64_json` 案例和停止后 Key 清除。后续仍可显式验证 generation、quality/format 组合和其他模型；记录结果和供应商错误，但不把 Key、原图或完整模型响应复制回仓库。

## 完成前审查与提交边界

实现完成后，主 Agent 复核以下内容：

1. `server.py`、HTML、启动脚本和 README 与已确认设计规格一致。
2. 默认 max 编辑路径与用户成功案例一致；quality/format 只按配置发送，不能通过 pro fallback 隐藏失败。
3. 文本和图像路径均不会重复 Base URL 的 `/v1`。
4. 所有错误、健康状态和日志都不包含 Key、Bearer token、图片 data URL 或完整请求体。
5. 自动测试不访问真实 provider；真实验证仅由用户主动运行。
6. `git status --short` 只包含本次样例、设计/计划文件和本 Session 必需的状态同步；没有修改 MVP 文件。

用户验收验证结果后，创建唯一 focused commit：

```powershell
git add docs/development/STATUS.md docs/development/sessions/2026-08-01-yibu-api-probe.md docs/superpowers/specs/2026-08-01-yibu-api-probe-design.md docs/superpowers/plans/2026-08-01-yibu-api-probe-implementation-plan.md samples/yibu-api-probe
git commit -m "feat: add yibu API model probe"
```

提交后运行 `git status --short` 确认工作树干净；不执行 push。
