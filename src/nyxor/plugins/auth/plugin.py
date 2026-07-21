"""The ``auth`` plugin: ``nyx auth login|approve|logout|whoami``.

``login`` runs a real OAuth 2.0 Device Authorization Grant (RFC 8628)
against a running NYXOR API (``nyx serve``, or NYXOR Cloud once it exists —
only ``--host`` changes). No password, no client secret embedded in the
CLI: it gets a short user code, waits for that code to be approved (in a
browser, or headlessly via ``nyx auth approve``), then saves the bearer
token it's issued. ``--token`` remains for pasting in a token obtained some
other way.
"""

from __future__ import annotations

import time

import httpx2 as httpx
import typer

from nyxor.core.context import NyxorContext
from nyxor.core.interfaces import PluginMetadata
from nyxor.core.qr import render_qr
from nyxor.plugins.auth.store import AuthStore, looks_like_a_token, mask_token

auth_app = typer.Typer(
    name="auth",
    help="Log in to a NYXOR API via OAuth2, or manage a saved token.",
    no_args_is_help=True,
)

DEFAULT_HOST = "http://127.0.0.1:8842"


def _connect_hint(host: str) -> str:
    return (
        f"[red]Couldn't reach {host}.[/red] Is the API running? "
        f"Start it with: [bold]nyx serve[/bold] (or pass --host)."
    )


@auth_app.command("login")
def login(
    ctx: typer.Context,
    host: str = typer.Option(DEFAULT_HOST, "--host", help="NYXOR API to authenticate against."),
    token: str | None = typer.Option(
        None, "--token", help="Skip the OAuth2 flow and save a token you already have."
    ),
) -> None:
    """Log in via OAuth2 device flow (default), or save a token with --token."""
    context: NyxorContext = ctx.obj

    if token is not None:
        token = token.strip()
        if not looks_like_a_token(token):
            context.console.print(
                "[red]That doesn't look like a token[/red] "
                "(need at least 16 characters, no spaces)."
            )
            raise typer.Exit(code=1)
        AuthStore().save(token)
        context.console.print(f"[green]Saved.[/green] Token stored as {mask_token(token)}.")
        return

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(f"{host}/oauth/device/code")
            resp.raise_for_status()
            device = resp.json()
    except httpx.ConnectError:
        context.console.print(_connect_hint(host))
        raise typer.Exit(code=1) from None
    except httpx.HTTPStatusError as exc:
        context.console.print(f"[red]{host} refused the request:[/red] {exc.response.text}")
        raise typer.Exit(code=1) from None

    context.console.print(f"[bold]Go to:[/bold] {device['verification_uri']}")
    context.console.print(f"[bold]Enter code:[/bold] {device['user_code']}")

    verification_uri_complete = device.get("verification_uri_complete")
    # Piping/redirecting this output (a log file, a CI job) would otherwise
    # fill it with unreadable block glyphs meant to be read by a camera,
    # not a human or a parser.
    if verification_uri_complete and context.console.is_terminal:
        context.console.print("\n[dim]Or scan with a phone:[/dim]\n")
        # markup/highlight off and soft_wrap on: this is a fixed grid of
        # block glyphs, not prose — Rich re-wrapping or re-coloring a line
        # would misalign it and make it unscannable.
        context.console.print(
            render_qr(verification_uri_complete), markup=False, highlight=False, soft_wrap=True
        )
        context.console.print()

    context.console.print(
        f"[dim]No browser handy? From another terminal: "
        f"nyx auth approve {device['user_code']} --host {host}[/dim]"
    )
    context.console.print("[dim]Waiting for approval...[/dim]")

    interval = float(device.get("interval", 3))
    deadline = time.monotonic() + float(device.get("expires_in", 600))

    with httpx.Client(timeout=10.0) as client:
        while time.monotonic() < deadline:
            time.sleep(interval)
            resp = client.post(f"{host}/oauth/token", params={"device_code": device["device_code"]})
            if resp.status_code == 200:
                access_token = resp.json()["access_token"]
                AuthStore().save(access_token)
                context.console.print(
                    f"[green]Logged in.[/green] Token stored as {mask_token(access_token)}."
                )
                return
            error = resp.json().get("detail", {})
            code = error.get("error") if isinstance(error, dict) else None
            if code == "authorization_pending":
                continue
            if code == "slow_down":
                interval += 2
                continue
            context.console.print(f"[red]Login failed:[/red] {error}")
            raise typer.Exit(code=1)

    context.console.print("[red]Timed out waiting for approval.[/red]")
    raise typer.Exit(code=1)


@auth_app.command("approve")
def approve(
    ctx: typer.Context,
    user_code: str,
    host: str = typer.Option(DEFAULT_HOST, "--host", help="NYXOR API the code was issued by."),
) -> None:
    """Approve a device login headlessly (no browser needed)."""
    context: NyxorContext = ctx.obj
    try:
        resp = httpx.post(
            f"{host}/oauth/device/approve", params={"user_code": user_code}, timeout=10.0
        )
    except httpx.ConnectError:
        context.console.print(_connect_hint(host))
        raise typer.Exit(code=1) from None

    if resp.status_code == 403:
        context.console.print(
            "[red]Couldn't approve:[/red] the API only accepts device-flow approval from "
            "localhost. If it's running on another host, approve over an SSH tunnel or from "
            "a shell on that host."
        )
        raise typer.Exit(code=1)
    if resp.status_code != 200:
        detail = resp.json().get("detail", resp.text)
        context.console.print(f"[red]Couldn't approve:[/red] {detail}")
        raise typer.Exit(code=1)
    context.console.print(f"[green]Approved.[/green] {user_code} can now finish logging in.")


@auth_app.command("logout")
def logout(ctx: typer.Context) -> None:
    """Delete the locally-saved API token."""
    context: NyxorContext = ctx.obj
    if AuthStore().clear():
        context.console.print("[green]Logged out.[/green] Token removed.")
    else:
        context.console.print("[dim]Not logged in — nothing to remove.[/dim]")


@auth_app.command("whoami")
def whoami(ctx: typer.Context) -> None:
    """Show whether a token is saved, and where."""
    context: NyxorContext = ctx.obj
    record = AuthStore().load()
    if record is None:
        context.console.print("[dim]Not logged in.[/dim] Run `nyx auth login` to authenticate.")
        raise typer.Exit(code=1)

    context.console.print(f"Token:    {mask_token(record['token'])}")
    context.console.print(f"Saved at: {record['saved_at']}")
    context.console.print(f"Location: {AuthStore().path}")


class AuthPlugin:
    metadata = PluginMetadata(
        name="auth",
        description="OAuth2 device-flow login to a NYXOR API, plus token management.",
        version="0.2.0",
        author="NYXOR",
        commands=("login", "approve", "logout", "whoami"),
        category="Setup & Config",
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        app.add_typer(auth_app, rich_help_panel=self.metadata.category)


PLUGIN = AuthPlugin()
