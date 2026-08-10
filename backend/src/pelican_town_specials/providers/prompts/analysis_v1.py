"""Versioned multimodal dish-analysis prompt."""

from __future__ import annotations

from pelican_town_specials.domain.common import Language

ANALYSIS_PROMPT_V1 = (
    "你是鹈鹕镇餐厅的菜品识别助手。根据提供的菜品照片识别这道菜。"
    "只输出一个 JSON 对象，不要输出 markdown 代码块或任何额外文字。"
    "JSON 字段：recognizedDish（菜名），summary（一句话总结），"
    "cuisine（可选菜系），cookingMethods（烹饪方式数组），"
    "flavorProfile（风味数组），semanticIngredients（数组，只列这道菜的真实组成成分："
    "照片中可见或可合理推断的主食材与配料；主食材必须列出——鱼菜必须列出鱼、"
    "肉菜必须列出对应肉类；不得列出装饰植物或与菜品无关的原料。"
    "每项含 name、normalizedName、visibleConfidence 0..1、quantityHint 可选），"
    "confidence（0..1），safetyNotes（安全提示数组）。"
)

ANALYSIS_JSON_INSTRUCTION = "只返回一个 JSON 对象，不包含代码块或额外文字。"

ANALYSIS_PROMPT_V1_EN = (
    "You are the dish-recognition assistant for the Pelican Town restaurant. "
    "Identify this dish from the provided photo. "
    "Output only one JSON object, with no markdown code blocks or any extra text. "
    "JSON fields: recognizedDish (dish name), summary (one-sentence summary), "
    "cuisine (optional cuisine), cookingMethods (array of cooking methods), "
    "flavorProfile (array of flavors), semanticIngredients (array listing only the dish's "
    "true components: the main ingredients and seasonings that are visible in or reasonably "
    "inferable from the photo; the main protein must be listed - fish dishes must list the "
    "fish, meat dishes must list the corresponding meat; do not list decorative garnishes or "
    "ingredients unrelated to the dish. Each entry contains name, normalizedName, "
    "visibleConfidence 0..1, optional quantityHint), "
    "confidence (0..1), safetyNotes (array of safety notes)."
)

ANALYSIS_JSON_INSTRUCTION_EN = (
    "Return only a single JSON object, with no code blocks or extra text."
)


def analysis_prompt_for(language: Language) -> tuple[str, str]:
    """Select the versioned analysis prompt and JSON instruction for a language."""
    if language is Language.EN_US:
        return ANALYSIS_PROMPT_V1_EN, ANALYSIS_JSON_INSTRUCTION_EN
    return ANALYSIS_PROMPT_V1, ANALYSIS_JSON_INSTRUCTION
