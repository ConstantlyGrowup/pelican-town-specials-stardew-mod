"""Task 30: the trial API key resource must never enter the repository.

The trial key is injected from the CI secret ``PTS_TRIAL_API_KEY`` into
``resources/trial/trial_api_key.txt`` only at build time (build.yml), and the
file is gitignored. These gates assert the path is both untracked and ignored,
so the key cannot leak through a commit, a source archive, or the onedir
bundle's tracked-content checks.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

TRIAL_KEY_RELATIVE = Path("resources") / "trial" / "trial_api_key.txt"


def _tracked_files() -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in proc.stdout.splitlines() if line]


def test_trial_key_resource_is_not_tracked() -> None:
    normalized = TRIAL_KEY_RELATIVE.as_posix()
    violations = [path for path in _tracked_files() if path == normalized]
    assert violations == [], f"tracked trial key resource: {violations}"


def test_trial_key_resource_is_gitignored() -> None:
    proc = subprocess.run(
        ["git", "check-ignore", "-q", TRIAL_KEY_RELATIVE.as_posix()],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    assert proc.returncode == 0, (
        ".gitignore must ignore the trial API key resource "
        f"(git check-ignore returned {proc.returncode})"
    )
