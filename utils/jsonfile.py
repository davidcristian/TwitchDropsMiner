"""Reading and writing the JSON files that the app keeps, and the JSON text of payloads."""
from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, TypeVar, cast

from yarl import URL

from constants import JsonType, PriorityMode


_JSON_T = TypeVar("_JSON_T", bound=Mapping[Any, Any])


def json_minify(data: JsonType | list[JsonType]) -> str:
    """
    Returns minified JSON for payload usage.
    """
    return json.dumps(data, separators=(',', ':'))


def _serialize(obj: Any) -> Any:
    # convert data
    d: int | str | float | list[Any] | JsonType
    if isinstance(obj, datetime):
        if obj.tzinfo is None:
            # assume naive objects are UTC
            obj = obj.replace(tzinfo=timezone.utc)
        d = obj.timestamp()
    elif isinstance(obj, set):
        d = list(obj)
    elif isinstance(obj, Enum):
        # NOTE: IntEnum cannot be used, as it will get serialized as a plain integer,
        # then loaded back as an integer as well.
        d = obj.value
    elif isinstance(obj, URL):
        d = str(obj)
    else:
        raise TypeError(obj)
    # store with type
    return {
        "__type": type(obj).__name__,
        "data": d,
    }


_MISSING = object()
SERIALIZE_ENV: dict[str, Callable[[Any], object]] = {
    "set": set,
    "URL": URL,
    "PriorityMode": PriorityMode,
    "datetime": lambda d: datetime.fromtimestamp(d, timezone.utc),
}


def _remove_missing(obj: JsonType) -> JsonType:
    # this modifies obj in place, but we return it just in case
    for key, value in obj.copy().items():
        if value is _MISSING:
            del obj[key]
        elif isinstance(value, dict):
            _remove_missing(value)
            if not value:
                # the dict is empty now, so remove it's key entirely
                del obj[key]
    return obj


def _deserialize(obj: JsonType) -> Any:
    if "__type" in obj:
        obj_type = obj["__type"]
        if obj_type in SERIALIZE_ENV:
            return SERIALIZE_ENV[obj_type](obj["data"])
        else:
            return _MISSING
    return obj


def merge_json(obj: JsonType, template: Mapping[Any, Any]) -> None:
    # NOTE: This modifies object in place
    for k, v in list(obj.items()):
        if k not in template:
            # unknown key: overwrite from template
            del obj[k]
        elif type(v) is not type(template[k]):
            # types don't match: overwrite from template
            obj[k] = template[k]
        elif isinstance(v, dict):
            assert isinstance(template[k], dict)
            merge_json(v, template[k])
    # ensure the object is not missing any keys
    for k in template.keys():
        if k not in obj:
            obj[k] = template[k]


def json_load(path: Path, defaults: _JSON_T, *, merge: bool = True) -> _JSON_T:
    new_path: Path = path.with_name(f"{path.name}.new")
    combined: JsonType | None = None
    # try new file first
    if new_path.exists():
        try:
            with new_path.open('r', encoding="utf8") as file:
                combined = _remove_missing(json.load(file, object_hook=_deserialize))
        except json.JSONDecodeError:
            # remove invalid file
            new_path.unlink()
    # try the old file
    if combined is None and path.exists():
        with path.open('r', encoding="utf8") as file:
            combined = _remove_missing(json.load(file, object_hook=_deserialize))
    # handle defaults and merging
    if combined is None:
        combined = dict(defaults)  # always make a copy of defaults
    elif merge:
        merge_json(combined, dict(defaults))
    return cast(_JSON_T, combined)


def json_save(path: Path, contents: Mapping[Any, Any], *, sort: bool = False) -> None:
    new_path: Path = path.with_name(f"{path.name}.new")
    with new_path.open('w', encoding="utf8") as file:
        json.dump(contents, file, default=_serialize, sort_keys=sort, indent=4)
    new_path.replace(path)
