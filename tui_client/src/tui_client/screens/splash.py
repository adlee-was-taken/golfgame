"""Splash screen: check for saved session token before showing login."""

from __future__ import annotations

import asyncio

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Static


_TITLE = (
    "⛳🏌️ [bold]GolfCards.club[/bold] "
    "[bold #aaaaaa]♠[/bold #aaaaaa]"
    "[bold #cc0000]♥[/bold #cc0000]"
    "[bold #aaaaaa]♣[/bold #aaaaaa]"
    "[bold #cc0000]♦[/bold #cc0000]"
)


class SplashScreen(Screen):
    """Shows session check status, then routes to lobby or login."""

    def compose(self) -> ComposeResult:
        with Container(id="connect-container"):
            yield Static(_TITLE, id="connect-title")
            yield Static("", id="splash-status")

        with Horizontal(classes="screen-footer"):
            yield Static("", classes="screen-footer-left")
            yield Static("\\[esc]\\[esc] quit", classes="screen-footer-right")

    def on_mount(self) -> None:
        self.run_worker(self._check_session(), exclusive=True)

    async def _check_session(self) -> None:
        from tui_client.client import GameClient

        status = self.query_one("#splash-status", Static)
        status.update("Checking for session token...")
        await asyncio.sleep(0.5)

        session = GameClient.load_session()
        if not session:
            status.update("Checking for session token... [bold yellow]NONE FOUND[/bold yellow]")
            await asyncio.sleep(0.8)
            self._go_to_login()
            return

        client = self.app.client
        client.restore_session(session)
        if await client.verify_token():
            status.update(f"Checking for session token... [bold green]SUCCESS[/bold green]")
            await asyncio.sleep(0.8)
            await self._go_to_lobby()
        else:
            GameClient.clear_session()
            status.update("Checking for session token... [bold red]EXPIRED[/bold red]")
            await asyncio.sleep(0.8)
            self._go_to_login()

    def _go_to_login(self) -> None:
        from tui_client.screens.connect import ConnectScreen

        self.app.switch_screen(ConnectScreen())

    async def _go_to_lobby(self) -> None:
        client = self.app.client
        await client.connect()
        client.save_session()
        from tui_client.screens.lobby import LobbyScreen

        self.app.switch_screen(LobbyScreen())
