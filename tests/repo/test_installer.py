"""Milestone 7 Task 23: per-user installer contract (repo-level gates).

The installer itself is compiled and smoke-tested by scripts/build_installer.ps1
and scripts/smoke_installer.ps1 on Windows (silent install / health / reinstall /
uninstall with workspace preservation). These tests lock the frozen installer
contract that otherwise would only be caught at build time: per-user install,
no admin rights, Gus icon, start-menu required / desktop optional, version
aligned with the frozen 1.0.0 metadata, a content gate shared with the bundle
build, and pinned installer tooling in CI.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

ISS = REPO_ROOT / "packaging" / "installer" / "PelicanTownSpecials.iss"
GATE = REPO_ROOT / "scripts" / "release_content_gate.ps1"
BUILD_INSTALLER = REPO_ROOT / "scripts" / "build_installer.ps1"
BUILD_WINDOWS = REPO_ROOT / "scripts" / "build_windows.ps1"
INSTALL_TOOL = REPO_ROOT / "scripts" / "install_innosetup.ps1"
FIND_ISCC = REPO_ROOT / "scripts" / "find_iscc.ps1"
SMOKE = REPO_ROOT / "scripts" / "smoke_installer.ps1"
VERSION_INFO = REPO_ROOT / "packaging" / "pyinstaller" / "version_info.txt"
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
BUILD = REPO_ROOT / ".github" / "workflows" / "build.yml"

WORKSPACE_DIR = "{localappdata}\\PelicanTownSpecials\\workspace"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _frozen_version() -> str:
    match = re.search(r"StringStruct\('FileVersion', '([^']+)'\)", _text(VERSION_INFO))
    assert match, "version_info.txt must declare a FileVersion"
    return match.group(1)


def test_installer_script_exists_and_uses_gus_icon() -> None:
    text = _text(ISS)
    # Setup wizard and uninstall entry both surface the Gus portrait.
    assert "pelican-town-specials.ico" in text, "setup icon must be the Gus icon"
    assert "UninstallDisplayIcon={app}\\PelicanTownSpecials.exe" in text


def test_per_user_install_without_admin() -> None:
    text = _text(ISS)
    assert "PrivilegesRequired=lowest" in text, "must not require administrator rights"
    assert "{localappdata}\\Programs\\PelicanTownSpecials" in text, (
        "default install dir must be per-user"
    )
    # The install dir must be disjoint from the workspace dir so uninstall can
    # never wipe user data (M7-T23-INSTALL-003/004).
    assert WORKSPACE_DIR not in text, "install dir must not overlap the workspace dir"
    assert "MinVersion=10.0" in text, "must target Windows 10/11"
    assert "ArchitecturesAllowed=x64os" in text, "must require a 64-bit OS"


def test_no_uninstall_delete_touches_workspace() -> None:
    text = _text(ISS)
    # If an [UninstallDelete] section appears it must never reference the
    # workspace location (M7-T23-INSTALL-003).
    uninstall_delete = re.search(
        r"\[UninstallDelete\](.*?)(?=\n\[|\Z)", text, re.DOTALL | re.IGNORECASE
    )
    assert uninstall_delete is None or "PelicanTownSpecials" not in uninstall_delete.group(1), (
        "[UninstallDelete] must not delete anything under the user profile"
    )


def test_start_menu_required_desktop_optional() -> None:
    text = _text(ISS)
    assert 'Name: "{group}\\Pelican Town Specials"' in text, "start-menu shortcut required"
    assert "desktopicon" in text, "desktop shortcut must be a task"
    assert re.search(r'Name: "desktopicon".*Flags: unchecked', text, re.DOTALL), (
        "desktop shortcut must be unchecked by default"
    )


def test_version_aligned_with_frozen_metadata() -> None:
    version = _frozen_version()
    text = _text(ISS)
    assert f'PtsAppVersion "{version}"' in text, (
        f"installer default version must match version_info.txt ({version})"
    )
    # The output basename must be driven by the single version define so the
    # installer name can never drift from the frozen metadata (M7-D04).
    assert re.search(
        r"OutputBaseFilename=PelicanTownSpecials-Setup-v\{#PtsAppVersion\}", text
    ), "output basename must derive from PtsAppVersion"


def test_content_gate_shared_and_consistent() -> None:
    gate = _text(GATE)
    for needle in (".env", "StarValleyCook", "launcher-error.log", "workspace", ".map"):
        assert needle in gate, f"shared content gate must reject {needle}"
    for script in (_text(BUILD_WINDOWS), _text(BUILD_INSTALLER)):
        assert "release_content_gate.ps1" in script, (
            "bundle and installer builds must use the shared content gate"
        )


def test_installer_tooling_pinned() -> None:
    tool = _text(INSTALL_TOOL)
    assert "6.7.3" in tool, "Inno Setup version must be pinned"
    assert "CURRENTUSER" in tool, "must install per-user without admin"
    assert "Get-FileHash" in tool and "SHA256" in tool, "must verify the download hash"
    assert "ISCC.exe" in tool
    finder = _text(FIND_ISCC)
    assert "ISCC.exe" in finder and "Inno Setup 6" in finder


def test_smoke_covers_uninstall_and_workspace() -> None:
    smoke = _text(SMOKE)
    assert "$uninstaller = Join-Path $appDir 'unins000.exe'" in smoke, (
        "smoke must exercise the real uninstaller"
    )
    assert "Invoke-Silent $uninstaller" in smoke, (
        "smoke must invoke the real uninstaller"
    )
    assert "/VERYSILENT" in smoke
    assert re.search(r'"/DIR=.*\$appDir', smoke), (
        "smoke must install into the generated isolated app directory"
    )
    assert "/NOICONS" in smoke, (
        "smoke must avoid creating or removing default shortcut/group artifacts"
    )
    assert "Join-Path $runRoot 'health-workspace'" in smoke
    assert "Join-Path $runRoot 'preserved-workspace'" in smoke
    assert "'--workspace', $healthWorkspace" in smoke, (
        "health smoke must use the isolated health workspace"
    )
    assert "$marker = Join-Path $workspaceDir" in smoke
    assert "Test-Path -LiteralPath $marker" in smoke, (
        "smoke must assert the workspace survives install/reinstall/uninstall"
    )
    # The smoke must never resolve or touch the app's real default workspace.
    assert "_default_workspace_path" not in smoke, (
        "smoke must use only explicitly isolated temporary workspaces"
    )


def test_ci_builds_and_smokes_installer() -> None:
    # The verified pipeline now lives in the reusable build.yml; ci.yml calls it
    # and never publishes (Milestone 7 Task 24).
    build = _text(BUILD)
    assert "install_innosetup.ps1" in build, "pipeline must pin/install Inno Setup"
    assert "build_installer.ps1" in build, "pipeline must build the installer"
    assert "smoke_installer.ps1" in build, "pipeline must smoke-test the installer"
    assert "PelicanTownSpecials-Setup-v${{ inputs.version }}.exe" in build, (
        "pipeline must upload the versioned setup exe"
    )
    ci = _text(CI)
    assert "uses: ./.github/workflows/build.yml" in ci, "ci.yml must call the shared pipeline"
