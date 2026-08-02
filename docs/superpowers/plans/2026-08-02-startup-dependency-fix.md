# Local Startup Dependency Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the documented Windows development commands start the FastAPI health API and Vite frontend, with dependency failures reported clearly.

**Architecture:** Keep the existing FastAPI application factory as the testable construction boundary and expose one module-level ASGI application for the standard Uvicorn command. Keep the existing Vite proxy and pnpm workspace; verify esbuild separately because its binary exists but the current restricted runner blocks Node child-process spawning.

**Tech Stack:** Python 3.13, FastAPI, Uvicorn, pytest, React, Vite 7, esbuild, pnpm.

## Global Constraints

- uv is not required for the startup path; do not commit a Python lockfile or virtual-environment configuration.
- Keep Vite bound to `127.0.0.1:5173` and proxy `/api` to `127.0.0.1:8000`.
- Preserve `create_app()` for tests and future injected configuration.
- Do not change the health response contract or implement Task 4+ functionality.
- Validate the exact startup command and both direct and proxied `/api/v1/health` requests before completion.

---

### Task 1: Reproduce the backend startup contract

**Files:**
- Modify: `backend/tests/api/test_health.py`
- Modify: `backend/src/pelican_town_specials/api/app.py`

- [x] **Step 1: Add a failing import-level startup test**

Add this test to `backend/tests/api/test_health.py`:

```python
from pelican_town_specials.api.app import app, create_app


def test_module_exports_uvicorn_application() -> None:
    assert app is not None
    assert app.title == create_app().title
```

- [x] **Step 2: Run the focused test and observe the expected failure**

Run:

```powershell
python -m pytest backend/tests/api/test_health.py::test_module_exports_uvicorn_application -q
```

Expected: collection fails because `pelican_town_specials.api.app` does not yet export `app`.

- [x] **Step 3: Export the standard ASGI application**

Append the following after `create_app()` in `backend/src/pelican_town_specials/api/app.py`:

```python


app = create_app()
```

- [x] **Step 4: Run the focused test and the existing health contract**

Run:

```powershell
python -m pytest backend/tests/api/test_health.py -q
```

Expected: both tests pass.

### Task 2: Validate frontend dependency and startup boundaries

**Files:**
- Modify: `frontend/package.json` only if a declared package is genuinely missing from a clean frozen install.
- Modify: `pnpm-lock.yaml` only if `frontend/package.json` changes require it.

- [x] **Step 1: Reinstall from the committed lockfile**

Run:

```powershell
pnpm install --frozen-lockfile
```

Expected: exit code 0 and no missing optional-platform dependency error.

- [x] **Step 2: Verify Vite starts in a normal Windows process**

Run from a regular PowerShell terminal:

```powershell
pnpm --dir frontend dev
```

Expected: Vite reports `http://127.0.0.1:5173/` without `spawn EPERM`.

- [x] **Step 3: Verify the proxy and backend together**

Run the backend command below in a second terminal, open the Vite URL, and request both endpoints:

```powershell
python -m uvicorn pelican_town_specials.api.app:app --app-dir backend/src --host 127.0.0.1 --port 8000
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
Invoke-RestMethod http://127.0.0.1:5173/api/v1/health
```

Expected: both responses have `status=ok`, `app=PelicanTownSpecials`, and `apiVersion=v1`.

### Task 3: Run regression checks

- [x] **Step 1: Run backend, frontend, and repository checks**

```powershell
python -m pytest backend/tests -q
pnpm --dir frontend test:run
pnpm --dir frontend lint
pnpm --dir frontend build
pwsh -File scripts/verify_local_docs_ignored.ps1
git diff --check
```

- [x] **Step 2: Confirm no tooling drift**

```powershell
git status --short
Test-Path .\backend\.venv
Test-Path .\frontend\.venv
```

Expected: no new `Python lockfile` or virtual environment paths.

## 实际执行结果

- [x] python -m pytest backend/tests -q：2 passed。
- [x] python -m ruff check backend 与 python -m mypy backend/src：通过。
- [x] pnpm frontend test:run、lint、build：通过；文档忽略检查通过。
- [x] 标准 Uvicorn 启动命令可用；后端直连和 Vite /api 代理 health 均返回 status=ok、app=PelicanTownSpecials、apiVersion=v1。
- [x] 用户手动启动 Vite 与后端，确认首页显示和 Network health 200；Task 3 与启动闭环一并验收。
- [x] 未新增 Python lockfile、.venv 或 Python 虚拟环境配置。
