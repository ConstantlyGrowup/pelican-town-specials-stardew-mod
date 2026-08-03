from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from pelican_town_specials.catalog import gameplay_rules
from pelican_town_specials.catalog.gameplay_rules import (
    GameplayRuleSet,
    validate_gameplay,
)
from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.domain.dish import (
    BuffAttributes,
    BuffSpec,
    GameIngredient,
    GameplaySpec,
    RecoverySpec,
)
from pelican_town_specials.domain.validation import ValidationSeverity

CATALOG_PATH = (
    Path(__file__).parents[3]
    / "resources"
    / "catalogs"
    / "stardew-1.6.15"
    / "vanilla-ingredients.json"
)


@pytest.fixture()
def catalog() -> VanillaCatalog:
    return VanillaCatalog.from_json(CATALOG_PATH)


def _ingredient(item_id: str = "256", quantity: int = 1) -> GameIngredient:
    return GameIngredient(
        itemId=item_id,
        displayName="model supplied text must not be trusted",
        quantity=quantity,
        mappingReason="validated candidate",
        catalogVersion="stardew-1.6.15-v1",
    )


def _spec(
    *,
    item_ids: tuple[str, ...] = ("256",),
    edibility: int = 8,
    sell_price: int = 60,
    buff: BuffSpec | None = None,
) -> GameplaySpec:
    return GameplaySpec(
        ingredients=[_ingredient(item_id) for item_id in item_ids],
        recovery=RecoverySpec(edibility=edibility),
        buff=buff,
        sellPrice=sell_price,
        isDrink=False,
    )


def _codes(report: object) -> set[str]:
    return {issue.code for issue in report.issues}  # type: ignore[attr-defined]


def test_valid_gameplay_uses_existing_recovery_derivation(catalog: VanillaCatalog) -> None:
    spec = _spec(edibility=80)

    report = validate_gameplay(spec, catalog)

    assert report.valid is True
    assert report.validator_version == "task8-gameplay-rules-v1"
    assert spec.recovery.calculation_version == "stardew-1.6"


