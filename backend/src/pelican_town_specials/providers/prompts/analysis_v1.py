"""Versioned multimodal dish-analysis prompt."""

from __future__ import annotations

from pelican_town_specials.domain.common import Language

ANALYSIS_PROMPT_V1 = (
    "你是鹈鹕镇餐厅的菜品识别助手。根据提供的菜品照片识别这道菜。"
    "命名与归一化规则：recognizedDish 必须使用照片证据支持的常见、简短中文菜名。"
    "同一道菜的常见同义表达要收敛到一个名称；例如“番茄炒蛋”和“西红柿炒鸡蛋”统一写为“番茄炒蛋”。"
    "不要并列输出别名，也不要添加创作性修饰。normalizedName 使用稳定、常见的中文词形，"
    "例如把“西红柿”归一为“番茄”、把“马铃薯”归一为“土豆”。"
    "保留所有会定义菜品身份的真实区别，包括主食材、酱汁、风味和做法；"
    "例如“番茄蛋汤”与“番茄炒蛋”必须区分。"
    "无法确认时保留不确定性，不要为了套用示例强行归类。"
    "只输出一个 JSON 对象，不要输出 markdown 代码块或任何额外文字。"
    "JSON 字段：recognizedDish（菜名），summary（一句话总结），"
    "cuisine（可选菜系），cookingMethods（烹饪方式数组），"
    "flavorProfile（风味数组），semanticIngredients（数组，只列这道菜的真实组成成分："
    "照片中可见或可合理推断的主食材与配料；主食材必须列出——鱼菜必须列出鱼、"
    "肉菜必须列出对应肉类；不得列出装饰植物或与菜品无关的原料。"
    "每项含 name、normalizedName、visibleConfidence 0..1、quantityHint 可选）。"
    "semanticIngredients 的 normalizedName 使用稳定、常见的中文词形；"
    "不要为了提高召回而编造或补充推测原料。"
    "cuisine、cookingMethods、flavorProfile、summary 使用简短一致的表达；保留照片证据与不确定性，"
    "不要把猜测写成确定事实。"
    "confidence（0..1），safetyNotes（安全提示数组）。"
)

ANALYSIS_JSON_INSTRUCTION = "只返回一个 JSON 对象，不包含代码块或额外文字。"

ANALYSIS_PROMPT_V1_EN = (
    "You are the dish-recognition assistant for the Pelican Town restaurant. "
    "Identify this dish from the provided photo. "
    "Naming and normalization rules: recognizedDish must use a short, common English dish name "
    "supported by the photo. Collapse common synonymous names for the same dish to one stable name; "
    "for example, use \"Tomato and Egg Stir-Fry\" for both \"Tomato Stir-Fried with Egg\" and "
    "\"Stir-Fried Eggs with Tomato\". Never list aliases together or add creative adjectives. "
    "Preserve all real distinctions that define dish identity, including main ingredients, sauces, "
    "flavors, and cooking methods; for example, \"Tomato Egg Soup\" and \"Tomato and Egg Stir-Fry\" "
    "must remain distinct. When uncertain, preserve that uncertainty and do not "
    "force the dish into the example or another category. Do not output Chinese dish names in en-US. "
    "Output only one JSON object, with no markdown code blocks or any extra text. "
    "JSON fields: recognizedDish (dish name), summary (one-sentence summary), "
    "cuisine (optional cuisine), cookingMethods (array of cooking methods), "
    "flavorProfile (array of flavors), semanticIngredients (array listing only the dish's "
    "true components: the main ingredients and seasonings that are visible in or reasonably "
    "inferable from the photo; the main protein must be listed - fish dishes must list the "
    "fish, meat dishes must list the corresponding meat; do not list decorative garnishes or "
    "ingredients unrelated to the dish. Each entry contains name, normalizedName, "
    "visibleConfidence 0..1, optional quantityHint). Use stable, common English word forms for "
    "semanticIngredients.normalizedName; include only ingredients supported by image evidence, "
    "and do not invent or add speculative ingredients to improve recall. Keep cuisine, "
    "cookingMethods, flavorProfile, and summary short and consistent; retain uncertainty and "
    "image evidence instead of presenting guesses as facts. "
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


def regeneration_instruction_section(
    instruction: str,
    *,
    language: Language,
) -> str:
    """Render this round's requirement as a separate, highest-priority block.

    ``contextText`` and this field deliberately stay in separate sections so
    a new round cannot accidentally replace the original request.  The
    explicit priority wording also gives the provider a deterministic rule
    when the two user inputs disagree.
    """
    if language is Language.EN_US:
        return (
            "\n\nCurrent regeneration requirements (highest priority for this round; "
            "when these conflict with Original contextText, follow these requirements "
            "while still obeying the photo evidence and output schema):\n"
            f"{instruction}"
        )
    return (
        "\n\n本轮重新生成要求（本轮优先级最高；如果与原始 contextText 冲突，"
        "请遵循本轮要求，同时仍遵守照片证据和输出 schema）：\n"
        f"{instruction}"
    )


def context_text_section(
    context_text: str,
    *,
    language: Language,
) -> str:
    """Render the original request as an independent prompt section.

    This is intentionally separate from ``regeneration_instruction_section``:
    the original request remains available as background context on every full
    regeneration, while the current round can override conflicting details.
    """
    if language is Language.EN_US:
        return (
            "\n\nOriginal contextText (the initial user request; keep it as background "
            "unless the current regeneration requirements override a detail):\n"
            f"{context_text}"
        )
    return (
        "\n\n原始 contextText（首次请求中的用户说明；除非本轮重新生成要求覆盖某项，"
        "否则将其作为背景要求保留）：\n"
        f"{context_text}"
    )
