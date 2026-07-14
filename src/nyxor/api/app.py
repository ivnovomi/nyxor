"""NYXOR's REST API — a fourth front-end over the exact same ``run_*``
coroutines the CLI, TUI, and NyxScript use. Optional (``uv sync --extra
api``); the ``serve`` plugin imports this module lazily so the base
install never needs FastAPI or uvicorn.
"""

from __future__ import annotations

import asyncio
import ipaddress
from html import escape as html_escape
from urllib.parse import urlsplit

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from nyxor import __version__
from nyxor.api.oauth import DeviceAuthStore, OAuthError
from nyxor.core.config import NyxorConfig, load_config
from nyxor.core.interfaces import PluginMetadata
from nyxor.core.models import ModuleResult
from nyxor.core.plugins import discover_plugins
from nyxor.core.scoring import SecurityScore, render_badge, score_results
from nyxor.plugins.audit.plugin import run_audit
from nyxor.plugins.dns_.plugin import run_lookup as dns_run_lookup
from nyxor.plugins.http_.plugin import run_inspect as http_run_inspect
from nyxor.plugins.inventory.store import InventoryStore
from nyxor.plugins.tls_.plugin import run_inspect as tls_run_inspect

SCAN_RATE_LIMIT = "20/minute"  # audit/dns/tls/http/badge — each triggers real network I/O
DEFAULT_RATE_LIMIT = "60/minute"


def create_app(config: NyxorConfig | None = None) -> FastAPI:
    """Build the FastAPI app. A fresh config is loaded if none is supplied."""
    config = config or load_config()
    devices = DeviceAuthStore()

    limiter = Limiter(key_func=get_remote_address, default_limits=[DEFAULT_RATE_LIMIT])

    app = FastAPI(
        title="NYXOR API",
        version=__version__,
        description=(
            "A REST front-end over NYXOR's scan modules — the same run_* "
            "coroutines the CLI, TUI, and NyxScript use. Every check here is "
            "the same safe, non-destructive observation NYXOR always makes: "
            "TCP-connect, DNS, TLS handshake, HTTP request. No exploitation.\n\n"
            "Rate limited per client IP. Scan endpoints additionally refuse "
            "to target private/loopback/link-local addresses (SSRF guard). "
            "`/inventory` requires a bearer token obtained via the OAuth2 "
            "device flow (`POST /oauth/device/code`)."
        ),
    )
    app.state.limiter = limiter
    app.add_exception_handler(
        RateLimitExceeded,
        _rate_limit_exceeded_handler,  # type: ignore[arg-type]  # slowapi/starlette stub mismatch
    )
    app.add_middleware(SlowAPIMiddleware)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/plugins", response_model=list[PluginMetadata])
    async def plugins() -> list[PluginMetadata]:
        return [
            discovered.plugin.metadata
            for discovered in discover_plugins(disabled=config.plugins.disabled)
        ]

    @app.get("/audit/{domain}", response_model=list[ModuleResult])
    @limiter.limit(SCAN_RATE_LIMIT)
    async def audit(request: Request, domain: str) -> list[ModuleResult]:
        await _ensure_public_target(domain)
        return await run_audit(domain, config, validate_url=_ensure_public_target)

    @app.get("/audit/{domain}/score")
    @limiter.limit(SCAN_RATE_LIMIT)
    async def audit_score(request: Request, domain: str) -> dict[str, object]:
        await _ensure_public_target(domain)
        results = await run_audit(domain, config, validate_url=_ensure_public_target)
        score = score_results(results)
        return _score_payload(domain, score)

    @app.get("/badge/{domain}.svg")
    @limiter.limit(SCAN_RATE_LIMIT)
    async def badge(request: Request, domain: str) -> Response:
        """A live-generated shields.io-style badge — re-audits on every request."""
        await _ensure_public_target(domain)
        results = await run_audit(domain, config, validate_url=_ensure_public_target)
        score = score_results(results)
        svg = render_badge(score, label=domain)
        return Response(content=svg, media_type="image/svg+xml")

    @app.get("/dns/{domain}", response_model=ModuleResult)
    @limiter.limit(SCAN_RATE_LIMIT)
    async def dns(request: Request, domain: str) -> ModuleResult:
        await _ensure_public_target(domain)
        return await dns_run_lookup(domain, config.dns.resolvers, config.dns.timeout_seconds)

    @app.get("/tls/{target}", response_model=ModuleResult)
    @limiter.limit(SCAN_RATE_LIMIT)
    async def tls(request: Request, target: str) -> ModuleResult:
        await _ensure_public_target(target)
        return await tls_run_inspect(target, config.tls.timeout_seconds)

    @app.get("/http", response_model=ModuleResult)
    @limiter.limit(SCAN_RATE_LIMIT)
    async def http(request: Request, url: str) -> ModuleResult:
        await _ensure_public_target(url)
        return await http_run_inspect(url, config.http, validate_url=_ensure_public_target)

    @app.get("/inventory")
    async def inventory(
        authorization: str | None = Header(default=None),
    ) -> list[dict[str, object]]:
        _require_bearer_token(devices, authorization)
        return [asset.model_dump(mode="json") for asset in InventoryStore().list()]

    # ---------- OAuth2 Device Authorization Grant (RFC 8628) ----------

    @app.post("/oauth/device/code")
    async def oauth_device_code(request: Request) -> dict[str, object]:
        auth = devices.create()
        base = str(request.base_url).rstrip("/")
        return {
            "device_code": auth.device_code,
            "user_code": auth.user_code,
            "verification_uri": f"{base}/oauth/device",
            "verification_uri_complete": f"{base}/oauth/device?user_code={auth.user_code}",
            "expires_in": 600,
            "interval": 3,
        }

    @app.get("/oauth/device", response_class=HTMLResponse)
    async def oauth_device_page(user_code: str = "") -> str:
        # `user_code` is an attacker-controllable query param reflected into
        # this page — escape it before interpolating, or a crafted link
        # (e.g. ?user_code="><script>...) could hijack the approval the
        # user thinks they're granting to their own device.
        safe_user_code = html_escape(user_code, quote=True)
        return f"""<!DOCTYPE html><html><head><title>NYXOR device login</title></head>
<body style="font-family:monospace;max-width:420px;margin:64px auto">
<h2>Approve CLI login</h2>
<form method="post" action="/oauth/device/approve">
  <input name="user_code" value="{safe_user_code}" placeholder="XXXX-XXXX"
    style="font-size:1.2em;padding:8px;width:100%;box-sizing:border-box" autofocus>
  <button type="submit" style="margin-top:12px;padding:8px 16px">Approve</button>
</form>
</body></html>"""

    @app.post("/oauth/device/approve")
    async def oauth_device_approve(request: Request, user_code: str) -> dict[str, str]:
        _require_loopback_caller(request)
        try:
            devices.approve(user_code)
        except OAuthError as exc:
            raise HTTPException(status_code=400, detail=exc.description) from exc
        return {"status": "approved"}

    @app.post("/oauth/token")
    async def oauth_token(device_code: str) -> dict[str, str]:
        try:
            token = devices.poll(device_code)
        except OAuthError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": exc.code, "error_description": exc.description},
            ) from exc
        return {"access_token": token, "token_type": "bearer"}

    return app


