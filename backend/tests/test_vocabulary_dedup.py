"""Tests for shared vocabulary-deduplication mechanics."""

from app.services.ai import Usage
from app.services.vocabulary_dedup import propose_merges


def test_propose_merges_rejects_invalid_ai_keys_and_targets() -> None:
    def propose(
        _survivors: list[str], _candidates: list[str]
    ) -> tuple[dict[str, str], Usage, bool]:
        return (
            {
                "Milk": "Egg",
                "Egg": "Cream",
                "Oil": "Egg",
            },
            Usage(),
            False,
        )

    merges, result = propose_merges(["Egg", "Milk", "Oil"], None, propose, candidate_window=2)

    assert merges == {"Milk": "Egg"}
    assert result.ai_merges == 1
    assert result.candidates == 2
