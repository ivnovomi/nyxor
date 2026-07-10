"""Windows autorun/startup entry enumeration.

Registry `Run`/`RunOnce` keys and the Startup folder — the two places
almost everything that "starts with Windows" actually registers itself.
Not Windows? Nothing to check; every function here returns an empty list
rather than raising, the same "just doesn't apply on this platform"
pattern the rest of NYXOR uses.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

_RUN_KEYS = (
    ("HKEY_CURRENT_USER", r"Software\Microsoft\Windows\CurrentVersion\Run"),
    ("HKEY_CURRENT_USER", r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
    ("HKEY_LOCAL_MACHINE", r"Software\Microsoft\Windows\CurrentVersion\Run"),
    ("HKEY_LOCAL_MACHINE", r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
)
_SUSPICIOUS_PATH_MARKERS = ("\\temp\\", "\\tmp\\", "\\appdata\\local\\temp\\", "\\downloads\\")


@dataclass(frozen=True)
class AutorunEntry:
    source: str
    name: str
    command: str


def extract_exe_path(command: str) -> str:
    command = command.strip()
    if command.startswith('"'):
        end = command.find('"', 1)
        if end != -1:
            return command[1:end]
    return command.split(" ")[0]


def is_suspicious(command: str) -> bool:
    exe = extract_exe_path(command).lower().replace("/", "\\")
    return any(marker in exe for marker in _SUSPICIOUS_PATH_MARKERS)


def list_registry_autoruns() -> list[AutorunEntry]:
    if sys.platform != "win32":
        return []
    import winreg

    hives = {
        "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
        "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
    }
    entries: list[AutorunEntry] = []
    for hive_name, subkey in _RUN_KEYS:
        try:
            with winreg.OpenKey(hives[hive_name], subkey) as key:
                index = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, index)
                    except OSError:
                        break
                    entries.append(
                        AutorunEntry(source=f"{hive_name}\\{subkey}", name=name, command=str(value))
                    )
                    index += 1
        except OSError:
            continue  # key doesn't exist on this machine — nothing registered there
    return entries


def list_startup_folder() -> list[AutorunEntry]:
    if sys.platform != "win32":
        return []
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return []
    folder = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    if not folder.is_dir():
        return []
    return [
        AutorunEntry(source="Startup folder", name=item.name, command=str(item))
        for item in folder.iterdir()
        if item.is_file()
    ]


def suspicious_autoruns() -> list[AutorunEntry]:
    all_entries = list_registry_autoruns() + list_startup_folder()
    return [entry for entry in all_entries if is_suspicious(entry.command)]
