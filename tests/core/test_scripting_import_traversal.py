from __future__ import annotations

from pathlib import Path

import pytest

from nyxor.core.config import load_config
from nyxor.core.scripting import run_script
from nyxor.core.scripting.errors import RuntimeScriptError


async def test_import_with_an_absolute_path_is_rejected(tmp_path: Path) -> None:
    # `Path.__truediv__` silently discards `base_dir` when the right side is
    # absolute — without a containment check, a script run without --unsafe
    # could read (and exfiltrate via print/save) any file the process can
    # access.
    secret = tmp_path / "secret.nyx"
    secret.write_text('set leaked = "sk-super-secret-value-12345"\n')

    workdir = tmp_path / "workdir"
    workdir.mkdir()
    with pytest.raises(RuntimeScriptError, match="outside the script's working directory"):
        await run_script(
            f'import "{secret.as_posix()}" as leaked\n',
            load_config(),
            base_dir=workdir,
        )


async def test_import_with_a_dotdot_escape_is_rejected(tmp_path: Path) -> None:
    secret = tmp_path / "secret.nyx"
    secret.write_text('set leaked = "sk-super-secret-value-12345"\n')

    workdir = tmp_path / "workdir"
    workdir.mkdir()
    with pytest.raises(RuntimeScriptError, match="outside the script's working directory"):
        await run_script(
            'import "../secret.nyx" as leaked\n',
            load_config(),
            base_dir=workdir,
        )


async def test_import_within_the_working_directory_still_works(tmp_path: Path) -> None:
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    (lib_dir / "helper.nyx").write_text('set greeting = "hi"\n')

    lines: list[str] = []
    await run_script(
        'import "lib/helper.nyx" as helper\nprint(helper.greeting)\n',
        load_config(),
        output=lines.append,
        base_dir=tmp_path,
    )
    assert lines == ["hi"]
