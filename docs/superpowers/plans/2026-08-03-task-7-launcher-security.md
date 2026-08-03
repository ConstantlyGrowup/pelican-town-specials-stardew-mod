# Task 7：Launcher、会话安全、同源静态托管与空闲退出 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让普通 Windows 用户通过 Launcher 双击启动本地应用，并让前端自动建立受保护的同源会话。

**Architecture:** 以可注入的内存 `SecurityState` 管理 launch token、session 和 CSRF；FastAPI 只绑定 loopback，将业务 API 保护在 session/Host/Origin/CSRF 校验之后。Launcher 用 `portalocker` 管理单实例，用可注入 OS 适配器选择端口、等待 health 和打开浏览器；前端从 fragment 完成 bootstrap，并只在内存保存 CSRF header。

**Tech Stack:** Python 3.13, FastAPI, Starlette, Uvicorn, portalocker, httpx, pytest, Ruff, mypy, React 19, TypeScript, Vite, Vitest, Testing Library。

## Global Constraints

- 只绑定 `127.0.0.1`，不提供 `0.0.0.0` 或机器级环境变量配置。
- launch token 只存在内存，TTL 60 秒，单次消费；token、Cookie、CSRF 不写日志、JSON、URL（bootstrap 后）或测试快照。
- 会话 Cookie 为 `HttpOnly`、`SameSite=Strict`、`Path=/`；CSRF 值只通过 `X-PTS-CSRF` 响应头交给前端并保存在页面内存。
- 健康检查、静态资源和 `/session/bootstrap` 不要求会话；其他 `/api/v1/**` 必须认证。
- 修改请求必须同时通过 loopback Host、Origin、session Cookie 和 CSRF header 检查；不注册 CORS。
- Launcher 只处理进程、端口、浏览器和运行记录，不读取 API Key 或业务记录。
- 默认空闲阈值为 600 秒；前端心跳间隔为 30 秒；测试必须通过时钟注入覆盖时间，不使用长时间 sleep。
- 前端必须保留现有开发入口：没有 launch fragment 时仍可渲染首页并执行 health probe。
- 每个子任务先写失败测试并观察预期失败，再写最小实现；本 Session 用户验收前不创建 commit。

---

### Task 1: 内存会话状态、认证依赖与 bootstrap API

**Files:**

- Create: `backend/src/pelican_town_specials/api/security.py`
- Create: `backend/src/pelican_town_specials/api/routes/session.py`
- Create: `backend/tests/api/test_session_security.py`
- Modify: `backend/src/pelican_town_specials/api/app.py`
- Modify: `backend/src/pelican_town_specials/api/error_handlers.py` only if stable auth recommended actions need mapping

**Interfaces:**

- `LaunchTokenStore.issue(now: float | None = None) -> str`
- `LaunchTokenStore.consume(token: str, now: float | None = None) -> bool`
- `SessionStore.create(now: float | None = None) -> SessionCredentials`
- `SessionStore.validate(session_id: str, now: float | None = None) -> SessionCredentials | None`
- `SessionStore.touch(session_id: str, now: float | None = None) -> None`
- `SecurityState.issue_launch_token() -> str`
- `POST /session/bootstrap` accepts `{"launchToken": str}`, returns 204, sets `PTS_SESSION` and `X-PTS-CSRF`
- `require_session(request: Request) -> SessionCredentials`
- `require_mutation_security(request: Request) -> SessionCredentials`

- [x] **Step 1: Write the failing security tests**

Add tests that use an injected allowed host and a fake clock. Cover:

```python
def test_bootstrap_sets_http_only_cookie_and_csrf_header(security_client) -> None:
    token = security_client.app.state.security.issue_launch_token()
    response = security_client.post(
        "/session/bootstrap",
        json={"launchToken": token},
        headers={"Host": "testserver"},
    )
    assert response.status_code == 204
    assert "pts_session=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    assert response.headers["x-pts-csrf"]
```

Also cover expired launch token, replayed token, missing session on settings GET, foreign Host, foreign Origin, missing/incorrect CSRF, and that the launch token never appears in response text or captured logs. The expected codes are `PTS_AUTH_LAUNCH_INVALID`, `PTS_AUTH_SESSION_REQUIRED`, `PTS_AUTH_HOST_INVALID`, `PTS_AUTH_ORIGIN_INVALID`, and `PTS_AUTH_CSRF_INVALID`.

