from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import typer
from rich.console import Console

from nyxor.core.config import load_config
from nyxor.core.context import NyxorContext
from nyxor.core.errors import NyxorError
from nyxor.core.models import ModuleResult
from nyxor.plugins.http_ import plugin as http_plugin
from nyxor.plugins.http_.screenshot import _host_resolver_rule, capture_screenshot


def test_host_resolver_rule_maps_the_hostname_to_the_pinned_ip() -> None:
    rule = _host_resolver_rule("https://example.com:8443/path", "93.184.216.34")
    assert rule == "--host-resolver-rules=MAP example.com 93.184.216.34"


def test_host_resolver_rule_returns_none_without_a_hostname() -> None:
    assert _host_resolver_rule("not-a-url", "93.184.216.34") is None


async def test_capture_screenshot_raises_a_friendly_error_without_the_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Force the import to fail regardless of whether the 'screenshot' extra
    # happens to be installed in whatever environment runs this test — the
    # main test suite never installs it (playwright/textual-image are heavy,
    # opt-in-only dependencies), and this exercises exactly that path.
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.async_api", None)

    with pytest.raises(NyxorError, match="'screenshot' extra"):
        await capture_screenshot("https://example.com", Path("/tmp/nyxor-test-shot.png"))


def test_http_inspect_refuses_screenshot_without_unsafe(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run_inspect(url, config, *, validate_url=None):
        return ModuleResult(module="http.inspect", target=url)

    monkeypatch.setattr(http_plugin, "run_inspect", fake_run_inspect)

    called = False

    async def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(http_plugin, "_screenshot_and_preview", fail_if_called)

    context = NyxorContext(config=load_config(), console=Console(record=True, width=120))
    ctx = SimpleNamespace(obj=context)

    with pytest.raises(typer.Exit) as exc_info:
        http_plugin.http_inspect(
            ctx, "https://example.com", screenshot=Path("/tmp/nyxor-test-shot.png"), unsafe=False
        )

    assert exc_info.value.exit_code == 1
    assert not called
    assert "--screenshot requires --unsafe" in context.console.export_text()
