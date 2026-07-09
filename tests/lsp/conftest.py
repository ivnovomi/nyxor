from __future__ import annotations

from collections.abc import Iterator

import pytest
from pygls.lsp.server import LanguageServer

from nyxor.lsp.server import server as _server


@pytest.fixture
def server() -> Iterator[LanguageServer]:
    """The real module-level LSP server, with a fresh workspace per test.

    It's a singleton in `nyxor.lsp.server` (mirroring how pygls servers are
    normally used — one process, one server), so tests just need to swap
    its workspace out; nothing else on it is test-specific state.
    """
    yield _server
