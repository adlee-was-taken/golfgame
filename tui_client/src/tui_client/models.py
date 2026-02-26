"""Data models for the TUI client."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CardData:
    """A single card as received from the server."""

    suit: Optional[str] = None  # "hearts", "diamonds", "clubs", "spades"
    rank: Optional[str] = None  # "A", "2".."10", "J", "Q", "K", "★"
    face_up: bool = False
    deck_id: Optional[int] = None

    @classmethod
    def from_dict(cls, d: dict) -> CardData:
        return cls(
            suit=d.get("suit"),
            rank=d.get("rank"),
            face_up=d.get("face_up", False),
            deck_id=d.get("deck_id"),
        )

    @property
    def display_suit(self) -> str:
        """Unicode suit symbol."""
        return {
            "hearts": "\u2665",
            "diamonds": "\u2666",
            "clubs": "\u2663",
            "spades": "\u2660",
        }.get(self.suit or "", "")

    @property
    def display_rank(self) -> str:
        if self.rank == "10":
            return "10"
        return self.rank or ""

    @property
    def is_red(self) -> bool:
        return self.suit in ("hearts", "diamonds")

    @property
    def is_joker(self) -> bool:
        return self.rank == "\u2605"


@dataclass
class PlayerData:
    """A player as received in game state."""

    id: str = ""
    name: str = ""
    cards: list[CardData] = field(default_factory=list)
    score: Optional[int] = None
    total_score: int = 0
    rounds_won: int = 0
    all_face_up: bool = False

    # Standard card values for visible score calculation
    _CARD_VALUES = {
        'A': 1, '2': -2, '3': 3, '4': 4, '5': 5, '6': 6,
        '7': 7, '8': 8, '9': 9, '10': 10, 'J': 10, 'Q': 10, 'K': 0, '★': -2,
    }

    @property
    def visible_score(self) -> int:
        """Compute score from face-up cards, zeroing matched columns."""
        if len(self.cards) < 6:
            return 0
        values = [0] * 6
        for i, c in enumerate(self.cards):
            if c.face_up and c.rank:
                values[i] = self._CARD_VALUES.get(c.rank, 0)
        # Zero out matched columns (same rank, both face-up)
        for col in range(3):
            top, bot = self.cards[col], self.cards[col + 3]
            if top.face_up and bot.face_up and top.rank and top.rank == bot.rank:
                values[col] = 0
                values[col + 3] = 0
        return sum(values)

    @classmethod
    def from_dict(cls, d: dict) -> PlayerData:
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            cards=[CardData.from_dict(c) for c in d.get("cards", [])],
            score=d.get("score"),
            total_score=d.get("total_score", 0),
            rounds_won=d.get("rounds_won", 0),
            all_face_up=d.get("all_face_up", False),
        )


@dataclass
class GameState:
    """Full game state from the server."""

    phase: str = "waiting"
    players: list[PlayerData] = field(default_factory=list)
    current_player_id: Optional[str] = None
    dealer_id: Optional[str] = None
    discard_top: Optional[CardData] = None
    deck_remaining: int = 0
    current_round: int = 1
    total_rounds: int = 1
    has_drawn_card: bool = False
    drawn_card: Optional[CardData] = None
    drawn_player_id: Optional[str] = None
    can_discard: bool = True
    waiting_for_initial_flip: bool = False
    initial_flips: int = 2
    flip_on_discard: bool = False
    flip_mode: str = "never"
    flip_is_optional: bool = False
    flip_as_action: bool = False
    knock_early: bool = False
    finisher_id: Optional[str] = None
    card_values: dict = field(default_factory=dict)
    active_rules: list = field(default_factory=list)
    deck_colors: list[str] = field(default_factory=lambda: ["red", "blue", "gold"])

    @classmethod
    def from_dict(cls, d: dict) -> GameState:
        discard = d.get("discard_top")
        drawn = d.get("drawn_card")
        return cls(
            phase=d.get("phase", "waiting"),
            players=[PlayerData.from_dict(p) for p in d.get("players", [])],
            current_player_id=d.get("current_player_id"),
            dealer_id=d.get("dealer_id"),
            discard_top=CardData.from_dict(discard) if discard else None,
            deck_remaining=d.get("deck_remaining", 0),
            current_round=d.get("current_round", 1),
            total_rounds=d.get("total_rounds", 1),
            has_drawn_card=d.get("has_drawn_card", False),
            drawn_card=CardData.from_dict(drawn) if drawn else None,
            drawn_player_id=d.get("drawn_player_id"),
            can_discard=d.get("can_discard", True),
            waiting_for_initial_flip=d.get("waiting_for_initial_flip", False),
            initial_flips=d.get("initial_flips", 2),
            flip_on_discard=d.get("flip_on_discard", False),
            flip_mode=d.get("flip_mode", "never"),
            flip_is_optional=d.get("flip_is_optional", False),
            flip_as_action=d.get("flip_as_action", False),
            knock_early=d.get("knock_early", False),
            finisher_id=d.get("finisher_id"),
            card_values=d.get("card_values", {}),
            active_rules=d.get("active_rules", []),
            deck_colors=d.get("deck_colors", ["red", "blue", "gold"]),
        )
