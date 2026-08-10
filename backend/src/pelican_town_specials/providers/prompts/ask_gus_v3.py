"""Versioned Ask Gus design prompt with vanilla-informed pricing."""

from __future__ import annotations

from pelican_town_specials.domain.common import Language
from pelican_town_specials.providers.prompts.ask_gus_v2 import (
    ASK_GUS_JSON_INSTRUCTION,
    ASK_GUS_JSON_INSTRUCTION_EN,
    ASK_GUS_PROMPT_V2,
    ASK_GUS_PROMPT_V2_EN,
)

ASK_GUS_PROMPT_V3 = ASK_GUS_PROMPT_V2 + (
    "售价必须参考星露谷 1.6.15 原版烹饪物的经济尺度，并与菜品实际玩法价值相称："
    "普通菜 80..250g，精致菜 250..400g，明确高档或复杂菜 400..500g；"
    "大多数菜应落在 100..400g。"
    "定价必须综合原料价值与稀有度、制作复杂度、恢复量、Buff 强度与持续时间、菜品定位，"
    "不得任意给出高价。普通菜或无 Buff 菜不得超过 500g，"
    "不得用抬高售价来补偿没有 Buff。"
    "超过 500g 只允许用于明确的传奇定位或特殊功能性消耗品，"
    "且必须在 gusComment 中清楚说明高价对应的玩法理由；"
    "原版 Oil of Garlic（蒜油）1000g 与 Magic Rock Candy（魔法糖冰棍）5000g"
    "仅作为这类极少数例外的校准参照，不得当作普通菜的定价模板。"
)

ASK_GUS_PROMPT_V3_EN = ASK_GUS_PROMPT_V2_EN + (
    "Sell price must follow the vanilla Stardew Valley 1.6.15 cooking economy scale and "
    "match the dish's actual gameplay value: ordinary dishes 80..250g, refined dishes "
    "250..400g, clearly premium or complex dishes 400..500g; most dishes should fall between "
    "100..400g. "
    "Pricing must weigh ingredient value and rarity, cooking complexity, recovery amount, "
    "Buff strength and duration, and dish positioning; do not arbitrarily give high prices. "
    "Ordinary dishes or dishes without a Buff must not exceed 500g, and do not compensate "
    "for having no Buff by raising the price. "
    "Above 500g is only allowed for an explicitly legendary position or a special functional "
    "consumable, and the gameplay reason for the high price must be clearly explained in "
    "gusComment; the vanilla Oil of Garlic (1000g) and Magic Rock Candy (5000g) serve only "
    "as calibration references for these extremely rare exceptions, not as pricing templates "
    "for ordinary dishes."
)


def ask_gus_prompt_for(language: Language) -> tuple[str, str]:
    """Select the versioned Ask Gus prompt and JSON instruction for a language."""
    if language is Language.EN_US:
        return ASK_GUS_PROMPT_V3_EN, ASK_GUS_JSON_INSTRUCTION_EN
    return ASK_GUS_PROMPT_V3, ASK_GUS_JSON_INSTRUCTION
