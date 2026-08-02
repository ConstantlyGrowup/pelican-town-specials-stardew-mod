# Task 6: Provider 设置、用户环境变量密钥与统一错误响应 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 实现后端 Provider Settings API：普通 Windows 用户可以由应用直接新增、更新和删除当前用户级 API Key；非机密 Provider 设置保存到工作区；所有相关错误使用统一且不泄露密钥的响应格式。

**Architecture:** 在 persistence 层新增可注入的 Windows 用户环境变量适配器和 Secret Store；在 application 层新增 Provider 设置模型与工作区 JSON 服务；在 API 层新增 settings 路由和统一异常处理器。应用工厂负责装配依赖，测试通过临时工作区和 fake environment adapter 隔离 Windows 注册表。

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, pydantic-settings, pytest, Ruff, mypy, 既有 atomic JSON workspace persistence.

**Status:** Secret Store、Provider Settings、Settings API、统一 ErrorEnvelope 和 create_app 装配已实现并通过用户验收；focused commit 已创建，当前等待下一 Task 授权。

## Global Constraints

- API Key 的唯一持久来源是当前 Windows 用户级环境变量 PTS_OPENAI_API_KEY；不写入 settings.json、workspace 文件、日志、异常详情、响应或 Git。
- set 操作同时写入当前用户环境和当前进程 os.environ；delete 操作同时清除两者，保存后无需重启即可生效。
- 用户级环境变量通过 Windows 系统接口实现，不使用 setx，不写机器级环境变量，也不要求管理员权限。
- Secret Store 不把 Key 写入 JSON 作为降级方案；底层读写失败必须转换为稳定的 AppError。
- apiKeyConfigured 和 apiKeySource 动态读取 Secret Store，不持久化到 settings.json。
- Task 6 不包含真实 Provider 调用、Launcher、前端页面、CSRF/会话、多 Provider、多 Key 历史或密钥轮换。
- 先写失败测试，再写实现；每个子任务完成后运行该子任务的 focused tests，并保持 Task 5 回归通过。
- 不在子任务中创建 commit；整个 Session 只在用户验收通过后创建一个 focused commit。

---

## Task 1: 环境变量适配器与 Secret Store

**Files:**

- Create: backend/src/pelican_town_specials/persistence/secret_store.py
- Create: backend/tests/persistence/test_secret_store.py
- Modify: backend/src/pelican_town_specials/domain/errors.py only if the existing AppError constructor needs a small compatible extension

### Step 1: Write the failing tests

Add a fake environment adapter with separate process and current-user stores. Cover:

- get returns a process value first;
- get falls back to the persisted current-user value;
- set creates a new current-user value and mirrors it into the process store;
- set replaces an existing value in both stores;
- delete removes both values and a later get returns no Key;
- current process lookup sees the new value immediately;
- an adapter write failure becomes AppError with code PTS_WORKSPACE_SECRET_STORE_UNAVAILABLE, HTTP 500, safe details, and no raw Key;
- the fake adapter can run on the non-Windows test environment without touching the real user registry.

Run:

    cd backend
    uv run pytest tests/persistence/test_secret_store.py -q

Expected result: the new tests fail because the Secret Store and adapter do not exist yet.

### Step 2: Implement the smallest environment abstraction

Define an EnvironmentAdapter protocol with process get/set/delete and current-user get/set/delete operations. Define a SecretValue alias using Pydantic SecretStr so callers do not accidentally serialize the plain value.

Implement a Windows environment adapter:

- process operations use os.environ;
- user operations use HKEY_CURRENT_USER\Environment through winreg;
- after a successful user write/delete, broadcast the standard Environment setting change so newly launched Windows processes can observe it;
- import or guard Windows-only facilities so module import and fake-adapter tests remain usable on non-Windows systems;
- never invoke a shell command or setx.

Implement WindowsEnvironmentSecretStore with:

    get_api_key() -> SecretValue | None
    set_api_key(value: SecretValue) -> None
    delete_api_key() -> None
    get_source() -> ApiKeySource

Use the fixed variable name PTS_OPENAI_API_KEY. Normalize blank values as absent, preserve the precedence process environment then current-user persisted environment, and keep an optional in-memory session value only for the source model. Endpoint writes in this Task always target the user environment. Convert registry/OS failures to the stable AppError without putting the secret into message or details.

### Step 3: Run focused verification

Run:

    cd backend
    uv run pytest tests/persistence/test_secret_store.py -q
    uv run ruff check src/pelican_town_specials/persistence/secret_store.py tests/persistence/test_secret_store.py

Confirm that the test fixture contains a sentinel Key only in memory and that no workspace file is created by the Secret Store tests.

---

## Task 2: Provider settings model and atomic workspace service

