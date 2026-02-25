"""Main game board screen with keyboard actions and message dispatch."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.events import Resize
from textual.screen import Screen
from textual.widgets import Static

from tui_client.models import GameState, PlayerData
from tui_client.widgets.hand import HandWidget
from tui_client.widgets.play_area import PlayAreaWidget
from tui_client.widgets.scoreboard import ScoreboardScreen
from tui_client.widgets.status_bar import StatusBarWidget


class GameScreen(Screen):
    """Main game board with card display and keyboard controls."""

    BINDINGS = [
        ("d", "draw_deck", "Draw from deck"),
        ("s", "pick_discard", "Pick from discard"),
        ("1", "select_1", "Position 1"),
        ("2", "select_2", "Position 2"),
        ("3", "select_3", "Position 3"),
        ("4", "select_4", "Position 4"),
        ("5", "select_5", "Position 5"),
        ("6", "select_6", "Position 6"),
        ("x", "discard_held", "Discard held card"),
        ("c", "cancel_draw", "Cancel draw"),
        ("f", "flip_mode", "Flip card"),
        ("p", "skip_flip", "Skip flip"),
        ("k", "knock_early", "Knock early"),
        ("n", "next_round", "Next round"),
    ]

    def __init__(self, initial_state: dict, is_host: bool = False):
        super().__init__()
        self._state = GameState.from_dict(initial_state)
        self._is_host = is_host
        self._player_id: str = ""
        self._awaiting_flip = False
        self._awaiting_initial_flip = False
        self._initial_flip_positions: list[int] = []
        self._can_flip_optional = False
        self._term_width: int = 80
        self._term_height: int = 24

    def compose(self) -> ComposeResult:
        yield StatusBarWidget(id="status-bar")
        with Container(id="game-content"):
            yield Static("", id="opponents-area")
            with Horizontal(id="play-area-row"):
                yield PlayAreaWidget(id="play-area")
            yield Static("", id="local-hand-label")
            yield HandWidget(id="local-hand")
            yield Static("", id="action-bar")

    def on_mount(self) -> None:
        self._player_id = self.app.player_id or ""
        self._term_width = self.app.size.width
        self._term_height = self.app.size.height
        self._full_refresh()

    def on_resize(self, event: Resize) -> None:
        self._term_width = event.size.width
        self._term_height = event.size.height
        self._full_refresh()

    def on_server_message(self, event) -> None:
        """Dispatch server messages to handlers."""
        handler = getattr(self, f"_handle_{event.msg_type}", None)
        if handler:
            handler(event.data)

    # ------------------------------------------------------------------
    # Server message handlers
    # ------------------------------------------------------------------

    def _handle_game_state(self, data: dict) -> None:
        state_data = data.get("game_state", data)
        self._state = GameState.from_dict(state_data)
        self._full_refresh()

    def _handle_your_turn(self, data: dict) -> None:
        self._awaiting_flip = False
        self._refresh_action_bar()

    def _handle_card_drawn(self, data: dict) -> None:
        from tui_client.models import CardData

        card = CardData.from_dict(data.get("card", {}))
        source = data.get("source", "deck")
        rank = card.display_rank
        suit = card.display_suit

        if source == "discard":
            self._set_action(
                f"Holding {rank}{suit} — Choose spot \[1] thru \[6] or \[c]ancel"
            )
            self._set_keymap("[1-6] Swap  [C] Cancel")
        else:
            self._set_action(
                f"Holding {rank}{suit} — Choose spot \[1] thru \[6] or \[x] to discard"
            )
            self._set_keymap("[1-6] Swap  [X] Discard")

    def _handle_can_flip(self, data: dict) -> None:
        self._awaiting_flip = True
        optional = data.get("optional", False)
        self._can_flip_optional = optional
        if optional:
            self._set_action("Keyboard: Flip a card \[1] thru \[6] or \[p] to skip")
            self._set_keymap("[1-6] Flip card  [P] Skip")
        else:
            self._set_action("Keyboard: Flip a face-down card \[1] thru \[6]")
            self._set_keymap("[1-6] Flip card")

    def _handle_round_over(self, data: dict) -> None:
        scores = data.get("scores", [])
        round_num = data.get("round", 1)
        total_rounds = data.get("total_rounds", 1)

        self.app.push_screen(
            ScoreboardScreen(
                scores=scores,
                title=f"Round {round_num} Complete",
                is_game_over=False,
                is_host=self._is_host,
                round_num=round_num,
                total_rounds=total_rounds,
            ),
            callback=self._on_scoreboard_dismiss,
        )

    def _handle_game_over(self, data: dict) -> None:
        scores = data.get("final_scores", [])

        self.app.push_screen(
            ScoreboardScreen(
                scores=scores,
                title="Game Over!",
                is_game_over=True,
                is_host=self._is_host,
            ),
            callback=self._on_scoreboard_dismiss,
        )

    def _handle_round_started(self, data: dict) -> None:
        state_data = data.get("game_state", data)
        self._state = GameState.from_dict(state_data)
        self._awaiting_flip = False
        self._awaiting_initial_flip = False
        self._initial_flip_positions = []
        self._full_refresh()

    def _handle_game_ended(self, data: dict) -> None:
        reason = data.get("reason", "Game ended")
        self._set_action(f"{reason}. Press Escape to return to lobby.")

    def _handle_error(self, data: dict) -> None:
        msg = data.get("message", "Unknown error")
        self._set_action(f"[red]Error: {msg}[/red]")

    def _handle_connection_closed(self, data: dict) -> None:
        self._set_action("[red]Connection lost.[/red]")

    def _on_scoreboard_dismiss(self, result: str | None) -> None:
        if result == "next_round":
            self.run_worker(self._send("next_round"))
        elif result == "lobby":
            self.run_worker(self._send("leave_game"))
            self.app.pop_screen()

    # ------------------------------------------------------------------
    # Click handlers (from widget messages)
    # ------------------------------------------------------------------

    def on_hand_widget_card_clicked(self, event: HandWidget.CardClicked) -> None:
        """Handle click on a card in the local hand."""
        self._select_position(event.position)

    def on_play_area_widget_deck_clicked(self, event: PlayAreaWidget.DeckClicked) -> None:
        """Handle click on the deck."""
        self.action_draw_deck()

    def on_play_area_widget_discard_clicked(self, event: PlayAreaWidget.DiscardClicked) -> None:
        """Handle click on the discard pile."""
        self.action_pick_discard()

    # ------------------------------------------------------------------
    # Keyboard actions
    # ------------------------------------------------------------------

    def action_draw_deck(self) -> None:
        if not self._is_my_turn() or self._state.has_drawn_card:
            return
        self.run_worker(self._send("draw", source="deck"))

    def action_pick_discard(self) -> None:
        if not self._is_my_turn() or self._state.has_drawn_card:
            return
        if not self._state.discard_top:
            return
        self.run_worker(self._send("draw", source="discard"))

    def action_select_1(self) -> None:
        self._select_position(0)

    def action_select_2(self) -> None:
        self._select_position(1)

    def action_select_3(self) -> None:
        self._select_position(2)

    def action_select_4(self) -> None:
        self._select_position(3)

    def action_select_5(self) -> None:
        self._select_position(4)

    def action_select_6(self) -> None:
        self._select_position(5)

    def _select_position(self, pos: int) -> None:
        # Initial flip phase
        if self._state.waiting_for_initial_flip:
            self._handle_initial_flip_select(pos)
            return

        # Flip after discard
        if self._awaiting_flip:
            self._do_flip(pos)
            return

        # Swap with held card
        if self._state.has_drawn_card and self._is_my_turn():
            self.run_worker(self._send("swap", position=pos))
            return

    def _handle_initial_flip_select(self, pos: int) -> None:
        if pos in self._initial_flip_positions:
            return  # already selected
        # Reject already face-up cards
        me = self._get_local_player()
        if me and pos < len(me.cards) and me.cards[pos].face_up:
            return

        self._initial_flip_positions.append(pos)

        # Immediately show the card as face-up locally for visual feedback
        if me and pos < len(me.cards):
            me.cards[pos].face_up = True
            hand = self.query_one("#local-hand", HandWidget)
            hand.update_player(
                me,
                deck_colors=self._state.deck_colors,
                is_current_turn=(me.id == self._state.current_player_id),
                is_knocker=(me.id == self._state.finisher_id and self._state.phase == "final_turn"),
                is_dealer=(me.id == self._state.dealer_id),
            )

        needed = self._state.initial_flips
        selected = len(self._initial_flip_positions)

        if selected >= needed:
            self.run_worker(
                self._send("flip_initial", positions=self._initial_flip_positions)
            )
            self._awaiting_initial_flip = False
            self._initial_flip_positions = []
        else:
            self._set_action(
                f"Keyboard: Choose {needed - selected} more card(s) to flip ({selected}/{needed})"
            )

    def _do_flip(self, pos: int) -> None:
        me = self._get_local_player()
        if me and pos < len(me.cards) and me.cards[pos].face_up:
            self._set_action("That card is already face-up! Pick a face-down card.")
            return
        self.run_worker(self._send("flip_card", position=pos))
        self._awaiting_flip = False

    def action_discard_held(self) -> None:
        if not self._is_my_turn() or not self._state.has_drawn_card:
            return
        if not self._state.can_discard:
            self._set_action("Can't discard a card drawn from discard. Swap or cancel.")
            return
        self.run_worker(self._send("discard"))

    def action_cancel_draw(self) -> None:
        if not self._is_my_turn() or not self._state.has_drawn_card:
            return
        self.run_worker(self._send("cancel_draw"))

    def action_flip_mode(self) -> None:
        if self._state.flip_as_action and self._is_my_turn() and not self._state.has_drawn_card:
            self._awaiting_flip = True
            self._set_action("Flip mode: select a face-down card [1-6]")

    def action_skip_flip(self) -> None:
        if self._awaiting_flip and self._can_flip_optional:
            self.run_worker(self._send("skip_flip"))
            self._awaiting_flip = False

    def action_knock_early(self) -> None:
        if not self._is_my_turn() or self._state.has_drawn_card:
            return
        if not self._state.knock_early:
            return
        self.run_worker(self._send("knock_early"))

    def action_next_round(self) -> None:
        if self._is_host and self._state.phase == "round_over":
            self.run_worker(self._send("next_round"))

    def action_leave_game(self) -> None:
        self.run_worker(self._send("leave_game"))
        self.app.pop_screen()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_my_turn(self) -> bool:
        return self._state.current_player_id == self._player_id

    def _get_local_player(self) -> PlayerData | None:
        for p in self._state.players:
            if p.id == self._player_id:
                return p
        return None

    async def _send(self, msg_type: str, **kwargs) -> None:
        try:
            await self.app.client.send(msg_type, **kwargs)
        except Exception as e:
            self._set_action(f"[red]Send error: {e}[/red]")

    def _set_action(self, text: str) -> None:
        try:
            self.query_one("#action-bar", Static).update(text)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _full_refresh(self) -> None:
        """Refresh all widgets from current game state."""
        state = self._state

        # Status bar
        status = self.query_one("#status-bar", StatusBarWidget)
        status.update_state(state, self._player_id)

        # Play area
        play_area = self.query_one("#play-area", PlayAreaWidget)
        play_area.update_state(state, local_player_id=self._player_id)

        # Local player hand (in bordered box with turn/knocker indicators)
        me = self._get_local_player()
        if me:
            self.query_one("#local-hand-label", Static).update("")
            hand = self.query_one("#local-hand", HandWidget)
            hand._is_local = True
            hand.update_player(
                me,
                deck_colors=state.deck_colors,
                is_current_turn=(me.id == state.current_player_id),
                is_knocker=(me.id == state.finisher_id and state.phase == "final_turn"),
                is_dealer=(me.id == state.dealer_id),
            )
        else:
            self.query_one("#local-hand-label", Static).update("")

        # Opponents - bordered boxes in a single Static
        opponents = [p for p in state.players if p.id != self._player_id]
        self._render_opponents(opponents)

        # Action bar
        self._refresh_action_bar()

    def _render_opponents(self, opponents: list[PlayerData]) -> None:
        """Render all opponent hands as bordered boxes into the opponents area.

        Adapts layout based on terminal width:
        - Narrow (<80): stack opponents vertically
        - Medium (80-119): 2-3 side-by-side with moderate spacing
        - Wide (120+): all side-by-side with generous spacing
        """
        if not opponents:
            self.query_one("#opponents-area", Static).update("")
            return

        from tui_client.widgets.hand import _check_column_match, _render_card_lines
        from tui_client.widgets.player_box import _visible_len, render_player_box

        state = self._state
        deck_colors = state.deck_colors
        width = self._term_width

        # Build each opponent's boxed display
        opp_blocks: list[list[str]] = []
        for opp in opponents:
            cards = opp.cards
            matched = _check_column_match(cards)
            card_lines = _render_card_lines(
                cards, deck_colors=deck_colors, matched=matched,
            )

            box = render_player_box(
                opp.name,
                score=opp.score,
                total_score=opp.total_score,
                content_lines=card_lines,
                is_current_turn=(opp.id == state.current_player_id),
                is_knocker=(opp.id == state.finisher_id and state.phase == "final_turn"),
                is_dealer=(opp.id == state.dealer_id),
                all_face_up=opp.all_face_up,
            )
            opp_blocks.append(box)

        # Determine how many opponents fit per row
        # Each box is ~21-24 chars wide
        opp_width = 22
        if width < 80:
            per_row = 1
            gap = "  "
        elif width < 120:
            gap = "  "
            per_row = max(1, (width - 4) // (opp_width + len(gap)))
        else:
            gap = "   "
            per_row = max(1, (min(width, 120) - 4) // (opp_width + len(gap)))

        # Render in rows of per_row opponents
        all_row_lines: list[str] = []
        for chunk_start in range(0, len(opp_blocks), per_row):
            chunk = opp_blocks[chunk_start : chunk_start + per_row]

            if len(chunk) == 1:
                all_row_lines.extend(chunk[0])
            else:
                max_height = max(len(b) for b in chunk)
                # Pad shorter blocks with spaces matching each block's visible width
                for b in chunk:
                    if b:
                        pad_width = _visible_len(b[0])
                    else:
                        pad_width = 0
                    while len(b) < max_height:
                        b.append(" " * pad_width)
                for row_idx in range(max_height):
                    parts = [b[row_idx] for b in chunk]
                    all_row_lines.append(gap.join(parts))

            if chunk_start + per_row < len(opp_blocks):
                all_row_lines.append("")

        self.query_one("#opponents-area", Static).update("\n".join(all_row_lines))

    def _refresh_action_bar(self) -> None:
        """Update action bar and keymap based on current game state."""
        state = self._state

        if state.phase in ("round_over", "game_over"):
            self._set_action("Keyboard: \[n]ext round")
            self._set_keymap("[N] Next round")
            return

        if state.waiting_for_initial_flip:
            needed = state.initial_flips
            selected = len(self._initial_flip_positions)
            self._set_action(
                f"Keyboard: Choose {needed} cards \[1] thru \[6] to flip ({selected}/{needed})"
            )
            self._set_keymap("[1-6] Select card")
            return

        if not self._is_my_turn():
            if state.current_player_id:
                for p in state.players:
                    if p.id == state.current_player_id:
                        self._set_action(f"Waiting for {p.name}...")
                        self._set_keymap("Waiting...")
                        return
            self._set_action("Waiting...")
            self._set_keymap("Waiting...")
            return

        if state.has_drawn_card:
            keys = ["[1-6] Swap"]
            if state.can_discard:
                self._set_action("Keyboard: Choose spot \[1] thru \[6] or \[x] to discard")
                keys.append("[X] Discard")
            else:
                self._set_action("Keyboard: Choose spot \[1] thru \[6] or \[c]ancel")
                keys.append("[C] Cancel")
            self._set_keymap("  ".join(keys))
            return

        parts = ["Choose \[d]eck or di\[s]card pile"]
        keys = ["[D] Draw", "[S] Pick discard"]
        if state.flip_as_action:
            parts.append("\[f]lip a card")
            keys.append("[F] Flip")
        if state.knock_early:
            parts.append("\[k]nock early")
            keys.append("[K] Knock")
        self._set_action("Keyboard: " + " or ".join(parts))
        self._set_keymap("  ".join(keys))

    def _set_keymap(self, text: str) -> None:
        try:
            self.app.set_keymap(text)
        except Exception:
            pass
