"""Gameplay validation layered on top of the frozen domain models."""

from __future__ import annotations

from dataclasses import dataclass

from pelican_town_specials.domain.common import utc_now
from pelican_town_specials.domain.dish import GameplaySpec
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.domain.validation import (
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
)

from .repository import VanillaCatalog

GAMEPLAY_VALIDATOR_VERSION = "task8-gameplay-rules-v1"
GAMEPLAY_SOURCE_VERSION = "stardew-1.6"
_REFERENCE_BUFF_DURATION_MINUTES = 10
_REFERENCE_BUFF_DURATION_MAX_MINUTES = 600
_BUFF_REFERENCE_SOURCE = "Stardew 1.6 gameplay reference"
_BUFF_REFERENCE_VERSION = "stardew-1.6-gameplay-reference-v1"


@dataclass(frozen=True, slots=True)
class GameplayRuleSet:
    """Immutable, versioned soft-rule configuration for one catalog."""

    version: str
    catalog_version: str
    source_version: str
    observed_edibility_min: int
    observed_edibility_max: int
    observed_sell_price_min: int
    observed_sell_price_max: int
    buff_duration_min: int
    buff_duration_max: int
    buff_reference_source: str = _BUFF_REFERENCE_SOURCE
    buff_reference_version: str = _BUFF_REFERENCE_VERSION

    @classmethod
    def from_catalog(cls, catalog: VanillaCatalog) -> GameplayRuleSet:
        usable_items = [item for item in catalog.items if item.usable_as_ingredient]
        edibilities = [
            item.edibility for item in usable_items if item.edibility is not None
        ]
        sell_prices = [
            item.sell_price for item in usable_items if item.sell_price is not None
        ]
        if not edibilities or not sell_prices:
            raise ValueError("catalog has no usable item ranges for gameplay rules")
        return cls(
            version=GAMEPLAY_VALIDATOR_VERSION,
            catalog_version=catalog.version,
            source_version=GAMEPLAY_SOURCE_VERSION,
            observed_edibility_min=min(edibilities),
            observed_edibility_max=max(edibilities),
            observed_sell_price_min=min(sell_prices),
            observed_sell_price_max=max(sell_prices),
            buff_duration_min=_REFERENCE_BUFF_DURATION_MINUTES,
            buff_duration_max=_REFERENCE_BUFF_DURATION_MAX_MINUTES,
        )


def validate_gameplay(
    spec: GameplaySpec,
    catalog: VanillaCatalog,
    *,
    rules: GameplayRuleSet | None = None,
) -> ValidationReport:
    """Validate catalog membership and gameplay facts without rebuilding the domain model."""

    selected_rules = rules or GameplayRuleSet.from_catalog(catalog)
    issues: list[ValidationIssue] = []

    if selected_rules.catalog_version != catalog.version:
        issues.append(
            _issue(
                code="PTS_VALIDATION_CATALOG_VERSION_MISMATCH",
                severity=ValidationSeverity.ERROR,
                path="catalog",
                message="Gameplay rules and catalog versions do not match.",
                details={
                    "catalogVersion": catalog.version,
                    "rulesCatalogVersion": selected_rules.catalog_version,
                },
            )
        )
        return _report(issues)

    for index, ingredient in enumerate(spec.ingredients):
        path = f"ingredients[{index}].itemId"
        try:
            item = catalog.require(ingredient.item_id)
        except AppError as exc:
            if exc.code == "PTS_VALIDATION_INGREDIENT_ID_UNKNOWN":
                issues.append(
                    _issue(
                        code="PTS_VALIDATION_INGREDIENT_ID_UNKNOWN",
                        severity=ValidationSeverity.ERROR,
                        path=path,
                        message="Ingredient ID is not present in the vanilla catalog.",
                    )
                )
                continue
            raise

        if ingredient.catalog_version != catalog.version:
            issues.append(
                _issue(
                    code="PTS_VALIDATION_INGREDIENT_CATALOG_VERSION_MISMATCH",
                    severity=ValidationSeverity.ERROR,
                    path=f"ingredients[{index}].catalogVersion",
                    message="Ingredient catalog version does not match the active catalog.",
                )
            )
        if item.is_category:
            issues.append(
                _issue(
                    code="PTS_VALIDATION_INGREDIENT_CATEGORY",
                    severity=ValidationSeverity.ERROR,
                    path=path,
                    message="Catalog category entries cannot be used as ingredients.",
                )
            )
        elif not item.usable_as_ingredient:
            issues.append(
                _issue(
                    code="PTS_VALIDATION_INGREDIENT_NOT_USABLE",
                    severity=ValidationSeverity.ERROR,
                    path=path,
                    message="Catalog entry is not usable as an ingredient.",
                )
            )

    _validate_recovery(spec, selected_rules, issues)
    _append_soft_warnings(spec, selected_rules, issues)
    return _report(issues)


