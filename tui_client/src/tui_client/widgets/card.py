"""Single card widget using Unicode box-drawing with Rich color markup."""

from __future__ import annotations

from textual.widgets import Static

from tui_client.models import CardData


# Web UI card back colors mapped to terminal hex equivalents
BACK_COLORS: dict[str, str] = {
    "red": "#c41e3a",
    "blue": "#2e5cb8",
    "green": "#228b22",
    "gold": "#daa520",
    "purple": "#6a0dad",
    "teal": "#008b8b",
    "pink": "#db7093",
    "slate": "#4a5568",
    "orange": "#e67e22",
    "cyan": "#00bcd4",
    "brown": "#8b4513",
    "yellow": "#daa520",
}

# Face-up card text colors (matching web UI)
SUIT_RED = "#c0392b"      # hearts, diamonds
SUIT_BLACK = "#e0e0e0"    # clubs, spades (light for dark terminal bg)
JOKER_COLOR = "#9b59b6"   # purple
BORDER_COLOR = "#888888"  # card border
EMPTY_COLOR = "#555555"   # empty card slot
POSITION_COLOR = "#f0e68c"  # pale yellow — distinct from suits and card backs
HIGHLIGHT_COLOR = "#ffaa00"  # bright amber — initial flip / attention


def _back_color_for_card(card: CardData, deck_colors: list[str] | None = None) -> str:
    """Get the hex color for a face-down card's back based on deck_id."""
    if deck_colors and card.deck_id is not None and card.deck_id < len(deck_colors):
        name = deck_colors[card.deck_id]
    else:
        name = "red"
    return BACK_COLORS.get(name, BACK_COLORS["red"])


def _top_border(position: int | None, d: str, color: str, highlight: bool = False) -> str:
    """Top border line, with position number replacing ┌ when present."""
    if position is not None:
        if highlight:
            hc = HIGHLIGHT_COLOR
            return f"[bold {hc}]{position}[/][{d}{color}]───┐[/{d}{color}]"
        return f"[{d}{color}]{position}───┐[/{d}{color}]"
    return f"[{d}{color}]┌───┐[/{d}{color}]"


def render_card(
    card: CardData | None,
    selected: bool = False,
    position: int | None = None,
    deck_colors: list[str] | None = None,
    dim: bool = False,
    highlight: bool = False,
) -> str:
    """Render a card as a 4-line Rich-markup string.

    Face-up:    Face-down:   Empty:
    ┌───┐       1───┐        ┌───┐
    │ A │       │░░░│        │   │
    │ ♠ │       │░░░│        │   │
    └───┘       └───┘        └───┘
    """
    d = "dim " if dim else ""
    bc = HIGHLIGHT_COLOR if highlight else BORDER_COLOR

    # Empty slot
    if card is None:
        c = EMPTY_COLOR
        return (
            f"[{d}{c}]┌───┐[/{d}{c}]\n"
            f"[{d}{c}]│   │[/{d}{c}]\n"
            f"[{d}{c}]│   │[/{d}{c}]\n"
            f"[{d}{c}]└───┘[/{d}{c}]"
        )

    top = _top_border(position, d, bc, highlight=highlight)

    # Face-down card with colored back
    if not card.face_up:
        back = _back_color_for_card(card, deck_colors)
        return (
            f"{top}\n"
            f"[{d}{bc}]│[/{d}{bc}][{d}{back}]░░░[/{d}{back}][{d}{bc}]│[/{d}{bc}]\n"
            f"[{d}{bc}]│[/{d}{bc}][{d}{back}]░░░[/{d}{back}][{d}{bc}]│[/{d}{bc}]\n"
            f"[{d}{bc}]└───┘[/{d}{bc}]"
        )

    # Joker
    if card.is_joker:
        jc = JOKER_COLOR
        icon = "🐉" if card.suit == "hearts" else "👹"
        return (
            f"{top}\n"
            f"[{d}{bc}]│[/{d}{bc}][{d}{jc}] {icon}[/{d}{jc}][{d}{bc}]│[/{d}{bc}]\n"
            f"[{d}{bc}]│[/{d}{bc}][{d}{jc}]JKR[/{d}{jc}][{d}{bc}]│[/{d}{bc}]\n"
            f"[{d}{bc}]└───┘[/{d}{bc}]"
        )

    # Face-up normal card
    fc = SUIT_RED if card.is_red else SUIT_BLACK
    rank = card.display_rank
    suit = card.display_suit
    rank_line = f"{rank:^3}"
    suit_line = f"{suit:^3}"

    return (
        f"{top}\n"
        f"[{d}{bc}]│[/{d}{bc}][{d}{fc}]{rank_line}[/{d}{fc}][{d}{bc}]│[/{d}{bc}]\n"
        f"[{d}{bc}]│[/{d}{bc}][{d}{fc}]{suit_line}[/{d}{fc}][{d}{bc}]│[/{d}{bc}]\n"
        f"[{d}{bc}]└───┘[/{d}{bc}]"
    )


class CardWidget(Static):
    """A single card display widget."""

    def __init__(
        self,
        card: CardData | None = None,
        selected: bool = False,
        position: int | None = None,
        matched: bool = False,
        deck_colors: list[str] | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._card = card
        self._selected = selected
        self._position = position
        self._matched = matched
        self._deck_colors = deck_colors

    def on_mount(self) -> None:
        self._refresh_display()

    def update_card(
        self,
        card: CardData | None,
        selected: bool = False,
        matched: bool = False,
        deck_colors: list[str] | None = None,
    ) -> None:
        self._card = card
        self._selected = selected
        self._matched = matched
        if deck_colors is not None:
            self._deck_colors = deck_colors
        self._refresh_display()

    def _refresh_display(self) -> None:
        text = render_card(
            self._card,
            self._selected,
            self._position,
            deck_colors=self._deck_colors,
            dim=self._matched,
        )
        self.update(text)