- [x] **Step 2: Run the focused tests and verify the expected red failure**

Run:

```powershell
python -m pytest backend/tests/api/test_session_security.py -q -p no:cacheprovider
```

Expected: collection or assertion failure because the security module, bootstrap route, and app protection do not exist yet. Fix only test setup errors until the failure is about the missing behavior.

- [x] **Step 3: Implement the smallest in-memory security boundary**

Use `secrets.token_urlsafe`, an injected monotonic clock, and dictionaries keyed by opaque token/session values. Consume launch tokens atomically, reject tokens older than 60 seconds, and never log values. Register the bootstrap router outside `/api/v1`; protect `/api/v1/**` except health with dependencies or a narrow middleware. Return AppError codes without raw request values. Allow `testserver` only through an explicit test `SecurityConfig`; production defaults are `127.0.0.1` and `localhost`.

- [x] **Step 4: Run focused tests and the existing API regression**

Run:

```powershell
python -m pytest backend/tests/api/test_session_security.py backend/tests/api/test_health.py backend/tests/api/test_settings.py -q -p no:cacheprovider
python -m ruff check backend/src/pelican_town_specials/api backend/tests/api
python -m mypy backend/src
```

Expected: all focused and existing health/settings tests pass; no token or CSRF value appears in output.

---

### Task 2: 单实例锁、运行记录与端口/浏览器适配

**Files:**

- Create: `backend/src/pelican_town_specials/launcher/__init__.py`
- Create: `backend/src/pelican_town_specials/launcher/instance.py`
- Create: `backend/src/pelican_town_specials/launcher/runtime.py`
- Create: `backend/tests/launcher/__init__.py`
- Create: `backend/tests/launcher/test_instance.py`
- Create: `backend/tests/launcher/test_runtime.py`

**Interfaces:**

- `RuntimeRecord(pid: int, port: int, url: str, started_at: datetime)`
- `InstanceLock.acquire() -> bool`, `InstanceLock.release() -> None`, context-manager support
- `RuntimeRecordStore.read() -> RuntimeRecord | None`, `write(record) -> None`, `clear() -> None`
- `PortAllocator.reserve(preferred: Sequence[int]) -> PortReservation`；保留 `choose` 作为释放式兼容辅助
- `BrowserOpener.open(url: str) -> None`
- `HealthProbe.wait_until_ready(url: str, timeout_seconds: float) -> None`

- [x] **Step 1: Write failing lock and runtime tests**

Use a temporary application-data directory and fake PID/clock. Verify the first lock succeeds, a second lock reports contention without deleting the first lock, runtime records round-trip through atomic JSON, malformed records are rejected safely, and cleanup removes only the owned record. Verify port selection skips occupied preferred ports and falls back to an OS-assigned port through an injected socket factory. Verify the browser opener and health probe are injectable and do not launch processes in unit tests.

- [x] **Step 2: Run the launcher focused tests and observe the red failure**

```powershell
python -m pytest backend/tests/launcher/test_instance.py backend/tests/launcher/test_runtime.py -q -p no:cacheprovider
```

Expected: module or symbol-not-found failure before implementation.

- [x] **Step 3: Implement the minimal launcher state adapters**

Use `portalocker.Lock` for the lock file, write runtime JSON atomically, validate `pid`, `port`, loopback URL and UTC timestamp with Pydantic, and never remove a record owned by a different PID/port. Keep browser, socket and HTTP operations behind callables so tests remain deterministic.

- [x] **Step 4: Run focused launcher tests and static checks**

```powershell
python -m pytest backend/tests/launcher/test_instance.py backend/tests/launcher/test_runtime.py -q -p no:cacheprovider
python -m ruff check backend/src/pelican_town_specials/launcher backend/tests/launcher
python -m mypy backend/src
```

---

### Task 3: 同源静态托管、心跳、主动关闭与空闲退出

**Files:**

