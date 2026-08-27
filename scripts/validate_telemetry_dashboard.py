"""Validate the internal, non-distributed M10 dashboard contract."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "packaging" / "telemetry" / "dashboard-manifest.json"
EXPECTED_DASHBOARDS = {"user-volume", "core-usage", "quality-and-m9"}
EXPECTED_WIDGETS = {
    "user-volume": {"dau", "wau", "mau"},
    "core-usage": {
        "mode-mix",
        "generation-success-rate",
        "generation-duration-p50",
        "generation-duration-p90",
        "archive-funnel",
        "export-funnel",
        "trial-used",
    },
    "quality-and-m9": {
        "terminal-outcomes",
        "memory-outcomes",
        "memory-duration",
    },
}
EXPECTED_CHECKLIST = {
    "posthog-project-settings",
    "marked-test-installation",
    "repository-variables",
    "dashboard-and-event-evidence",
}
FORBIDDEN_TERMS = (
    "app_version",
    "app version",
    "version adoption",
    "new-version adoption",
)
FORBIDDEN_NORMALIZED_TERMS = (
    "appversion",
    "applicationversion",
    "versionadoption",
    "newversionadoption",
)


def _load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("dashboard manifest must be a JSON object")
    return value


def validate_manifest(path: Path = MANIFEST_PATH) -> list[str]:
    errors: list[str] = []
    try:
        manifest = _load_manifest(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"cannot load dashboard manifest: {exc}"]

    if manifest.get("manifestVersion") != 1:
        errors.append("manifestVersion must be 1")
    if manifest.get("eventSchemaVersion") != 1:
        errors.append("eventSchemaVersion must be 1")
    if manifest.get("distribution") != "internal-only":
        errors.append("dashboard manifest must be internal-only")

    filters = manifest.get("filters")
    if not isinstance(filters, dict):
        errors.append("filters must be an object")
    else:
        production = filters.get("production")
        if not isinstance(production, dict):
            errors.append("production filter is required")
        elif production.get("type") != "exclude_test_channel":
            errors.append("production filter must exclude the test channel")
        elif production.get("posthogCohort") != "m10-test-channel":
            errors.append("production filter must name the m10-test-channel cohort")

    dashboards = manifest.get("dashboards")
    if not isinstance(dashboards, list):
        errors.append("dashboards must be a list")
    else:
        dashboard_ids = {
            item.get("id")
            for item in dashboards
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        if dashboard_ids != EXPECTED_DASHBOARDS:
            errors.append(
                "dashboards must contain user-volume, core-usage, and quality-and-m9"
            )
        for dashboard in dashboards:
            if not isinstance(dashboard, dict):
                errors.append("dashboard entries must be objects")
                continue
            widgets = dashboard.get("widgets")
            if not isinstance(widgets, list) or not widgets:
                errors.append(f"dashboard {dashboard.get('id')} needs widgets")
                continue
            expected_widgets = EXPECTED_WIDGETS.get(dashboard.get("id"), set())
            widget_ids = {
                widget.get("id")
                for widget in widgets
                if isinstance(widget, dict) and isinstance(widget.get("id"), str)
            }
            if widget_ids != expected_widgets:
                errors.append(
                    f"dashboard {dashboard.get('id')} has an unexpected widget set"
                )
            for widget in widgets:
                if not isinstance(widget, dict):
                    errors.append("dashboard widgets must be objects")
                elif widget.get("filter") != "production":
                    errors.append(
                        f"dashboard widget {widget.get('id')} lacks the production filter"
                    )

    serialized = json.dumps(manifest, ensure_ascii=False).lower()
    for term in FORBIDDEN_TERMS:
        if term in serialized:
            errors.append(f"dashboard manifest contains forbidden term: {term}")
    normalized = re.sub(r"[^a-z0-9]+", "", serialized)
    for term in FORBIDDEN_NORMALIZED_TERMS:
        if term in normalized:
            errors.append(
                "dashboard manifest contains forbidden version dimension: "
                f"{term}"
            )

    checklist = manifest.get("manualAcceptanceChecklist")
    if not isinstance(checklist, list):
        errors.append("manualAcceptanceChecklist must be a list")
    else:
        checklist_ids = {
            item.get("id")
            for item in checklist
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        if checklist_ids != EXPECTED_CHECKLIST:
            errors.append("manual checklist must contain all four external evidence items")
        for item in checklist:
            if not isinstance(item, dict):
                errors.append("manual checklist entries must be objects")
                continue
            if item.get("status") != "pending_external":
                errors.append(
                    f"manual item {item.get('id')} must remain pending_external until review"
                )
            checks = item.get("checks")
            if not isinstance(checks, list) or not checks or not all(
                isinstance(check, str) and check.strip() for check in checks
            ):
                errors.append(f"manual item {item.get('id')} needs non-empty checks")

    return errors


def main() -> int:
    errors = validate_manifest()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: validated internal telemetry dashboard manifest at {MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