def _validate_recovery(
    spec: GameplaySpec,
    rules: GameplayRuleSet,
    issues: list[ValidationIssue],
) -> None:
    if spec.recovery.calculation_version != rules.source_version:
        issues.append(
            _issue(
                code="PTS_VALIDATION_RECOVERY_CALCULATION_VERSION_MISMATCH",
                severity=ValidationSeverity.ERROR,
                path="recovery.calculationVersion",
                message="Recovery calculation version is not supported by the rules.",
                details={
                    "expectedVersion": rules.source_version,
                    "actualVersion": spec.recovery.calculation_version,
                },
            )
        )


def _append_soft_warnings(
    spec: GameplaySpec,
    rules: GameplayRuleSet,
    issues: list[ValidationIssue],
) -> None:
    recovery = spec.recovery
    if not rules.observed_edibility_min <= recovery.edibility <= rules.observed_edibility_max:
        issues.append(
            _issue(
                code="PTS_VALIDATION_GAMEPLAY_EDIBILITY_OUTSIDE_OBSERVED_RANGE",
                severity=ValidationSeverity.WARNING,
                path="recovery.edibility",
                message="Recovery edibility is outside the observed vanilla range.",
                details={
                    "actual": recovery.edibility,
                    "observedMin": rules.observed_edibility_min,
                    "observedMax": rules.observed_edibility_max,
                    "catalogVersion": rules.catalog_version,
                    "sourceVersion": rules.source_version,
                },
            )
        )

    if not rules.observed_sell_price_min <= spec.sell_price <= rules.observed_sell_price_max:
        issues.append(
            _issue(
                code="PTS_VALIDATION_GAMEPLAY_SELL_PRICE_OUTSIDE_OBSERVED_RANGE",
                severity=ValidationSeverity.WARNING,
                path="sellPrice",
                message="Sell price is outside the observed vanilla range.",
                details={
                    "actual": spec.sell_price,
                    "observedMin": rules.observed_sell_price_min,
                    "observedMax": rules.observed_sell_price_max,
                    "catalogVersion": rules.catalog_version,
                    "sourceVersion": rules.source_version,
                },
            )
        )

    if spec.buff is not None and not rules.buff_duration_min <= spec.buff.duration_minutes <= rules.buff_duration_max:
        issues.append(
            _issue(
                code="PTS_VALIDATION_BUFF_DURATION_OUTSIDE_REFERENCE_RANGE",
                severity=ValidationSeverity.WARNING,
                path="buff.durationMinutes",
                message="Buff duration is outside the versioned reference range.",
                details={
                    "actual": spec.buff.duration_minutes,
                    "referenceMin": rules.buff_duration_min,
                    "referenceMax": rules.buff_duration_max,
                    "referenceSource": rules.buff_reference_source,
                    "referenceVersion": rules.buff_reference_version,
                },
            )
        )


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
        validator_version=GAMEPLAY_VALIDATOR_VERSION,
    )
