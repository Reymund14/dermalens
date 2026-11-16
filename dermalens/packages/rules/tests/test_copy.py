from dermalens_rules.copy import FORBIDDEN_WORDS, all_result_strings
from dermalens_rules.seed import RED_FLAGS


def test_vocabulary_lock():
    for s in all_result_strings() + [q for _, q, _ in RED_FLAGS]:
        low = s.lower()
        for w in FORBIDDEN_WORDS:
            assert w not in low, f"forbidden word {w!r} in copy: {s!r}"
