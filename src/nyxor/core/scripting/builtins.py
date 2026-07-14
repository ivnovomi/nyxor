"""Pure built-in functions callable from any NyxScript expression.

Almost everything here is a plain, synchronous, side-effect-free function
over NyxScript's own value types (str, int, float, bool, list) — no I/O, so
unlike `run`/`ui.*` these never need to be awaited by the interpreter.
`now()` is the one exception: it's synchronous and does no I/O either, but
it's non-deterministic (reads the wall clock) — there's no way to write a
useful `lib/time.nyx` without it. The regex_* functions are the other
exception: they run in a separate worker *process* with a wall-clock
timeout rather than directly — see `_run_regex_op` for why a thread isn't
enough to protect against a catastrophic-backtracking pattern.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import multiprocessing as mp
import random
import re
import threading
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


def format_value(value: Any) -> str:
    """Renders any NyxScript value the way script output shows it — bools as

    lowercase true/false (not Python's True/False), lists/dicts
    recursively in NyxScript's own bracket syntax. Used by both `print`
    (via the interpreter) and the `str()` builtin, which must agree: `str(x)`
    where `x` came from `print x` would otherwise silently disagree with
    what the script just saw on screen (`str(true)` giving `"True"` while
    `print true` shows `true`).
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ", ".join(format_value(v) for v in value) + "]"
    if isinstance(value, dict):
        pairs = ", ".join(f"{format_value(k)}: {format_value(v)}" for k, v in value.items())
        return "{" + pairs + "}"
    return str(value)


def _str(args: list[Any]) -> str:
    if len(args) != 1:
        raise _arity_error("str", "1 argument", len(args))
    return format_value(args[0])


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


_REGEX_TIMEOUT_SECONDS = 1.0
_REGEX_MAX_INPUT_LEN = 100_000

# `spawn` (not `fork`) so this behaves identically on Windows, where it's
# the only option anyway — no point in the two platforms having different
# regex-timeout behavior.
_REGEX_MP_CONTEXT = mp.get_context("spawn")

# A single, lazily-started, long-lived worker process, reused across every
# regex_* call in this interpreter's lifetime — see `_run_regex_op` for why
# a *process* is needed at all, and why it's one persistent worker rather
# than a fresh spawn per call (spawning a whole interpreter, especially on
# Windows, costs tens to hundreds of milliseconds; doing that on every
# `regex_match()` inside a loop would make the language painfully slow).
_regex_lock = threading.Lock()
_regex_process: mp.process.BaseProcess | None = None
_regex_conn: Any = None


def _compile_regex(pattern: str) -> re.Pattern[str]:
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"invalid regex {pattern!r}: {exc}") from exc


def _check_regex_input_len(text: str) -> None:
    if len(text) > _REGEX_MAX_INPUT_LEN:
        raise ValueError(
            f"regex input is {len(text):,} characters (limit {_REGEX_MAX_INPUT_LEN:,})"
        )


def _regex_worker_loop(conn: Any) -> None:
    """The persistent worker process's main loop — a plain module-level

    function so `multiprocessing`'s `spawn` start method can pickle a
    reference to it. Handles one `(op, pattern, text, replacement)` request
    at a time for as long as the parent process keeps it alive.
    """
    while True:
        try:
            op, pattern, text, replacement = conn.recv()
        except EOFError:
            return
        try:
            compiled = re.compile(pattern)
            value: Any
            if op == "match":
                value = bool(compiled.search(text))
            elif op == "find":
                found = compiled.search(text)
                value = found.group(0) if found else None
            elif op == "find_all":
                # findall() returns tuples for patterns with capture groups
                # — NyxScript has no tuple type, only list, so normalize.
                value = [
                    list(r) if isinstance(r, tuple) else r for r in compiled.findall(text)
                ]
            else:
                value = compiled.sub(replacement, text)
            conn.send(("ok", value))
        except Exception as exc:  # noqa: BLE001 - reported back to the caller, not swallowed
            conn.send(("error", str(exc)))


def _kill_regex_worker() -> None:
    """Terminate (or hard-kill) the current worker and clear it, so the

    next call spawns a fresh one instead of queueing behind whatever this
    one is still stuck doing.
    """
    global _regex_process, _regex_conn
    process, _regex_process = _regex_process, None
    conn, _regex_conn = _regex_conn, None
    if conn is not None:
        with contextlib.suppress(OSError):
            conn.close()
    if process is not None and process.is_alive():
        process.terminate()
        process.join(timeout=1.0)
        if process.is_alive():
            process.kill()