def test_gameplay_consumes_recovery_facts_without_recomputing(
    catalog: VanillaCatalog, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _spec(edibility=80)

    monkeypatch.setattr(
        gameplay_rules,
        "floor",
        lambda _value: pytest.fail("Gameplay must not recompute RecoverySpec values"),
        raising=False,
    )

    report = validate_gameplay(spec, catalog)

    assert report.valid is True


@pytest.mark.parametrize(
    ("item_id", "code"),
    [
        ("NotReal", "PTS_VALIDATION_INGREDIENT_ID_UNKNOWN"),
        ("-5", "PTS_VALIDATION_INGREDIENT_CATEGORY"),
        ("0", "PTS_VALIDATION_INGREDIENT_NOT_USABLE"),
    ],
)
def test_ingredient_membership_errors_are_stable_and_safe(
    catalog: VanillaCatalog, item_id: str, code: str
) -> None:
    report = validate_gameplay(_spec(item_ids=(item_id,)), catalog)

    assert report.valid is False
    issue = next(issue for issue in report.issues if issue.code == code)
    assert issue.severity is ValidationSeverity.ERROR
    assert issue.path == "ingredients[0].itemId"
    assert issue.details == {}
    assert "model supplied" not in issue.message
    assert "Tomato" not in issue.message
    assert "NotReal" not in issue.message


def test_rule_version_mismatch_is_a_safe_error(catalog: VanillaCatalog) -> None:
    rules = GameplayRuleSet(
        version="task8-gameplay-rules-test",
        catalog_version="stardew-1.6.14-v1",
        source_version="stardew-1.6",
        observed_edibility_min=0,
        observed_edibility_max=200,
        observed_sell_price_min=1,
        observed_sell_price_max=5000,
        buff_duration_min=10,
        buff_duration_max=600,
    )

    report = validate_gameplay(_spec(), catalog, rules=rules)

    assert report.valid is False
    assert _codes(report) == {"PTS_VALIDATION_CATALOG_VERSION_MISMATCH"}
    assert report.issues[0].details == {
        "catalogVersion": "stardew-1.6.15-v1",
        "rulesCatalogVersion": "stardew-1.6.14-v1",
    }


def test_observed_range_warnings_do_not_make_report_invalid(catalog: VanillaCatalog) -> None:
    spec = _spec(edibility=300, sell_price=6000)
    rules = GameplayRuleSet.from_catalog(catalog)

    report = validate_gameplay(spec, catalog, rules=rules)

    assert report.valid is True
    assert {issue.severity for issue in report.issues} == {ValidationSeverity.WARNING}
    assert _codes(report) == {
        "PTS_VALIDATION_GAMEPLAY_EDIBILITY_OUTSIDE_OBSERVED_RANGE",
        "PTS_VALIDATION_GAMEPLAY_SELL_PRICE_OUTSIDE_OBSERVED_RANGE",
    }
    for issue in report.issues:
        assert issue.details["catalogVersion"] == "stardew-1.6.15-v1"
        assert issue.details["sourceVersion"] == "stardew-1.6"


def test_buff_duration_reference_warning_is_warning_only(catalog: VanillaCatalog) -> None:
    buff = BuffSpec(id="speed", durationMinutes=900, attributes=BuffAttributes(speed=1))

    report = validate_gameplay(_spec(buff=buff), catalog)
    rules = GameplayRuleSet.from_catalog(catalog)

    assert report.valid is True
    assert _codes(report) == {"PTS_VALIDATION_BUFF_DURATION_OUTSIDE_REFERENCE_RANGE"}
    assert report.issues[0].severity is ValidationSeverity.WARNING
    assert report.issues[0].path == "buff.durationMinutes"
    assert rules.buff_reference_source == "Stardew 1.6 gameplay reference"
    assert rules.buff_reference_version == "stardew-1.6-gameplay-reference-v1"
    assert report.issues[0].details == {
        "actual": 900,
        "referenceMin": 10,
        "referenceMax": 600,
        "referenceSource": "Stardew 1.6 gameplay reference",
        "referenceVersion": "stardew-1.6-gameplay-reference-v1",
    }


def test_structural_limits_remain_owned_by_domain_models() -> None:
    one = _spec(item_ids=("256",))
    eight = _spec(item_ids=tuple(str(item_id) for item_id in range(8)))
    assert len(one.ingredients) == 1
    assert len(eight.ingredients) == 8

    with pytest.raises(ValidationError):
        _spec(item_ids=tuple(str(item_id) for item_id in range(9)))
    with pytest.raises(ValidationError):
        _spec(item_ids=("256", "256"))
    with pytest.raises(ValidationError):
        _spec(item_ids=())

    for quantity in (1, 99):
        assert _ingredient(quantity=quantity).quantity == quantity
    with pytest.raises(ValidationError):
        GameIngredient(
            itemId="256",
            displayName="Tomato",
            quantity=100,
            mappingReason="validated candidate",
            catalogVersion="stardew-1.6.15-v1",
        )

    for edibility in (0, 500):
        assert RecoverySpec(edibility=edibility).edibility == edibility
    with pytest.raises(ValidationError):
        RecoverySpec(edibility=501)

    for sell_price in (0, 50000):
        assert _spec(sell_price=sell_price).sell_price == sell_price
    with pytest.raises(ValidationError):
        _spec(sell_price=50001)

    for duration in (10, 1440):
        assert BuffSpec(
            id="speed", durationMinutes=duration, attributes=BuffAttributes(speed=1)
        ).duration_minutes == duration
    with pytest.raises(ValidationError):
        BuffSpec(id="speed", durationMinutes=15, attributes=BuffAttributes(speed=1))


def test_recovery_derived_fields_cannot_be_supplied_by_caller() -> None:
    with pytest.raises(ValidationError):
        RecoverySpec(edibility=80, energyRestore=1)