**Files:**

- Create: backend/src/pelican_town_specials/application/__init__.py
- Create: backend/src/pelican_town_specials/application/settings.py
- Create: backend/tests/application/__init__.py
- Create: backend/tests/application/test_settings.py
- Modify: backend/src/pelican_town_specials/config.py
- Modify: backend/src/pelican_town_specials/persistence/workspace.py only if a settings path property is useful for dependency wiring

### Step 1: Write the failing tests

Cover the settings service and its models:

- a new temporary workspace returns providerKind OPENAI_COMPATIBLE and the documented default base URL;
- model IDs are initially empty/unconfigured but a PUT payload must require 1–120 characters;
- saving a base URL removes only trailing slashes;
- chatTimeoutSeconds accepts 30–600 and rejects values outside that range;
- imageTimeoutSeconds accepts 60–900 and rejects values outside that range;
- maxAutomaticRetries accepts 0–3 and rejects values outside that range;
- unknown fields are rejected;
- after save, a new service instance reads the same settings from app-state/settings.json;
- the JSON file contains only non-secret settings and remains recoverable through the existing backup-aware reader when the primary file is invalid;
- settings writes use atomic_write_json and do not store apiKeyConfigured, apiKeySource, or the test Key.

Run:

    cd backend
    uv run pytest tests/application/test_settings.py -q

Expected result: tests fail because the models and service do not exist.

### Step 2: Implement settings models and service

Create strict camelCase API/storage models for:

- ProviderSettings: providerKind, baseUrl, visionModel, textModel, imageModel, chatTimeoutSeconds, imageTimeoutSeconds, maxAutomaticRetries;
- ProviderSettingsUpdate with required, non-empty model IDs and the same numeric constraints;
- ApiKeySource with ENVIRONMENT, SESSION, NONE;
- a response/view model that adds dynamic apiKeyConfigured and apiKeySource without changing the persisted document.

Use default base URL https://yibuapi.com/v1 and normalize trailing slashes before validation/persistence. Keep providerKind fixed to OPENAI_COMPATIBLE. Store the document at WorkspacePaths.app_state_dir / settings.json through atomic_write_json and read_json_with_backup. If the settings document does not exist, return the documented defaults; do not create a secret fallback file.

Add an application service that accepts WorkspacePaths and a Secret Store dependency, loads/saves non-secret settings, and builds the public provider view by querying the Secret Store on every read. Map invalid/corrupt settings and persistence failures to safe AppError codes without exposing file contents.

Extend AppConfig only as needed to provide a deterministic default workspace root under the current user application data directory and allow PTS_WORKSPACE_PATH to override it for the running application. Keep existing health tests independent from an actual user workspace by allowing app-factory dependency injection.

### Step 3: Run focused verification

Run:

    cd backend
    uv run pytest tests/application/test_settings.py tests/persistence/test_atomic.py tests/persistence/test_workspace_migration.py -q
    uv run ruff check src/pelican_town_specials/application tests/application src/pelican_town_specials/config.py

Inspect the temporary workspace after save and confirm no Key or key-like field is present in any JSON.

---

## Task 3: Settings API routes and application wiring

**Files:**

- Create: backend/src/pelican_town_specials/api/routes/settings.py
- Create: backend/tests/api/test_settings.py
- Modify: backend/src/pelican_town_specials/api/app.py
- Modify: backend/src/pelican_town_specials/api/routes/__init__.py only if route exports are needed

### Step 1: Write the failing API contract tests

Build a TestClient with a temporary WorkspacePaths and fake Secret Store. Cover:

- GET /api/v1/settings/provider returns non-secret settings plus apiKeyConfigured and apiKeySource;
- PUT /api/v1/settings/provider persists valid non-secret settings and GET returns them;
- PUT /api/v1/settings/provider/key creates a Key and returns only configuration status/source;
- repeating the same endpoint updates the current-user value and remains immediately readable by the fake process store;
- DELETE /api/v1/settings/provider/key removes the Key and returns unconfigured status;
- no successful response contains the sentinel Key, including nested fields and headers;
- invalid settings and invalid Key input return the unified error shape;
- the existing /api/v1/health contract remains unchanged.

Run:

    cd backend
    uv run pytest tests/api/test_settings.py tests/api/test_health.py -q

Expected result: the new route tests fail because the router and dependency wiring do not exist.

### Step 2: Implement routes and dependency injection

Add:

- GET /settings/provider;
- PUT /settings/provider;
- PUT /settings/provider/key with a request model containing a SecretStr apiKey;
- DELETE /settings/provider/key.

