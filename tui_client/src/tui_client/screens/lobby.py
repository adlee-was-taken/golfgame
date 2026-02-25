"""Lobby screen: create/join room, add CPUs, configure, start game."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    Collapsible,
    Input,
    Label,
    OptionList,
    Select,
    Static,
    Switch,
)
from textual.widgets.option_list import Option


DECK_PRESETS = {
    "classic": ["red", "blue", "gold"],
    "ninja": ["green", "purple", "orange"],
    "ocean": ["blue", "teal", "cyan"],
    "forest": ["green", "gold", "brown"],
    "sunset": ["orange", "red", "purple"],
    "berry": ["purple", "pink", "red"],
    "neon": ["pink", "cyan", "green"],
    "royal": ["purple", "gold", "red"],
    "earth": ["brown", "green", "gold"],
    "all-red": ["red", "red", "red"],
    "all-blue": ["blue", "blue", "blue"],
    "all-green": ["green", "green", "green"],
}


class LobbyScreen(Screen):
    """Room creation, joining, and pre-game configuration."""

    BINDINGS = [
        ("plus_sign", "add_cpu", "Add CPU"),
        ("equals_sign", "add_cpu", "Add CPU"),
        ("hyphen_minus", "remove_cpu", "Remove CPU"),
        ("enter", "start_or_create", "Start/Create"),
    ]

    def __init__(self):
        super().__init__()
        self._room_code: str | None = None
        self._player_id: str | None = None
        self._is_host: bool = False
        self._players: list[dict] = []
        self._in_room: bool = False

    def compose(self) -> ComposeResult:
        with Container(id="lobby-container"):
            yield Static("[bold]GolfCards.club[/bold]", id="lobby-title")
            yield Static("", id="room-info")

            # Pre-room: join/create
            with Vertical(id="pre-room"):
                yield Input(placeholder="Room code (leave blank to create new)", id="input-room-code")
                with Horizontal(id="pre-room-buttons"):
                    yield Button("Create Room", id="btn-create", variant="primary")
                    yield Button("Join Room", id="btn-join", variant="default")

            # In-room: player list + controls + settings
            with Vertical(id="in-room"):
                yield Static("[bold]Players[/bold]", id="player-list-label")
                yield Static("", id="player-list")

                # CPU controls: compact [+] [-]
                with Horizontal(id="cpu-controls"):
                    yield Label("CPU:", id="cpu-label")
                    yield Button("+", id="btn-cpu-add", variant="default")
                    yield Button("−", id="btn-cpu-remove", variant="warning")
                    yield Button("?", id="btn-cpu-random", variant="default")

                # CPU profile picker (hidden by default)
                yield OptionList(id="cpu-profile-list")

                # Host settings (collapsible sections)
                with Vertical(id="host-settings"):
                    with Collapsible(title="Game Settings", collapsed=True, id="coll-game"):
                        with Horizontal(classes="setting-row"):
                            yield Label("Holes")
                            yield Select(
                                [(str(v), v) for v in (1, 3, 9, 18)],
                                value=9,
                                id="sel-rounds",
                                allow_blank=False,
                            )
                        with Horizontal(classes="setting-row"):
                            yield Label("Decks")
                            yield Select(
                                [(str(v), v) for v in (1, 2, 3)],
                                value=1,
                                id="sel-decks",
                                allow_blank=False,
                            )
                        with Horizontal(classes="setting-row"):
                            yield Label("Initial Flips")
                            yield Select(
                                [(str(v), v) for v in (0, 1, 2)],
                                value=2,
                                id="sel-initial-flips",
                                allow_blank=False,
                            )
                        with Horizontal(classes="setting-row"):
                            yield Label("Flip Mode")
                            yield Select(
                                [("Never", "never"), ("Always", "always"), ("Endgame", "endgame")],
                                value="never",
                                id="sel-flip-mode",
                                allow_blank=False,
                            )

                    with Collapsible(title="House Rules", collapsed=True, id="coll-rules"):
                        # Joker variant
                        with Horizontal(classes="setting-row"):
                            yield Label("Jokers")
                            yield Select(
                                [
                                    ("None", "none"),
                                    ("Standard (−2)", "standard"),
                                    ("Lucky Swing (−5)", "lucky_swing"),
                                    ("Eagle Eye (+2/−4)", "eagle_eye"),
                                ],
                                value="none",
                                id="sel-jokers",
                                allow_blank=False,
                            )

                        # Scoring rules
                        yield Static("[bold]Scoring[/bold]", classes="rules-header")
                        with Horizontal(classes="rule-row"):
                            yield Label("Super Kings (K = −2)")
                            yield Switch(id="sw-super_kings")
                        with Horizontal(classes="rule-row"):
                            yield Label("Ten Penny (10 = 1)")
                            yield Switch(id="sw-ten_penny")
                        with Horizontal(classes="rule-row"):
                            yield Label("One-Eyed Jacks (J♥/J♠ = 0)")
                            yield Switch(id="sw-one_eyed_jacks")
                        with Horizontal(classes="rule-row"):
                            yield Label("Negative Pairs Keep Value")
                            yield Switch(id="sw-negative_pairs_keep_value")
                        with Horizontal(classes="rule-row"):
                            yield Label("Four of a Kind (−20)")
                            yield Switch(id="sw-four_of_a_kind")

                        # Knock & Endgame
                        yield Static("[bold]Knock & Endgame[/bold]", classes="rules-header")
                        with Horizontal(classes="rule-row"):
                            yield Label("Knock Penalty (+10)")
                            yield Switch(id="sw-knock_penalty")
                        with Horizontal(classes="rule-row"):
                            yield Label("Knock Bonus (−5)")
                            yield Switch(id="sw-knock_bonus")
                        with Horizontal(classes="rule-row"):
                            yield Label("Knock Early")
                            yield Switch(id="sw-knock_early")
                        with Horizontal(classes="rule-row"):
                            yield Label("Flip as Action")
                            yield Switch(id="sw-flip_as_action")

                        # Bonuses & Penalties
                        yield Static("[bold]Bonuses & Penalties[/bold]", classes="rules-header")
                        with Horizontal(classes="rule-row"):
                            yield Label("Underdog Bonus (−3)")
                            yield Switch(id="sw-underdog_bonus")
                        with Horizontal(classes="rule-row"):
                            yield Label("Tied Shame (+5)")
                            yield Switch(id="sw-tied_shame")
                        with Horizontal(classes="rule-row"):
                            yield Label("Blackjack (21→0)")
                            yield Switch(id="sw-blackjack")
                        with Horizontal(classes="rule-row"):
                            yield Label("Wolfpack")
                            yield Switch(id="sw-wolfpack")

                    with Collapsible(title="Deck Style", collapsed=True, id="coll-deck"):
                        with Horizontal(classes="setting-row"):
                            yield Select(
                                [(name.replace("-", " ").title(), name) for name in DECK_PRESETS],
                                value="classic",
                                id="sel-deck-style",
                                allow_blank=False,
                            )
                            yield Static(
                                self._render_deck_preview("classic"),
                                id="deck-preview",
                            )

                yield Button("Start Game", id="btn-start", variant="success")

            yield Static("", id="lobby-status")

    def on_mount(self) -> None:
        self._update_visibility()
        self._update_keymap()

    def reset_to_pre_room(self) -> None:
        """Reset lobby back to create/join state after leaving a game."""
        self._room_code = None
        self._player_id = None
        self._is_host = False
        self._players = []
        self._in_room = False
        self._set_room_info("")
        self._set_status("")
        try:
            self.query_one("#input-room-code", Input).value = ""
            self.query_one("#player-list", Static).update("")
        except Exception:
            pass
        self._update_visibility()
        self._update_keymap()

    def _update_visibility(self) -> None:
        try:
            self.query_one("#pre-room").display = not self._in_room
            self.query_one("#in-room").display = self._in_room
            # Host-only controls
            self.query_one("#cpu-controls").display = self._in_room and self._is_host
            self.query_one("#host-settings").display = self._in_room and self._is_host
            self.query_one("#btn-start").display = self._in_room and self._is_host
        except Exception:
            pass

    def _update_keymap(self) -> None:
        try:
            if self._in_room and self._is_host:
                self.app.set_keymap("[Esc] Leave  [+] Add CPU  [−] Remove  [Enter] Start  [Esc][Esc] Quit")
            elif self._in_room:
                self.app.set_keymap("[Esc] Leave  Waiting for host...  [Esc][Esc] Quit")
            else:
                self.app.set_keymap("[Esc] Back  [Tab] Navigate  [Enter] Create/Join  [Esc][Esc] Quit")
        except Exception:
            pass

    def handle_escape(self) -> None:
        """Single escape: leave room → pre-room, or pre-room → back to connect."""
        if self._in_room:
            self.run_worker(self._send("leave_game"))
            self.reset_to_pre_room()
        else:
            self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-create":
            self._create_room()
        elif event.button.id == "btn-join":
            self._join_room()
        elif event.button.id == "btn-cpu-add":
            self._show_cpu_picker()
        elif event.button.id == "btn-cpu-remove":
            self._remove_cpu()
        elif event.button.id == "btn-cpu-random":
            self._add_random_cpu()
        elif event.button.id == "btn-start":
            self._start_game()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "input-room-code":
            code = event.value.strip()
            if code:
                self._join_room()
            else:
                self._create_room()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "cpu-profile-list":
            profile_name = str(event.option.id) if event.option.id else ""
            self.run_worker(self._send("add_cpu", profile_name=profile_name))
            event.option_list.display = False

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "sel-deck-style" and event.value is not None:
            try:
                preview = self.query_one("#deck-preview", Static)
                preview.update(self._render_deck_preview(str(event.value)))
            except Exception:
                pass

    def action_add_cpu(self) -> None:
        if self._in_room and self._is_host:
            self._show_cpu_picker()

    def action_remove_cpu(self) -> None:
        if self._in_room and self._is_host:
            self._remove_cpu()

    def action_start_or_create(self) -> None:
        if self._in_room and self._is_host:
            self._start_game()
        elif not self._in_room:
            code = self.query_one("#input-room-code", Input).value.strip()
            if code:
                self._join_room()
            else:
                self._create_room()

    def _create_room(self) -> None:
        player_name = self.app.client.username or "Player"
        self.run_worker(self._send("create_room", player_name=player_name))

    def _join_room(self) -> None:
        code = self.query_one("#input-room-code", Input).value.strip().upper()
        if not code:
            self._set_status("Enter a room code to join")
            return
        player_name = self.app.client.username or "Player"
        self.run_worker(self._send("join_room", room_code=code, player_name=player_name))

    @staticmethod
    def _render_deck_preview(preset_name: str) -> str:
        """Render mini card-back swatches for a deck color preset."""
        from tui_client.widgets.card import BACK_COLORS

        colors = DECK_PRESETS.get(preset_name, ["red", "blue", "gold"])
        # Show unique colors only (e.g. all-red shows one wider swatch)
        seen: list[str] = []
        for c in colors:
            if c not in seen:
                seen.append(c)

        parts: list[str] = []
        for color_name in seen:
            hex_color = BACK_COLORS.get(color_name, BACK_COLORS["red"])
            parts.append(f"[{hex_color}]░░░[/]")
        return " ".join(parts)

    def _add_random_cpu(self) -> None:
        """Add a random CPU (server picks the profile)."""
        self.run_worker(self._send("add_cpu"))

    def _show_cpu_picker(self) -> None:
        """Request CPU profiles from server and show picker."""
        self.run_worker(self._send("get_cpu_profiles"))

    def _handle_cpu_profiles(self, data: dict) -> None:
        """Populate and show the CPU profile option list."""
        profiles = data.get("profiles", [])
        option_list = self.query_one("#cpu-profile-list", OptionList)
        option_list.clear_options()
        for p in profiles:
            name = p.get("name", "?")
            style = p.get("style", "")
            option_list.add_option(Option(f"{name} — {style}", id=name))
        option_list.display = True
        option_list.focus()

    def _remove_cpu(self) -> None:
        self.run_worker(self._send("remove_cpu"))

    def _collect_settings(self) -> dict:
        """Read all Select/Switch values and return kwargs for start_game."""
        settings: dict = {}

        try:
            settings["rounds"] = self.query_one("#sel-rounds", Select).value
            settings["decks"] = self.query_one("#sel-decks", Select).value
            settings["initial_flips"] = self.query_one("#sel-initial-flips", Select).value
            settings["flip_mode"] = self.query_one("#sel-flip-mode", Select).value
        except Exception:
            settings.setdefault("rounds", 9)
            settings.setdefault("decks", 1)
            settings.setdefault("initial_flips", 2)
            settings.setdefault("flip_mode", "never")

        # Joker variant → booleans
        try:
            joker_mode = self.query_one("#sel-jokers", Select).value
        except Exception:
            joker_mode = "none"

        settings["use_jokers"] = joker_mode != "none"
        settings["lucky_swing"] = joker_mode == "lucky_swing"
        settings["eagle_eye"] = joker_mode == "eagle_eye"

        # Boolean house rules from switches
        rule_ids = [
            "super_kings", "ten_penny", "one_eyed_jacks",
            "negative_pairs_keep_value", "four_of_a_kind",
            "knock_penalty", "knock_bonus", "knock_early", "flip_as_action",
            "underdog_bonus", "tied_shame", "blackjack", "wolfpack",
        ]
        for rule_id in rule_ids:
            try:
                settings[rule_id] = self.query_one(f"#sw-{rule_id}", Switch).value
            except Exception:
                settings[rule_id] = False

        # Deck colors from preset
        try:
            preset = self.query_one("#sel-deck-style", Select).value
            settings["deck_colors"] = DECK_PRESETS.get(preset, ["red", "blue", "gold"])
        except Exception:
            settings["deck_colors"] = ["red", "blue", "gold"]

        return settings

    def _start_game(self) -> None:
        self._set_status("Starting game...")
        settings = self._collect_settings()
        self.run_worker(self._send("start_game", **settings))

    async def _send(self, msg_type: str, **kwargs) -> None:
        try:
            await self.app.client.send(msg_type, **kwargs)
        except Exception as e:
            self._set_status(f"Error: {e}")

    def on_server_message(self, event) -> None:
        handler = getattr(self, f"_handle_{event.msg_type}", None)
        if handler:
            handler(event.data)

    def _handle_room_created(self, data: dict) -> None:
        self._room_code = data.get("room_code", "")
        self._player_id = data.get("player_id", "")
        self.app.player_id = self._player_id
        self._is_host = True
        self._in_room = True
        self._set_room_info(f"Room [bold]{self._room_code}[/bold]  (You are host)")
        self._set_status("Add CPU opponents, then start when ready.")
        self._update_visibility()
        self._update_keymap()

    def _handle_room_joined(self, data: dict) -> None:
        self._room_code = data.get("room_code", "")
        self._player_id = data.get("player_id", "")
        self.app.player_id = self._player_id
        self._in_room = True
        self._set_room_info(f"Room [bold]{self._room_code}[/bold]")
        self._set_status("Waiting for host to start the game.")
        self._update_visibility()
        self._update_keymap()

    def _handle_player_joined(self, data: dict) -> None:
        self._players = data.get("players", [])
        self._refresh_player_list()

    def _handle_game_started(self, data: dict) -> None:
        from tui_client.screens.game import GameScreen
        game_state = data.get("game_state", {})
        self.app.push_screen(GameScreen(game_state, self._is_host))

    def _handle_error(self, data: dict) -> None:
        self._set_status(f"[red]Error: {data.get('message', 'Unknown error')}[/red]")

    def _refresh_player_list(self) -> None:
        lines = []
        for i, p in enumerate(self._players, 1):
            name = p.get("name", "?")
            tags = []
            if p.get("is_host"):
                tags.append("[bold cyan]Host[/bold cyan]")
            if p.get("is_cpu"):
                tags.append("[yellow]CPU[/yellow]")
            suffix = f"  {' '.join(tags)}" if tags else ""
            lines.append(f"  {i}. {name}{suffix}")
        self.query_one("#player-list", Static).update("\n".join(lines) if lines else "  (empty)")

    def _set_room_info(self, text: str) -> None:
        self.query_one("#room-info", Static).update(text)

    def _set_status(self, text: str) -> None:
        self.query_one("#lobby-status", Static).update(text)
