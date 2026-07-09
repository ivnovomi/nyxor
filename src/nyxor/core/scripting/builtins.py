"""Pure built-in functions callable from any NyxScript expression.

Everything here is a plain, synchronous, side-effect-free function over
NyxScript's own value types (str, int, float, bool, list) — no I/O, so
unlike `run`/`ui.*` these never need to be awaited by the interpreter.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

BuiltinFn = Callable[[list[Any]], Any]


def _arity_error(name: str, expected: str, got: int) -> TypeError:
    return TypeError(f"{name}() expects {expected}, got {got} argument(s)")


def _len(args: list[Any]) -> int:
    if len(args) != 1:
        raise _arity_error("len", "1 argument", len(args))
    return len(args[0])


def _range(args: list[Any]) -> list[int]:
    if not (1 <= len(args) <= 3):
        raise _arity_error("range", "1 to 3 arguments", len(args))
    return list(range(*(int(a) for a in args)))


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
    return type(value).__name__


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
}