Never echo the request model for validation errors. The key endpoint response should contain only apiKeyConfigured and apiKeySource (plus the standard success response shape if one is introduced), never the SecretStr value. Use app.state dependencies or explicit factory parameters so tests can provide a temporary workspace and fake Secret Store while production uses WindowsEnvironmentSecretStore and the configured default workspace.

Register the settings router under /api/v1 without changing the health route. Ensure a settings service is created per request or cached only with immutable dependency references; a Key update must be visible to the next request in the same process.

### Step 3: Run focused verification

Run:

    cd backend
    uv run pytest tests/api/test_settings.py tests/api/test_health.py -q
    uv run ruff check src/pelican_town_specials/api tests/api

Search the generated response bodies and captured exception text in tests for the sentinel Key and assert it is absent.

---

## Task 4: Unified error envelope and exception handlers

**Files:**

- Create: backend/src/pelican_town_specials/api/error_handlers.py
- Create: backend/tests/api/test_error_envelope.py
- Modify: backend/src/pelican_town_specials/api/app.py
- Modify: backend/src/pelican_town_specials/domain/errors.py only if a compatible error field is required

### Step 1: Write the failing tests

Cover three failure classes:

- a route raises AppError and the response preserves its HTTP status and stable code;
- FastAPI request validation returns the same envelope with a safe input-validation code and does not echo the submitted Key or full body;
- a route raises an unexpected exception and receives HTTP 500, code PTS_SYSTEM_UNEXPECTED, a UUID requestId, empty/safe details, and no traceback in the response.

Also assert that every envelope contains error.code, message, retryable, requestId, details, and recommendedAction, and that requestId is a UUID4.

Run:

    cd backend
    uv run pytest tests/api/test_error_envelope.py -q

Expected result: tests fail because FastAPI still emits its default validation and exception responses.

### Step 2: Implement the handlers

Create a stable ErrorEnvelope serializer. Add handlers for:

- AppError: use the exception status/code/message/retryable/details, sanitize details through the existing safe-detail rules, and map a recommendedAction from the stable code;
- RequestValidationError: emit a generic input error, preserve only safe field locations if useful, and strip submitted values;
- Exception: log server-side with requestId but return only PTS_SYSTEM_UNEXPECTED and a safe action.

Generate requestId at the boundary, use UTC occurred-at only if the public envelope requires it, and do not include stack traces, request bodies, provider raw responses, or SecretStr representations in the response. Register all handlers from create_app so both tests and the exported module-level app use the same behavior.

### Step 3: Run focused verification

Run:

    cd backend
    uv run pytest tests/api/test_error_envelope.py tests/api/test_settings.py tests/api/test_health.py -q
    uv run ruff check src/pelican_town_specials/api src/pelican_town_specials/domain/errors.py tests/api

Review every error response assertion for the absence of the sentinel Key.

---

## Task 5: Dependency cleanup, documentation sync, and full verification

**Files:**

- Modify: backend/pyproject.toml to remove the no-longer-used keyring runtime dependency
- Modify: docs/architecture/MVP_TECHNICAL_DESIGN.md
- Modify: docs/plans/MVP_IMPLEMENTATION_PLAN.md
- Modify: StarValleyCook_项目设计源索引与状态快照.md
- Modify: AGENTS.md
- Modify: docs/development/STATUS.md
- Modify: docs/development/sessions/2026-08-02-task-6-provider-settings.md

### Step 1: Write or update regression checks before cleanup

Add a small dependency/configuration assertion if the existing test layout has a suitable place; otherwise use repository checks to ensure:

- keyring is not a runtime dependency;
- no implementation path imports keyring;
- formal design, implementation plan, source index, STATUS, and Session record all describe current-user environment storage and the actual Task6 scope;
- uv remains only the project development/dependency execution tool, not an application feature or user-facing manual configuration step.

### Step 2: Apply documentation and configuration changes

Remove keyring from backend runtime dependencies. Keep existing uv/lockfile policy unchanged. Update the Task6 records after implementation so they name actual files, tests, behavior, limitations, and the next acceptance state. Preserve ignored status of formal design sources while keeping their content synchronized with the approved design.

### Step 3: Run the full verification suite

From backend, run:

    uv run pytest -q
    uv run ruff check src tests
    uv run mypy src

Run repository checks:

    git diff --check
    rg -n -i "PTS_OPENAI_API_KEY|apiKey|api_key|keyring|Credential Locker" backend/src backend/tests docs AGENTS.md README.md

Manually inspect that:

- the API starts and /api/v1/health remains 200;
- a temporary workspace contains no Key after add, update, or delete;
- the current process sees an updated Key without restart;
- successful and failed settings requests never return the Key.

Only after all checks pass should the Session move to verification/awaiting_user_acceptance. Do not commit or push before explicit user acceptance.
