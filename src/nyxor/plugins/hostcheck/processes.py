"""Heuristic checks over currently-running processes.

Not an antivirus — no signature database, no real-time protection, no
kernel hooks. Two honest, explainable heuristics over what `psutil` can
already see: a process claiming to be a well-known Windows system process
but running from the wrong place (classic masquerading), and a process
running from a temp/downloads-style directory.
"""

from __future__ import annotations

from dataclasses import dataclass

import psutil

# Names Windows always runs from a specific, well-known location — anything
# else using one of these names is the strongest signal available without
# an actual signature database. Most live in System32/SysWOW64; explorer.exe
# is the one legitimate exception, running straight out of \Windows itself
# (checking it against "\system32\" like the others is a false positive —
# real Windows installs never put it there).
_SYSTEM32_PROCESS_NAMES = {
    "svchost.exe",
    "csrss.exe",
    "wininit.exe",
    "winlogon.exe",
    "lsass.exe",
    "smss.exe",
    "services.exe",
    "spoolsv.exe",
    "taskhostw.exe",
}
_WINDOWS_ROOT_PROCESS_NAMES = {"explorer.exe"}
_SYSTEM_DIRS = ("system32", "syswow64", "winsxs")
_SUSPICIOUS_PATH_MARKERS = ("\\temp\\", "\\tmp\\", "\\appdata\\local\\temp\\", "\\downloads\\")


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    name: str
    exe: str | None
    username: str | None


@dataclass(frozen=True)
class ProcessFinding:
    pid: int
    name: str
    exe: str | None
    severity: str  # "high" | "medium"
    reason: str


def _is_masquerading(info: ProcessInfo) -> bool:
    name = info.name.lower()
    is_system32_name = name in _SYSTEM32_PROCESS_NAMES
    is_windows_root_name = name in _WINDOWS_ROOT_PROCESS_NAMES
    if not is_system32_name and not is_windows_root_name:
        return False
    if not info.exe:
        return True  # claims a system name; can't vouch for an unreadable path either

    exe_lower = info.exe.lower().replace("/", "\\")
    if is_windows_root_name:
        return not exe_lower.endswith(f"\\windows\\{name}")
    return not any(f"\\{d}\\" in exe_lower for d in _SYSTEM_DIRS)


def _is_suspicious_path(info: ProcessInfo) -> bool:
    if not info.exe:
        return False
    exe_lower = info.exe.lower().replace("/", "\\")
    return any(marker in exe_lower for marker in _SUSPICIOUS_PATH_MARKERS)


def evaluate(info: ProcessInfo) -> ProcessFinding | None:
    if _is_masquerading(info):
        where = info.exe if info.exe else "path unreadable"
        expected = (
            "\\Windows\\"
            if info.name.lower() in _WINDOWS_ROOT_PROCESS_NAMES
            else "System32/SysWOW64"
        )
        return ProcessFinding(
            pid=info.pid,
            name=info.name,
            exe=info.exe,
            severity="high",
            reason=f"Named like a Windows system process, but not running "
            f"from {expected} ({where})",
        )
    if _is_suspicious_path(info):
        return ProcessFinding(
            pid=info.pid,
            name=info.name,
            exe=info.exe,
            severity="medium",
            reason=f"Running from a temp/downloads-style path: {info.exe}",
        )
    return None


def list_running_processes() -> list[ProcessInfo]:
    """The real process list, straight from psutil — the only impure function here."""
    infos: list[ProcessInfo] = []
    for proc in psutil.process_iter(["pid", "name", "exe", "username"]):
        try:
            data = proc.info
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        infos.append(
            ProcessInfo(
                pid=data["pid"],
                name=data["name"] or "",
                exe=data["exe"],
                username=data["username"],
            )
        )
    return infos


def scan_processes(processes: list[ProcessInfo] | None = None) -> list[ProcessFinding]:
    """Evaluate every process, real or (in tests) supplied, returning only the flagged ones."""
    if processes is None:
        processes = list_running_processes()
    findings = []
    for info in processes:
        finding = evaluate(info)
        if finding is not None:
            findings.append(finding)
    return findings
