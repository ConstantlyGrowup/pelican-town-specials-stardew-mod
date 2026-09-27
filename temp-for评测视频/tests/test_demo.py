"""Focused checks for the independent, local video demo."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Self

from fastapi.testclient import TestClient

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import prepare_cases
import server


def test_frozen_dataset_and_negative_rule() -> None:
    cases, manifest = prepare_cases.build()
    assert manifest["case_count"] == 720
    assert manifest["positive_count"] == manifest["negative_count"] == 360
    assert manifest["unique_state_count"] == 720
    for case in cases:
        if case["gold_choice"] == "unreasonable":
            assert case["item_id"] in {"139", "129", "246", "256"}
            assert case["difficulty"] == "clear_cross_category"
        else:
            assert case["difficulty"] == "known_gold"


def test_provider_state_has_no_gold_and_preserves_translation_rule() -> None:
    case = next(row for row in server.CASES if row["item_id"] == "246")
    encoded = json.dumps(server.state_for_case(case), ensure_ascii=False)
    assert "gold_choice" not in encoded
    assert "gold_reason" not in encoded
    assert "acceptable_item_ids" not in encoded
    assert "Wheat Flour" in encoded
    assert "大麦粉" in encoded


def test_scoring_keeps_invalid_and_failed_in_denominator() -> None:
    rows = [
        {"gold_choice": "unreasonable", "status": "completed", "decision": "unreasonable", "correct": True, "cost_usd": 0.01},
        {"gold_choice": "reasonable", "status": "completed", "decision": "undecidable", "correct": False, "cost_usd": None},
        {"gold_choice": "unreasonable", "status": "failed", "decision": None, "correct": None, "cost_usd": None},
    ]
    result = server.metrics(rows, 1000)
    assert result["correct"] == 1
    assert result["negative_correct"] == 1
    assert result["done"] == 3
    assert result["valid"] == 1
    assert result["undecidable"] == 1
    assert result["failed"] == 1
    assert result["cost_usd"] == 0.01
    assert result["cost_reported"] == 1
    assert result["cost_missing"] == 2
    assert result["accuracy_final"] == 1 / 3


def test_dashboard_bootstrap_does_not_expose_key(monkeypatch: Any) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "private-test-key")
    client = TestClient(server.app)
    response = client.get("/api/bootstrap")
    assert response.status_code == 200
    assert response.json()["dataset"]["case_count"] == 720
    assert response.json()["pilot"] == server.PILOT_SUMMARY
    assert response.json()["pilot"]["case_count"] == 32
    assert response.json()["api_key_available"] is True
    assert "private-test-key" not in response.text


def test_fake_two_case_run_and_request_isolation(monkeypatch: Any) -> None:
    captured: list[dict[str, Any]] = []

    class FakeResponse:
        status_code = 200

        def __init__(self, choice: str) -> None:
            self.choice = choice

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return {
                "model": "typesafe/jev-1.13-20260917",
                "provider": "TypeSafe",
                "answers": {
                    "ingredient_mapping": {
                        "type": "choice",
                        "choice": self.choice,
                        "confidence": 0.9,
                    }
                },
                "usage": {"cost": 0.001},
            }

    class FakeClient:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_args: object) -> None:
            pass

        async def post(self, _url: str, *, json: dict[str, Any], headers: dict[str, str]) -> FakeResponse:
            captured.append(json)
            assert headers["Authorization"] == "Bearer private-test-key"
            return FakeResponse("reasonable" if len(captured) == 1 else "unreasonable")

    selected = [
        next(row for row in server.ROWS_TEMPLATE if row["gold_choice"] == "reasonable"),
        next(row for row in server.ROWS_TEMPLATE if row["gold_choice"] == "unreasonable"),
    ]
    source = [next(case for case in server.CASES if case["case_id"] == row["case_id"]) for row in selected]
    monkeypatch.setattr(server, "ROWS_TEMPLATE", selected)
    monkeypatch.setattr(server, "CASES", source)
    monkeypatch.setattr(server.httpx, "AsyncClient", FakeClient)
    monkeypatch.setenv("OPENROUTER_API_KEY", "private-test-key")
    with TemporaryDirectory(dir=HERE, prefix="test-run-") as task_tmp:
        task_path = Path(task_tmp)
        monkeypatch.setattr(server, "RUNS_DIR", task_path)
        run = server.Run("fake-run", 1)
        asyncio.run(server.execute_run(run))
        assert run.status == "completed"
        assert run.snapshot()["metrics"]["correct"] == 2
        assert run.snapshot()["metrics"]["cost_usd"] == 0.002
        assert len(captured) == 2
        assert "gold_choice" not in json.dumps(captured)
        assert "gold_reason" not in json.dumps(captured)
        assert (task_path / "fake-run/events.jsonl").exists()


def test_start_requires_confirmed_live_key(monkeypatch: Any) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    client = TestClient(server.app)
    response = client.post("/api/runs", json={"concurrency": 8, "confirm": True})
    assert response.status_code == 400


def test_pilot_selection_is_fixed_balanced_and_separate() -> None:
    selected = [server.CASES[index] for index in server.PILOT_INDICES]
    assert len(selected) == 32
    assert len({case["case_id"] for case in selected}) == 32
    assert len({case["dish_en"] for case in selected}) == 32
    assert sum(case["gold_choice"] == "reasonable" for case in selected) == 16
    assert sum(case["gold_choice"] == "unreasonable" for case in selected) == 16
    assert server.pilot_indices(server.CASES) == server.PILOT_INDICES
    pilot = server.Run("pilot-structure", 64, scope="pilot32", restored=True)
    assert pilot.effective_concurrency == 32
    assert pilot.snapshot()["scope"] == "pilot32"
    assert pilot.snapshot()["metrics"]["total"] == 32
    assert pilot.snapshot()["selection_sha256"] == server.PILOT_SHA256
    full = server.Run("full-structure", 64, restored=True)
    assert full.snapshot()["metrics"]["total"] == 720


def test_fake_pilot_sends_only_32_selected_states(monkeypatch: Any) -> None:
    captured: list[dict[str, Any]] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return {
                "model": "typesafe/jev-1.13-20260917",
                "answers": {"ingredient_mapping": {"type": "choice", "choice": "reasonable", "confidence": 0.9}},
                "usage": {"cost": 0.001},
            }

    class FakeClient:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_args: object) -> None:
            pass

        async def post(self, _url: str, *, json: dict[str, Any], headers: dict[str, str]) -> FakeResponse:
            captured.append(json)
            assert headers["Authorization"] == "Bearer private-test-key"
            return FakeResponse()

    monkeypatch.setattr(server.httpx, "AsyncClient", FakeClient)
    monkeypatch.setenv("OPENROUTER_API_KEY", "private-test-key")
    with TemporaryDirectory(dir=HERE, prefix="test-run-") as task_tmp:
        monkeypatch.setattr(server, "RUNS_DIR", Path(task_tmp))
        run = server.Run("pilot-fake", 64, scope="pilot32")
        asyncio.run(server.execute_run(run))
        assert run.status == "completed"
        assert run.snapshot()["metrics"]["done"] == 32
        assert run.snapshot()["metrics"]["cost_usd"] == 0.032
        assert len(captured) == 32
        assert "gold_choice" not in json.dumps(captured)
        assert "gold_reason" not in json.dumps(captured)
        first = captured[0]["state"]
        expected = server.state_for_case(server.CASES[server.PILOT_INDICES[0]])
        assert first == expected


def test_concurrency_choices_are_explicit_and_bounded(monkeypatch: Any) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "private-test-key")
    client = TestClient(server.app)
    assert server.CONCURRENCY_OPTIONS == {1, 8, 32, 64, 128, 720}
    for unsupported in (0, 2, 719, 721, 10000):
        response = client.post("/api/runs", json={"concurrency": unsupported, "confirm": True})
        assert response.status_code == 400
    before = len(server.RUNS)
    assert client.post("/api/runs", json={"concurrency": 32, "scope": "pilot32", "confirm": False}).status_code == 400
    assert client.post("/api/runs", json={"concurrency": 32, "scope": "unknown", "confirm": True}).status_code == 422
    assert len(server.RUNS) == before
