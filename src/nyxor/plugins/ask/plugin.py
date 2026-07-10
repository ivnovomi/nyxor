"""The ``ask`` plugin: ``nyx ask`` — chat with a local model about your

recorded scan history (`nyx audit`/`nyx trends`). Single-shot with a
question on the command line, or an interactive REPL with none — either
way, it's the same local Ollama model `nyx analyze` already talks to, fed
nothing but the trend history already sitting in your own trends.json.
Nothing leaves the machine unless you point ``--host`` at something else
yourself.
"""

from __future__ import annotations

import asyncio

import typer
from rich.markup import escape as escape_markup

from nyxor.core.context import NyxorContext
from nyxor.core.interfaces import PluginMetadata
from nyxor.plugins.analyze.advisor import ask as ask_model
from nyxor.plugins.analyze.ollama import OllamaUnavailable
from nyxor.plugins.trends.store import TrendStore


async def _ask_once(context: NyxorContext, question: str, *, host: str, model: str) -> None:
    ai_config = context.config.ai
    history = TrendStore().all_domains()
    try:
        answer = await ask_model(
            question, history, host=host, model=model, timeout_seconds=ai_config.timeout_seconds
        )
    except OllamaUnavailable as exc:
        context.console.print(f"[bold red]No local model available[/bold red] ({exc}).")
        context.console.print(
            "[dim]Install Ollama (ollama.com) and run `ollama pull llama3.2` — "
            "nyx ask needs a model to answer with, there's no template fallback here.[/dim]"
        )
        raise typer.Exit(code=1) from exc
    context.console.print(escape_markup(answer))


async def _ask_repl(context: NyxorContext, *, host: str, model: str) -> None:
    console = context.console
    console.print(
        f"[dim]nyx ask — chatting with local model '{model}' about your recorded scan "
        "history. 'exit' or Ctrl+D/Ctrl+C to quit.[/dim]"
    )
    while True:
        try:
            question = input("ask> ")
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if not question.strip():
            continue
        if question.strip() in ("exit", "quit"):
            break
        await _ask_once(context, question, host=host, model=model)


def _ask(
    ctx: typer.Context,
    question: str | None = typer.Argument(
        None, help="A question about your scan history. Omit for an interactive prompt."
    ),
    host: str | None = typer.Option(
        None, "--host", help="Local (or Cloud) model server. Defaults to config ai.ollama_host."
    ),
    model: str | None = typer.Option(
        None, "--model", help="Model name. Defaults to config ai.model."
    ),
) -> None:
    """Ask a local model about your recorded audit/trend history."""
    context: NyxorContext = ctx.obj
    ai_config = context.config.ai
    host = host or ai_config.ollama_host
    model = model or ai_config.model

    if question:
        asyncio.run(_ask_once(context, question, host=host, model=model))
    else:
        asyncio.run(_ask_repl(context, host=host, model=model))


class AskPlugin:
    metadata = PluginMetadata(
        name="ask",
        description="Chat with a local model about your recorded scan history.",
        version="0.1.0",
        author="NYXOR",
        commands=("ask",),
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        app.command("ask")(_ask)


PLUGIN = AskPlugin()
