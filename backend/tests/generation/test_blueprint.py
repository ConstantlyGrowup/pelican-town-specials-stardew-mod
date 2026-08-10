"""Blueprint visual update: user-field protection, stage order, failure keep-stale."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from pelican_town_specials.domain.common import GenerationStage
from pelican_town_specials.domain.dish import FieldAuthority
from pelican_town_specials.domain.draft import DraftStatus
from pelican_town_specials.generation.blueprint import (
    BLUEPRINT_STAGE_ORDER,
    blueprint_preview_prompt,
    build_blueprint_visual_brief,
)
from pelican_town_specials.generation.events import GenerationEvent
from pelican_town_specials.images import downscale_for_vision
from pelican_town_specials.images.vision_input import EDIT_MIN_PIXELS
from pelican_town_specials.providers.contracts import ImageOperation

from .conftest import (
    GenerationHarness,
    blueprint_preview_command,
)

BLUEPRINT_FORBIDDEN_STAGES = (
    GenerationStage.DISH_ANALYSIS,
    GenerationStage.GAMEPLAY_DESIGN,
    GenerationStage.INGREDIENT_MAPPING,
)


async def _collect(
    agen: AsyncIterator[GenerationEvent],
) -> list[GenerationEvent]:
    events: list[GenerationEvent] = []
    async for event in agen:
        events.append(event)
    return events


async def test_blueprint_generation_never_changes_user_fields(
    harness: GenerationHarness, blueprint_stale
) -> None:
    before = blueprint_stale.model_dump(include={"presentation", "gameplay"})
    await _collect(
        harness.orchestrator.run(blueprint_preview_command(blueprint_stale))
    )
    after = harness.orchestrator.drafts.get(blueprint_stale.draft_id)
    assert after.model_dump(include={"presentation", "gameplay"}) == before
    assert after.status is DraftStatus.REVIEWABLE


async def test_blueprint_stage_order_and_image_only_calls(
    harness: GenerationHarness, blueprint_stale
) -> None:
    events = await _collect(
        harness.orchestrator.run(blueprint_preview_command(blueprint_stale))
    )
    succeeded = [
        event.stage for event in events if event.type == "stage.succeeded"
    ]
    # Exact six-stage blueprint sequence, no Ask Gus analysis stages.
    assert succeeded == list(BLUEPRINT_STAGE_ORDER)
    for forbidden in BLUEPRINT_FORBIDDEN_STAGES:
        assert forbidden not in succeeded
    # The icon is generated first, then the model renders the complete preview
    # with the original photograph and same-round icon source.
    assert harness.gateway.calls == ["image", "image"]
    assert len(harness.gateway.image_requests) == 2
    icon_request, preview_request = harness.gateway.image_requests
    assert icon_request.operation is ImageOperation.GENERATION
    assert preview_request.operation is ImageOperation.EDIT
    assert preview_request.quality == "high"
    assert len(preview_request.source_images) == 2
    original_ref = harness.asset_store.stat(
        blueprint_stale.source.original_image_asset_id
    )
    with harness.asset_store.open(original_ref) as handle:
        original_data = handle.read()
    downscaled, media_type = downscale_for_vision(
        original_data, min_pixels=EDIT_MIN_PIXELS
    )
    assert preview_request.source_images[0].data == downscaled
    assert preview_request.source_images[0].media_type is media_type
    for required_text in (
        blueprint_stale.presentation.display_name,
        blueprint_stale.presentation.category_label,
        blueprint_stale.presentation.description,
        f"能量：+{blueprint_stale.gameplay.recovery.energy_restore}",
        f"生命：+{blueprint_stale.gameplay.recovery.health_restore}",
        f"售价：{blueprint_stale.gameplay.sell_price}g",
        "item hover tooltip",
        "不是海报",
        "无 Buff：不要生成增益行和持续时间行",
    ):
        assert required_text in preview_request.prompt
    assert "持续时间：" not in preview_request.prompt
    assert events[-1].type == "attempt.succeeded"

    restored = harness.orchestrator.drafts.get(blueprint_stale.draft_id)
    assert restored.revision == blueprint_stale.revision + 1
    assert restored.visuals is not None
    assert restored.visuals.source_revision == restored.revision


def test_blueprint_buff_prompt_uses_localized_rows_icons_and_duration(
    blueprint_stale,
) -> None:
    from pelican_town_specials.domain.dish import BuffAttributes, BuffSpec

    assert blueprint_stale.presentation is not None
    assert blueprint_stale.gameplay is not None
    gameplay = blueprint_stale.gameplay.model_copy(
        update={
            "buff": BuffSpec(
                id="internal-buff-id",
                durationMinutes=490,
                attributes=BuffAttributes(
                    farmingLevel=1,
                    fishingLevel=-2,
                    miningLevel=3,
                    foragingLevel=-4,
                    combatLevel=5,
                    luckLevel=1,
                    attack=-6,
                    defense=7,
                    immunity=-8,
                    magneticRadius=9,
                    maxStamina=-10,
                    speed=1,
                ),
            )
        }
    )

    prompt = blueprint_preview_prompt(blueprint_stale.presentation, gameplay)

    expected_price = f"售价：{gameplay.sell_price}g"
    assert prompt.endswith(expected_price)

    for row in (
        "耕种 +1",
        "钓鱼 -2",
        "采矿 +3",
        "采集 -4",
        "战斗 +5",
        "幸运 +1",
        "攻击 -6",
        "防御 +7",
        "免疫 -8",
        "磁力 +9",
        "最大体力 -10",
        "速度 +1",
        "持续时间：8:10",
    ):
        assert row in prompt
    for internal_text in (
        "internal-buff-id",
        "farmingLevel",
        "fishingLevel",
        "miningLevel",
        "foragingLevel",
        "combatLevel",
        "luckLevel",
        "attack",
        "defense",
        "immunity",
        "magneticRadius",
        "maxStamina",
        "speed",
    ):
        assert internal_text not in prompt
    for layout_instruction in (
        "恢复值和每条增益行左侧使用匹配的星露谷式像素状态图标",
        "增益行后添加一条游戏式分隔线",
        "时钟像素图标",
        "金币像素图标",
        "售价作为最后一行",
    ):
        assert layout_instruction in prompt

    assert gameplay.buff is not None
    seven_hour_buff = gameplay.buff.model_copy(update={"duration_minutes": 420})
    seven_hour_gameplay = gameplay.model_copy(update={"buff": seven_hour_buff})
    seven_hour_prompt = blueprint_preview_prompt(
        blueprint_stale.presentation, seven_hour_gameplay
    )
    assert "持续时间：7:00" in seven_hour_prompt


async def test_blueprint_visual_brief_is_deterministic_and_model_free(
    harness: GenerationHarness, blueprint_stale
) -> None:
    await _collect(
        harness.orchestrator.run(blueprint_preview_command(blueprint_stale))
    )
    # No analyze/design calls: VISUAL_BRIEF is a deterministic user-field function.
    assert harness.gateway.calls == ["image", "image"]
    restored = harness.orchestrator.drafts.get(blueprint_stale.draft_id)
    assert restored.visuals is not None
    assert restored.visuals.visual_brief == build_blueprint_visual_brief(
        blueprint_stale.presentation, blueprint_stale.gameplay
    )


async def test_blueprint_failure_keeps_stale_preview(
    harness: GenerationHarness, blueprint_stale
) -> None:
    harness.gateway.fail_stage = GenerationStage.ICON_GENERATION_AND_NORMALIZATION
    events = await _collect(
        harness.orchestrator.run(blueprint_preview_command(blueprint_stale))
    )
    assert events[-1].type == "attempt.failed"
    restored = harness.orchestrator.drafts.get(blueprint_stale.draft_id)
    # Stays STALE_PREVIEW; user fields and old visuals are preserved.
    assert restored.status is DraftStatus.STALE_PREVIEW
    assert restored.presentation == blueprint_stale.presentation
    assert restored.gameplay == blueprint_stale.gameplay
    assert restored.visuals == blueprint_stale.visuals
    # Active attempt cleared and failure recorded.
    assert restored.active_attempt_id is None
    assert restored.last_error is not None
    assert restored.last_attempt_id is not None
    # Only the icon image generation was attempted.
    assert harness.gateway.calls == ["image"]


async def test_blueprint_cancel_keeps_stale_preview(
    harness: GenerationHarness, blueprint_stale
) -> None:
    harness.gateway.delay = 0.3
    agen = harness.orchestrator.run(blueprint_preview_command(blueprint_stale))
    holder: list[GenerationEvent] = []

    async def consume() -> None:
        async for event in agen:
            holder.append(event)

    task = asyncio.create_task(consume())
    for _ in range(200):
        if holder and holder[0].attempt_id is not None:
            break
        await asyncio.sleep(0.01)
    assert holder, "attempt.started was never emitted"
    attempt_id = holder[0].attempt_id
    assert attempt_id is not None

    await asyncio.sleep(0.05)
    assert harness.orchestrator.cancel(attempt_id) is True
    await task

    restored = harness.orchestrator.drafts.get(blueprint_stale.draft_id)
    # Cancelled preview keeps STALE_PREVIEW with user fields and old visuals.
    assert restored.status is DraftStatus.STALE_PREVIEW
    assert restored.active_attempt_id is None
    assert restored.last_error is not None
    assert restored.presentation == blueprint_stale.presentation
    assert restored.gameplay == blueprint_stale.gameplay
    assert restored.visuals == blueprint_stale.visuals
    assert holder[-1].type == "attempt.failed"
    assert holder[-1].error is not None
    assert holder[-1].error.code == "PTS_GEN_CANCELLED"


def test_blueprint_preview_prompt_stays_within_provider_limit() -> None:
    """Blueprint prompt must fit the 1500-char provider contract even with
    maximum-length user fields and a maximum BuffSpec."""
    from pelican_town_specials.domain.dish import (
        BuffAttributes,
        BuffSpec,
        GameIngredient,
        GameplaySpec,
        PresentationSpec,
        RecoverySpec,
    )
    from pelican_town_specials.generation.blueprint import blueprint_preview_prompt

    presentation = PresentationSpec(
        displayName="名" * 60,
        internalName="MaxName",
        categoryLabel="类" * 40,
        description="描" * 400,
        tags=[],
    )
    gameplay = GameplaySpec(
        ingredients=[
            GameIngredient(
                itemId=str(index),
                displayName="材" * 80,
                quantity=1,
                mappingReason="catalog match",
                catalogVersion="stardew-1.6.15-v1",
            )
            for index in range(8)
        ],
        recovery=RecoverySpec(edibility=500),
        sellPrice=50000,
        isDrink=False,
        buff=BuffSpec(
            id="益" * 80,
            durationMinutes=1440,
            attributes=BuffAttributes(
                farmingLevel=99999,
                fishingLevel=99999,
                miningLevel=99999,
                foragingLevel=99999,
                combatLevel=99999,
                luckLevel=99999,
                attack=99999,
                defense=99999,
                immunity=99999,
                magneticRadius=99999,
                maxStamina=99999,
                speed=99999,
            ),
        ),
    )
    prompt = blueprint_preview_prompt(presentation, gameplay)
    assert len(prompt) <= 1500


def test_blueprint_preview_prompt_en_stays_within_provider_limit() -> None:
    """The English tooltip prompt must also fit the 1500-char provider contract
    with maximum-length user fields and a maximum BuffSpec (M7-T26-GEN-002)."""
    from pelican_town_specials.domain.common import Language
    from pelican_town_specials.domain.dish import (
        BuffAttributes,
        BuffSpec,
        GameIngredient,
        GameplaySpec,
        PresentationSpec,
        RecoverySpec,
    )
    from pelican_town_specials.generation.blueprint import blueprint_preview_prompt

    presentation = PresentationSpec(
        displayName="N" * 60,
        internalName="MaxName",
        categoryLabel="C" * 40,
        description="D" * 400,
        tags=[],
    )
    gameplay = GameplaySpec(
        ingredients=[
            GameIngredient(
                itemId=str(index),
                displayName="I" * 80,
                quantity=1,
                mappingReason="catalog match",
                catalogVersion="stardew-1.6.15-v1",
            )
            for index in range(8)
        ],
        recovery=RecoverySpec(edibility=500),
        sellPrice=50000,
        isDrink=False,
        buff=BuffSpec(
            id="B" * 80,
            durationMinutes=1440,
            attributes=BuffAttributes(
                farmingLevel=99999,
                fishingLevel=99999,
                miningLevel=99999,
                foragingLevel=99999,
                combatLevel=99999,
                luckLevel=99999,
                attack=99999,
                defense=99999,
                immunity=99999,
                magneticRadius=99999,
                maxStamina=99999,
                speed=99999,
            ),
        ),
    )
    prompt = blueprint_preview_prompt(
        presentation, gameplay, language=Language.EN_US
    )
    assert len(prompt) <= 1500


def test_blueprint_enforce_preview_prompt_budget_rejects_oversized_prompt() -> None:
    """The shared budget gate rejects an oversized Blueprint prompt with a
    controlled non-retryable error; the current builder stays within the
    contract for maximum legal user fields and BuffSpec."""
    from pelican_town_specials.domain.errors import AppError
    from pelican_town_specials.generation.blueprint import (
        enforce_preview_prompt_budget,
    )

    enforce_preview_prompt_budget("词条" * 700)  # within 1500 chars: no-op.
    with pytest.raises(AppError) as raised:
        enforce_preview_prompt_budget("词条" * 800)  # > 1500 chars.
    error = raised.value
    assert error.code == "PTS_PREVIEW_PROMPT_TOO_LONG"
    assert error.http_status == 422
    assert error.retryable is False


async def test_blueprint_preserves_provenance_and_cache_eligibility(
    harness: GenerationHarness, blueprint_stale
) -> None:
    await _collect(
        harness.orchestrator.run(blueprint_preview_command(blueprint_stale))
    )
    restored = harness.orchestrator.drafts.get(blueprint_stale.draft_id)
    # Provenance keeps user authority and cache ineligibility; the successful
    # preview records which visual prompt template produced it (R-03).
    assert restored.provenance.cache_eligibility is False
    assert (
        FieldAuthority.AGENT_ASSIGNED
        not in restored.provenance.authority_by_field.values()
    )
    assert restored.provenance.prompt_versions == {
        "visual": "visual-v3-multi-image-edit-zh"
    }


# --- Task 26: en-US prompt branches -----------------------------------------


def _en_presentation_and_gameplay() -> tuple:
    from pelican_town_specials.domain.dish import (
        GameIngredient,
        GameplaySpec,
        PresentationSpec,
        RecoverySpec,
    )

    presentation = PresentationSpec(
        displayName="Spring Noodle Bowl",
        internalName="SpringNoodleBowl",
        categoryLabel="Main Course",
        description="A warm bowl of spring noodles.",
        tags=["spring", "noodles"],
    )
    gameplay = GameplaySpec(
        ingredients=[
            GameIngredient(
                itemId="24",
                displayName="Parsnip",
                quantity=1,
                mappingReason="catalog match",
                catalogVersion="stardew-1.6.15-v1",
            )
        ],
        recovery=RecoverySpec(edibility=80),
        sellPrice=220,
        isDrink=False,
    )
    return presentation, gameplay


def test_build_full_tooltip_prompt_en_uses_english_labels() -> None:
    from pelican_town_specials.domain.common import Language
    from pelican_town_specials.generation.blueprint import (
        build_full_tooltip_prompt,
    )

    presentation, gameplay = _en_presentation_and_gameplay()
    prompt = build_full_tooltip_prompt(
        presentation, gameplay, language=Language.EN_US
    )
    assert prompt.endswith(f"Price:{gameplay.sell_price}g")
    for required in (
        "Title:",
        "Category:",
        "Description:",
        "Energy:",
        "Health:",
        "Price:",
        "item hover tooltip",
        "not a poster",
        "No Buff: do not generate a buff row or a duration row.",
    ):
        assert required in prompt
    for forbidden in (
        "标题：",
        "类别：",
        "描述：",
        "能量：",
        "生命：",
        "售价：",
        "无 Buff：",
        "持续时间：",
    ):
        assert forbidden not in prompt
    assert "Duration:" not in prompt


def test_build_full_tooltip_prompt_en_buff_rows_use_english_labels() -> None:
    from pelican_town_specials.domain.common import Language
    from pelican_town_specials.domain.dish import BuffAttributes, BuffSpec
    from pelican_town_specials.generation.blueprint import (
        build_full_tooltip_prompt,
    )

    presentation, gameplay = _en_presentation_and_gameplay()
    gameplay = gameplay.model_copy(
        update={
            "buff": BuffSpec(
                id="buff-en",
                durationMinutes=490,
                attributes=BuffAttributes(
                    farmingLevel=1,
                    fishingLevel=-2,
                    miningLevel=3,
                    combatLevel=5,
                    speed=1,
                ),
            )
        }
    )
    prompt = build_full_tooltip_prompt(
        presentation, gameplay, language=Language.EN_US
    )
    for row in (
        "Farming +1",
        "Fishing -2",
        "Mining +3",
        "Combat +5",
        "Speed +1",
        "Duration:8:10",
    ):
        assert row in prompt
    for forbidden in ("耕种", "钓鱼", "采矿", "战斗", "速度", "持续时间："):
        assert forbidden not in prompt
    for guidance in (
        "pixel icons left of the recovery",
        "divider after buffs",
        "clock icon left of the duration row",
        "coin icon left of the price row",
    ):
        assert guidance in prompt


def test_build_blueprint_visual_brief_en() -> None:
    from pelican_town_specials.domain.common import Language
    from pelican_town_specials.generation.blueprint import (
        build_blueprint_visual_brief,
    )

    presentation, gameplay = _en_presentation_and_gameplay()
    brief = build_blueprint_visual_brief(
        presentation, gameplay, language=Language.EN_US
    )
    assert "Stardew Valley-style dish illustration:" in brief
    assert "category Main Course" in brief
    assert "Main ingredients: Parsnip" in brief
    assert "pixel art style" in brief
    assert "星露谷" not in brief


def test_blueprint_icon_prompt_en() -> None:
    from pelican_town_specials.domain.common import Language
    from pelican_town_specials.generation.blueprint import blueprint_icon_prompt

    presentation, _gameplay = _en_presentation_and_gameplay()
    prompt = blueprint_icon_prompt(presentation, language=Language.EN_US)
    assert prompt.startswith(
        "Stardew Valley-style 16×16 game icon: Spring Noodle Bowl"
    )
    assert "magenta background" in prompt
    assert "no shadows, no reflections, no text, no borders" in prompt
    assert "星露谷" not in prompt


async def test_blueprint_en_draft_uses_english_prompts(
    harness: GenerationHarness, blueprint_stale_en
) -> None:
    events = await _collect(
        harness.orchestrator.run(blueprint_preview_command(blueprint_stale_en))
    )
    assert events[-1].type == "attempt.succeeded"
    icon_request, preview_request = harness.gateway.image_requests
    assert "Stardew Valley-style 16×16 game icon" in icon_request.prompt
    assert "星露谷风格的 16×16 游戏图标" not in icon_request.prompt
    for required_text in (
        "item hover tooltip",
        "not a poster",
        "Title:",
        "Category:",
        "Description:",
        "Energy:",
        "Health:",
        "Price:",
    ):
        assert required_text in preview_request.prompt
    for forbidden in (
        "标题：",
        "类别：",
        "描述：",
        "能量：",
        "生命：",
        "售价：",
        "无 Buff：",
        "持续时间：",
    ):
        assert forbidden not in preview_request.prompt
    restored = harness.orchestrator.drafts.get(blueprint_stale_en.draft_id)
    assert restored.visuals is not None
    assert restored.visuals.prompt_version == "visual-v3-multi-image-edit-en"
    # Provenance stays user-authored (no AGENT_ASSIGNED, no cache eligibility)
    # but records which visual prompt template produced the preview (R-03).
    assert (
        restored.provenance.authority_by_field
        == blueprint_stale_en.provenance.authority_by_field
    )
    assert restored.provenance.cache_eligibility is False
    assert restored.provenance.prompt_versions == {
        "visual": "visual-v3-multi-image-edit-en"
    }
