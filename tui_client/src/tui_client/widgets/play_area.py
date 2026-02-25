"""Deck + discard + held card area."""

from __future__ import annotations

import re
from dataclasses import replace

from textual.events import Click
from textual.message import Message
from textual.widgets import Static

from tui_client.models import CardData, GameState
from tui_client.widgets.card import render_card

# Fixed column width for each card section (card is 5 wide)
_COL_WIDTH = 12

# Lime green for the held card highlight
_HOLDING_COLOR = "#80ff00"


def _pad_center(text: str, width: int) -> str:
    """Center-pad a plain or Rich-markup string to *width* visible chars."""
    visible = re.sub(r"\[.*?\]", "", text)
    pad = max(0, width - len(visible))
    left = pad // 2
    right = pad - left
    return " " * left + text + " " * right


class PlayAreaWidget(Static):
    """Displays the deck, discard pile, and held card.

    Layout order: DECK  [HOLDING]  DISCARD
    HOLDING only appears when the player has drawn a card.
    """

    class DeckClicked(Message):
        """Posted when the deck is clicked."""

    class DiscardClicked(Message):
        """Posted when the discard pile is clicked."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._state: GameState | None = None
        self._local_player_id: str = ""
        self._has_holding: bool = False

    def update_state(self, state: GameState, local_player_id: str = "") -> None:
        self._state = state
        if local_player_id:
            self._local_player_id = local_player_id
        self._refresh()

    def on_mount(self) -> None:
        self._refresh()

    def on_click(self, event: Click) -> None:
        """Map click to deck or discard column."""
        x = event.x
        # Layout: DECK (col 0..11) [HOLDING (col 12..23)] DISCARD (last col)
        if x < _COL_WIDTH:
            self.post_message(self.DeckClicked())
        elif self._has_holding and x >= 2 * _COL_WIDTH:
            self.post_message(self.DiscardClicked())
        elif not self._has_holding and x >= _COL_WIDTH:
            self.post_message(self.DiscardClicked())

    def _refresh(self) -> None:
        if not self._state:
            self.update("")
            return

        state = self._state

        # Deck card (face-down)
        deck_card = CardData(face_up=False, deck_id=0)
        deck_text = render_card(deck_card, deck_colors=state.deck_colors)
        deck_lines = deck_text.split("\n")

        # Discard card
        discard_text = render_card(state.discard_top, deck_colors=state.deck_colors)
        discard_lines = discard_text.split("\n")

        # Held card — force face_up so render_card shows the face
        # Only show when it's the local player holding
        held_lines = None
        local_holding = (
            state.has_drawn_card
            and state.drawn_card
            and state.drawn_player_id == self._local_player_id
        )
        if local_holding:
            revealed = replace(state.drawn_card, face_up=True)
            held_text = render_card(revealed, deck_colors=state.deck_colors)
            held_lines = held_text.split("\n")

        self._has_holding = held_lines is not None

        # Always render 3 columns so the box stays a fixed width
        num_card_lines = max(len(deck_lines), len(discard_lines))
        lines = []
        for i in range(num_card_lines):
            d = deck_lines[i] if i < len(deck_lines) else "     "
            c = discard_lines[i] if i < len(discard_lines) else "     "
            row = _pad_center(d, _COL_WIDTH)
            if held_lines:
                h = held_lines[i] if i < len(held_lines) else "     "
                row += _pad_center(h, _COL_WIDTH)
            else:
                row += " " * _COL_WIDTH
            row += _pad_center(c, _COL_WIDTH)
            lines.append(row)

        # Labels row — always 3 columns
        deck_label = f"DECK:{state.deck_remaining}"
        discard_label = "DISCARD"
        label = _pad_center(deck_label, _COL_WIDTH)
        if held_lines:
            holding_label = f"[bold {_HOLDING_COLOR}]HOLDING[/]"
            label += _pad_center(holding_label, _COL_WIDTH)
        else:
            label += " " * _COL_WIDTH
        label += _pad_center(discard_label, _COL_WIDTH)
        lines.append(label)

        self.update("\n".join(lines))
