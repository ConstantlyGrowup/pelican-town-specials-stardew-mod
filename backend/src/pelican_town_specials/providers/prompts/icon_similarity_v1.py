"""Versioned bilingual prompt for canonical icon visual reuse judgment.

M13 Task 58: after a semantic Canonical match (text identity confirmed), the
vision model compares the current dish photo with the recorded canonical icon
SOURCE artwork and returns one visual similarity score. A score of exactly
0.75 or above means the recorded icon can stand in for the current photo;
0.749 or below means a new icon is generated from the current photo while the
matched text stays reused.
"""

from __future__ import annotations

from pelican_town_specials.domain.common import Language

ICON_SIMILARITY_PROMPT_VERSION = "icon-similarity-v1"

ICON_SIMILARITY_PROMPT_ZH_CN = (
    "你是鹈鹕镇新菜单的图标复用判定器。第一张图是本次拍摄的菜品照片，"
    "第二张图是一道已归档的同名菜品的像素图标源图。"
    "判断这道菜的图标是否与照片中的同一道菜外观足够接近、可以直接复用："
    "比较食物主体的颜色、切片/块状/条状形态、摆盘排列、主要配菜与可见结构。"
    "允许真实照片到像素画的风格抽象与配色简化，忽略背景、餐具材质、光照和拍摄角度的小差异。"
    "不要因为菜名相同就直接给高分：例如同样是“生鱼片”，三文鱼橙色切片与白鱼肉片、"
    "或明显不同的摆盘结构仍可能不适配。"
    "只输出一个严格 JSON 对象，只能有 visualSimilarity 一个 0 到 1 的数字字段；"
    "不要输出解释、理由或 Markdown。"
)

ICON_SIMILARITY_JSON_INSTRUCTION_ZH_CN = (
    '严格只返回 JSON：{"visualSimilarity":0.0}。visualSimilarity 必须是 0 到 1 的数字。'
)

ICON_SIMILARITY_PROMPT_EN_US = (
    "You are the Pelican Town Specials icon-reuse judge. The first image is the current "
    "photo of the dish; the second image is the pixel-art icon source of an archived dish "
    "with the same name. Decide whether the archived dish's icon is visually close enough to "
    "the dish in the photo to be reused directly: compare the color of the food subject, its "
    "slice/chunk/strand shapes, its plating arrangement, the main side ingredients, and the "
    "visible structure. Allow the abstraction and color simplification that real photos "
    "receive when turned into pixel art; ignore small differences in background, tableware "
    "material, lighting, and shooting angle. Never give a high score just because the dish "
    "names match: two dishes both named \"sashimi\" may still not fit when one shows orange "
    "salmon slices and the other white fish slices or a clearly different plating structure. "
    "Return one strict JSON object with exactly one field visualSimilarity, a number from 0 "
    "to 1; do not output explanations, reasons, or Markdown."
)

ICON_SIMILARITY_JSON_INSTRUCTION_EN_US = (
    'Return JSON only: {"visualSimilarity":0.0}. visualSimilarity must be a number from 0 to 1.'
)


def icon_similarity_prompt_for(language: Language) -> tuple[str, str]:
    """Return the frozen icon reuse prompt and strict single-field instruction."""

    if language is Language.EN_US:
        return (
            ICON_SIMILARITY_PROMPT_EN_US,
            ICON_SIMILARITY_JSON_INSTRUCTION_EN_US,
        )
    return ICON_SIMILARITY_PROMPT_ZH_CN, ICON_SIMILARITY_JSON_INSTRUCTION_ZH_CN
