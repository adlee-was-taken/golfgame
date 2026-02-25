"""Connection screen: login or sign up form."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Static

_TITLE = (
    "⛳🏌️ [bold]GolfCards.club[/bold] "
    "[bold #aaaaaa]♠[/bold #aaaaaa]"
    "[bold #cc0000]♥[/bold #cc0000]"
    "[bold #aaaaaa]♣[/bold #aaaaaa]"
    "[bold #cc0000]♦[/bold #cc0000]"
)


class ConnectScreen(Screen):
    """Initial screen for logging in or signing up."""

    def __init__(self):
        super().__init__()
        self._mode: str = "login"  # "login" or "signup"

    def compose(self) -> ComposeResult:
        with Container(id="connect-container"):
            yield Static(_TITLE, id="connect-title")

            # Login form
            with Vertical(id="login-form"):
                yield Static("Log in to play")
                yield Input(placeholder="Username", id="input-username")
                yield Input(placeholder="Password", password=True, id="input-password")
                with Horizontal(id="connect-buttons"):
                    yield Button("Login", id="btn-login", variant="primary")
                yield Button(
                    "No account? [bold cyan]Sign Up[/bold cyan]",
                    id="btn-toggle-signup",
                    variant="default",
                )

            # Signup form
            with Vertical(id="signup-form"):
                yield Static("Create an account")
                yield Input(placeholder="Invite Code", id="input-invite-code")
                yield Input(placeholder="Username", id="input-signup-username")
                yield Input(placeholder="Email (optional)", id="input-signup-email")
                yield Input(
                    placeholder="Password (min 8 chars)",
                    password=True,
                    id="input-signup-password",
                )
                with Horizontal(id="signup-buttons"):
                    yield Button("Sign Up", id="btn-signup", variant="primary")
                yield Button(
                    "Have an account? [bold cyan]Log In[/bold cyan]",
                    id="btn-toggle-login",
                    variant="default",
                )

            yield Static("", id="connect-status")

    def on_mount(self) -> None:
        self._update_form_visibility()

    def _update_form_visibility(self) -> None:
        try:
            self.query_one("#login-form").display = self._mode == "login"
            self.query_one("#signup-form").display = self._mode == "signup"
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-login":
            self._do_login()
        elif event.button.id == "btn-signup":
            self._do_signup()
        elif event.button.id == "btn-toggle-signup":
            self._mode = "signup"
            self._set_status("")
            self._update_form_visibility()
        elif event.button.id == "btn-toggle-login":
            self._mode = "login"
            self._set_status("")
            self._update_form_visibility()

    def key_escape(self) -> None:
        """Escape goes back to login if on signup form."""
        if self._mode == "signup":
            self._mode = "login"
            self._set_status("")
            self._update_form_visibility()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "input-password":
            self._do_login()
        elif event.input.id == "input-signup-password":
            self._do_signup()

    def _do_login(self) -> None:
        self._set_status("Logging in...")
        self._disable_buttons()
        self.run_worker(self._login_flow(), exclusive=True)

    def _do_signup(self) -> None:
        self._set_status("Signing up...")
        self._disable_buttons()
        self.run_worker(self._signup_flow(), exclusive=True)

    async def _login_flow(self) -> None:
        client = self.app.client
        try:
            username = self.query_one("#input-username", Input).value.strip()
            password = self.query_one("#input-password", Input).value
            if not username or not password:
                self._set_status("Username and password required")
                self._enable_buttons()
                return
            await client.login(username, password)
            self._set_status(f"Logged in as {client.username}")
            await self._connect_ws()
        except Exception as e:
            self._set_status(f"[red]{e}[/red]")
            self._enable_buttons()

    async def _signup_flow(self) -> None:
        client = self.app.client
        try:
            invite = self.query_one("#input-invite-code", Input).value.strip()
            username = self.query_one("#input-signup-username", Input).value.strip()
            email = self.query_one("#input-signup-email", Input).value.strip()
            password = self.query_one("#input-signup-password", Input).value
            if not username or not password:
                self._set_status("Username and password required")
                self._enable_buttons()
                return
            if len(password) < 8:
                self._set_status("Password must be at least 8 characters")
                self._enable_buttons()
                return
            await client.register(username, password, invite_code=invite, email=email)
            self._set_status(f"Account created! Welcome, {client.username}")
            await self._connect_ws()
        except Exception as e:
            self._set_status(f"[red]{e}[/red]")
            self._enable_buttons()

    async def _connect_ws(self) -> None:
        client = self.app.client
        self._set_status("Connecting...")
        await client.connect()
        self._set_status("Connected!")
        from tui_client.screens.lobby import LobbyScreen
        self.app.push_screen(LobbyScreen())

    def _set_status(self, text: str) -> None:
        self.query_one("#connect-status", Static).update(text)

    def _disable_buttons(self) -> None:
        for btn in self.query("Button"):
            btn.disabled = True

    def _enable_buttons(self) -> None:
        for btn in self.query("Button"):
            btn.disabled = False