def _require_loopback_caller(request: Request) -> None:
    """Device-flow approval has no separate operator credential to check —

    unlike a real IdP (Google, GitHub), NYXOR has no account system, so
    nothing distinguishes "the legitimate operator clicked approve" from
    "any client that can reach this API called POST /oauth/device/approve".
    Without this check, a script could call ``/oauth/device/code`` and then
    immediately self-approve its own ``user_code``, minting itself a valid
    bearer token for ``/inventory`` with zero human involvement whenever the
    API is bound beyond loopback (``nyx serve --host 0.0.0.0``).

    Restricting approval to callers on the same host as the server makes the
    already-documented mitigation ("the CLI's default bind of 127.0.0.1")
    an enforced boundary instead of an incidental one: an operator serving
    on a non-loopback interface for scanning still keeps approval local
    (e.g. via an SSH tunnel) rather than open to anyone who can reach the
    API.
    """
    host = request.client.host if request.client else None
    try:
        ip = ipaddress.ip_address(host) if host else None
    except ValueError:
        ip = None
    if ip is None or not ip.is_loopback:
        raise HTTPException(
            status_code=403,
            detail=(
                "device-flow approval is only accepted from localhost — "
                "if the API is served on a non-loopback interface, approve "
                "over an SSH tunnel or from a shell on the same host"
            ),
        )


def _require_bearer_token(devices: DeviceAuthStore, authorization: str | None) -> None:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="missing bearer token — run `nyx auth login` against this API first",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.removeprefix("Bearer ").strip()
    if not devices.is_valid_token(token):
        raise HTTPException(status_code=401, detail="invalid or expired token")


def _hostname_from_target(raw: str) -> str:
    """Pull a bare hostname/IP out of a domain, ``host:port``, ``[ipv6]:port``, or URL string."""
    if "://" in raw:
        return urlsplit(raw).hostname or ""
    if raw.startswith("[") and "]" in raw:
        return raw[1 : raw.index("]")]
    if raw.count(":") == 1:
        host, _, port = raw.partition(":")
        if port.isdigit():
            return host
    return raw


def _reject_if_unsafe_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, hostname: str) -> None:
    unsafe = (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
        # Belt-and-suspenders: catches ranges like the 100.64.0.0/10 CGNAT /
        # Shared Address Space block, which Python's ipaddress module
        # deliberately excludes from *both* is_private and is_global (it's
        # neither), so it would otherwise sail past every check above while
        # still routing to cloud-internal infrastructure (AWS ENIs, etc.).
        or not ip.is_global
    )
    if unsafe:
        raise HTTPException(
            status_code=400,
            detail=f"refusing to scan {hostname!r}: resolves to a non-public address ({ip})",
        )


async def _ensure_public_target(raw: str) -> None:
    """Block SSRF: refuse to scan loopback/private/link-local/metadata addresses.

    This API is meant to audit *other people's* infrastructure over the public
    internet — without this check, ``/http?url=http://169.254.169.254/...`` or
    ``/tls/127.0.0.1:6379`` would turn an internet-facing NYXOR instance into a
    generic internal-network probe for anyone who can reach it.
    """
    hostname = _hostname_from_target(raw)
    if not hostname:
        return

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        ip = None

    if ip is not None:
        _reject_if_unsafe_ip(ip, hostname)
        return

    try:
        loop = asyncio.get_running_loop()
        infos = await loop.getaddrinfo(hostname, None)
    except OSError:
        return  # let the actual scan surface the resolution failure

    for info in infos:
        _reject_if_unsafe_ip(ipaddress.ip_address(info[4][0]), hostname)


def _score_payload(domain: str, score: SecurityScore) -> dict[str, object]:
    return {
        "domain": domain,
        "grade": score.grade,
        "points": score.points,
        "finding_counts": {
            severity.value: count for severity, count in score.finding_counts.items()
        },
    }
