"""Blueprint visual generation: fixed stage order, deterministic brief, prompts."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from pelican_town_specials.domain.common import GenerationStage
from pelican_town_specials.domain.dish import GameplaySpec, PresentationSpec
from pelican_town_specials.domain.draft import GenerationAttemptKind
from pelican_town_specials.generation.events import GenerationEvent

if TYPE_CHECKING:
    from pelican_town_specials.generation.orchestrator import (
        GenerationCommand,
        GenerationOrchestrator,
    )

BLUEPRINT_STAGE_ORDER: tuple[GenerationStage, ...] = (
    GenerationStage.INPUT_VALIDATION,
    GenerationStage.VISUAL_BRIEF,
    GenerationStage.ICON_GENERATION_AND_NORMALIZATION,
    GenerationStage.PREVIEW_ART_GENERATION_AND_COMPOSITION,
    GenerationStage.RESULT_VALIDATION,
    GenerationStage.ATOMIC_PROMOTION,
)


def build_blueprint_visual_brief(
    presentation: PresentationSpec,
    gameplay: GameplaySpec,
) -> str:
    """Deterministically derive a visual brief from user-owned Blueprint fields."""
    ingredients = "、".join(item.display_name for item in gameplay.ingredients)
    return (
        f"星露谷风格菜品插画：{presentation.display_name}，"
        f"分类{presentation.category_label}，"
        f"{presentation.description} 主要食材：{ingredients}。"
        f"暖色调，乡村酒馆桌面，像素风。"
    )


def blueprint_icon_prompt(presentation: PresentationSpec) -> str:
    return f"星露谷风格的 16×16 游戏图标：{presentation.display_name}"


def blueprint_preview_prompt(
    presentation: PresentationSpec,
    visual_brief: str,
) -> str:
    return (
        f"星露谷风格的菜品插画：{presentation.display_name}，{visual_brief}"
    )


def run_blueprint_preview(
    orchestrator: GenerationOrchestrator,
    command: GenerationCommand,
) -> AsyncIterator[GenerationEvent]:
    """Validate a BLUEPRINT_PREVIEW command and delegate to the orchestrator."""
    if command.kind is not GenerationAttemptKind.BLUEPRINT_PREVIEW:
        raise ValueError("run_blueprint_preview requires kind BLUEPRINT_PREVIEW")
    return orchestrator.run(command)
