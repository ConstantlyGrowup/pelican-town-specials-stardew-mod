"""Versioned bilingual prompt for the internal Canonical matcher."""

from __future__ import annotations

from pelican_town_specials.domain.common import Language

CANONICAL_MATCH_PROMPT_VERSION = "canonical-match-v1"

CANONICAL_MATCH_PROMPT_ZH_CN = (
    "你是鹈鹕镇新菜单的 Canonical 菜品匹配器。只判断当前菜品是否与候选中的某一道是同一道现实菜品，"
    "不要判断是否相似、同菜系或可替代。当前 contextText 是这一次的新要求；如果它改变了菜品本体，"
    "或与候选菜品的现实设定冲突，应明显降低置信度并低于命中阈值。只能从提供的候选 ID 中选择一个，"
    "没有可靠匹配时返回 null。只输出一个严格 JSON 对象，且只能有 candidateId 和 confidence 两个字段；"
    "不要输出解释、理由、推理过程、候选列表或 Markdown。"
)

CANONICAL_MATCH_PROMPT_EN_US = (
    "You are the Pelican Town Specials Canonical dish matcher. Decide only whether the current dish is the same "
    "real-world dish as exactly one supplied candidate; do not decide whether it is merely similar, from the same "
    "cuisine, or a substitute. The current contextText is a new request for this attempt. If it changes the dish's "
    "identity or conflicts with the candidate's real-world dish setting, lower confidence clearly below the hit "
    "threshold. Select only one supplied candidate ID, or return null when there is no reliable match. Return one "
    "strict JSON object with exactly the two fields candidateId and confidence; do not output explanation, reasons, "
    "reasoning, a candidate list, or Markdown."
)

CANONICAL_MATCH_JSON_INSTRUCTION_ZH_CN = (
    '严格只返回 JSON：{"candidateId":"候选 UUID 或 null","confidence":0.0}。'
    "candidateId 必须是请求中提供的 ID 或 null；confidence 必须是 0 到 1 的数字。"
)

CANONICAL_MATCH_JSON_INSTRUCTION_EN_US = (
    'Return JSON only: {"candidateId":"a supplied candidate UUID or null","confidence":0.0}. '
    "candidateId must be one supplied ID or null; confidence must be a number from 0 to 1."
)


def canonical_match_prompt_for(language: Language) -> tuple[str, str]:
    """Return the frozen matcher prompt and strict two-field instruction."""

    if language is Language.EN_US:
        return (
            CANONICAL_MATCH_PROMPT_EN_US,
            CANONICAL_MATCH_JSON_INSTRUCTION_EN_US,
        )
    return CANONICAL_MATCH_PROMPT_ZH_CN, CANONICAL_MATCH_JSON_INSTRUCTION_ZH_CN
