"""The ``hostcheck`` plugin: ``nyx hostcheck`` — passive local host hygiene.

Not an antivirus. No signature database, no real-time protection, no
kernel hooks, no claim to be "better than" anything that actually does
those things. Three honest, explainable checks: process name/path
mismatches, autorun entries pointing at temp-style paths, and — only if
you supply your own free VirusTotal API key — a hash-reputation lookup.
Findings are reported the same way every other NYXOR module reports
things: read them, decide what to do. ``--kill`` only ever acts on
something you explicitly confirm, one process at a time.
"""

from __future__ import annotations

import asyncio
from typing import Any

import typer
from rich.table import Table

from nyxor.core.context import NyxorContext
from nyxor.core.interfaces import PluginMetadata
from nyxor.core.models import Finding, ModuleResult, Severity
from nyxor.core.output import emit_results
from nyxor.plugins.hostcheck.autorun import suspicious_autoruns
from nyxor.plugins.hostcheck.processes import ProcessFinding, scan_processes
from nyxor.plugins.hostcheck.reputation import check_hash, sha256_of

_SEVERITY_MAP = {
    "high": Severity.HIGH,
    "medium": Severity.MEDIUM,
    "low": Severity.LOW,
    "info": Severity.INFO,
}


async def _vt_augment(
    finding: ProcessFinding, vt_api_key: str
) -> tuple[ProcessFinding, dict[str, Any]]:
    evidence: dict[str, Any] = {"pid": finding.pid, "exe": finding.exe}
    if not finding.exe:
        return finding, evidence

    digest = sha256_of(finding.exe)
    if not digest:
        return finding, evidence
    evidence["sha256"] = digest

    stats = await check_hash(digest, vt_api_key)
    if not stats:
        return finding, evidence
    evidence["virustotal"] = stats

    if stats["malicious"] > 0 and finding.severity != "high":
        finding = ProcessFinding(
            pid=finding.pid,
            name=finding.name,
            exe=finding.exe,
            severity="high",
            reason=finding.reason
            + f" — VirusTotal: {stats['malicious']} engine(s) flag this hash as malicious",
        )
    return finding, evidence


async def run_hostcheck(
    *,
    vt_api_key: str | None = None,
    check_processes: bool = True,
    check_autorun: bool = True,
) -> ModuleResult:
    result = ModuleResult(module="hostcheck", target="localhost")

    process_findings = scan_processes() if check_processes else []
    for pf in process_findings:
        evidence: dict[str, Any] = {"pid": pf.pid, "exe": pf.exe}
        if vt_api_key:
            pf, evidence = await _vt_augment(pf, vt_api_key)
        result.findings.append(
            Finding(
                title=f"Process: {pf.name} (pid {pf.pid})",
                severity=_SEVERITY_MAP[pf.severity],
                target="localhost",
                description=pf.reason,
                evidence=evidence,
                tags=("process",),
            )
        )

    if check_autorun:
        for entry in suspicious_autoruns():
            result.findings.append(
                Finding(
                    title=f"Autorun: {entry.name}",
                    severity=Severity.MEDIUM,
                    target="localhost",
                    description=f"{entry.source} -> {entry.command}",
                    evidence={"source": entry.source, "command": entry.command},
                    tags=("autorun",),
                )
            )

    if not vt_api_key:
        result.raw_data["note"] = (
            "No VirusTotal API key supplied — local heuristics only. Pass "
            "--vt-api-key (or set VT_API_KEY) for hash-reputation lookups."
        )
    return result


def _print_summary(context: NyxorContext, result: ModuleResult) -> None:
    table = Table(
        title=f"hostcheck — {len(result.findings)} finding(s)",
        show_header=True,
        header_style="bold",
    )
    table.add_column("Severity")
    table.add_column("Finding")
    table.add_column("Detail")
    for finding in result.findings:
        table.add_row(finding.severity.value.upper(), finding.title, finding.description)
    context.console.print(table)
    note = result.raw_data.get("note")
    if note:
        context.console.print(f"[dim]{note}[/]")


def _kill_high_severity(context: NyxorContext, result: ModuleResult, *, yes: bool) -> None:
    import psutil

    targets = [f for f in result.findings if f.severity == Severity.HIGH and "pid" in f.evidence]
    if not targets:
        context.console.print("[dim]No HIGH-severity process findings to act on.[/]")
        return

    for finding in targets:
        pid = finding.evidence["pid"]
        if not yes and not typer.confirm(f"Terminate PID {pid} — {finding.title}?"):
            context.console.print(f"[dim]Skipped PID {pid}.[/]")
            continue
        try:
            psutil.Process(pid).terminate()
            context.console.print(f"[green]Terminated[/] PID {pid} ({finding.title})")
        except psutil.NoSuchProcess:
            context.console.print(f"[dim]PID {pid} already gone.[/]")
        except psutil.AccessDenied:
            context.console.print(
                f"[red]Access denied[/] terminating PID {pid} — try running as Administrator."
            )


def _hostcheck(
    ctx: typer.Context,
    vt_api_key: str | None = typer.Option(
        None,
        "--vt-api-key",
        envvar="VT_API_KEY",
        help="Your own free VirusTotal API key, for hash-reputation lookups.",
    ),
    kill: bool = typer.Option(
        False, "--kill", help="Offer to terminate HIGH-severity process findings, one at a time."
    ),
    yes: bool = typer.Option(
        False, "--yes", help="Don't ask for confirmation before killing (use with --kill)."
    ),
) -> None:
    """Passive local host hygiene checks: suspicious processes and autorun entries.

    Not an antivirus — no signatures, no real-time protection.
    """
    context: NyxorContext = ctx.obj
    result = asyncio.run(run_hostcheck(vt_api_key=vt_api_key))

    if context.output.format == "table" and context.output.output_path is None:
        _print_summary(context, result)
    emit_results(context, [result], title="NYXOR Host Check")

    if kill:
        _kill_high_severity(context, result, yes=yes)


class HostcheckPlugin:
    metadata = PluginMetadata(
        name="hostcheck",
        description="Passive local host hygiene checks (processes, autorun) — not an antivirus.",
        version="0.1.0",
        author="NYXOR",
        commands=("hostcheck",),
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        app.command("hostcheck")(_hostcheck)


PLUGIN = HostcheckPlugin()
