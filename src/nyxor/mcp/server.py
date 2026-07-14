"""NYXOR's MCP server — a fifth front-end over the exact same ``run_*``
coroutines the CLI, TUI, REST API, and NyxScript use.

Deliberately narrower than the REST API: no ``--unsafe`` NyxScript
execution (``python:``/``pip``) and no `hostcheck --kill` are exposed
here. An MCP tool can be invoked autonomously by whatever agent is
driving the conversation — the human-in-the-loop confirmation that gates
those two features everywhere else in NYXOR doesn't exist over MCP, so
this surface just doesn't offer them at all rather than trying to
re-implement a confirmation step inside a tool call.

Requires the optional ``mcp`` extra (``uv sync --extra mcp``); imported
lazily by the CLI so the base install doesn't need the MCP SDK at all.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from nyxor.core.config import load_config
from nyxor.core.models import ModuleResult
from nyxor.core.scoring import score_results
from nyxor.core.scripting import lint_source, run_script
from nyxor.plugins.audit.plugin import run_audit
from nyxor.plugins.dns_.plugin import run_lookup as dns_run_lookup
from nyxor.plugins.hostcheck.plugin import run_hostcheck
from nyxor.plugins.http_.plugin import run_inspect as http_run_inspect
from nyxor.plugins.recon.plugin import run_recon
from nyxor.plugins.tls_.plugin import run_inspect as tls_run_inspect

mcp = FastMCP(
    "nyxor",
    instructions=(
        "NYXOR is a passive, non-destructive infrastructure auditing toolkit. "
        "Every tool here only observes — DNS lookups, TLS handshakes, HTTP "
        "requests, certificate-transparency logs, a local process listing — "
        "none of them exploit, modify, or attack anything. Only audit "
        "domains and hosts you're authorized to test."
    ),
)


def _format_results(results: list[ModuleResult]) -> str:
    lines: list[str] = []
    for result in results:
        lines.append(f"## {result.module} — {result.target}")
        if result.errors:
            lines.append(f"Errors: {'; '.join(result.errors)}")
        if not result.findings:
            lines.append("No findings.")
        for finding in result.findings:
            lines.append(f"- [{finding.severity.value}] {finding.title}: {finding.description}")
        lines.append("")
    return "\n".join(lines)


@mcp.tool()
async def audit(domain: str) -> str:
    """Run a combined DNS + TLS + HTTP audit and return a letter grade plus every finding."""
    results = await run_audit(domain, load_config())
    score = score_results(results)
    header = f"# Audit: {domain} — grade {score.grade} ({score.points}/100)\n\n"
    return header + _format_results(results)


@mcp.tool()
async def dns_lookup(domain: str) -> str:
    """DNS record lookup, DNSSEC, and mail-record (SPF/DMARC/MX) checks for a domain."""
    config = load_config()
    result = await dns_run_lookup(domain, config.dns.resolvers, config.dns.timeout_seconds)
    return _format_results([result])


@mcp.tool()
async def tls_inspect(target: str) -> str:
    """TLS certificate inspection for a HOST, HOST:PORT, or URL."""
    result = await tls_run_inspect(target, load_config().tls.timeout_seconds)
    return _format_results([result])


@mcp.tool()
async def http_inspect(url: str) -> str:
    """HTTP response headers, redirects, cookies, and security-header checks for a URL."""
    result = await http_run_inspect(url, load_config().http)
    return _format_results([result])


@mcp.tool()
async def recon(domain: str, resolve: bool = True) -> str:
    """Passive subdomain discovery via certificate transparency logs (crt.sh).

    No active scanning of the target — only reads a public, third-party
    log of certificates already issued for the domain.
    """
    results = await run_recon(domain, resolve=resolve)
    return _format_results(results)


@mcp.tool()
async def hostcheck() -> str:
    """Passive local host hygiene check on THIS machine: process name/path

    mismatches and suspicious autorun entries. Not an antivirus, and
    never terminates anything — read-only, same as every other tool here.
    """
    result = await run_hostcheck()
    return _format_results([result])


@mcp.tool()
def lint_nyxscript(source: str) -> str:
    """Statically check a NyxScript source string — undefined variables, unknown

    modules, stray break/continue/return — without executing a single
    line of it.
    """
    issues = lint_source(source)
    if not issues:
        return "No issues found."
    return "\n".join(str(issue) for issue in issues)


@mcp.tool()
async def run_nyxscript(source: str) -> str:
    """Lint, then run, a NyxScript source string and return its printed output.

    Runs with the same safety default as everywhere else in NYXOR:
    ``python:``/``pip``/``socket.*`` are all disabled (this tool never
    passes ``--unsafe``), so a script can only do what NyxScript's own
    sandboxed grammar and audited scan modules allow — no arbitrary code
    execution and no arbitrary-host network access reachable from an MCP
    call. ``allow_unsafe_directive=False`` closes the one gap that would
    otherwise leave: a script's own ``unsafe`` statement (see the language
    guide) flips all three on for anyone running it locally, but that same
    statement is refused outright here — `unsafe=False` on this path is a
    hard ceiling, not just a starting value a submitted script could raise
    itself.
    """
    issues = lint_source(source)
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        return "Lint errors — fix these before running:\n" + "\n".join(
            str(issue) for issue in errors
        )

    output_lines: list[str] = []
    try:
        await run_script(
            source,
            load_config(),
            output=output_lines.append,
            unsafe=False,
            allow_unsafe_directive=False,
        )
    except Exception as exc:  # surface any NyxScript error as tool output, not a server crash
        output_lines.append(f"Error: {exc}")
    return "\n".join(output_lines) if output_lines else "(no output)"


def main() -> None:
    """Run the server over stdio — the transport MCP clients expect."""
    mcp.run()


if __name__ == "__main__":
    main()
