"""Milestone 6 Task 20: tracked repository content must not leak into a release.

A release is assembled from the working tree; anything tracked that looks like a
secret, a design document, a workspace, a log, a source map, or a build output
would end up inside the onedir bundle (or a future source archive). These gates
fail before the build even starts.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DESIGN_DOC_PREFIXES = (
    "design docs/",
    "docs/architecture/",
    "docs/plans/",
    "最初设计功能清点/",
)
STARVALLEYCOOK_PREFIX = "StarValleyCook"


def _tracked_files() -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in proc.stdout.splitlines() if line]


def _assert_no_violations(label: str, violations: list[str]) -> None:
    assert violations == [], f"tracked {label}: {violations}"


def test_no_secret_env_files_tracked() -> None:
    violations = [
        path
        for path in _tracked_files()
        if path.split("/")[-1].startswith(".env")
        and path.split("/")[-1] != ".env.example"
    ]
    _assert_no_violations("secret env files", violations)


def test_no_design_documents_tracked() -> None:
    violations = [
        path
        for path in _tracked_files()
        if path.startswith(DESIGN_DOC_PREFIXES) or path.startswith(STARVALLEYCOOK_PREFIX)
    ]
    _assert_no_violations("design documents", violations)


def test_no_workspace_data_tracked() -> None:
    violations = [path for path in _tracked_files() if path.startswith("workspace/")]
    _assert_no_violations("workspace data", violations)


def test_no_log_files_tracked() -> None:
    violations = [path for path in _tracked_files() if path.endswith(".log")]
    _assert_no_violations("log files", violations)


def test_no_source_maps_tracked() -> None:
    violations = [path for path in _tracked_files() if path.endswith(".map")]
    _assert_no_violations("source maps", violations)


def test_build_output_not_tracked() -> None:
    violations = [
        path
        for path in _tracked_files()
        if path == "dist"
        or path.startswith("dist/")
        or path == "frontend/dist"
        or path.startswith("frontend/dist/")
    ]
    _assert_no_violations("build output", violations)
