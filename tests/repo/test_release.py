"""Milestone 7 Task 24: GitHub Release workflow contract (repo-level gates).

The release flow is validated locally; no real GitHub Release is created here.
These tests lock the frozen release contract: v* tag / manual-dispatch-only
triggering, version consistency with version_info.txt, minimal write
permissions (release job only), artifact manifest, and no secret leakage.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

BUILD = REPO_ROOT / ".github" / "workflows" / "build.yml"
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
RELEASE = REPO_ROOT / ".github" / "workflows" / "release.yml"
CHECK_VERSION = REPO_ROOT / "scripts" / "check_release_version.ps1"
NOTES = REPO_ROOT / "scripts" / "generate_release_notes.ps1"
RELEASE_README = REPO_ROOT / "packaging" / "release" / "README.txt"
VERSION_INFO = REPO_ROOT / "packaging" / "pyinstaller" / "version_info.txt"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _frozen_version() -> str:
    match = re.search(r"StringStruct\('FileVersion', '([^']+)'\)", _text(VERSION_INFO))
    assert match, "version_info.txt must declare a FileVersion"
    return match.group(1)


def test_release_triggered_only_by_tag_or_manual() -> None:
    release = _text(RELEASE)
    assert "'v*'" in release, "release must trigger only on v* tags"
    assert "workflow_dispatch" in release, "release must support a manual dispatch"
    assert "gh release create" in release, "release job must create the Release"
    # CI must never publish on ordinary push/PR.
    ci = _text(CI)
    assert "pull_request" in ci, "ci must run on PRs"
    assert "gh release create" not in ci, "ci must never create a Release"


def test_release_build_pipeline_is_reused_and_gated() -> None:
    build = _text(BUILD)
    assert "workflow_call" in build, "build.yml must be reusable"
    assert "install_innosetup.ps1" in build, "pipeline must pin/install Inno Setup"
    assert "build_installer.ps1" in build, "pipeline must build the installer"
    assert "smoke_installer.ps1" in build, "pipeline must smoke-test the installer"
    assert "smoke_windows_bundle.ps1" in build, "pipeline must smoke-test the bundle"
    assert "check_release_version.ps1" in build, "version drift gate must run in the pipeline"
    assert "Compress-Archive" in build, "portable ZIP must be built in the pipeline"
    assert "if-no-files-found: error" in build, "missing artifacts must fail the pipeline"
    assert "uses: ./.github/workflows/build.yml" in _text(RELEASE), (
        "release.yml must reuse the Release packaging pipeline"
    )
    assert "uses: ./.github/workflows/build.yml" not in _text(CI), (
        "ordinary CI must not run the Release packaging pipeline"
    )


def test_ci_splits_fast_push_checks_from_pr_and_main_checks() -> None:
    ci = _text(CI)

    assert "branches:\n      - '**'" in ci, "all branch pushes must receive fast CI"
    assert "pull_request:" in ci, "CI must run for pull requests"
    assert "backend-fast:" in ci and "frontend-fast:" in ci
    assert "python -m ruff check backend" in ci
    assert "python -m mypy backend/src" in ci
    assert "python -m pytest backend/tests tests/repo -q" in ci
    assert "pnpm --dir frontend test:run" in ci
    assert "pnpm --dir frontend lint" in ci
    assert "pnpm --dir frontend build" in ci
    assert (
        "python -m pytest tests/integration/test_task39_telemetry_e2e.py -q"
        in ci
    )

    full = ci.split("  pr-main-integration:", maxsplit=1)[1]
    assert (
        "if: github.event_name == 'pull_request' || github.ref == 'refs/heads/main'"
        in full
    )
    assert "needs: [backend-fast, frontend-fast]" in full
    assert "scripts/check_openapi_drift.ps1" in full
    assert "python -m pytest tests/integration -q" in full
    assert "pnpm --dir frontend exec playwright install chromium" in full
    assert "pnpm --dir frontend e2e" in full

    # The fast workflow checks source and frontend output only; release build
    # and upload remain exclusive to the reusable Release pipeline.
    assert "build.yml" not in ci
    assert "install_innosetup.ps1" not in ci
    assert "build_installer.ps1" not in ci
    assert "actions/upload-artifact" not in ci
    assert "PTS_TRIAL_API_KEY" not in ci
    assert "secrets." not in ci


def test_version_consistency_driven_by_one_define() -> None:
    version = _frozen_version()
    assert version == "1.5.7", "frozen metadata version is expected to be 1.5.7"
    # The pipeline default, the drift gate and the release input all center on
    # the same version, so the installer / ZIP / checksum / title can't disagree.
    build = _text(BUILD)
    assert f"default: '{version}'" in build, "pipeline default version must match the frozen version"
    assert "PelicanTownSpecials-Setup-v${{ inputs.version }}.exe" in build
    assert "PelicanTownSpecials-windows-x64-v${{ inputs.version }}.zip" in build
    check = _text(CHECK_VERSION)
    assert "version_info.txt" in check and "FileVersion" in check, (
        "drift gate must compare against version_info.txt"
    )
    assert f"'v{version}'" in _text(RELEASE) or f'"v{version}"' in _text(RELEASE), (
        "manual release input default must be v<frozen version>"
    )


def test_release_repeatable_and_repo_scoped() -> None:
    # A re-run of an existing tag must update the Release rather than fail, and
    # gh must know which repository to publish to without a checkout
    # (M7-T24-RELEASE-001/002 round-1 MUST_FIX).
    release = _text(RELEASE)
    assert "gh release view" in release, "must detect an existing Release"
    assert "gh release edit" in release, "must update an existing Release"
    assert "gh release upload" in release and "--clobber" in release, (
        "must re-upload assets idempotently"
    )
    assert "GH_REPO" in release and "github.repository" in release, (
        "release job must set the repository context for gh"
    )


def test_minimal_write_permissions_and_no_secrets() -> None:
    for path in (BUILD, CI, RELEASE):
        text = _text(path)
        # The personal provider key must never be referenced from any workflow,
        # and SUPER_SECRET is a generic leak probe. The bare "secrets." needle
        # is no longer a blanket ban: Task 30 intentionally forwards the trial
        # API key as a workflow-call secret (locked by the positive assertions
        # below), which is the single exception to the no-secret rule.
        for needle in ("PTS_OPENAI_API_KEY", "SUPER_SECRET"):
            assert needle not in text, f"{path.name} must not reference {needle!r}"
        if path == RELEASE:
            # The workflow default stays read-only; contents: write is granted
            # only to the create-release job (job-scoped, indented under a job).
            assert "permissions:\n  contents: read" in text, (
                "release workflow default must stay read-only"
            )
            assert "permissions:\n      contents: write" in text, (
                "contents: write must be scoped to the release job only"
            )
        else:
            assert "contents: write" not in text, f"{path.name} must stay read-only"
            assert "permissions:\n  contents: read" in text, (
                f"{path.name} must declare read-only permissions"
            )

    # Task 30 trial-key forwarding contract (T30-TRIAL-006): build.yml declares
    # the trial key as an optional workflow-call secret (so an unset repo secret
    # keeps the gitignored trial resource absent and the trial safely reports
    # unavailable), and both callers forward it on the reusable-pipeline call.
    build = _text(BUILD)
    assert "workflow_call" in build, "build.yml must remain a reusable workflow"
    assert "PTS_TRIAL_API_KEY" in build, (
        "build.yml must declare the trial key secret"
    )
    assert "required: false" in build, (
        "trial key secret must stay optional so an unset repo secret is safe"
    )
    assert "secrets.PTS_TRIAL_API_KEY" in build, (
        "the injection step must read the forwarded trial key secret"
    )
    assert "PTS_TRIAL_API_KEY" not in _text(CI), (
        "fast CI must not read or forward the trial key secret"
    )
    assert "PTS_TRIAL_API_KEY" in _text(RELEASE), (
        "release.yml must forward the trial key secret to build.yml"
    )


def test_release_assets_checksum_and_notes_consistent() -> None:
    release = _text(RELEASE)
    version = _frozen_version()
    # The checksum is generated over the exact published artifacts and attached.
    assert "sha256sum" in release, "checksum must be generated from the release assets"
    assert "SHA256SUMS.txt" in release, "checksum file must be a release asset"
    # Assets are versioned from the resolved output and the notes are attached.
    assert "PelicanTownSpecials-Setup-v${{ needs.resolve-version.outputs.version }}.exe" in release
    assert "PelicanTownSpecials-windows-x64-v${{ needs.resolve-version.outputs.version }}.zip" in release
    assert "--notes-file" in release, "release must carry the generated notes"
    assert f"v{version}" in release, "release title/tag must use the frozen version"
    notes = _text(NOTES)
    assert "SHA256SUMS.txt" in notes, "notes must reference the checksum file"
    assert "PelicanTownSpecials-Setup-v" in notes, "notes must reference the installer"
    assert "%LOCALAPPDATA%\\Programs\\PelicanTownSpecials" in notes, (
        "notes must give the per-user install steps"
    )
    for expected in (
        "原料映射升级",
        "本地检索",
        "自动回退",
        "收集品排序",
        "最新收录优先",
        "试用服务迁移",
        "额度与规则保持不变",
        "批量删除",
        "二次确认",
        "打包菜单",
        "报错信息",
        "英文提示",
        "问问 Gus",
        "中文界面",
        "gpt-image-2",
        "总额度为 5 次",
        "一次性恢复完整 5 次",
        "个人设置不受影响",
    ):
        assert expected in notes, f"release notes must mention {expected!r}"

    readme = _text(RELEASE_README)
    assert "v1.5.7" in readme, "bundle README must identify v1.5.7"
    assert "可先使用公共试用，也可以在「设置」页配置个人服务" in readme
    assert "英文提示" in readme
    assert "批量删除" in readme
    assert "试用服务迁移" in readme
    assert "最新收录优先" in readme
    assert "原料映射升级" in readme
    for expected in (
        "gpt-image-2",
        "总额度为 5 次",
        "一次性恢复完整 5 次",
        "个人设置不受影响",
    ):
        assert expected in readme, f"bundle README must mention {expected!r}"
