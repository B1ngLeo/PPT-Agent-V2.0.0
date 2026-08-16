import re

from instant_ppt_domain.ids import new_ulid


def test_ulids_are_canonical_and_monotonic() -> None:
    values = [new_ulid() for _ in range(1000)]
    assert values == sorted(values)
    assert len(values) == len(set(values))
    assert all(re.fullmatch(r"[0-9A-HJKMNP-TV-Z]{26}", value) for value in values)
