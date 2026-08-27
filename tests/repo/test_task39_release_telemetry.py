"""Repository-level contracts for M10 Task 39 release telemetry."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD = REPO_ROOT / ".github" / "workflows" / "build.yml"
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
RELEASE = REPO_ROOT / ".github" / "workflows" / "release.yml"
CONFIG_WRITER = REPO_ROOT / "scripts" / "write_telemetry_config.ps1"
BUILD_WINDOWS = REPO_ROOT / "scripts" / "build_windows.ps1"
SMOKE_BUNDLE = REPO_ROOT / "scripts" / "smoke_windows_bundle.ps1"
SMOKE_INSTALLER = REPO_ROOT / "scripts" / "smoke_installer.ps1"
CONTENT_GATE = REPO_ROOT / "scripts" / "release_content_gate.ps1"
DOWNLOAD_REPORT = REPO_ROOT / "scripts" / "report_release_downloads.ps1"
DASHBOARD = REPO_ROOT / "packaging" / "telemetry" / "dashboard-manifest.json"
DASHBOARD_VALIDATOR = REPO_ROOT / "scripts" / "validate_telemetry_dashboard.py"
GITIGNORE = REPO_ROOT / ".gitignore"
PYINSTALLER_SPEC = REPO_ROOT / "packaging" / "pyinstaller" / "PelicanTownSpecials.spec"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _run_pwsh(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["pwsh", "-NoProfile", *arguments],
        cwd=REPO_ROOT,
        check=check,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def _ps_quote(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def _run_gate(root: Path) -> list[str]:
    command = (
        f". {_ps_quote(CONTENT_GATE)}; "
        f"@(Test-ReleaseContent -Root {_ps_quote(root)}) | ConvertTo-Json -Compress"
    )
    result = _run_pwsh("-Command", command)
    output = result.stdout.strip()
    if not output:
        return []
    decoded = json.loads(output)
    if isinstance(decoded, str):
        return [decoded]
    return list(decoded)


@pytest.mark.skipif(
    subprocess.run(
        ["pwsh", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.Major"],
        capture_output=True,
        check=False,
    ).returncode
    != 0,
    reason="PowerShell 7 is required for the Windows workflow contract tests",
)
def test_release_config_writer_creates_only_the_fixed_public_resource(
    tmp_path: Path,
) -> None:
    output = tmp_path / "resources" / "telemetry" / "telemetry.json"
    result = _run_pwsh(
        "-File",
        str(CONFIG_WRITER),
        "-OutputPath",
        str(output),
        "-TelemetryHost",
        "https://fake.local",
        "-TelemetryProjectToken",
        "phc_test_only",
        "-EnabledForBuild",
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "schemaVersion": 1,
        "host": "https://fake.local",
        "projectToken": "phc_test_only",
        "enabledForBuild": True,
    }


@pytest.mark.skipif(
    subprocess.run(
        ["pwsh", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.Major"],
        capture_output=True,
        check=False,
    ).returncode
    != 0,
    reason="PowerShell 7 is required for the Windows workflow contract tests",
)
def test_release_config_writer_clears_stale_resource_when_inputs_are_incomplete(
    tmp_path: Path,
) -> None:
    output = tmp_path / "resources" / "telemetry" / "telemetry.json"
    output.parent.mkdir(parents=True)
    output.write_text('{"enabledForBuild":true}', encoding="utf-8")

    result = _run_pwsh(
        "-File",
        str(CONFIG_WRITER),
        "-OutputPath",
        str(output),
    )

    assert result.returncode == 0, result.stderr
    assert not output.exists()


@pytest.mark.skipif(
    subprocess.run(
        ["pwsh", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.Major"],
        capture_output=True,
        check=False,
    ).returncode
    != 0,
    reason="PowerShell 7 is required for the Windows workflow contract tests",
)
def test_release_config_writer_rejects_non_https_origins(tmp_path: Path) -> None:
    output = tmp_path / "telemetry.json"
    result = _run_pwsh(
        "-File",
        str(CONFIG_WRITER),
        "-OutputPath",
        str(output),
        "-TelemetryHost",
        "http://fake.local",
        "-TelemetryProjectToken",
        "phc_test_only",
        "-EnabledForBuild",
        check=False,
    )

    assert result.returncode != 0
    assert not output.exists()


@pytest.mark.skipif(
    subprocess.run(
        ["pwsh", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.Major"],
        capture_output=True,
        check=False,
    ).returncode
    != 0,
    reason="PowerShell 7 is required for the Windows workflow contract tests",
)
def test_release_config_writer_rejects_private_capture_token_markers(
    tmp_path: Path,
) -> None:
    output = tmp_path / "telemetry.json"
    result = _run_pwsh(
        "-File",
        str(CONFIG_WRITER),
        "-OutputPath",
        str(output),
        "-TelemetryHost",
        "https://fake.local",
        "-TelemetryProjectToken",
        "phx_management_test",
        "-EnabledForBuild",
        check=False,
    )

    assert result.returncode != 0
    assert not output.exists()


def test_workflows_keep_ci_config_free_and_release_uses_repository_variables() -> None:
    build = _text(BUILD)
    ci = _text(CI)
    release = _text(RELEASE)

    for input_name in (
        "telemetry_host",
        "telemetry_project_token",
        "telemetry_enabled_for_build",
    ):
        assert input_name in build
    assert "write_telemetry_config.ps1" in _text(BUILD_WINDOWS)
    assert "resources/telemetry/telemetry.json" in _text(CONTENT_GATE)

    assert "PTS_TELEMETRY_" not in ci
    for variable in (
        "vars.PTS_TELEMETRY_HOST",
        "vars.PTS_TELEMETRY_PROJECT_TOKEN",
        "vars.PTS_TELEMETRY_ENABLED_FOR_BUILD",
    ):
        assert variable in release
    assert "secrets.PTS_TELEMETRY" not in release
    assert "management" not in (build + ci + release).lower()
    assert "admin_api_key" not in (build + ci + release).lower()


def test_telemetry_resource_has_one_ignored_path_and_is_copied_by_pyinstaller() -> None:
    gitignore_lines = {
        line.strip()
        for line in _text(GITIGNORE).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert "/resources/telemetry/telemetry.json" in gitignore_lines

    spec = _text(PYINSTALLER_SPEC)
    assert '"resources"' in spec
    assert '"resources"' in spec and "frontend/dist" in spec


def test_smoke_scripts_disable_telemetry_and_restore_the_parent_environment() -> None:
    for path in (SMOKE_BUNDLE, SMOKE_INSTALLER):
        text = _text(path)
        assert "$env:PTS_TELEMETRY_DISABLED = '1'" in text
        assert "PTS_TELEMETRY_DISABLED" in text
        assert "Remove-Item Env:PTS_TELEMETRY_DISABLED" in text
        assert "Start-Process" in text


def test_installer_smoke_uses_no_icons_and_direct_isolated_launches() -> None:
    text = _text(SMOKE_INSTALLER)

    # The run root is generated under the system temp directory and has a
    # strict name guard before any recursive cleanup is possible.
    assert "pts-installer-smoke-" in text
    assert "^pts-installer-smoke-[0-9a-f]{32}$" in text
    assert "Assert-SmokeRunRoot $runRoot" in text
    assert "$runRootCreated = $true" in text

    # Install and reinstall share the same explicit Inno location arguments;
    # /NOICONS prevents any default or smoke shortcut/group creation, and no
    # /GROUP override or Start Menu path is allowed in this smoke.
    assert re.search(r'"/DIR=.*\$appDir', text)
    assert "'/NOICONS'" in text
    assert not re.search(r'(?i)/GROUP(?:=|["`])', text)
    assert "START MENU" not in text.upper()
    assert "startMenu" not in text
    assert "startLnk" not in text
    assert ".lnk" not in text.lower()
    assert "WScript.Shell" not in text
    assert "if ($UseInstallLocation)" in text
    assert "$args += $innoInstallArguments" in text
    assert text.count("Invoke-Silent $setupFull") == 2
    assert text.count("-UseInstallLocation") == 2
    assert text.count("Start-Process -FilePath $appExe") == 2
    assert "Start-Process -FilePath $startLnk" not in text

    # The preservation marker is entirely below the validated run root. The
    # old default-workspace probe and default install path must stay absent.
    assert "$workspaceDir = [System.IO.Path]::GetFullPath((Join-Path $runRoot" in text
    assert "_default_workspace_path" not in text
    assert "$env:LOCALAPPDATA" not in text
    assert "Programs\\PelicanTownSpecials" not in text
    assert "Programs\\Pelican Town Specials" not in text
    assert "Test-Path -LiteralPath $marker -PathType Leaf" in text

    # Cleanup may recurse only through the validated unique temp-root guard;
    # it must not directly delete a workspace or user-computed default path.
    assert "Remove-SmokeRunRoot $runRoot" in text
    assert "Assert-SmokeRunRoot $path" in text
    assert "Remove-Item -LiteralPath $workspaceDir" not in text


def test_installer_smoke_registry_preflight_is_exact_and_read_only() -> None:
    text = _text(SMOKE_INSTALLER)

    assert "$innoAppId = '{F3A6C7E2-4B91-4E0D-9C6A-8D5F2B1A7C43}'" in text
    assert (
        'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\'
        '$($innoAppId)_is1'
    ) in text
    assert "[Microsoft.Win32.RegistryHive]::CurrentUser" in text
    assert "[Microsoft.Win32.RegistryView]::Registry64" in text
    assert "[Microsoft.Win32.RegistryView]::Registry32" in text
    assert "[Microsoft.Win32.RegistryKey]::OpenBaseKey" in text
    assert "$baseKey.OpenSubKey($innoUninstallSubKey, $false)" in text
    assert "GetSubKeyNames" not in text

    # The exact-key read-only preflight must execute before either setup call.
    preflight = text.index(
        "$preExistingRegistrationViews = @(Get-ExactInnoUninstallRegistrationViews)"
    )
    first_setup = text.index("$code = Invoke-Silent $setupFull")
    assert preflight < first_setup
    assert "if ($preExistingRegistrationViews.Count -gt 0)" in text
    assert "No setup process was started" in text

    # Installation must create the exact entry; uninstallation must remove it
    # in both views through Inno itself, never through smoke-script deletion.
    installed_assertion = text.index(
        "$installedRegistrationViews = @(Get-ExactInnoUninstallRegistrationViews)"
    )
    uninstaller = text.index("$code = Invoke-Silent $uninstaller")
    absence_assertion = text.index(
        "$remainingRegistrationViews = @(Get-ExactInnoUninstallRegistrationViews)"
    )
    assert first_setup < installed_assertion < uninstaller < absence_assertion
    assert "if ($installedRegistrationViews.Count -eq 0)" in text
    assert "if ($remainingRegistrationViews.Count -gt 0)" in text

    for forbidden in (
        "DeleteSubKey",
        "DeleteSubKeyTree",
        "DeleteValue",
        "Remove-Item HKCU",
        "Remove-Item Registry::",
    ):
        assert forbidden not in text


def test_release_content_gate_allows_only_a_valid_telemetry_resource(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bundle"
    config = root / "resources" / "telemetry" / "telemetry.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "host": "https://fake.local",
                "projectToken": "phc_test_only",
                "enabledForBuild": True,
            }
        ),
        encoding="utf-8",
    )
    (root / "README.txt").write_text("release bundle", encoding="utf-8")

    assert _run_gate(root) == []


@pytest.mark.skipif(
    subprocess.run(
        ["pwsh", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.Major"],
        capture_output=True,
        check=False,
    ).returncode
    != 0,
    reason="PowerShell 7 is required for the release content gate tests",
)
def test_release_content_gate_rejects_private_state_events_paths_and_keys(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "events.json").write_text(
        '{"installationId":"00000000-0000-4000-8000-000000000000",'
        '"event":"generation finished","distinct_id":"private"}',
        encoding="utf-8",
    )
    (root / "admin.txt").write_text(
        "POSTHOG_MANAGEMENT_API_KEY=do-not-ship\n"
        "C:\\Users\\example\\secret.json\n",
        encoding="utf-8",
    )
    violations = _run_gate(root)
    joined = "\n".join(violations).lower()

    assert "events.json" in joined
    assert "admin.txt" in joined


def test_release_content_gate_rejects_invalid_telemetry_schema(tmp_path: Path) -> None:
    root = tmp_path / "bundle"
    config = root / "resources" / "telemetry" / "telemetry.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "host": "http://not-https",
                "projectToken": "phc_test_only",
                "enabledForBuild": False,
                "extra": "not allowed",
            }
        ),
        encoding="utf-8",
    )

    violations = _run_gate(root)
    assert any("telemetry.json" in item.lower() for item in violations)


@pytest.mark.skipif(
    subprocess.run(
        ["pwsh", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.Major"],
        capture_output=True,
        check=False,
    ).returncode
    != 0,
    reason="PowerShell 7 is required for the release content gate tests",
)
def test_release_content_gate_rejects_unexpected_telemetry_paths_and_state_files(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bundle"
    (root / "other").mkdir(parents=True)
    (root / "other" / "telemetry.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "host": "https://fake.local",
                "projectToken": "phc_test_only",
                "enabledForBuild": True,
            }
        ),
        encoding="utf-8",
    )
    (root / "telemetry-state.sqlite3").write_bytes(b"private state")
    violations = _run_gate(root)
    joined = "\n".join(violations).lower()
    assert "telemetry.json" in joined
    assert "telemetry-state.sqlite3" in joined


def test_dashboard_manifest_is_internal_and_covers_the_frozen_metrics() -> None:
    assert DASHBOARD.exists()
    assert not str(DASHBOARD).replace("\\", "/").startswith(
        str(REPO_ROOT / "resources").replace("\\", "/")
    )
    manifest = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    assert manifest["manifestVersion"] == 1
    assert manifest["eventSchemaVersion"] == 1
    assert manifest["distribution"] == "internal-only"
    assert manifest["filters"]["production"]["type"] == "exclude_test_channel"
    assert manifest["filters"]["production"]["posthogCohort"] == "m10-test-channel"
    assert {item["id"] for item in manifest["dashboards"]} == {
        "user-volume",
        "core-usage",
        "quality-and-m9",
    }
    serialized = json.dumps(manifest).lower()
    for forbidden in (
        "app_version",
        "app version",
        "version adoption",
        "new-version adoption",
    ):
        assert forbidden not in serialized
    assert {
        item["id"] for item in manifest["manualAcceptanceChecklist"]
    } == {
        "posthog-project-settings",
        "marked-test-installation",
        "repository-variables",
        "dashboard-and-event-evidence",
    }
    assert all(
        item["status"] == "pending_external"
        for item in manifest["manualAcceptanceChecklist"]
    )


def test_dashboard_manifest_validator_is_local_and_deterministic() -> None:
    result = subprocess.run(
        ["python", str(DASHBOARD_VALIDATOR)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_download_report_is_read_only_and_offline_fixture_testable(tmp_path: Path) -> None:
    fixture = tmp_path / "release.json"
    fixture.write_text(
        json.dumps(
            {
                "tag_name": "v1.3.0",
                "assets": [
                    {
                        "name": "PelicanTownSpecials-Setup-v1.3.0.exe",
                        "download_count": 12,
                    },
                    {
                        "name": "PelicanTownSpecials-windows-x64-v1.3.0.zip",
                        "download_count": 34,
                    },
                    {"name": "SHA256SUMS.txt", "download_count": 99},
                ],
            }
        ),
        encoding="utf-8",
    )
    result = _run_pwsh(
        "-File",
        str(DOWNLOAD_REPORT),
        "-FixturePath",
        str(fixture),
    )
    report = json.loads(result.stdout)

    assert report["releaseTag"] == "v1.3.0"
    assert report["installerDownloadCount"] == 12
    assert report["portableDownloadCount"] == 34
    assert "re-upload" in report["caveat"].lower()

    text = _text(DOWNLOAD_REPORT).lower()
    assert "invoke-restmethod" in text
    assert "-method get" in text
    for forbidden in ("gh release upload", "gh release edit", "gh release create"):
        assert forbidden not in text