def _ensure_regex_worker() -> Any:
    global _regex_process, _regex_conn
    if _regex_process is not None and _regex_process.is_alive() and _regex_conn is not None:
        return _regex_conn
    parent_conn, child_conn = _REGEX_MP_CONTEXT.Pipe()
    process = _REGEX_MP_CONTEXT.Process(target=_regex_worker_loop, args=(child_conn,), daemon=True)
    process.start()
    child_conn.close()  # only the child should hold the writable end
    _regex_process = process
    _regex_conn = parent_conn
    return parent_conn


def _run_regex_op(op: str, pattern: str, text: str, replacement: str = "") -> Any:
    """Runs a regex operation in the persistent worker process, with a hard

    wall-clock timeout.

    Why a *process*, not a thread: CPython's `re` engine never releases the
    GIL mid-match, so a catastrophic-backtracking pattern (e.g. `(a+)+b`
    against a long non-matching input) holds the GIL for its entire —
    effectively unbounded — run. A watchdog *thread* waiting on
    `Thread.join(timeout=…)` can't get scheduled to even notice the
    deadline passed, since noticing it also needs the GIL that the runaway
    match is holding. A separate process has its own GIL, so unlike a
    thread it can actually be killed outright when it overruns.
    """
    _check_regex_input_len(text)
    _compile_regex(pattern)  # fail fast on a bad pattern before bothering the worker

    with _regex_lock:
        try:
            conn = _ensure_regex_worker()
            conn.send((op, pattern, text, replacement))
            if conn.poll(_REGEX_TIMEOUT_SECONDS):
                status, payload = conn.recv()
            else:
                _kill_regex_worker()
                raise ValueError(
                    f"regex evaluation exceeded {_REGEX_TIMEOUT_SECONDS}s — likely "
                    "catastrophic backtracking in the pattern"
                )
        except (BrokenPipeError, EOFError, OSError, RuntimeError) as exc:
            _kill_regex_worker()
            raise ValueError(f"regex worker process is unavailable: {exc}") from exc

    if status == "error":
        raise ValueError(payload)
    return payload


def _regex_match(args: list[Any]) -> bool:
    if len(args) != 2:
        raise _arity_error("regex_match", "2 arguments (text, pattern)", len(args))
    text, pattern = str(args[0]), str(args[1])
    return bool(_run_regex_op("match", pattern, text))


def _regex_find(args: list[Any]) -> Any:
    # No null in NyxScript, so — like get() — the "not found" value is a
    # mandatory default rather than something implicit.
    if len(args) != 3:
        raise _arity_error("regex_find", "3 arguments (text, pattern, default)", len(args))
    text, pattern, default = str(args[0]), str(args[1]), args[2]
    result = _run_regex_op("find", pattern, text)
    return result if result is not None else default


def _regex_find_all(args: list[Any]) -> list[Any]:
    if len(args) != 2:
        raise _arity_error("regex_find_all", "2 arguments (text, pattern)", len(args))
    text, pattern = str(args[0]), str(args[1])
    return list(_run_regex_op("find_all", pattern, text))


def _regex_replace(args: list[Any]) -> str:
    if len(args) != 3:
        raise _arity_error("regex_replace", "3 arguments (text, pattern, replacement)", len(args))
    text, pattern, replacement = str(args[0]), str(args[1]), str(args[2])
    return str(_run_regex_op("replace", pattern, text, replacement))


def _sha256(args: list[Any]) -> str:
    if len(args) != 1:
        raise _arity_error("sha256", "1 argument", len(args))
    return hashlib.sha256(str(args[0]).encode("utf-8")).hexdigest()


def _md5(args: list[Any]) -> str:
    # For fingerprinting/dedup keys, not password/security-sensitive
    # hashing — NyxScript has no auth system for md5's collision
    # weaknesses to matter against.
    if len(args) != 1:
        raise _arity_error("md5", "1 argument", len(args))
    return hashlib.md5(str(args[0]).encode("utf-8")).hexdigest()


def _base64_encode(args: list[Any]) -> str:
    if len(args) != 1:
        raise _arity_error("base64_encode", "1 argument", len(args))
    return base64.b64encode(str(args[0]).encode("utf-8")).decode("ascii")


