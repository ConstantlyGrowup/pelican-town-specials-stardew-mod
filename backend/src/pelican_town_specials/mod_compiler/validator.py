"""Compile-time validation for Content Patcher exports.

``validate_export`` implements the validation steps of the compile algorithm
(design 14.7 steps 2-4): snapshot integrity, in-pack uniqueness, and
catalog-gated gameplay checks. All issues reuse the ``PTS_VALIDATION_*``
code family and the shared ``ValidationIssue``/``ValidationReport`` types.
"""

from __future__ import annotations

import hashlib
import json

from pelican_town_specials.catalog.gameplay_rules import validate_gameplay
from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.domain.archive import ArchivedDish
from pelican_town_specials.domain.common import utc_now
from pelican_town_specials.domain.export import ExportSpec
from pelican_town_specials.domain.validation import (
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
)

from .ids import validate_internal_name

EXPORT_VALIDATOR_VERSION = "task16-export-validator-v1"


class ExportValidationError(Exception):
    """Raised when an export fails validation; carries the full report."""

    def __init__(self, report: ValidationReport) -> None:
        super().__init__("export validation failed")
        self.report = report


def validate_export(
    spec: ExportSpec,
    dishes: list[ArchivedDish],
    catalog: VanillaCatalog,
) -> ValidationReport:
    """Validate a full export: snapshot integrity, uniqueness, gameplay."""
    issues = _structure_issues(spec, dishes)
    for index, dish in enumerate(dishes):
        gameplay_report = validate_gameplay(dish.gameplay, catalog)
        for issue in gameplay_report.issues:
            issues.append(
                _issue(
                    code=issue.code,
                    severity=issue.severity,
                    path=f"dishes[{index}].{issue.path}"
                    if issue.path is not None
                    else f"dishes[{index}]",
                    message=issue.message,
                    details=dict(issue.details),
                )
            )
    return _report(issues)


def validate_export_structure(
    spec: ExportSpec,
    dishes: list[ArchivedDish],
) -> ValidationReport:
    """Structural validation without the catalog; used by the compiler."""
    return _report(_structure_issues(spec, dishes))


def _structure_issues(
    spec: ExportSpec,
    dishes: list[ArchivedDish],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    dish_by_id = {dish.dish_id: dish for dish in dishes}
    for index, dish_id in enumerate(spec.dish_ids):
        if dish_id not in dish_by_id:
            issues.append(
                _issue(
                    code="PTS_VALIDATION_DISH_MISSING",
                    severity=ValidationSeverity.ERROR,
                    path=f"dishIds[{index}]",
                    message="Export references a dish that is not present in the snapshot set.",
                    details={"dishId": str(dish_id)},
                )
            )

    spec_ids = set(spec.dish_ids)
    seen_dish_ids: set[object] = set()
    internal_names: dict[str, str] = {}
    for index, dish in enumerate(dishes):
        if dish.dish_id not in spec_ids:
            issues.append(
                _issue(
                    code="PTS_VALIDATION_DISH_UNREFERENCED",
                    severity=ValidationSeverity.ERROR,
                    path=f"dishes[{index}].dishId",
                    message="A snapshot is not referenced by the export spec.",
                    details={"dishId": str(dish.dish_id)},
                )
            )
        if dish.dish_id in seen_dish_ids:
            issues.append(
                _issue(
                    code="PTS_VALIDATION_DUPLICATE_DISH_ID",
                    severity=ValidationSeverity.ERROR,
                    path=f"dishes[{index}].dishId",
                    message="The snapshot set contains a duplicate dish id.",
                    details={"dishId": str(dish.dish_id)},
                )
            )
        seen_dish_ids.add(dish.dish_id)

        internal_name = dish.presentation.internal_name
        if not validate_internal_name(internal_name):
            issues.append(
                _issue(
                    code="PTS_VALIDATION_INTERNAL_NAME_INVALID",
                    severity=ValidationSeverity.ERROR,
                    path=f"dishes[{index}].presentation.internalName",
                    message="Internal name must match the required token format.",
                )
            )
        first_dish_id = internal_names.get(internal_name)
        if first_dish_id is not None:
            issues.append(
                _issue(
                    code="PTS_VALIDATION_DUPLICATE_INTERNAL_NAME",
                    severity=ValidationSeverity.ERROR,
                    path=f"dishes[{index}].presentation.internalName",
                    message="Internal names must be unique within a pack.",
                    details={
                        "internalName": internal_name,
                        "firstDishId": first_dish_id,
                    },
                )
            )
        else:
            internal_names[internal_name] = str(dish.dish_id)

        if _content_hash_of(dish) != dish.content_hash:
            issues.append(
                _issue(
                    code="PTS_VALIDATION_CONTENT_HASH_MISMATCH",
                    severity=ValidationSeverity.ERROR,
                    path=f"dishes[{index}].contentHash",
                    message="Archived dish content hash does not match its snapshot.",
                )
            )
        if dish.visuals.icon_16_asset_id is None:
            issues.append(
                _issue(
                    code="PTS_VALIDATION_ICON_16_MISSING",
                    severity=ValidationSeverity.ERROR,
                    path=f"dishes[{index}].visuals.icon16AssetId",
                    message="Archived dish has no 16px icon asset.",
                )
            )
    return issues


def _content_hash_of(dish: ArchivedDish) -> str:
    """Recompute the canonical snapshot hash used by the archiver."""
    payload = {
        "presentation": dish.presentation.model_dump(by_alias=True, mode="json"),
        "gameplay": dish.gameplay.model_dump(by_alias=True, mode="json"),
        "visuals": dish.visuals.model_dump(by_alias=True, mode="json"),
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _issue(
    *,
    code: str,
    severity: ValidationSeverity,
    path: str,
    message: str,
    details: dict[str, str | int | float | bool | None] | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity=severity,
        path=path,
        message=message,
        details=details or {},
    )


def _report(issues: list[ValidationIssue]) -> ValidationReport:
    return ValidationReport(
        valid=not any(issue.severity is ValidationSeverity.ERROR for issue in issues),
        issues=issues,
        validated_at=utc_now(),
        validator_version=EXPORT_VALIDATOR_VERSION,
    )