- Create: `backend/src/pelican_town_specials/api/routes/app_control.py`
- Create: `backend/tests/api/test_static_frontend.py`
- Modify: `backend/src/pelican_town_specials/api/app.py`
- Modify: `backend/src/pelican_town_specials/api/error_handlers.py` only for the stable missing-assets action

**Interfaces:**

- `ActivityTracker.touch(session_id: str, now: float | None = None) -> None`
- `ActivityTracker.set_busy(is_busy: bool) -> None`
- `ActivityTracker.should_shutdown(now: float | None = None) -> bool`
- `ActivityTracker.request_shutdown() -> None`
- `POST /app/heartbeat -> 204`
- `POST /app/shutdown -> 202`
- `create_app(..., static_dir: Path | None = None, activity_tracker: ActivityTracker | None = None)`

- [x] **Step 1: Write failing static/lifecycle tests**

Create a temporary `dist` with `index.html` and an asset. Verify `/` and known assets are served, an unknown browser path falls back to `index.html`, a missing static directory returns `PTS_SYSTEM_WEB_ASSETS_MISSING`, health remains available, heartbeat requires a session and updates the tracker, shutdown requires a session and requests graceful shutdown, and the tracker only expires after 600 seconds with no busy operation.

- [x] **Step 2: Run the tests and verify red**

```powershell
python -m pytest backend/tests/api/test_static_frontend.py -q -p no:cacheprovider
```

Expected: route or fixture failure because static mounting and app-control routes are absent.

- [x] **Step 3: Implement static mounting and activity control**

Mount the configured static directory without exposing arbitrary filesystem paths. Register SPA fallback only for browser GETs that are not API, session/control, FastAPI docs/schema paths, or known files. Use a lifespan/background task or an injected shutdown callback so tests can assert the request without sleeping. Convert a missing production asset directory into `PTS_SYSTEM_WEB_ASSETS_MISSING`.

- [x] **Step 4: Run focused API and full backend regression**

```powershell
python -m pytest backend/tests/api/test_static_frontend.py backend/tests/api/test_session_security.py backend/tests/api/test_health.py backend/tests/api/test_settings.py -q -p no:cacheprovider
python -m ruff check backend
python -m mypy backend/src
```

---

### Task 4: Launcher 主流程与命令行入口

**Files:**

- Create: `backend/src/pelican_town_specials/launcher/main.py`
- Create: `backend/tests/launcher/test_main.py`
- Modify: `backend/src/pelican_town_specials/api/app.py` only for the launcher dependency injection hook

**Interfaces:**

- `main(argv: Sequence[str] | None = None) -> int`
- CLI options: `--no-browser`, `--workspace PATH`, `--port INT`, `--exit-after-health-check`
- `LauncherDependencies` with injectable `InstanceLock`, `RuntimeRecordStore`, reserved loopback port, `BrowserOpener`, `HealthProbe`, server runner and clock

- [x] **Step 1: Write failing launcher orchestration tests**

Cover a first instance creating a runtime record, issuing a launch token, waiting for health, opening `http://127.0.0.1:{port}/#launch=...`, and cleaning up on exit. Cover a second instance that finds a healthy record and opens the existing URL without starting another server. Cover unhealthy/stale records being cleared before a new launch, `--no-browser`, `--exit-after-health-check`, and missing static assets returning a nonzero result with the stable error code.

- [x] **Step 2: Run the launcher tests and verify red**

```powershell
python -m pytest backend/tests/launcher/test_main.py -q -p no:cacheprovider
```

Expected: module or orchestration symbol-not-found failure.

- [x] **Step 3: Implement the minimal startup sequence**

Keep `main` orchestration-only: parse arguments, acquire/reuse the instance, reserve a bound loopback socket and pass that same socket to Uvicorn, construct `AppConfig`/`WorkspacePaths`/`SecurityState`, wait for health, open the fragment URL, and stop/clean up on exit. Do not read API Key values or implement business operations in launcher code.
- 通用启动、health 或端口失败必须给出稳定错误码和可读的 app-state/launcher-error.log 路径；日志不包含原始异常、launch token、Cookie、CSRF 或 API Key。

- [x] **Step 4: Run launcher tests and a no-browser smoke command**

