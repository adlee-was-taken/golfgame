"""
Game state rebuilder for event sourcing.

This module provides the ability to reconstruct game state from an event stream.
The RebuiltGameState class mirrors the Game class structure but is built
entirely from events rather than direct mutation.

Usage:
    events = await event_store.get_events(game_id)
    state = rebuild_state(events)
    print(state.phase, state.current_player_id)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from models.events import GameEvent, EventType


class GamePhase(str, Enum):
    """Game phases matching game.py GamePhase."""
    WAITING = "waiting"
    INITIAL_FLIP = "initial_flip"
    PLAYING = "playing"
    FINAL_TURN = "final_turn"
    ROUND_OVER = "round_over"
    GAME_OVER = "game_over"


@dataclass
class CardState:
    """
    A card's state during replay.

    Attributes:
        rank: Card rank (A, 2-10, J, Q, K, or Joker).
        suit: Card suit (hearts, diamonds, clubs, spades).
        face_up: Whether the card is visible.
    """
    rank: str
    suit: str
    face_up: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for comparison."""
        return {
            "rank": self.rank,
            "suit": self.suit,
            "face_up": self.face_up,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CardState":
        """Create from dictionary."""
        return cls(
            rank=d["rank"],
            suit=d["suit"],
            face_up=d.get("face_up", False),
        )


@dataclass
class PlayerState:
    """
    A player's state during replay.

    Attributes:
        id: Unique player identifier.
        name: Display name.
        cards: The player's 6-card hand.
        score: Current round score.
        total_score: Cumulative score across rounds.
        rounds_won: Number of rounds won.
        is_cpu: Whether this is a CPU player.
        cpu_profile: CPU profile name (for AI analysis).
    """
    id: str
    name: str
    cards: list[CardState] = field(default_factory=list)
    score: int = 0
    total_score: int = 0
    rounds_won: int = 0
    is_cpu: bool = False
    cpu_profile: Optional[str] = None

    def all_face_up(self) -> bool:
        """Check if all cards are revealed."""
        return all(card.face_up for card in self.cards)


@dataclass
class RebuiltGameState:
    """
    Game state rebuilt from events.

    This class reconstructs the full game state by applying events in sequence.
    It mirrors the structure of the Game class from game.py but is immutable
    and derived entirely from events.

    Attributes:
        game_id: UUID of the game.
        room_code: 4-letter room code.
        phase: Current game phase.
        players: Map of player_id -> PlayerState.
        player_order: List of player IDs in turn order.
        current_player_idx: Index of current player in player_order.
        deck_remaining: Cards left in deck (approximated).
        discard_pile: Cards in discard pile (most recent at end).
        drawn_card: Card currently held by active player.
        current_round: Current round number (1-indexed).
        total_rounds: Total rounds in game.
        options: GameOptions as dict.
        sequence_num: Last applied event sequence.
        finisher_id: Player who went out first this round.
        initial_flips_done: Set of player IDs who completed initial flips.
    """
    game_id: str
    room_code: str = ""
    phase: GamePhase = GamePhase.WAITING
    players: dict[str, PlayerState] = field(default_factory=dict)
    player_order: list[str] = field(default_factory=list)
    current_player_idx: int = 0
    deck_remaining: int = 0
    discard_pile: list[CardState] = field(default_factory=list)
    drawn_card: Optional[CardState] = None
    drawn_from_discard: bool = False
    current_round: int = 0
    total_rounds: int = 1
    options: dict = field(default_factory=dict)
    sequence_num: int = 0
    finisher_id: Optional[str] = None
    players_with_final_turn: set = field(default_factory=set)
    initial_flips_done: set = field(default_factory=set)
    host_id: Optional[str] = None

    def apply(self, event: GameEvent) -> "RebuiltGameState":
        """
        Apply an event to produce new state.

        Events must be applied in sequence order.

        Args:
            event: The event to apply.

        Returns:
            self for chaining.

        Raises:
            ValueError: If event is out of sequence or unknown type.
        """
        # Validate sequence (first event can be 1, then must be sequential)
        expected_seq = self.sequence_num + 1 if self.sequence_num > 0 else 1
        if event.sequence_num != expected_seq:
            raise ValueError(
                f"Expected sequence {expected_seq}, got {event.sequence_num}"
            )

        # Dispatch to handler
        handler = getattr(self, f"_apply_{event.event_type.value}", None)
        if handler is None:
            raise ValueError(f"Unknown event type: {event.event_type}")

        handler(event)
        self.sequence_num = event.sequence_num
        return self

    # -------------------------------------------------------------------------
    # Lifecycle Event Handlers
    # -------------------------------------------------------------------------

    def _apply_game_created(self, event: GameEvent) -> None:
        """Handle game_created event."""
        self.room_code = event.data["room_code"]
        self.host_id = event.data["host_id"]
        self.options = event.data.get("options", {})

    def _apply_player_joined(self, event: GameEvent) -> None:
        """Handle player_joined event."""
        player_id = event.player_id
        self.players[player_id] = PlayerState(
            id=player_id,
            name=event.data["player_name"],
            is_cpu=event.data.get("is_cpu", False),
            cpu_profile=event.data.get("cpu_profile"),
        )

    def _apply_player_left(self, event: GameEvent) -> None:
        """Handle player_left event."""
        player_id = event.player_id
        if player_id in self.players:
            del self.players[player_id]
        if player_id in self.player_order:
            self.player_order.remove(player_id)
            # Adjust current player index if needed
            if self.current_player_idx >= len(self.player_order):
                self.current_player_idx = 0

    def _apply_game_started(self, event: GameEvent) -> None:
        """Handle game_started event."""
        self.player_order = event.data["player_order"]
        self.total_rounds = event.data["num_rounds"]
        self.options = event.data.get("options", self.options)
        # Note: round_started will set up the actual round

    def _apply_round_started(self, event: GameEvent) -> None:
        """Handle round_started event."""
        self.current_round = event.data["round_num"]
        self.finisher_id = None
        self.players_with_final_turn = set()
        self.initial_flips_done = set()
        self.drawn_card = None
        self.drawn_from_discard = False
        self.current_player_idx = 0
        self.discard_pile = []

        # Deal cards to players (all face-down)
        dealt_cards = event.data["dealt_cards"]
        for player_id, cards_data in dealt_cards.items():
            if player_id in self.players:
                self.players[player_id].cards = [
                    CardState.from_dict(c) for c in cards_data
                ]
                # Reset round score
                self.players[player_id].score = 0

        # Start discard pile
        first_discard = event.data.get("first_discard")
        if first_discard:
            card = CardState.from_dict(first_discard)
            card.face_up = True
            self.discard_pile.append(card)

        # Set phase based on initial_flips setting
        initial_flips = self.options.get("initial_flips", 2)
        if initial_flips == 0:
            self.phase = GamePhase.PLAYING
        else:
            self.phase = GamePhase.INITIAL_FLIP

        # Approximate deck size (we don't track exact cards)
        num_decks = self.options.get("num_decks", 1)
        cards_per_deck = 52
        if self.options.get("use_jokers"):
            if self.options.get("lucky_swing"):
                cards_per_deck += 1  # Single joker
            else:
                cards_per_deck += 2  # Two jokers
        total_cards = num_decks * cards_per_deck
        dealt_count = len(self.players) * 6 + 1  # 6 per player + 1 discard
        self.deck_remaining = total_cards - dealt_count

    def _apply_round_ended(self, event: GameEvent) -> None:
        """Handle round_ended event."""
        self.phase = GamePhase.ROUND_OVER
        scores = event.data["scores"]

        # Update player scores
        for player_id, score in scores.items():
            if player_id in self.players:
                self.players[player_id].score = score
                self.players[player_id].total_score += score

        # Determine round winner (lowest score)
        if scores:
            min_score = min(scores.values())
            for player_id, score in scores.items():
                if score == min_score and player_id in self.players:
                    self.players[player_id].rounds_won += 1

        # Apply final hands if provided
        final_hands = event.data.get("final_hands", {})
        for player_id, cards_data in final_hands.items():
            if player_id in self.players:
                self.players[player_id].cards = [
                    CardState.from_dict(c) for c in cards_data
                ]
                # Ensure all cards are face up
                for card in self.players[player_id].cards:
                    card.face_up = True

    def _apply_game_ended(self, event: GameEvent) -> None:
        """Handle game_ended event."""
        self.phase = GamePhase.GAME_OVER
        # Final scores are already tracked in players

    # -------------------------------------------------------------------------
    # Gameplay Event Handlers
    # -------------------------------------------------------------------------

    def _apply_initial_flip(self, event: GameEvent) -> None:
        """Handle initial_flip event."""
        player_id = event.player_id
        player = self.players.get(player_id)
        if not player:
            return

        positions = event.data["positions"]
        cards = event.data["cards"]

        for pos, card_data in zip(positions, cards):
            if 0 <= pos < len(player.cards):
                player.cards[pos] = CardState.from_dict(card_data)
                player.cards[pos].face_up = True

        self.initial_flips_done.add(player_id)

        # Check if all players have flipped
        if len(self.initial_flips_done) == len(self.players):
            self.phase = GamePhase.PLAYING

    def _apply_card_drawn(self, event: GameEvent) -> None:
        """Handle card_drawn event."""
        card = CardState.from_dict(event.data["card"])
        card.face_up = True
        self.drawn_card = card
        self.drawn_from_discard = event.data["source"] == "discard"

        if self.drawn_from_discard and self.discard_pile:
            self.discard_pile.pop()
        else:
            self.deck_remaining = max(0, self.deck_remaining - 1)

    def _apply_card_swapped(self, event: GameEvent) -> None:
        """Handle card_swapped event."""
        player_id = event.player_id
        player = self.players.get(player_id)
        if not player:
            return

        position = event.data["position"]
        new_card = CardState.from_dict(event.data["new_card"])
        old_card = CardState.from_dict(event.data["old_card"])

        # Place new card in hand
        new_card.face_up = True
        if 0 <= position < len(player.cards):
            player.cards[position] = new_card

        # Add old card to discard
        old_card.face_up = True
        self.discard_pile.append(old_card)

        # Clear drawn card
        self.drawn_card = None
        self.drawn_from_discard = False

        # Advance turn
        self._end_turn(player)

    def _apply_card_discarded(self, event: GameEvent) -> None:
        """Handle card_discarded event."""
        player_id = event.player_id
        player = self.players.get(player_id)

        if self.drawn_card:
            self.drawn_card.face_up = True
            self.discard_pile.append(self.drawn_card)
            self.drawn_card = None
            self.drawn_from_discard = False

        # Check if flip_on_discard mode requires a flip
        # If not, end turn now
        flip_mode = self.options.get("flip_mode", "never")
        if flip_mode == "never":
            if player:
                self._end_turn(player)
        # For "always" or "endgame", wait for flip_card or flip_skipped event

    def _apply_card_flipped(self, event: GameEvent) -> None:
        """Handle card_flipped event (after discard in flip mode)."""
        player_id = event.player_id
        player = self.players.get(player_id)
        if not player:
            return

        position = event.data["position"]
        card = CardState.from_dict(event.data["card"])
        card.face_up = True

        if 0 <= position < len(player.cards):
            player.cards[position] = card

        self._end_turn(player)

    def _apply_flip_skipped(self, event: GameEvent) -> None:
        """Handle flip_skipped event (endgame mode optional flip)."""
        player_id = event.player_id
        player = self.players.get(player_id)
        if player:
            self._end_turn(player)

    def _apply_flip_as_action(self, event: GameEvent) -> None:
        """Handle flip_as_action event (house rule)."""
        player_id = event.player_id
        player = self.players.get(player_id)
        if not player:
            return

        position = event.data["position"]
        card = CardState.from_dict(event.data["card"])
        card.face_up = True

        if 0 <= position < len(player.cards):
            player.cards[position] = card

        self._end_turn(player)

    def _apply_knock_early(self, event: GameEvent) -> None:
        """Handle knock_early event (house rule)."""
        player_id = event.player_id
        player = self.players.get(player_id)
        if not player:
            return

        positions = event.data["positions"]
        cards = event.data["cards"]

        for pos, card_data in zip(positions, cards):
            if 0 <= pos < len(player.cards):
                card = CardState.from_dict(card_data)
                card.face_up = True
                player.cards[pos] = card

        self._end_turn(player)

    # -------------------------------------------------------------------------
    # Turn Management
    # -------------------------------------------------------------------------

    def _end_turn(self, player: PlayerState) -> None:
        """
        Handle end of player's turn.

        Checks for going out and advances to next player.
        """
        # Check if player went out
        if player.all_face_up() and self.finisher_id is None:
            self.finisher_id = player.id
            self.phase = GamePhase.FINAL_TURN
            self.players_with_final_turn.add(player.id)
        elif self.phase == GamePhase.FINAL_TURN:
            # In final turn, reveal all cards after turn ends
            for card in player.cards:
                card.face_up = True
            self.players_with_final_turn.add(player.id)

        # Advance to next player
        self._next_turn()

    def _next_turn(self) -> None:
        """Advance to the next player's turn."""
        if not self.player_order:
            return

        if self.phase == GamePhase.FINAL_TURN:
            # Check if all players have had their final turn
            all_done = all(
                pid in self.players_with_final_turn
                for pid in self.player_order
            )
            if all_done:
                # Round will end (round_ended event will set phase)
                return

        # Move to next player
        self.current_player_idx = (self.current_player_idx + 1) % len(self.player_order)

    # -------------------------------------------------------------------------
    # Query Methods
    # -------------------------------------------------------------------------

    @property
    def current_player_id(self) -> Optional[str]:
        """Get the current player's ID."""
        if self.player_order and 0 <= self.current_player_idx < len(self.player_order):
            return self.player_order[self.current_player_idx]
        return None

    @property
    def current_player(self) -> Optional[PlayerState]:
        """Get the current player's state."""
        player_id = self.current_player_id
        return self.players.get(player_id) if player_id else None

    def discard_top(self) -> Optional[CardState]:
        """Get the top card of the discard pile."""
        return self.discard_pile[-1] if self.discard_pile else None

    def get_player(self, player_id: str) -> Optional[PlayerState]:
        """Get a player's state by ID."""
        return self.players.get(player_id)


def rebuild_state(events: list[GameEvent]) -> RebuiltGameState:
    """
    Rebuild game state from a list of events.

    Args:
        events: List of events in sequence order.

    Returns:
        Reconstructed game state.

    Raises:
        ValueError: If events list is empty or has invalid sequence.
    """
    if not events:
        raise ValueError("Cannot rebuild state from empty event list")

    state = RebuiltGameState(game_id=events[0].game_id)
    for event in events:
        state.apply(event)

    return state


async def rebuild_state_from_store(
    event_store,
    game_id: str,
    to_sequence: Optional[int] = None,
) -> RebuiltGameState:
    """
    Rebuild game state by loading events from the store.

    Args:
        event_store: EventStore instance.
        game_id: Game UUID.
        to_sequence: Optional sequence to rebuild up to.

    Returns:
        Reconstructed game state.
    """
    events = await event_store.get_events(game_id, to_sequence=to_sequence)
    return rebuild_state(events)
