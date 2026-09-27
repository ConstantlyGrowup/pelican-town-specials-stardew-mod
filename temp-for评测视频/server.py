"""Local-only JEV evaluation dashboard. No requests are sent before a user starts a run."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from scripts import evaluate_ingredients as jev

CASES_FILE = HERE / "data/cases.jsonl"
MANIFEST_FILE = HERE / "data/manifest.json"
RUNS_DIR = HERE / "runs"
CONCURRENCY_OPTIONS = frozenset({1, 8, 32, 64, 128, 720})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def load_dataset() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not CASES_FILE.exists() or not MANIFEST_FILE.exists():
        raise RuntimeError("先运行 prepare_cases.py 冻结演示数据")
    raw = CASES_FILE.read_bytes()
    cases = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line]
    manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    if hashlib.sha256(raw).hexdigest().upper() != manifest["sha256"]:
        raise RuntimeError("冻结数据 SHA-256 不一致")
    if len(cases) != manifest["case_count"]:
        raise RuntimeError("冻结数据数量不一致")
    return cases, manifest


CASES, MANIFEST = load_dataset()


def pilot_indices(cases: list[dict[str, Any]]) -> tuple[int, ...]:
    """Choose a stable, balanced spread of distinct dishes from the frozen set."""
    selected: list[int] = []
    used_dishes: set[str] = set()
    for label in ("reasonable", "unreasonable"):
        pool = [(index, case) for index, case in enumerate(cases) if case["gold_choice"] == label]
        if len(pool) < 16:
            raise RuntimeError("冻结数据不足以构造 32 题小批量试跑")
        for slot in range(16):
            start = slot * len(pool) // 16
            for offset in range(len(pool)):
                index, case = pool[(start + offset) % len(pool)]
                if case["dish_en"] not in used_dishes:
                    selected.append(index)
                    used_dishes.add(case["dish_en"])
                    break
            else:
                raise RuntimeError("冻结数据不足以覆盖 32 道不同菜品")
    return tuple(sorted(selected))


PILOT_INDICES = pilot_indices(CASES)
PILOT_CASE_IDS = [CASES[index]["case_id"] for index in PILOT_INDICES]
PILOT_SHA256 = hashlib.sha256(
    json.dumps(PILOT_CASE_IDS, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
).hexdigest().upper()
PILOT_SUMMARY = {
    "case_count": len(PILOT_INDICES),
    "positive_count": sum(CASES[index]["gold_choice"] == "reasonable" for index in PILOT_INDICES),
    "negative_count": sum(CASES[index]["gold_choice"] == "unreasonable" for index in PILOT_INDICES),
    "dish_count": len({CASES[index]["dish_en"] for index in PILOT_INDICES}),
    "sha256": PILOT_SHA256,
}

ROWS_TEMPLATE = [
    {
        key: case[key]
        for key in (
            "case_id", "dish_zh", "dish_en", "query_id", "ingredient", "normalized_name",
            "item_en", "item_zh", "item_id", "gold_choice", "gold_reason", "case_type", "difficulty"
        )
    }
    | {
        "status": "queued", "decision": None, "correct": None, "latency_ms": None,
        "confidence": None, "cost_usd": None, "model": None, "error_code": None,
    }
    for case in CASES
]


def state_for_case(case: dict[str, Any]) -> dict[str, Any]:
    # Explicit allowlist: Gold labels and label notes never reach the provider.
    state = {
        "dish_context": {"name_en": case["dish_en"], "name_zh": case["dish_zh"]},
        "semantic_ingredient": {
            "name": case["ingredient"], "normalized_name": case["normalized_name"]
        },
        "mapped_game_ingredient": {
            "item_id": case["item_id"], "name_en": case["item_en"], "name_zh": case["item_zh"]
        },
    }
    if case["item_id"] == "246":
        state["catalog_translation_note"] = (
            "Catalog item 246 is Wheat Flour in the original English game. "
            "Its Chinese display name 大麦粉 is an imprecise game translation; "
            "judge this item as wheat flour."
        )
    return state


def metrics(rows: list[dict[str, Any]], elapsed_ms: float) -> dict[str, Any]:
    total = len(rows)
    terminal = [r for r in rows if r["status"] in {"completed", "failed", "skipped"}]
    valid = [r for r in rows if r["status"] == "completed" and r["decision"] in {"reasonable", "unreasonable"}]
    correct = sum(r["correct"] is True for r in rows)
    positive = [r for r in rows if r["gold_choice"] == "reasonable"]
    negative = [r for r in rows if r["gold_choice"] == "unreasonable"]
    reported = [r["cost_usd"] for r in rows if isinstance(r["cost_usd"], (int, float))]
    attempted = [r for r in rows if r["status"] in {"completed", "failed"}]
    return {
        "total": total,
        "done": len(terminal),
        "attempted": len(attempted),
        "valid": len(valid),
        "correct": correct,
        "positive_total": len(positive),
        "positive_correct": sum(r["correct"] is True for r in positive),
        "negative_total": len(negative),
        "negative_correct": sum(r["correct"] is True for r in negative),
        "undecidable": sum(r["decision"] == "undecidable" for r in rows),
        "failed": sum(r["status"] == "failed" for r in rows),
        "skipped": sum(r["status"] == "skipped" for r in rows),
        "running": sum(r["status"] == "running" for r in rows),
        "cost_usd": sum(reported) if reported else None,
        "cost_reported": len(reported),
        "cost_missing": len(attempted) - len(reported),
        "throughput": round(len(valid) / (elapsed_ms / 1000), 2) if elapsed_ms > 0 else 0,
        "accuracy_observed": correct / len(attempted) if attempted else None,
        "accuracy_final": correct / total if len(terminal) == total else None,
    }


class StartRequest(BaseModel):
    concurrency: int
    confirm: bool
    scope: Literal["full", "pilot32"] = "full"


class Run:
    def __init__(self, run_id: str, concurrency: int, *, scope: str = "full", restored: bool = False) -> None:
        self.run_id = run_id
        self.concurrency = concurrency
        if scope not in {"full", "pilot32"}:
            raise ValueError("unknown run scope")
        self.scope = scope
        self.case_indices = tuple(range(len(CASES))) if scope == "full" else PILOT_INDICES
        self.selection_sha256 = MANIFEST["sha256"] if scope == "full" else PILOT_SHA256
        self.effective_concurrency = min(concurrency, len(self.case_indices))
        self.status = "running"
        self.mode = "live"
        self.started_at = utc_now()
        self.finished_at: str | None = None
        self.start_clock = time.perf_counter()
        self.elapsed_fixed_ms: float | None = None
        self.rows = [dict(ROWS_TEMPLATE[index]) for index in self.case_indices]
        self.next_index = 0
        self.stop_requested = False
        self.version = 0
        self.condition = asyncio.Condition()
        self.dispatch_lock = asyncio.Lock()
        self.path = RUNS_DIR / run_id
        if not restored:
            self.path.mkdir(parents=True, exist_ok=False)
            self._write_meta()

    def _write_meta(self) -> None:
        payload = {
            "run_id": self.run_id,
            "concurrency": self.concurrency,
            "effective_concurrency": self.effective_concurrency,
            "scope": self.scope,
            "selection_sha256": self.selection_sha256,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_ms": self.elapsed_fixed_ms,
            "dataset_sha256": MANIFEST["sha256"],
            "model": jev.MODEL,
        }
        self.path.mkdir(parents=True, exist_ok=True)
        temp = self.path / "run.tmp.json"
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path / "run.json")

    def elapsed_ms(self) -> float | None:
        if self.status == "interrupted":
            return None
        if self.elapsed_fixed_ms is not None:
            return self.elapsed_fixed_ms
        return round((time.perf_counter() - self.start_clock) * 1000, 1)

    def snapshot(self) -> dict[str, Any]:
        elapsed = self.elapsed_ms()
        return {
            "run_id": self.run_id,
            "status": self.status,
            "mode": self.mode,
            "concurrency": self.concurrency,
            "effective_concurrency": self.effective_concurrency,
            "scope": self.scope,
            "selection_sha256": self.selection_sha256,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_ms": elapsed,
            "metrics": metrics(self.rows, elapsed or 0),
            "rows": self.rows,
            "model": jev.MODEL,
            "actual_models": sorted({r["model"] for r in self.rows if r["model"]}),
            "dataset_sha256": MANIFEST["sha256"],
        }

    async def changed(self) -> None:
        async with self.condition:
            self.version += 1
            self.condition.notify_all()

    async def append_result(self, index: int) -> None:
        # One line per case preserves completed work across a browser refresh or process restart.
        with (self.path / "events.jsonl").open("a", encoding="utf-8") as file:
            file.write(json.dumps({"index": index, "row": self.rows[index]}, ensure_ascii=False) + "\n")
        await self.changed()


RUNS: dict[str, Run] = {}
START_LOCK = asyncio.Lock()


def restore_runs() -> None:
    if not RUNS_DIR.exists():
        return
    for meta_file in RUNS_DIR.glob("*/run.json"):
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            if meta.get("dataset_sha256") != MANIFEST["sha256"]:
                continue
            run = Run(meta["run_id"], int(meta["concurrency"]), scope=meta.get("scope", "full"), restored=True)
            if meta.get("selection_sha256", run.selection_sha256) != run.selection_sha256:
                continue
            run.started_at = meta["started_at"]
            run.finished_at = meta.get("finished_at")
            run.elapsed_fixed_ms = meta.get("elapsed_ms")
            events_file = run.path / "events.jsonl"
            if events_file.exists():
                for line in events_file.read_text(encoding="utf-8").splitlines():
                    event = json.loads(line)
                    run.rows[event["index"]] = event["row"]
            if meta["status"] in {"running", "stopping"}:
                run.status = "interrupted"
                run.finished_at = utc_now()
                # A process restart cannot recover in-flight remote responses.
                for row in run.rows:
                    if row["status"] in {"queued", "running"}:
                        row["status"] = "skipped"
                run._write_meta()
            else:
                run.status = meta["status"]
            RUNS[run.run_id] = run
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            continue


restore_runs()
app = FastAPI(title="JEV 文本评测视频演示")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


def run_summaries() -> list[dict[str, Any]]:
    return [
        {
            "run_id": run.run_id,
            "status": run.status,
            "mode": run.mode,
            "concurrency": run.concurrency,
            "effective_concurrency": run.effective_concurrency,
            "scope": run.scope,
            "selection_sha256": run.selection_sha256,
            "elapsed_ms": run.elapsed_ms(),
            "metrics": metrics(run.rows, run.elapsed_ms() or 0),
            "started_at": run.started_at,
            "dataset_sha256": MANIFEST["sha256"],
            "model": jev.MODEL,
            "actual_models": sorted({row["model"] for row in run.rows if row["model"]}),
        }
        for run in sorted(RUNS.values(), key=lambda value: value.started_at, reverse=True)[:20]
    ]


@app.get("/")
def index() -> FileResponse:
    return FileResponse(HERE / "static/index.html")


@app.get("/api/bootstrap")
def bootstrap() -> dict[str, Any]:
    latest = max(RUNS.values(), key=lambda r: r.started_at, default=None)
    return {
        "dataset": MANIFEST,
        "pilot": PILOT_SUMMARY,
        "model": jev.MODEL,
        "api_key_available": bool(os.environ.get("OPENROUTER_API_KEY")),
        "active_run_id": latest.run_id if latest else None,
        "recent_runs": run_summaries(),
    }


@app.get("/api/runs")
def list_runs() -> list[dict[str, Any]]:
    return run_summaries()


@app.post("/api/runs")
async def start_run(request: StartRequest) -> dict[str, str]:
    if request.concurrency not in CONCURRENCY_OPTIONS or request.confirm is not True:
        raise HTTPException(400, "请选择页面提供的并发档位，并确认本次付费评测")
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise HTTPException(400, "本地服务进程没有 OPENROUTER_API_KEY")
    async with START_LOCK:
        active = next((r for r in RUNS.values() if r.status in {"running", "stopping"}), None)
        if active is not None:
            return {"run_id": active.run_id}
        run = Run(uuid.uuid4().hex[:12], request.concurrency, scope=request.scope)
        RUNS[run.run_id] = run
        asyncio.create_task(execute_run(run))
        return {"run_id": run.run_id}


async def _send_case(client: httpx.AsyncClient, run: Run, index: int, api_key: str) -> None:
    row = run.rows[index]
    row["status"] = "running"
    await run.changed()
    state = state_for_case(CASES[run.case_indices[index]])
    body = jev.build_decisions_request(state)
    started = time.perf_counter()
    try:
        response = await client.post(
            jev.API_URL,
            json=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        response.raise_for_status()
        parsed = jev.parse_decisions_response(response.json())
        row["status"] = "completed"
        row["decision"] = parsed["decision"]
        row["correct"] = parsed["decision"] == row["gold_choice"]
        row["confidence"] = parsed["confidence"]
        row["model"] = parsed["model"]
        usage = parsed.get("usage") or {}
        row["cost_usd"] = usage.get("cost")
    except httpx.HTTPStatusError as exc:
        row["status"] = "failed"
        row["error_code"] = f"HTTP_{exc.response.status_code}"
    except (httpx.HTTPError, ValueError, TypeError, KeyError, jev.EvaluationError) as exc:
        row["status"] = "failed"
        row["error_code"] = type(exc).__name__
    finally:
        row["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        await run.append_result(index)


async def execute_run(run: Run) -> None:
    api_key = os.environ["OPENROUTER_API_KEY"]

    async def worker(client: httpx.AsyncClient) -> None:
        while True:
            async with run.dispatch_lock:
                if run.stop_requested or run.next_index >= len(run.rows):
                    return
                index = run.next_index
                run.next_index += 1
            await _send_case(client, run, index, api_key)

    try:
        limits = httpx.Limits(
            max_connections=run.effective_concurrency,
            max_keepalive_connections=min(run.effective_concurrency, 100),
        )
        async with httpx.AsyncClient(timeout=45.0, limits=limits) as client:
            await asyncio.gather(*(worker(client) for _ in range(run.effective_concurrency)))
    finally:
        if run.stop_requested:
            for index, row in enumerate(run.rows):
                if row["status"] == "queued":
                    row["status"] = "skipped"
                    await run.append_result(index)
        run.status = "stopped" if run.stop_requested else "completed"
        run.finished_at = utc_now()
        run.elapsed_fixed_ms = run.elapsed_ms()
        run._write_meta()
        await run.changed()


def require_run(run_id: str) -> Run:
    try:
        return RUNS[run_id]
    except KeyError as exc:
        raise HTTPException(404, "未找到运行记录") from exc


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    return require_run(run_id).snapshot()


@app.post("/api/runs/{run_id}/stop")
async def stop_run(run_id: str) -> dict[str, Any]:
    run = require_run(run_id)
    if run.status == "running":
        run.stop_requested = True
        run.status = "stopping"
        run._write_meta()
        await run.changed()
    return {"run_id": run_id, "status": run.status}


@app.get("/api/runs/{run_id}/events")
async def events(run_id: str) -> StreamingResponse:
    run = require_run(run_id)

    async def stream():
        seen = -1
        while True:
            if seen != run.version:
                seen = run.version
                yield "data: " + json.dumps(run.snapshot(), ensure_ascii=False) + "\n\n"
                if run.status in {"completed", "stopped", "interrupted"}:
                    break
                # Coalesce bursts: 720 responses must not generate 720 full-table frames.
                await asyncio.sleep(0.1)
            try:
                async with run.condition:
                    await asyncio.wait_for(
                        run.condition.wait_for(lambda target=seen: run.version != target), timeout=10
                    )
            except TimeoutError:
                yield ": keepalive\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/api/runs/{run_id}/export")
def export_run(run_id: str) -> JSONResponse:
    run = require_run(run_id)
    return JSONResponse(
        {"dataset": MANIFEST, "run": run.snapshot()},
        headers={"Content-Disposition": f'attachment; filename="jev-run-{run_id}.json"'},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8765)
