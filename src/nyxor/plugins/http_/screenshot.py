"""Full-page website screenshots via a headless Chromium (Playwright).

Gated behind ``--unsafe`` (see ``nyx http inspect --screenshot``): unlike
the rest of this module's HTTP inspection, a real browser executes the
page's own JavaScript and loads whatever subresources it references —
images, ``fetch()`` calls, WebSocket connections — none of which route
through this project's SSRF guard (:func:`nyxor.plugins.http_.inspector.
inspect`'s IP-pinning only covers the single request/response chain it
drives itself). Capturing a screenshot of a page you don't control can
therefore make outbound requests to hosts of the *page's* choosing, not
just the target's — a real capability expansion past NYXOR's
passive-audit identity, same reasoning as ``socket.*`` in NyxScript.

The one request this module *can* still pin cheaply is the top-level
navigation, via Chromium's own ``--host-resolver-rules`` launch flag —
the browser-level equivalent of the SNI/Host-header pinning
``inspector.py`` does for plain HTTP requests. That only covers the
top-level document, though; everything the page's own script pulls in
afterward is exactly the risk ``--unsafe`` is consenting to.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from nyxor.core.errors import NyxorError

_DEFAULT_TIMEOUT_SECONDS = 30.0


class ScreenshotError(Exception):
    """Raised when a screenshot could not be captured."""


def _host_resolver_rule(url: str, pinned_ip: str) -> str | None:
    """Build a Chromium ``--host-resolver-rules`` launch arg pinning ``url``'s

    host to ``pinned_ip``, or ``None`` if ``url`` has no hostname to pin.
    """
    hostname = urlsplit(url).hostname
    if not hostname:
        return None
    return f"--host-resolver-rules=MAP {hostname} {pinned_ip}"


async def capture_screenshot(
    url: str,
    output_path: Path,
    *,
    timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    pinned_ip: str | None = None,
) -> None:
    """Render ``url`` in headless Chromium and save a full-page PNG.

    ``timeout`` is seconds, matching every other timeout in this project
    (Playwright's own API takes milliseconds internally).
    """
    try:
        # 'screenshot' is a deliberately optional extra (not in CI's default
        # install matrix, so mypy can't see its stubs there either) — see the
        # module docstring for why.
        from playwright.async_api import Error as PlaywrightError  # type: ignore[import-not-found]
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise NyxorError(
            "Screenshots need the 'screenshot' extra.",
            hint="Install it with: uv sync --extra screenshot",
        ) from exc

    launch_args = []
    if pinned_ip is not None:
        rule = _host_resolver_rule(url, pinned_ip)
        if rule is not None:
            launch_args.append(rule)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(args=launch_args)
            try:
                page = await browser.new_page()
                await page.goto(url, timeout=timeout * 1000, wait_until="load")
                await page.screenshot(path=str(output_path), full_page=True)
            finally:
                await browser.close()
    except PlaywrightError as exc:
        raise ScreenshotError(f"Could not capture a screenshot of {url}: {exc}") from exc
