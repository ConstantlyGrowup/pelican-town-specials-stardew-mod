"""Versioned Ask Gus design prompt with vanilla-informed pricing."""

from __future__ import annotations

from pelican_town_specials.providers.prompts.ask_gus_v2 import ASK_GUS_PROMPT_V2

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
