"""Task 10 OpenAPI contract tests for catalog and Blueprint PATCH inputs."""

from __future__ import annotations

from .conftest import ApiServices


def test_openapi_contains_catalog_search_path(services: ApiServices) -> None:
    schema = services.client.app.openapi()

    assert "/api/v1/catalog/ingredients" in schema["paths"]
    assert "get" in schema["paths"]["/api/v1/catalog/ingredients"]


def test_openapi_catalog_schemas_are_public(services: ApiServices) -> None:
    schema = services.client.app.openapi()
    schemas = schema["components"]["schemas"]

    assert "IngredientCatalogSearchResult" in schemas
    assert "IngredientCatalogItemView" in schemas
    properties = schemas["IngredientCatalogItemView"]["properties"]
    assert set(properties) == {"itemId", "displayNameEn", "displayNameZh"}


def test_openapi_recovery_input_has_no_derived_fields(services: ApiServices) -> None:
    schema = services.client.app.openapi()
    schemas = schema["components"]["schemas"]

    recovery_properties = schemas["BlueprintRecoveryInput"]["properties"]
    assert set(recovery_properties) == {"edibility"}
    for derived in (
        "energyRestore",
        "healthRestore",
        "calculationVersion",
    ):
        assert derived not in recovery_properties


def test_openapi_patch_inputs_are_request_dtos(services: ApiServices) -> None:
    schema = services.client.app.openapi()
    schemas = schema["components"]["schemas"]

    patch_properties = schemas["DraftPatchRequest"]["properties"]

    def _refs(value: object) -> list[str]:
        if isinstance(value, dict):
            if "$ref" in value:
                return [value["$ref"]]
            return [
                ref
                for item in value.get("anyOf", [])
                if isinstance(item, dict) and "$ref" in item
                for ref in [item["$ref"]]
            ]
        return []

    assert any(
        ref.endswith("BlueprintPresentationInput")
        for ref in _refs(patch_properties["presentation"])
    )
    assert any(
        ref.endswith("BlueprintGameplayInput")
        for ref in _refs(patch_properties["gameplay"])
    )
    assert "expectedRevision" in patch_properties
