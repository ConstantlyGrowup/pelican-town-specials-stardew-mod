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

_VISUAL_BRIEF_CAP = 200
_PROMPT_MAX_CHARS = 1500


def clip_visual_brief(brief: str) -> str:
    """Bound the non-business atmosphere reference so the edit prompt stays
    within the provider contract (``prompt`` max 1500 chars). Business fields
    are never compressed by this helper."""
    if len(brief) <= _VISUAL_BRIEF_CAP:
        return brief
    return brief[:_VISUAL_BRIEF_CAP] + "…"


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
    visual_brief: str,
) -> str:
    recovery = gameplay.recovery
    buff = gameplay.buff
    if buff is None:
        buff_text = "无增益行（不要虚构 Buff）"
    else:
        attributes = buff.attributes.model_dump(
            exclude_defaults=True, by_alias=True
        )
        attribute_text = "、".join(
            f"{key}={value}" for key, value in attributes.items()
        )
        buff_text = (
            f"增益：{buff.id}，持续{buff.duration_minutes}分钟，"
            f"属性：{attribute_text}。"
        )
    return (
        "MULTI-IMAGE GENERATIVE EDIT。输入图1是必须保留的真实菜品原图，"
        "输入图2是同一轮生成的菜品像素图标。以输入图1作为不可替换的摄影底图，"
        "保持原始宽高比、裁切、食物、器皿、桌面、背景、光影、透视、景深和摄影质感；"
        "只在不遮挡主体的负空间叠加 UI，UI 以外区域必须与原图视觉一致。准确复用输入图2"
        "的轮廓、色板和像素特征，把它自然放在词条卡上方或轻压上边框。"
        "由图像模型在这一次 EDIT 中生成完整的星露谷物语物品悬浮词条卡，"
        "不要使用本地模板、Pillow、Canvas、HTML/CSS 或前端组件排版。"
        "卡片使用饱和暖金橙/蜂蜜橙羊皮纸渐变，多层深棕与橙棕硬边像素框、"
        "像素装饰角、游戏式分隔线和端点、轻微硬投影、紧凑内边距；标题居中醒目，"
        "类别用紫色或紫红色强调，体力、生命、Buff、时钟和金币使用统一像素符号。"
        f"所有可见文字和数字必须逐字逐数来自当前 Blueprint 字段："
        f"标题={presentation.display_name}；类别={presentation.category_label}；"
        f"描述={presentation.description}；体力+{recovery.energy_restore}；"
        f"生命+{recovery.health_restore}；售价={gameplay.sell_price}g；"
        f"{buff_text}"
        f"视觉氛围参考（不可作为额外卡片文字）：{clip_visual_brief(visual_brief)}。"
        "Blueprint 字段是唯一内容真源，模型不得改写名称、分类、描述、数值或 Draft。"
        "禁止重画、像素化、扩图、裁切或整体调色真实照片；禁止苍白米色网页卡、"
        "PPT 文本框、餐厅菜单、左右分栏、大面积侧栏、黑色整图边框和额外无关文字。"
    )


def run_blueprint_preview(
    orchestrator: GenerationOrchestrator,
    command: GenerationCommand,
) -> AsyncIterator[GenerationEvent]:
    """Validate a BLUEPRINT_PREVIEW command and delegate to the orchestrator."""
    if command.kind is not GenerationAttemptKind.BLUEPRINT_PREVIEW:
        raise ValueError("run_blueprint_preview requires kind BLUEPRINT_PREVIEW")
    return orchestrator.run(command)
