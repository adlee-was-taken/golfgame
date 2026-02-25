"""2x3 card grid for one player's hand."""

from __future__ import annotations

from textual.events import Click
from textual.message import Message
from textual.widgets import Static

from tui_client.models import CardData, PlayerData
from tui_client.widgets.card import render_card

# Color for the match connector lines (muted green — pairs cancel to 0)
_MATCH_COLOR = "#6a9955"


def _check_column_match(cards: list[CardData]) -> list[bool]:
    """Check which cards are in matched columns (both face-up, same rank).

    Cards layout: [0][1][2]
                  [3][4][5]
    Columns: (0,3), (1,4), (2,5)
    """
    matched = [False] * 6
    if len(cards) < 6:
        return matched

    for col in range(3):
        top = cards[col]
        bot = cards[col + 3]
        if (
            top.face_up
            and bot.face_up
            and top.rank is not None
            and top.rank == bot.rank
        ):
            matched[col] = True
            matched[col + 3] = True
    return matched


def _build_match_connector(matched: list[bool]) -> str | None:
    """Build a connector line with ║ ║ under each matched column.

    Card layout:  5-char card, 1-char gap, repeated.
    Positions:    01234 5 6789A B CDEFG
                  card0   card1   card2

    For each matched column, place ║ at offsets 1 and 3 within the card span.
    """
    has_any = matched[0] or matched[1] or matched[2]
    if not has_any:
        return None

    # Build a 17-char line (3 cards * 5 + 2 gaps)
    chars = list(" " * 17)
    for col in range(3):
        if matched[col]:  # top card matched implies column matched
            base = col * 6  # card start position (0, 6, 12)
            chars[base + 1] = "║"
            chars[base + 3] = "║"

    line = "".join(chars)
    return f"[{_MATCH_COLOR}]{line}[/]"


def _render_card_lines(
    cards: list[CardData],
    *,
    is_local: bool = False,
    deck_colors: list[str] | None = None,
    matched: list[bool] | None = None,
    highlight: bool = False,
) -> list[str]:
    """Render the 2x3 card grid as a list of text lines (no box).

    Inserts a connector line with ║ ║ between rows for matched columns.
    """
    if matched is None:
        matched = _check_column_match(cards)
    lines: list[str] = []
    for row_idx, row_start in enumerate((0, 3)):
        # Insert connector between row 0 and row 1
        if row_idx == 1:
            connector = _build_match_connector(matched)
            if connector:
                lines.append(connector)

        row_line_parts: list[list[str]] = []
        for i in range(3):
            idx = row_start + i
            card = cards[idx] if idx < len(cards) else None
            pos = idx + 1 if is_local else None
            text = render_card(
                card,
                position=pos,
                deck_colors=deck_colors,
                dim=matched[idx],
                highlight=highlight,
            )
            card_lines = text.split("\n")
            while len(row_line_parts) < len(card_lines):
                row_line_parts.append([])
            for ln_idx, ln in enumerate(card_lines):
                row_line_parts[ln_idx].append(ln)
        for parts in row_line_parts:
            lines.append(" ".join(parts))
    return lines


class HandWidget(Static):
    """Displays a player's 2x3 card grid as rich text, wrapped in a player box."""

    class CardClicked(Message):
        """Posted when a card position is clicked in the local hand."""

        def __init__(self, position: int) -> None:
            super().__init__()
            self.position = position

    def __init__(
        self,
        player: PlayerData | None = None,
        is_local: bool = False,
        deck_colors: list[str] | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._player = player
        self._is_local = is_local
        self._deck_colors = deck_colors
        # State flags for the player box
        self._is_current_turn: bool = False
        self._is_knocker: bool = False
        self._is_dealer: bool = False
        self._has_connector: bool = False
        self._highlight: bool = False
        self._box_width: int = 0

    def update_player(
        self,
        player: PlayerData,
        deck_colors: list[str] | None = None,
        *,
        is_current_turn: bool = False,
        is_knocker: bool = False,
        is_dealer: bool = False,
        highlight: bool = False,
    ) -> None:
        self._player = player
        if deck_colors is not None:
            self._deck_colors = deck_colors
        self._is_current_turn = is_current_turn
        self._is_knocker = is_knocker
        self._is_dealer = is_dealer
        self._highlight = highlight
        self._refresh()

    def on_mount(self) -> None:
        self._refresh()

    def on_click(self, event: Click) -> None:
        """Map click coordinates to card position (0-5)."""
        if not self._is_local or not self._box_width:
            return

        # The content is centered in the widget — compute the x offset
        x_offset = max(0, (self.size.width - self._box_width) // 2)
        x = event.x - x_offset
        y = event.y

        # Box layout:
        # Line 0: top border
        # Lines 1-4: row 0 cards (4 lines each)
        # Line 5 (optional): match connector
        # Lines 5-8 or 6-9: row 1 cards
        # Last line: bottom border
        #
        # Content x: │ <space> then cards at x offsets 2, 8, 14 (each 5 wide, 1 gap)

        # Determine column from x (content starts at x=2 inside box)
        # Card 0: x 2-6, Card 1: x 8-12, Card 2: x 14-18
        col = -1
        if 2 <= x <= 6:
            col = 0
        elif 8 <= x <= 12:
            col = 1
        elif 14 <= x <= 18:
            col = 2

        if col < 0:
            return

        # Determine row from y
        # y=0: top border, y=1..4: row 0 cards, then optional connector, then row 1
        row = -1
        if 1 <= y <= 4:
            row = 0
        else:
            row1_start = 6 if self._has_connector else 5
            if row1_start <= y <= row1_start + 3:
                row = 1

        if row < 0:
            return

        position = row * 3 + col
        self.post_message(self.CardClicked(position))

    def _refresh(self) -> None:
        if not self._player or not self._player.cards:
            self.update("")
            return

        from tui_client.widgets.player_box import _visible_len, render_player_box

        cards = self._player.cards
        matched = _check_column_match(cards)
        self._has_connector = any(matched[:3])

        card_lines = _render_card_lines(
            cards,
            is_local=self._is_local,
            deck_colors=self._deck_colors,
            matched=matched,
            highlight=self._highlight,
        )

        box_lines = render_player_box(
            self._player.name,
            score=self._player.score,
            total_score=self._player.total_score,
            content_lines=card_lines,
            is_current_turn=self._is_current_turn,
            is_knocker=self._is_knocker,
            is_dealer=self._is_dealer,
            is_local=self._is_local,
            all_face_up=self._player.all_face_up,
        )

        # Store box width for click coordinate mapping
        if box_lines:
            self._box_width = _visible_len(box_lines[0])

        self.update("\n".join(box_lines))
