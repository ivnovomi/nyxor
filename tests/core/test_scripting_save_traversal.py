from __future__ import annotations

from pathlib import Path

import pytest

from nyxor.core.config import load_config
from nyxor.core.models import ModuleResult
from nyxor.core.scripting import run_script
from nyxor.core.scripting.errors import RuntimeScriptError
from nyxor.core.scripting.stdlib import MODULE_RUNNERS


async def _fake_run_dns(target: str, config: object) -> list[ModuleResult]:
    return [ModuleResult(module="dns.lookup", target=target)]


@pytest.fixture(autouse=True)
def _stub_dns_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    # `save` only needs *some* ModuleResult in scope — stub the dns runner
    # so these tests don't touch the network.
    monkeypatch.setitem(MODULE_RUNNERS, "dns", _fake_run_dns)


async def test_save_with_an_absolute_path_is_rejected(tmp_path: Path) -> None:
    # `Path.__truediv__` silently discards `base_dir` when the right side is
    # absolute — without a containment check, this would happily write
    # outside the script's working directory with no --unsafe required.
    outside = tmp_path / "outside" / "escaped.json"
    with pytest.raises(RuntimeScriptError, match="outside the script's working directory"):
        await run_script(
            f'run dns "example.com" as r\nsave r to "{outside.as_posix()}"\n',
            load_config(),
            base_dir=tmp_path / "workdir",
        )
    assert not outside.exists()


async def test_save_with_a_dotdot_escape_is_rejected(tmp_path: Path) -> None:
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    with pytest.raises(RuntimeScriptError, match="outside the script's working directory"):
        await run_script(
            'run dns "example.com" as r\nsave r to "../escaped.json"\n',
            load_config(),
            base_dir=workdir,
        )
    assert not (tmp_path / "escaped.json").exists()


async def test_save_within_the_working_directory_still_works(tmp_path: Path) -> None:
    lines: list[str] = []
    await run_script(
        'run dns "example.com" as r\nsave r to "report.json"\n',
        load_config(),
        output=lines.append,
        base_dir=tmp_path,
    )
    assert (tmp_path / "report.json").exists()
