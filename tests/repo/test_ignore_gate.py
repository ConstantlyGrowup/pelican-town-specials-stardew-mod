"""Milestone 7: local design/planning docs ignore-gate regression.

`build_windows.ps1` -> `verify_local_docs_ignored.ps1` must pass on a fresh CI
checkout, where the gitignored design sources are NOT materialised on disk.
Directory ignore patterns (e.g. `/docs/architecture/`) only match when `git
check-ignore` can determine the path is a directory, so the gate passes the
directory paths with a trailing slash. These tests lock that the script keeps
the slash on directory entries and that the mechanism works for absent
directories — the exact condition that previously broke CI (and the v1.0.0
release) while passing on a developer machine where the directories exist.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE = REPO_ROOT / "scripts" / "verify_local_docs_ignored.ps1"

GITIGNORE_DIR_PATTERNS = (
    "/design docs/\n",
    "/最初设计功能清点/\n",
    "/docs/architecture/\n",
    "/docs/plans/\n",
    "/StarValleyCook_项目设计源索引与状态快照.md\n",
)


def _gate_text() -> str:
    return GATE.read_text(encoding="utf-8")


def test_gate_script_marks_directory_entries_with_trailing_slash() -> None:
    text = _gate_text()
    # Directory patterns in .gitignore end with '/', so the gate must pass a
    # trailing slash to `git check-ignore` for them to match absent dirs.
    for entry in ("design docs", "最初设计功能清点", "docs/architecture", "docs/plans"):
        assert f"'{entry}/'" in text, f"gate must pass {entry}/ with a trailing slash"
    # The single file entry must keep no slash (its pattern is not a directory).
    assert "StarValleyCook_项目设计源索引与状态快照.md'" in text


def test_check_ignore_matches_nonexistent_directory_with_trailing_slash(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitignore").write_text("".join(GITIGNORE_DIR_PATTERNS), encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)

    # The directories do NOT exist on disk — the fresh-checkout CI condition.
    # With a trailing slash git treats the path as a directory and the ignore
    # pattern matches; without it an absent path cannot be confirmed as a
    # directory and the gate would (incorrectly) fail.
    for path in ("design docs/", "docs/architecture/", "docs/plans/", "最初设计功能清点/"):
        result = subprocess.run(["git", "check-ignore", "--quiet", "--", path], cwd=repo)
        assert result.returncode == 0, (
            f"{path} should be ignored while absent (trailing slash)"
        )

    # The file entry (no slash) is also ignored while absent.
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", "--", "StarValleyCook_项目设计源索引与状态快照.md"],
        cwd=repo,
    )
    assert result.returncode == 0, "file path should be ignored while absent"

    # Documenting the regression premise: an absent directory WITHOUT the
    # trailing slash is reported as NOT ignored (the CI failure).
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", "--", "docs/architecture"],
        cwd=repo,
    )
    assert result.returncode != 0, (
        "absent directory without slash must not match (regression premise)"
    )
