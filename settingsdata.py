"""Check the values loaded from settings.json, which a hand edit can leave in a form the app cannot use."""
from __future__ import annotations

from collections import abc
from typing import Any


def drop_non_text_items(settings: abc.MutableMapping[str, Any]) -> list[tuple[str, object]]:
    """Remove the items that are not strings from the lists and sets in settings; return each key and item removed."""
    removed: list[tuple[str, object]] = []
    for key, value in list(settings.items()):
        if not isinstance(value, (list, set)):
            continue
        wrong = [item for item in value if not isinstance(item, str)]
        if wrong:
            settings[key] = type(value)(item for item in value if isinstance(item, str))
            removed.extend((key, item) for item in wrong)
    return removed
