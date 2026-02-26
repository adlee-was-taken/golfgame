"""Main Textual App for the Golf TUI client."""

from __future__ import annotations

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
        ("q", "quit_app", ""),
    ]

    def __init__(self, server: str, use_tls: bool = True):
        super().__init__()
        self.client = GameClient(server, use_tls)
        self.client._app = self
        self.player_id: str | None = None

    def compose(self) -> ComposeResult:
        yield KeymapBar(id="keymap-bar")

    def on_mount(self) -> None:
        from tui_client.screens.splash import SplashScreen
        self.push_screen(SplashScreen())
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
        """Escape goes back — delegated to the active screen."""
        handler = getattr(self.screen, "handle_escape", None)
        if handler:
            handler()

    def action_quit_app(self) -> None:
        """[q] quits the app. Immediate on login, confirmation elsewhere."""
        # Don't capture q when typing in input fields
        focused = self.focused
        if focused and hasattr(focused, "value"):
            return
        # Don't handle here on game screen (game has its own q binding)
        if self.screen.__class__.__name__ == "GameScreen":
            return

        screen_name = self.screen.__class__.__name__
        if screen_name == "ConnectScreen":
            self.exit()
        else:
            from tui_client.screens.confirm import ConfirmScreen
            self.push_screen(
                ConfirmScreen("Quit GolfCards?"),
                callback=self._on_quit_confirm,
            )

    def _on_quit_confirm(self, confirmed: bool) -> None:
        if confirmed:
            self.exit()

    def _update_keymap(self) -> None:
        """Update the keymap bar based on current screen."""
        screen_name = self.screen.__class__.__name__
        keymap = getattr(self.screen, "KEYMAP_HINT", None)
        if keymap:
            text = keymap
        elif screen_name == "ConnectScreen":
            text = "[Tab] Navigate  [Enter] Submit  [q] Quit"
        elif screen_name == "LobbyScreen":
            text = "[Esc] Back  [Tab] Navigate  [Enter] Create/Join  [q] Quit"
        else:
            text = "[q] Quit"
        try:
            self.query_one("#keymap-bar", KeymapBar).update(text)
        except Exception:
            pass

    def set_keymap(self, text: str) -> None:
        """Allow screens to update the keymap bar dynamically."""
        try:
            self.query_one("#keymap-bar", KeymapBar).update(text)
        except Exception:
            pass

    async def on_unmount(self) -> None:
        await self.client.disconnect()
