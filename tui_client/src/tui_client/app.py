"""Main Textual App for the Golf TUI client."""

from __future__ import annotations

import time

from textual.app import App, ComposeResult
from textual.message import Message
from textual.widgets import Static

from tui_client.client import GameClient


class ServerMessage(Message):
    """A message received from the game server."""

    def __init__(self, data: dict) -> None:
        super().__init__()
        self.msg_type: str = data.get("type", "")
        self.data: dict = data


class KeymapBar(Static):
    """Bottom bar showing available keys for the current context."""

    DEFAULT_CSS = """
    KeymapBar {
        dock: bottom;
        height: 1;
        background: #1a1a2e;
        color: #888888;
        padding: 0 1;
    }
    """


class GolfApp(App):
    """Golf Card Game TUI Application."""

    TITLE = "GolfCards.club"
    CSS_PATH = "styles.tcss"

    BINDINGS = [
        ("escape", "esc_pressed", ""),
    ]

    def __init__(self, server: str, use_tls: bool = True):
        super().__init__()
        self.client = GameClient(server, use_tls)
        self.client._app = self
        self.player_id: str | None = None
        self._last_escape: float = 0.0

    def compose(self) -> ComposeResult:
        yield KeymapBar(id="keymap-bar")

    def on_mount(self) -> None:
        from tui_client.screens.connect import ConnectScreen
        self.push_screen(ConnectScreen())
        self._update_keymap()

    def on_screen_resume(self) -> None:
        self._update_keymap()

    def post_server_message(self, data: dict) -> None:
        """Called from GameClient listener to inject server messages."""
        msg = ServerMessage(data)
        self.call_later(self._route_server_message, msg)

    def _route_server_message(self, msg: ServerMessage) -> None:
        """Forward a server message to the active screen."""
        screen = self.screen
        handler = getattr(screen, "on_server_message", None)
        if handler:
            handler(msg)

    def action_esc_pressed(self) -> None:
        """Single escape goes back, double-escape quits."""
        now = time.monotonic()
        if now - self._last_escape < 0.5:
            self.exit()
        else:
            self._last_escape = now
            # Let the active screen handle single escape
            handler = getattr(self.screen, "handle_escape", None)
            if handler:
                handler()

    def _update_keymap(self) -> None:
        """Update the keymap bar based on current screen."""
        screen_name = self.screen.__class__.__name__
        keymap = getattr(self.screen, "KEYMAP_HINT", None)
        if keymap:
            text = keymap
        elif screen_name == "ConnectScreen":
            text = "[Tab] Navigate  [Enter] Submit  [Esc][Esc] Quit"
        elif screen_name == "LobbyScreen":
            text = "[Esc] Back  [Tab] Navigate  [Enter] Submit  [Esc][Esc] Quit"
        else:
            text = "[Esc][Esc] Quit"
        try:
            self.query_one("#keymap-bar", KeymapBar).update(text)
        except Exception:
            pass

    def set_keymap(self, text: str) -> None:
        """Allow screens to update the keymap bar dynamically.

        Always appends [Esc Esc] Quit on the right for discoverability.
        """
        if "[Esc]" not in text.replace("[Esc][Esc]", ""):
            text = f"{text}  [Esc][Esc] Quit"
        try:
            self.query_one("#keymap-bar", KeymapBar).update(text)
        except Exception:
            pass

    async def on_unmount(self) -> None:
        await self.client.disconnect()
