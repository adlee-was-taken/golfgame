"""Connection screen: server URL + optional login form."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Input, Static


class ConnectScreen(Screen):
    """Initial screen for connecting to the server."""

    def compose(self) -> ComposeResult:
        with Container(id="connect-container"):
            yield Static("GolfCards.club", id="connect-title")
            yield Static("Login (optional - leave blank to play as guest)")
            yield Input(placeholder="Username", id="input-username")
            yield Input(placeholder="Password", password=True, id="input-password")
            with Horizontal(id="connect-buttons"):
                yield Button("Connect as Guest", id="btn-guest", variant="default")
                yield Button("Login & Connect", id="btn-login", variant="primary")
            yield Static("", id="connect-status")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-guest":
            self._connect(login=False)
        elif event.button.id == "btn-login":
            self._connect(login=True)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Enter key in password field triggers login
        if event.input.id == "input-password":
            self._connect(login=True)

    def _connect(self, login: bool) -> None:
        self._set_status("Connecting...")
        self._disable_buttons()
        self.run_worker(self._do_connect(login), exclusive=True)

    async def _do_connect(self, login: bool) -> None:
        client = self.app.client

        try:
            if login:
                username = self.query_one("#input-username", Input).value.strip()
                password = self.query_one("#input-password", Input).value
                if not username or not password:
                    self._set_status("Username and password required")
                    self._enable_buttons()
                    return
                self._set_status("Logging in...")
                await client.login(username, password)
                self._set_status(f"Logged in as {client.username}")

            self._set_status("Connecting to WebSocket...")
            await client.connect()
            self._set_status("Connected!")

            # Move to lobby
            from tui_client.screens.lobby import LobbyScreen
            self.app.push_screen(LobbyScreen())

        except Exception as e:
            self._set_status(f"Error: {e}")
            self._enable_buttons()

    def _set_status(self, text: str) -> None:
        self.query_one("#connect-status", Static).update(text)

    def _disable_buttons(self) -> None:
        for btn in self.query("Button"):
            btn.disabled = True

    def _enable_buttons(self) -> None:
        for btn in self.query("Button"):
            btn.disabled = False
