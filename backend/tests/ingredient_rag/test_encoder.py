from __future__ import annotations

import pytest

from pelican_town_specials.ingredient_rag.encoder import sentencepiece_input_ids
from pelican_town_specials.ingredient_rag.errors import IngredientRagUnavailable


class _FakeSentencePiece:
    def encode(self, text: str, out_type: type[int]) -> list[int]:
        del text, out_type
        return list(range(200))

    def unk_id(self) -> int:
        return -1

    def bos_id(self) -> int:
        return -2

    def eos_id(self) -> int:
        return -3


def test_sentencepiece_adds_model_special_tokens_and_truncates_to_128() -> None:
    input_ids = sentencepiece_input_ids(_FakeSentencePiece(), "query: " + "egg " * 200)

    assert len(input_ids) == 128
    assert input_ids[0] == 0
    assert input_ids[1:-1] == list(range(1, 127))
    assert input_ids[-1] == 2


@pytest.mark.parametrize("control_token", ["<s>", "</s>", "<unk>", "<pad>", "<mask>"])
def test_sentencepiece_control_literals_fail_open_without_echoing_input(
    control_token: str,
) -> None:
    with pytest.raises(IngredientRagUnavailable) as caught:
        sentencepiece_input_ids(_FakeSentencePiece(), f"query: {control_token}")

    assert caught.value.reason_code == "rag_tokenizer_input_unsupported"
    assert str(caught.value) == "rag_tokenizer_input_unsupported"
    assert control_token not in str(caught.value)
