"""NYXOR's REST API — a fourth front-end over the exact same ``run_*``
coroutines the CLI, TUI, and NyxScript use. Optional (``uv sync --extra
api``); the ``serve`` plugin imports this module lazily so the base
install never needs FastAPI or uvicorn.
"""

from __future__ import annotations

from fastapi import FastAPI, Response

from nyxor import __version__
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


def create_app(config: NyxorConfig | None = None) -> FastAPI:
    """Build the FastAPI app. A fresh config is loaded if none is supplied."""
    config = config or load_config()

    app = FastAPI(
        title="NYXOR API",
        version=__version__,
        description=(
            "A REST front-end over NYXOR's scan modules — the same run_* "
            "coroutines the CLI, TUI, and NyxScript use. Every check here is "
            "the same safe, non-destructive observation NYXOR always makes: "
            "TCP-connect, DNS, TLS handshake, HTTP request. No exploitation."
        ),
    )

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
    async def audit(domain: str) -> list[ModuleResult]:
        return await run_audit(domain, config)

    @app.get("/audit/{domain}/score")
    async def audit_score(domain: str) -> dict[str, object]:
        results = await run_audit(domain, config)
        score = score_results(results)
        return _score_payload(domain, score)

    @app.get("/badge/{domain}.svg")
    async def badge(domain: str) -> Response:
        """A live-generated shields.io-style badge — re-audits on every request."""
        results = await run_audit(domain, config)
        score = score_results(results)
        svg = render_badge(score, label=domain)
        return Response(content=svg, media_type="image/svg+xml")

    @app.get("/dns/{domain}", response_model=ModuleResult)
    async def dns(domain: str) -> ModuleResult:
        return await dns_run_lookup(domain, config.dns.resolvers, config.dns.timeout_seconds)

    @app.get("/tls/{target}", response_model=ModuleResult)
    async def tls(target: str) -> ModuleResult:
        return await tls_run_inspect(target, config.tls.timeout_seconds)

    @app.get("/http", response_model=ModuleResult)
    async def http(url: str) -> ModuleResult:
        return await http_run_inspect(url, config.http)

    @app.get("/inventory")
    async def inventory() -> list[dict[str, object]]:
        return [asset.model_dump(mode="json") for asset in InventoryStore().list()]

    return app


def _score_payload(domain: str, score: SecurityScore) -> dict[str, object]:
    return {
        "domain": domain,
        "grade": score.grade,
        "points": score.points,
        "finding_counts": {
            severity.value: count for severity, count in score.finding_counts.items()
        },
    }
