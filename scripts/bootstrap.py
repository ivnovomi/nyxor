#!/usr/bin/env python3
"""Set up a local NYXOR development environment: `uv sync` + a sanity check."""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    subprocess.run(["uv", "sync", "--extra", "dev"], check=True)
    subprocess.run(["uv", "run", "nyx", "doctor"], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
