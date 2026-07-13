"""Pure built-in functions callable from any NyxScript expression.

Almost everything here is a plain, synchronous, side-effect-free function
over NyxScript's own value types (str, int, float, bool, list) — no I/O, so
unlike `run`/`ui.*` these never need to be awaited by the interpreter.
`now()` is the one exception: it's synchronous and does no I/O either, but
it's non-deterministic (reads the wall clock) — there's no way to write a
useful `lib/time.nyx` without it.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

BuiltinFn = Callable[[list[Any]], Any]

#: Handled specially by the interpreter (they need to *call* a NyxScript
#: function value per item, which a plain synchronous builtin can't do) —
#: not in :data:`BUILTIN_FUNCTIONS`, but the linter/interpreter both treat
#: a call to one of these as a known function, same as a real builtin.
HIGHER_ORDER_FUNCTIONS = frozenset({"map", "filter", "sort_by", "reduce"})


def _arity_error(name: str, expected: str, got: int) -> TypeError:
    return TypeError(f"{name}() expects {expected}, got {got} argument(s)")


def _len(args: list[Any]) -> int:
    if len(args) != 1:
        raise _arity_error("len", "1 argument", len(args))
    return len(args[0])


#: `range()` eagerly materializes a Python list (there's no lazy iterator
#: type in NyxScript) — without a cap, `range(10**12)` would try to
#: allocate a list that large in one call, no loop or --unsafe required.
#: Matches the interpreter's MAX_LOOP_ITERATIONS order of magnitude.
_MAX_RANGE_LEN = 1_000_000


def _range(args: list[Any]) -> list[int]:
    if not (1 <= len(args) <= 3):
        raise _arity_error("range", "1 to 3 arguments", len(args))
    bounds = tuple(int(a) for a in args)
    span = len(range(*bounds))
    if span > _MAX_RANGE_LEN:
        raise ValueError(f"range() would produce {span:,} items (limit {_MAX_RANGE_LEN:,})")
    return list(range(*bounds))


def _upper(args: list[Any]) -> str:
    if len(args) != 1:
        raise _arity_error("upper", "1 argument", len(args))
    return str(args[0]).upper()


def _lower(args: list[Any]) -> str:
    if len(args) != 1:
        raise _arity_error("lower", "1 argument", len(args))
    return str(args[0]).lower()


def _strip(args: list[Any]) -> str:
    if len(args) != 1:
        raise _arity_error("strip", "1 argument", len(args))
    return str(args[0]).strip()


def _split(args: list[Any]) -> list[str]:
    if len(args) != 2:
        raise _arity_error("split", "2 arguments (text, separator)", len(args))
    return str(args[0]).split(str(args[1]))


def _join(args: list[Any]) -> str:
    if len(args) != 2:
        raise _arity_error("join", "2 arguments (list, separator)", len(args))
    return str(args[1]).join(str(item) for item in args[0])


def _contains(args: list[Any]) -> bool:
    if len(args) != 2:
        raise _arity_error("contains", "2 arguments (collection, item)", len(args))
    return args[1] in args[0]


def _str(args: list[Any]) -> str:
    if len(args) != 1:
        raise _arity_error("str", "1 argument", len(args))
    return str(args[0])


def _int(args: list[Any]) -> int:
    if len(args) != 1:
        raise _arity_error("int", "1 argument", len(args))
    return int(args[0])


def _float(args: list[Any]) -> float:
    if len(args) != 1:
        raise _arity_error("float", "1 argument", len(args))
    return float(args[0])


def _abs(args: list[Any]) -> Any:
    if len(args) != 1:
        raise _arity_error("abs", "1 argument", len(args))
    return abs(args[0])


def _round(args: list[Any]) -> Any:
    if not (1 <= len(args) <= 2):
        raise _arity_error("round", "1 or 2 arguments", len(args))
    return round(*args)


def _sorted(args: list[Any]) -> list[Any]:
    if len(args) != 1:
        raise _arity_error("sorted", "1 argument", len(args))
    return sorted(args[0])


def _reversed(args: list[Any]) -> list[Any]:
    if len(args) != 1:
        raise _arity_error("reversed", "1 argument", len(args))
    return list(reversed(args[0]))


def _min(args: list[Any]) -> Any:
    if not args:
        raise _arity_error("min", "at least 1 argument", len(args))
    return min(args[0]) if len(args) == 1 else min(args)


def _max(args: list[Any]) -> Any:
    if not args:
        raise _arity_error("max", "at least 1 argument", len(args))
    return max(args[0]) if len(args) == 1 else max(args)


def _sum(args: list[Any]) -> Any:
    if len(args) != 1:
        raise _arity_error("sum", "1 argument", len(args))
    return sum(args[0])


def _type_of(args: list[Any]) -> str:
    if len(args) != 1:
        raise _arity_error("type_of", "1 argument", len(args))
    value = args[0]
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    # NyxFunction lives in interpreter.py, which imports this module — checking
    # by class name here avoids a circular import for one string comparison.
    if type(value).__name__ == "NyxFunction":
        return "function"
    return type(value).__name__


def _keys(args: list[Any]) -> list[Any]:
    if len(args) != 1:
        raise _arity_error("keys", "1 argument", len(args))
    if not isinstance(args[0], dict):
        raise TypeError(f"keys() expects a dict, got {type(args[0]).__name__}")
    return list(args[0].keys())


def _values(args: list[Any]) -> list[Any]:
    if len(args) != 1:
        raise _arity_error("values", "1 argument", len(args))
    if not isinstance(args[0], dict):
        raise TypeError(f"values() expects a dict, got {type(args[0]).__name__}")
    return list(args[0].values())


def _items(args: list[Any]) -> list[list[Any]]:
    if len(args) != 1:
        raise _arity_error("items", "1 argument", len(args))
    if not isinstance(args[0], dict):
        raise TypeError(f"items() expects a dict, got {type(args[0]).__name__}")
    return [[k, v] for k, v in args[0].items()]


def _get(args: list[Any]) -> Any:
    # NyxScript has no null/none literal, so — unlike Python's dict.get —
    # the default is mandatory: there's no value to hand back otherwise.
    if len(args) != 3:
        raise _arity_error("get", "3 arguments (dict, key, default)", len(args))
    mapping, key, default = args
    if not isinstance(mapping, dict):
        raise TypeError(f"get() expects a dict, got {type(mapping).__name__}")
    return mapping.get(key, default)


def _replace(args: list[Any]) -> str:
    if len(args) != 3:
        raise _arity_error("replace", "3 arguments (text, old, new)", len(args))
    text, old, new = args
    return str(text).replace(str(old), str(new))


def _starts_with(args: list[Any]) -> bool:
    if len(args) != 2:
        raise _arity_error("starts_with", "2 arguments (text, prefix)", len(args))
    return str(args[0]).startswith(str(args[1]))


def _ends_with(args: list[Any]) -> bool:
    if len(args) != 2:
        raise _arity_error("ends_with", "2 arguments (text, suffix)", len(args))
    return str(args[0]).endswith(str(args[1]))


def _find(args: list[Any]) -> int:
    if len(args) != 2:
        raise _arity_error("find", "2 arguments (text, needle)", len(args))
    return str(args[0]).find(str(args[1]))


def _zip(args: list[Any]) -> list[list[Any]]:
    if len(args) != 2:
        raise _arity_error("zip", "2 arguments (list, list)", len(args))
    a, b = args
    if not isinstance(a, list) or not isinstance(b, list):
        raise TypeError("zip() expects two lists")
    return [[x, y] for x, y in zip(a, b, strict=False)]


def _has_null(value: Any) -> bool:
    """True if a decoded JSON value contains a ``null`` anywhere — NyxScript

    has no null/none to represent one with.
    """
    if value is None:
        return True
    if isinstance(value, list):
        return any(_has_null(v) for v in value)
    if isinstance(value, dict):
        return any(_has_null(v) for v in value.values())
    return False


def _parse_json(args: list[Any]) -> Any:
    if len(args) != 1:
        raise _arity_error("parse_json", "1 argument", len(args))
    try:
        value = json.loads(str(args[0]))
    except json.JSONDecodeError as exc:
        raise ValueError(f"parse_json(): invalid JSON — {exc}") from exc
    if _has_null(value):
        raise ValueError("parse_json(): the JSON contains 'null', which NyxScript can't represent")
    return value


def _to_json(args: list[Any]) -> str:
    if len(args) != 1:
        raise _arity_error("to_json", "1 argument", len(args))
    try:
        return json.dumps(args[0])
    except TypeError as exc:
        raise TypeError(f"to_json(): {exc}") from exc


def _now(args: list[Any]) -> float:
    if args:
        raise _arity_error("now", "no arguments", len(args))
    return time.time()


def _to_iso8601(args: list[Any]) -> str:
    if len(args) != 1:
        raise _arity_error("to_iso8601", "1 argument (epoch seconds)", len(args))
    try:
        return datetime.fromtimestamp(float(args[0]), tz=UTC).isoformat()
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError(f"to_iso8601(): invalid timestamp — {exc}") from exc


BUILTIN_FUNCTIONS: dict[str, BuiltinFn] = {
    "len": _len,
    "range": _range,
    "upper": _upper,
    "lower": _lower,
    "strip": _strip,
    "split": _split,
    "join": _join,
    "contains": _contains,
    "str": _str,
    "int": _int,
    "float": _float,
    "abs": _abs,
    "round": _round,
    "sorted": _sorted,
    "reversed": _reversed,
    "min": _min,
    "max": _max,
    "sum": _sum,
    "type_of": _type_of,
    "keys": _keys,
    "values": _values,
    "items": _items,
    "get": _get,
    "replace": _replace,
    "starts_with": _starts_with,
    "ends_with": _ends_with,
    "find": _find,
    "zip": _zip,
    "parse_json": _parse_json,
    "to_json": _to_json,
    "now": _now,
    "to_iso8601": _to_iso8601,
}
