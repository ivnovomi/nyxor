"""The ``analyze`` plugin: ``nyx analyze <domain>`` — an AI-written summary.

Prefers a local model (Ollama, on your own hardware — free, nothing leaves
the machine). Falls back to a deterministic rule-based summary if no local
model is reachable, so the command always produces something. NYXOR Cloud
points the same command at a hosted model instead of Ollama, for anyone
who'd rather not run one — see `--host`.
"""

from __future__ import annotations

import asyncio

import typer

from nyxor.core.context import NyxorContext
from nyxor.core.interfaces import PluginMetadata
from nyxor.plugins.analyze.heuristics import summarize
from nyxor.plugins.analyze.ollama import OllamaUnavailable, build_prompt, generate
from nyxor.plugins.audit.plugin import run_audit


def _analyze(
    ctx: typer.Context,
    domain: str,
    host: str | None = typer.Option(
        None, "--host", help="Local (or Cloud) model server. Defaults to config ai.ollama_host."
    ),
    model: str | None = typer.Option(
        None, "--model", help="Model name. Defaults to config ai.model."
    ),
    no_local: bool = typer.Option(
        False, "--no-local", help="Skip the local model and go straight to the rule-based summary."
    ),
) -> None:
    """Audit a domain and get a short written summary of what it found."""
    context: NyxorContext = ctx.obj
    ai_config = context.config.ai
    host = host or ai_config.ollama_host
    model = model or ai_config.model

    results = asyncio.run(run_audit(domain, context.config))

    summary: str | None = None
    used_local_model = False

    if not no_local:
        prompt = build_prompt(domain, results)
        try:
            summary = asyncio.run(
                generate(prompt, host=host, model=model, timeout_seconds=ai_config.timeout_seconds)
            )
            used_local_model = True
        except OllamaUnavailable as exc:
            context.console.print(f"[dim]No local model available ({exc}).[/dim]")

    if summary is None:
        summary = summarize(domain, results)

    context.console.print()
    if used_local_model:
        context.console.print(f"[bold #7ee7e1]AI summary[/] (local model: {model})")
    else:
        context.console.print("[bold]Summary[/] (rule-based — no local model found)")
        context.console.print(
            "[dim]Install Ollama (ollama.com) and run `ollama pull llama3.2` for an AI-written "
            "summary, entirely local. NYXOR Cloud runs this on a hosted model instead — no GPU, "
            "nothing to install.[/dim]"
        )
    # `summary` is plain text (rule-based or model-generated) that can
    # legitimately contain "[medium]"-style substrings — printing it with
    # markup enabled would have Rich silently swallow those as (invalid)
    # style tags instead of showing them.
    context.console.print(summary, markup=False)


class AnalyzePlugin:
    metadata = PluginMetadata(
        name="analyze",
        description="AI-written findings summary — local model preferred, rule-based fallback.",
        version="0.1.0",
        author="NYXOR",
        commands=("analyze",),
        category="AI (local model)",
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        """Register the analyze command with the Typer application.
        
        Parameters:
        	app (typer.Typer): The application to which the command is added.
        	context (NyxorContext): The plugin execution context.
        """
        app.command("analyze", rich_help_panel=self.metadata.category)(_analyze)


PLUGIN = AnalyzePlugin()
