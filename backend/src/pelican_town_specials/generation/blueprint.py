"""Blueprint visual generation: fixed stage order, deterministic brief, prompts."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from pelican_town_specials.domain.common import GenerationStage, Language
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

_BUFF_ATTRIBUTE_LABELS_ZH: tuple[tuple[str, str], ...] = (
    ("farming_level", "耕种"),
    ("fishing_level", "钓鱼"),
    ("mining_level", "采矿"),
    ("foraging_level", "采集"),
    ("combat_level", "战斗"),
    ("luck_level", "幸运"),
    ("attack", "攻击"),
    ("defense", "防御"),
    ("immunity", "免疫"),
    ("magnetic_radius", "磁力"),
    ("max_stamina", "最大体力"),
    ("speed", "速度"),
)

_BUFF_ATTRIBUTE_LABELS_EN: tuple[tuple[str, str], ...] = (
    ("farming_level", "Farming"),
    ("fishing_level", "Fishing"),
    ("mining_level", "Mining"),
    ("foraging_level", "Foraging"),
    ("combat_level", "Combat"),
    ("luck_level", "Luck"),
    ("attack", "Attack"),
    ("defense", "Defense"),
    ("immunity", "Immunity"),
    ("magnetic_radius", "Magnetic"),
    ("max_stamina", "Max Energy"),
    ("speed", "Speed"),
)


def _buff_attribute_labels(
    language: Language,
) -> tuple[tuple[str, str], ...]:
    if language is Language.EN_US:
        return _BUFF_ATTRIBUTE_LABELS_EN
    return _BUFF_ATTRIBUTE_LABELS_ZH


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
    *,
    language: Language = Language.ZH_CN,
) -> str:
    """Deterministically derive a visual brief from user-owned Blueprint fields."""
    if language is Language.EN_US:
        ingredients = ", ".join(item.display_name for item in gameplay.ingredients)
        return (
            f"Stardew Valley-style dish illustration: {presentation.display_name}, "
            f"category {presentation.category_label}, "
            f"{presentation.description} Main ingredients: {ingredients}. "
            "Warm colors, rustic tavern table, pixel art style."
        )
    ingredients = "、".join(item.display_name for item in gameplay.ingredients)
    return (
        f"星露谷风格菜品插画：{presentation.display_name}，"
        f"分类{presentation.category_label}，"
        f"{presentation.description} 主要食材：{ingredients}。"
        f"暖色调，乡村酒馆桌面，像素风。"
    )


def blueprint_icon_prompt(
    presentation: PresentationSpec,
    *,
    language: Language = Language.ZH_CN,
) -> str:
    if language is Language.EN_US:
        return (
            f"Stardew Valley-style 16×16 game icon: {presentation.display_name}"
            ". Single item centered, solid magenta background (#FF00FF), no shadows, "
            "no reflections, no text, no borders"
        )
    return (
        f"星露谷风格的 16×16 游戏图标：{presentation.display_name}"
        "。单个物品居中，纯洋红色背景（#FF00FF），无阴影、无反光、无文字、无边框"
    )


def blueprint_preview_prompt(
    presentation: PresentationSpec,
    gameplay: GameplaySpec,
    *,
    language: Language = Language.ZH_CN,
) -> str:
    """Blueprint alias of the shared full-tooltip edit prompt."""
    return build_full_tooltip_prompt(presentation, gameplay, language=language)


def build_full_tooltip_prompt(
    presentation: PresentationSpec,
    gameplay: GameplaySpec,
    *,
    language: Language = Language.ZH_CN,
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
    english = language is Language.EN_US
    if buff is None:
        buff_rows = ""
        duration_row = ""
        if english:
            row_guidance = (
                "Stardew pixel icons left of the recovery rows and a gold coin icon left "
                "of the price row (last). "
                "No Buff: do not generate a buff row or a duration row. "
            )
        else:
            row_guidance = (
                "恢复值行左侧使用匹配的星露谷式像素状态图标；"
                "售价行左侧使用金币像素图标，售价作为最后一行。"
                "无 Buff：不要生成增益行和持续时间行。"
            )
    else:
        labels = _buff_attribute_labels(language)
        buff_rows = "".join(
            f"{label} {value:+d}\n"
            for field_name, label in labels
            if (value := getattr(buff.attributes, field_name)) != 0
        )
        hours, minutes = divmod(buff.duration_minutes, 60)
        if english:
            duration_row = f"Duration:{hours}:{minutes:02d}\n"
            row_guidance = (
                "Stardew pixel icons left of the recovery and each buff row, a divider "
                "after buffs, a clock icon left of the duration row, a coin icon left of "
                "the price row (last). "
            )
        else:
            duration_row = f"持续时间：{hours}:{minutes:02d}\n"
            row_guidance = (
                "恢复值和每条增益行左侧使用匹配的星露谷式像素状态图标；"
                "增益行后添加一条游戏式分隔线；"
                "持续时间行左侧使用时钟像素图标；"
                "售价行左侧使用金币像素图标，售价作为最后一行。"
            )
    if english:
        header = (
            "Input 1 = real dish photo (irreplaceable base); input 2 = pixel icon "
            "(reproduce exactly). Keep the photo's crop, table, background, lighting, "
            "perspective and texture unchanged; do not redraw, recolor, extend or "
            "pixelate. Add a Stardew Valley item hover tooltip box in a blank area clear "
            "of the subject; it must look like the in-game tooltip, not a poster or web "
            "card. Place the pixel icon above or overlapping the box top edge; keep all "
            "else identical. "
            f"{row_guidance}"
            "Text must come only from the fields below (no additions, deletions or "
            "invented Buffs):\n"
        )
        return (
            header
            + f"Title:{presentation.display_name}\n"
            + f"Category:{presentation.category_label}\n"
            + f"Description:{presentation.description}\n"
            + f"Energy:+{recovery.energy_restore}\n"
            + f"Health:+{recovery.health_restore}\n"
            + buff_rows
            + duration_row
            + f"Price:{gameplay.sell_price}g"
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
        f"{row_guidance}"
        "所有文字必须严格来自以下结构化字段，不要增删改，"
        "不要虚构额外 Buff：\n"
        f"标题：{presentation.display_name}\n"
        f"类别：{presentation.category_label}\n"
        f"描述：{presentation.description}\n"
        f"能量：+{recovery.energy_restore}\n"
        f"生命：+{recovery.health_restore}\n"
        f"{buff_rows}"
        f"{duration_row}"
        f"售价：{gameplay.sell_price}g"
    )


def run_blueprint_preview(
    orchestrator: GenerationOrchestrator,
    command: GenerationCommand,
) -> AsyncIterator[GenerationEvent]:
    """Validate a BLUEPRINT_PREVIEW command and delegate to the orchestrator."""
    if command.kind is not GenerationAttemptKind.BLUEPRINT_PREVIEW:
        raise ValueError("run_blueprint_preview requires kind BLUEPRINT_PREVIEW")
    return orchestrator.run(command)
