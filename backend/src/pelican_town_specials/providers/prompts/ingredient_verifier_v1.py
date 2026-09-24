"""Single-call, dish-level ingredient candidate verification prompt."""

from __future__ import annotations

import json

from pelican_town_specials.providers.contracts import IngredientVerifierRequest

PROMPT_VERSION = "ingredient-verifier-v1"


def ingredient_verifier_prompt(
    request: IngredientVerifierRequest,
) -> tuple[str, str]:
    """Build the minimal user payload and strict output instruction."""

    payload = {
        "dishName": request.dish_name,
        "ingredients": [
            {
                "index": ingredient.index,
                "name": ingredient.name,
                "candidates": [
                    {
                        "itemId": candidate.item_id,
                        "displayNameEn": candidate.display_name_en,
                        "displayNameZh": candidate.display_name_zh,
                    }
                    for candidate in ingredient.candidates
                ],
            }
            for ingredient in request.ingredients
        ],
    }
    prompt = (
        "判断每项现实原料是否能合理对应到候选游戏原料。只能从该项给出的候选中选择一个 itemId；"
        "若没有明确合理的对应项，必须选择 null。不能创造候选，也不能重复使用同一个 itemId。"
        "按给定 index 原样返回每项结果。\n\n"
        "待核验内容：\n"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )
    instruction = (
        "只返回一个 JSON 对象，形如 {\"items\":[{\"index\":0,"
        "\"selectedItemId\":\"候选 itemId 或 null\"}]}。"
        "必须包含输入中每个 index，selectedItemId 必须是该项候选 ID 之一或 null。"
    )
    return prompt, instruction
