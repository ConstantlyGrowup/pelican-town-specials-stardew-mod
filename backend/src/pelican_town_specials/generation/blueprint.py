"""Blueprint visual generation: fixed stage order, deterministic brief, prompts."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from pelican_town_specials.domain.common import GenerationStage
from pelican_town_specials.domain.dish import GameplaySpec, PresentationSpec
from pelican_town_specials.domain.draft import GenerationAttemptKind
from pelican_town_specials.domain.errors import AppError
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

_PROMPT_MAX_CHARS = 1500


def enforce_preview_prompt_budget(prompt: str) -> None:
    """Final shared budget gate for the Ask Gus and Blueprint edit prompts.

    Business fields stay verbatim; if even the compressed prompt exceeds the
    frozen provider contract (``ImageGenerationRequest.prompt`` max 1500
    chars), the stage fails with a controlled non-retryable validation error
    before any provider call instead of a ValidationError raised deep inside
    request construction.
    """
    if len(prompt) > _PROMPT_MAX_CHARS:
        raise AppError(
            code="PTS_PREVIEW_PROMPT_TOO_LONG",
            message="菜品字段内容过长，无法生成词条卡预览。请缩短描述、名称或增益后重试。",
            http_status=422,
            details={"promptLimit": _PROMPT_MAX_CHARS},
            retryable=False,
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
    gameplay: GameplaySpec,
) -> str:
    """Blueprint alias of the shared full-tooltip edit prompt."""
    return build_full_tooltip_prompt(presentation, gameplay)


def build_full_tooltip_prompt(
    presentation: PresentationSpec,
    gameplay: GameplaySpec,
) -> str:
    """Shared hard-anchor prompt for Ask Gus and Blueprint preview edits.

    The prompt anchors on Stardew Valley's in-game item hover tooltip
    language with only minimal layout constraints, then the verbatim
    validated field content. No material/design adjectives (parchment,
    gradients, corner ornaments) are used: the tooltip *type* is the
    priority, not surface description.
    """
    recovery = gameplay.recovery
    buff = gameplay.buff
    if buff is None:
        buff_text = "无 Buff：不要生成增益行"
    else:
        attributes = buff.attributes.model_dump(
            exclude_defaults=True, by_alias=True
        )
        attribute_text = "、".join(
            f"{key}={value}" for key, value in attributes.items()
        )
        buff_text = (
            f"Buff：{buff.id}，持续{buff.duration_minutes}分钟，"
            f"属性：{attribute_text}"
        )
    return (
        "输入图1是真实菜品原图，必须作为不可替换的摄影底图保留。"
        "输入图2是该菜品的像素图标，必须准确复用。"
        "以输入图1为基础，保持原始宽高比、裁切、食物、器皿、桌面、背景、"
        "光影、透视、景深和摄影质感不变。不要重画真实照片，不要整体调色，"
        "不要扩图，不要像素化真实照片。"
        "在画面留白区域添加一个《星露谷物语》风格的物品悬浮词条框。"
        "这个词条框必须看起来像 Stardew Valley 游戏内的 item hover tooltip。"
        "它应该是游戏内物品提示框，而不是海报、菜单、网页卡片、PPT 文本框、"
        "说明书卡片或羊皮纸公告板。"
        "词条框放在不遮挡主体的负空间区域。"
        "像素图标放在词条框上方或轻压上边框。"
        "除词条框和像素图标外，其余区域保持与原图一致。"
        "所有文字必须严格来自以下结构化字段，不要增删改，"
        "不要虚构额外 Buff：\n"
        f"标题：{presentation.display_name}\n"
        f"类别：{presentation.category_label}\n"
        f"描述：{presentation.description}\n"
        f"能量：+{recovery.energy_restore}\n"
        f"生命：+{recovery.health_restore}\n"
        f"售价：{gameplay.sell_price}g\n"
        f"{buff_text}"
    )


def run_blueprint_preview(
    orchestrator: GenerationOrchestrator,
    command: GenerationCommand,
) -> AsyncIterator[GenerationEvent]:
    """Validate a BLUEPRINT_PREVIEW command and delegate to the orchestrator."""
    if command.kind is not GenerationAttemptKind.BLUEPRINT_PREVIEW:
        raise ValueError("run_blueprint_preview requires kind BLUEPRINT_PREVIEW")
    return orchestrator.run(command)
