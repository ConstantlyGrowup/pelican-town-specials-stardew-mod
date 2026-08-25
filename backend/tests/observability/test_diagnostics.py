"""Diagnostics bundle and structured logging tests (Task 19 Step 1/3).

Covers T19-REDACTION-001 (bundle excludes secrets, business records and
data-image payloads; rotation bounds; header/query/prompt redaction) and
T19-OBSERVABILITY-001 (structured log field whitelist).
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from backend.tests.domain.factories import canonical_registration_fixture
from PIL import Image

from pelican_town_specials.domain.assets import MediaType
from pelican_town_specials.domain.canonical import CanonicalIconInput
from pelican_town_specials.observability.diagnostics import DiagnosticsBuilder
from pelican_town_specials.observability.logging import (
    configure_logging,
    log_event,
    purge_expired_logs,
    read_log_lines,
)
from pelican_town_specials.observability.redaction import LOG_FIELD_WHITELIST
from pelican_town_specials.persistence.canonical_registry import SQLiteCanonicalRegistry
from pelican_town_specials.persistence.workspace import WorkspacePaths


def inspect_zip(bundle: bytes) -> tuple[list[str], str]:
    with zipfile.ZipFile(io.BytesIO(bundle)) as handle:
        names = handle.namelist()
        text = "".join(
            handle.read(name).decode("utf-8", errors="replace") + "\n"
            for name in names
        )
    return names, text


@pytest.fixture
def workspace(tmp_path: Path) -> WorkspacePaths:
    return WorkspacePaths.create(tmp_path / "workspace")


@pytest.fixture
def diagnostics(workspace: WorkspacePaths) -> DiagnosticsBuilder:
    return DiagnosticsBuilder(workspace=workspace)


def test_diagnostic_bundle_excludes_secrets_and_business_records(
    diagnostics: DiagnosticsBuilder,
    workspace: WorkspacePaths,
) -> None:
    logs_dir = workspace.app_state_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "pts-structured.log").write_text(
        json.dumps(
            {
                "timestamp": "2026-08-06T00:00:00Z",
                "level": "ERROR",
                "requestId": "req-1",
                "errorCode": "PTS_PROVIDER_REQUEST_FAILED",
                "stage": "DISH_ANALYSIS",
            }
        )
        + "\n"
        + "legacy line: cookbook/dish-1 drafts/draft-1 Bearer sk-test-secret "
        + "data:image/png;base64,AAAA query token=secret\n",
        encoding="utf-8",
    )

    bundle = diagnostics.build(request_id="fixture-request")
    names, text = inspect_zip(bundle)

    assert all(
        "cookbook/" not in name and "drafts/" not in name for name in names
    )
    assert "cookbook/" not in text
    assert "drafts/" not in text
    assert "sk-test-secret" not in text
    assert "data:image" not in text


def test_diagnostic_bundle_excludes_registry_icons_and_raw_generation_context(
    diagnostics: DiagnosticsBuilder,
    workspace: WorkspacePaths,
) -> None:
    """Diagnostics remain aggregate-only even when the workspace is populated."""

    def png_bytes(size: int, color: str) -> bytes:
        output = io.BytesIO()
        Image.new("RGBA", (size, size), color).save(output, format="PNG")
        return output.getvalue()

    def icon_input(data: bytes, size: int) -> CanonicalIconInput:
        return CanonicalIconInput(
            data=data,
            mediaType=MediaType.PNG,
            sha256=hashlib.sha256(data).hexdigest(),
            byteSize=len(data),
            width=size,
            height=size,
        )

    # Seed the real SQLite Registry and its private icon store. The diagnostic
    # builder must not copy either into its support bundle.
    registry = SQLiteCanonicalRegistry(workspace)
    registration = canonical_registration_fixture()
    source_icon = png_bytes(32, "gold")
    icon_16 = png_bytes(16, "orange")
    registry.register(
        registration,
        icon_source=icon_input(source_icon, 32),
        icon_16=icon_input(icon_16, 16),
    )

    raw_original = workspace.assets_dir / "raw-original-photo.png"
    raw_preview = workspace.assets_dir / "raw-preview-photo.png"
    raw_original.write_bytes(png_bytes(8, "navy"))
    raw_preview.write_bytes(png_bytes(8, "orchid"))
    logs_dir = workspace.app_state_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "pts-structured.log").write_text(
        json.dumps(
            {
                "timestamp": "2026-08-25T00:00:00Z",
                "level": "INFO",
                "requestId": "req-task36-privacy",
                "stage": "DISH_ANALYSIS",
                "usage": {
                    "contextText": "RAW_CONTEXT_SHOULD_NOT_LEAK",
                    "matcherPayload": "RAW_MATCHER_PAYLOAD_SHOULD_NOT_LEAK",
                    "prompt": "sk-fake-task36-secret",
                    "image": "data:image/png;base64,RAW_IMAGE_SHOULD_NOT_LEAK",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    names, text = inspect_zip(diagnostics.build(request_id="req-task36-privacy"))

    assert "canonical/registry.sqlite3" not in names
    assert all("canonical/" not in name for name in names)
    assert all("raw-original-photo.png" not in name for name in names)
    assert all("raw-preview-photo.png" not in name for name in names)
    for forbidden in (
        "RAW_CONTEXT_SHOULD_NOT_LEAK",
        "RAW_MATCHER_PAYLOAD_SHOULD_NOT_LEAK",
        "sk-fake-task36-secret",
        "data:image/png",
    ):
        assert forbidden not in text


def test_diagnostic_bundle_contains_summary_files(
    diagnostics: DiagnosticsBuilder,
    workspace: WorkspacePaths,
) -> None:
    logs_dir = workspace.app_state_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "pts-structured.log").write_text(
        json.dumps(
            {
                "timestamp": "2026-08-06T00:00:00Z",
                "level": "ERROR",
                "requestId": "req-1",
                "errorCode": "PTS_GEN_VALIDATION_FAILED",
                "stage": "RECIPE_DESIGN",
                "elapsedMs": 120,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    names, text = inspect_zip(diagnostics.build(request_id="req-x"))

    assert "app.json" in names
    assert "os.json" in names
    assert "capabilities.json" in names
    assert "errors.json" in names
    assert "stages.json" in names
    assert "logs.json" in names
    assert "PTS_GEN_VALIDATION_FAILED" in text
    assert "req-x" in text


def test_structured_log_fields_are_whitelisted(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    configure_logging(logs_dir)
    log_event(
        logging.INFO,
        request_id="req-1",
        draft_id="draft-1",
        attempt_id="attempt-1",
        stage="DISH_ANALYSIS",
        model_id="gpt-5.6-luna",
        extra="must-not-leak",
    )

    records = read_log_lines(logs_dir)

    assert len(records) == 1
    assert set(records[0].keys()) <= LOG_FIELD_WHITELIST
    assert records[0]["requestId"] == "req-1"
    assert records[0]["draftId"] == "draft-1"
    assert "extra" not in records[0]


def test_log_rotation_bounds_total_size(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    configure_logging(logs_dir, total_max_bytes=4096, backup_count=2)

    for index in range(400):
        log_event(logging.INFO, request_id=f"req-{index}", stage="TEST")

    files = list(logs_dir.glob("pts-structured*"))
    total_size = sum(path.stat().st_size for path in files)
    backups = [path for path in files if path.name != "pts-structured.log"]

    assert total_size <= 4096
    assert len(backups) <= 2


def test_purge_expired_logs_removes_old_files(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    old = logs_dir / "pts-structured.log"
    old.write_text("old\n", encoding="utf-8")
    old_time = datetime.now(UTC) - timedelta(days=10)
    os.utime(old, (old_time.timestamp(), old_time.timestamp()))
    fresh = logs_dir / "pts-structured.log.1"
    fresh.write_text("fresh\n", encoding="utf-8")
    fresh_time = datetime.now(UTC) - timedelta(days=1)
    os.utime(fresh, (fresh_time.timestamp(), fresh_time.timestamp()))

    removed = purge_expired_logs(logs_dir, max_days=7)

    assert removed == 1
    assert not old.exists()
    assert fresh.exists()


def test_configure_logging_purges_expired_logs_at_setup(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    # A stale rotated file (unlike the active log, it is not recreated by the
    # rotating handler) must be purged when logging is configured.
    stale = logs_dir / "pts-structured.log.1"
    stale.write_text("old expired\n", encoding="utf-8")
    old_time = datetime.now(UTC) - timedelta(days=10)
    os.utime(stale, (old_time.timestamp(), old_time.timestamp()))

    configure_logging(logs_dir)

    assert not stale.exists()


def test_read_log_lines_excludes_expired_logs(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    path = logs_dir / "pts-structured.log"
    path.write_text(
        json.dumps(
            {
                "timestamp": "2026-08-06T00:00:00Z",
                "level": "INFO",
                "requestId": "req-old",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    old_time = datetime.now(UTC) - timedelta(days=10)
    os.utime(path, (old_time.timestamp(), old_time.timestamp()))

    records = read_log_lines(logs_dir)

    assert records == []


def test_configure_logging_trims_excess_rotated_files(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    for index in (1, 2, 3, 4, 5):
        (logs_dir / f"pts-structured.log.{index}").write_text(
            "x\n", encoding="utf-8"
        )

    configure_logging(logs_dir, backup_count=2)

    remaining = [
        path
        for path in logs_dir.glob("pts-structured.log.*")
        if path.name != "pts-structured.log"
    ]
    assert len(remaining) <= 2


def test_diagnostic_bundle_scrubs_nested_secrets(
    diagnostics: DiagnosticsBuilder,
    workspace: WorkspacePaths,
) -> None:
    logs_dir = workspace.app_state_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "pts-structured.log").write_text(
        json.dumps(
            {
                "timestamp": "2026-08-06T00:00:00Z",
                "level": "INFO",
                "requestId": "req-1",
                "usage": {
                    "prompt": "sk-test-secret",
                    "image": "data:image/png;base64,AAAA",
                    "path": r"C:\app-state\drafts\abc\recipe.json",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _, text = inspect_zip(diagnostics.build(request_id="req-x"))

    assert "sk-test-secret" not in text
    assert "data:image" not in text
    assert "drafts" not in text


def test_diagnostic_logs_all_records_respect_whitelist(
    diagnostics: DiagnosticsBuilder,
    workspace: WorkspacePaths,
) -> None:
    logs_dir = workspace.app_state_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "pts-structured.log").write_text(
        json.dumps(
            {
                "timestamp": "2026-08-06T00:00:00Z",
                "level": "ERROR",
                "requestId": "req-1",
                "errorCode": "PTS_PROVIDER_REQUEST_FAILED",
            }
        )
        + "\n"
        + "legacy non-json line: Bearer sk-test-secret data:image/png;base64,AAAA\n",
        encoding="utf-8",
    )

    bundle = diagnostics.build(request_id="req-x")
    with zipfile.ZipFile(io.BytesIO(bundle)) as handle:
        logs = json.loads(handle.read("logs.json").decode("utf-8"))

    assert isinstance(logs, list)
    assert logs
    for record in logs:
        assert isinstance(record, dict)
        assert set(record.keys()) <= LOG_FIELD_WHITELIST