def _base64_decode(args: list[Any]) -> str:
    if len(args) != 1:
        raise _arity_error("base64_decode", "1 argument", len(args))
    try:
        # binascii.Error (what b64decode actually raises) is a ValueError
        # subclass, so this catches both malformed padding/alphabet issues.
        raw = base64.b64decode(str(args[0]), validate=False)
    except ValueError as exc:
        raise ValueError(f"base64_decode(): invalid base64 — {exc}") from exc
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            "base64_decode(): decoded bytes aren't valid UTF-8 text "
            "(NyxScript has no binary/bytes type to hold them otherwise)"
        ) from exc


def _random(args: list[Any]) -> float:
    if args:
        raise _arity_error("random", "no arguments", len(args))
    return random.random()


# --- byte-level helpers ---------------------------------------------------
# NyxScript has no bytes type, so binary data crosses the `socket.*`
# boundary (see sockets.py) as a list of ints 0-255. These are the pure,
# always-available (no --unsafe needed) conversions for building and
# parsing binary protocol messages out of that — packing/unpacking
# integers is network byte order (big-endian), since that's what almost
# every wire protocol uses.


def _bytes_from_hex(args: list[Any]) -> list[int]:
    if len(args) != 1:
        raise _arity_error("bytes_from_hex", "1 argument", len(args))
    text = str(args[0])
    try:
        return list(bytes.fromhex(text))
    except ValueError as exc:
        raise ValueError(f"bytes_from_hex(): invalid hex string — {exc}") from exc


def _bytes_to_hex(args: list[Any]) -> str:
    if len(args) != 1:
        raise _arity_error("bytes_to_hex", "1 argument (a list of byte values)", len(args))
    if not isinstance(args[0], list):
        raise TypeError(f"bytes_to_hex() expects a list, got {type(args[0]).__name__}")
    try:
        return bytes(int(b) for b in args[0]).hex()
    except (TypeError, ValueError) as exc:
        raise ValueError("bytes_to_hex(): list must contain integers 0-255") from exc


def _bytes_from_string(args: list[Any]) -> list[int]:
    if len(args) != 1:
        raise _arity_error("bytes_from_string", "1 argument", len(args))
    return list(str(args[0]).encode("utf-8"))


def _bytes_to_string(args: list[Any]) -> str:
    if len(args) != 1:
        raise _arity_error("bytes_to_string", "1 argument (a list of byte values)", len(args))
    if not isinstance(args[0], list):
        raise TypeError(f"bytes_to_string() expects a list, got {type(args[0]).__name__}")
    try:
        return bytes(int(b) for b in args[0]).decode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"bytes_to_string(): {exc}") from exc


def _pack_uint(width: int, name: str, args: list[Any]) -> list[int]:
    if len(args) != 1:
        raise _arity_error(name, "1 argument", len(args))
    n = int(args[0])
    if not (0 <= n < 2 ** (width * 8)):
        raise ValueError(f"{name}(): {n} doesn't fit in an unsigned {width * 8}-bit integer")
    return list(n.to_bytes(width, byteorder="big"))


def _unpack_uint(width: int, name: str, args: list[Any]) -> int:
    if len(args) != 1:
        raise _arity_error(name, "1 argument (a list of byte values)", len(args))
    if not isinstance(args[0], list) or len(args[0]) != width:
        raise ValueError(f"{name}() expects a list of exactly {width} byte values")
    try:
        return int.from_bytes(bytes(int(b) for b in args[0]), byteorder="big")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}(): list must contain integers 0-255") from exc


def _pack_uint16(args: list[Any]) -> list[int]:
    return _pack_uint(2, "pack_uint16", args)


def _pack_uint32(args: list[Any]) -> list[int]:
    return _pack_uint(4, "pack_uint32", args)


def _unpack_uint16(args: list[Any]) -> int:
    return _unpack_uint(2, "unpack_uint16", args)


def _unpack_uint32(args: list[Any]) -> int:
    return _unpack_uint(4, "unpack_uint32", args)


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
    "sha256": _sha256,
    "md5": _md5,
    "base64_encode": _base64_encode,
    "base64_decode": _base64_decode,
    "random": _random,
    "bytes_from_hex": _bytes_from_hex,
    "bytes_to_hex": _bytes_to_hex,
    "bytes_from_string": _bytes_from_string,
    "bytes_to_string": _bytes_to_string,
    "pack_uint16": _pack_uint16,
    "pack_uint32": _pack_uint32,
    "unpack_uint16": _unpack_uint16,
    "unpack_uint32": _unpack_uint32,
    "regex_match": _regex_match,
    "regex_find": _regex_find,
    "regex_find_all": _regex_find_all,
    "regex_replace": _regex_replace,
}