```powershell
python -m pytest backend/tests/launcher backend/tests/api/test_session_security.py backend/tests/api/test_static_frontend.py -q -p no:cacheprovider
python -m pelican_town_specials.launcher.main --no-browser --workspace C:\tmp\pts-task7-workspace --port 43127 --exit-after-health-check
```

Expected: tests pass; smoke exits after `/api/v1/health` and leaves no owned lock/runtime record.

---

### Task 5: 前端 bootstrap、CSRF middleware 与文档同步

**Files:**

- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/main.tsx`
- Create: `frontend/src/api/session.test.ts`
- Modify: `frontend/src/app/App.test.tsx` only if the existing home-page test needs a bootstrap-safe fixture
- Modify: `docs/architecture/MVP_TECHNICAL_DESIGN.md`
- Modify: `docs/plans/MVP_IMPLEMENTATION_PLAN.md`
- Modify: `StarValleyCook_项目设计源索引与状态快照.md`
- Modify: `AGENTS.md`
- Modify: `docs/development/STATUS.md`
- Create: `docs/development/sessions/2026-08-03-task-7-launcher-security.md`

**Interfaces:**

- `bootstrapSession(launchToken: string): Promise<string>` returns and stores the CSRF token in module memory
- `clearLaunchFragment(location: Location, history: History): void`
- `apiClient` adds `X-PTS-CSRF` to non-GET same-origin requests after bootstrap

- [x] **Step 1: Write failing frontend bootstrap tests**

Using Vitest and `fetch` stubs, verify a launch fragment posts to `/session/bootstrap`, uses `credentials: "same-origin"`, reads `X-PTS-CSRF`, clears the fragment only after a 204 response, and adds the CSRF header to a mutation. Verify a no-fragment entry does not call bootstrap and still renders the existing health-probe home.

- [x] **Step 2: Run frontend tests and observe red**

```powershell
pnpm --dir frontend test:run -- src/api/session.test.ts
```

Expected: missing bootstrap export or failing behavior assertions.

- [x] **Step 3: Implement the minimal frontend session flow**

Keep the CSRF value in a module variable only. In `main.tsx`, bootstrap before the health probe when a `launch` fragment exists; call `history.replaceState` after success. Configure the typed client request middleware to add the header only for same-origin mutation requests.

- [x] **Step 4: Run frontend checks**

```powershell
pnpm --dir frontend test:run
pnpm --dir frontend lint
pnpm --dir frontend build
```

---

### Task 6: Task7 全量验证与验收资料

**Files:**

- Modify: `docs/superpowers/specs/2026-08-03-task-7-launcher-security-design.md`
- Modify: `docs/superpowers/plans/2026-08-03-task-7-launcher-security.md`
- Modify: `docs/development/STATUS.md`
- Modify: `docs/development/sessions/2026-08-03-task-7-launcher-security.md`
- Modify: `README.md`
- Modify: `docs/development/README.md`

**Interfaces:**

- Produces the final verification record; no new product interface.

- [x] **Step 1: Run all backend and frontend checks**

```powershell
python -m pytest backend/tests -q -p no:cacheprovider
python -m ruff check backend
python -m mypy backend/src
pnpm --dir frontend test:run
pnpm --dir frontend lint
pnpm --dir frontend build
git diff --check
```

- [x] **Step 2: Run the scoped local-shell manual verification**

Use a temporary workspace and built `frontend/dist` to verify the real no-browser Launcher shell reaches loopback health and cleans its runtime record; the final smoke used port 43132. Cover second-instance reuse, browser bootstrap, settings mutation, foreign Host/Origin, CSRF and idle shutdown with the deterministic API/Launcher/frontend tests.

- [x] **Step 3: Self-review the plan and update status**

Search the implementation and logs for launch token, Cookie, CSRF and API Key leakage; confirm no 0.0.0.0, setx, machine registry or Credential Locker path was introduced. Keep the Session in verification during the final independent review, then move it to awaiting_user_acceptance only after the evidence is current.

- [x] **Step 4: User acceptance gate**

The user explicitly accepted the verification result. One focused commit covers Task7 code, tests and related control-plane documents; remote push is authorized separately and is being executed now.

