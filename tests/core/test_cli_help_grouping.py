from __future__ import annotations

from nyxor.core.cli import _CATEGORY_PRIORITY, _category_sort_key


def test_known_categories_sort_in_priority_order() -> None:
    categories = ["Fun", "Scanning", "API", "AI (local model)"]
    ordered = sorted(categories, key=_category_sort_key)
    assert ordered == sorted(categories, key=_CATEGORY_PRIORITY.index)
    assert ordered[0] == "Scanning"


def test_unknown_category_sorts_after_every_known_one() -> None:
    key = _category_sort_key("Some Third-Party Plugin")
    assert key == len(_CATEGORY_PRIORITY)
    assert all(_category_sort_key(c) < key for c in _CATEGORY_PRIORITY)


def test_scanning_is_first_priority() -> None:
    assert _CATEGORY_PRIORITY[0] == "Scanning"
