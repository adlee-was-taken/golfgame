"""
Event definitions for Golf game event sourcing.

All game actions are stored as immutable events, enabling:
- Full game replay from any point
- Audit trails for all player actions
- Stats aggregation from event streams
- Deterministic state reconstruction

Events are the single source of truth for game state.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Any
import json


class EventType(str, Enum):
    """All possible event types in a Golf game."""

    # Lifecycle events
    GAME_CREATED = "game_created"
    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    GAME_STARTED = "game_started"
    ROUND_STARTED = "round_started"
    ROUND_ENDED = "round_ended"
    GAME_ENDED = "game_ended"

    # Gameplay events
    INITIAL_FLIP = "initial_flip"
    CARD_DRAWN = "card_drawn"
    CARD_SWAPPED = "card_swapped"
    CARD_DISCARDED = "card_discarded"
    CARD_FLIPPED = "card_flipped"
    FLIP_SKIPPED = "flip_skipped"
    FLIP_AS_ACTION = "flip_as_action"
    KNOCK_EARLY = "knock_early"


@dataclass
class GameEvent:
    """
    Base class for all game events.

    Events are immutable records of actions that occurred in a game.
    They contain all information needed to reconstruct game state.

    Attributes:
        event_type: The type of event (from EventType enum).
        game_id: UUID of the game this event belongs to.
        sequence_num: Monotonically increasing sequence number within game.
        timestamp: When the event occurred (UTC).
        player_id: ID of player who triggered the event (if applicable).
        data: Event-specific payload data.
    """

    event_type: EventType
    game_id: str
    sequence_num: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    player_id: Optional[str] = None
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize event to dictionary for JSON storage."""
        return {
            "event_type": self.event_type.value,
            "game_id": self.game_id,
            "sequence_num": self.sequence_num,
            "timestamp": self.timestamp.isoformat(),
            "player_id": self.player_id,
            "data": self.data,
        }

    def to_json(self) -> str:
        """Serialize event to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: dict) -> "GameEvent":
        """Deserialize event from dictionary."""
        timestamp = d["timestamp"]
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)

        return cls(
            event_type=EventType(d["event_type"]),
            game_id=d["game_id"],
            sequence_num=d["sequence_num"],
            timestamp=timestamp,
            player_id=d.get("player_id"),
            data=d.get("data", {}),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "GameEvent":
        """Deserialize event from JSON string."""
        return cls.from_dict(json.loads(json_str))


# =============================================================================
# Event Factory Functions
# =============================================================================
# These provide type-safe event construction with proper data structures.


def game_created(
    game_id: str,
    sequence_num: int,
    room_code: str,
    host_id: str,
    options: dict,
) -> GameEvent:
    """
    Create a GameCreated event.

    Emitted when a new game room is created.

    Args:
        game_id: UUID for the new game.
        sequence_num: Should be 1 (first event).
        room_code: 4-letter room code.
        host_id: Player ID of the host.
        options: GameOptions as dict.
    """
    return GameEvent(
        event_type=EventType.GAME_CREATED,
        game_id=game_id,
        sequence_num=sequence_num,
        player_id=host_id,
        data={
            "room_code": room_code,
            "host_id": host_id,
            "options": options,
        },
    )


def player_joined(
    game_id: str,
    sequence_num: int,
    player_id: str,
    player_name: str,
    is_cpu: bool = False,
    cpu_profile: Optional[str] = None,
) -> GameEvent:
    """
    Create a PlayerJoined event.

    Emitted when a player (human or CPU) joins the game.

    Args:
        game_id: Game UUID.
        sequence_num: Event sequence number.
        player_id: Unique player identifier.
        player_name: Display name.
        is_cpu: Whether this is a CPU player.
        cpu_profile: CPU profile name (for AI replay analysis).
    """
    return GameEvent(
        event_type=EventType.PLAYER_JOINED,
        game_id=game_id,
        sequence_num=sequence_num,
        player_id=player_id,
        data={
            "player_name": player_name,
            "is_cpu": is_cpu,
            "cpu_profile": cpu_profile,
        },
    )


def player_left(
    game_id: str,
    sequence_num: int,
    player_id: str,
    reason: str = "left",
) -> GameEvent:
    """
    Create a PlayerLeft event.

    Emitted when a player leaves the game.

    Args:
        game_id: Game UUID.
        sequence_num: Event sequence number.
        player_id: ID of player who left.
        reason: Why they left (left, disconnected, kicked).
    """
    return GameEvent(
        event_type=EventType.PLAYER_LEFT,
        game_id=game_id,
        sequence_num=sequence_num,
        player_id=player_id,
        data={"reason": reason},
    )


def game_started(
    game_id: str,
    sequence_num: int,
    player_order: list[str],
    num_decks: int,
    num_rounds: int,
    options: dict,
) -> GameEvent:
    """
    Create a GameStarted event.

    Emitted when the host starts the game. This locks in settings
    but doesn't deal cards (that's RoundStarted).

    Args:
        game_id: Game UUID.
        sequence_num: Event sequence number.
        player_order: List of player IDs in turn order.
        num_decks: Number of card decks being used.
        num_rounds: Total rounds to play.
        options: Final GameOptions as dict.
    """
    return GameEvent(
        event_type=EventType.GAME_STARTED,
        game_id=game_id,
        sequence_num=sequence_num,
        data={
            "player_order": player_order,
            "num_decks": num_decks,
            "num_rounds": num_rounds,
            "options": options,
        },
    )


def round_started(
    game_id: str,
    sequence_num: int,
    round_num: int,
    deck_seed: int,
    dealt_cards: dict[str, list[dict]],
    first_discard: dict,
) -> GameEvent:
    """
    Create a RoundStarted event.

    Emitted at the start of each round. Contains all information
    needed to recreate the initial state deterministically.

    Args:
        game_id: Game UUID.
        sequence_num: Event sequence number.
        round_num: Round number (1-indexed).
        deck_seed: Random seed used for deck shuffle.
        dealt_cards: Map of player_id -> list of 6 card dicts.
                     Cards include {rank, suit} (face_up always False).
        first_discard: The first card on the discard pile.
    """
    return GameEvent(
        event_type=EventType.ROUND_STARTED,
        game_id=game_id,
        sequence_num=sequence_num,
        data={
            "round_num": round_num,
            "deck_seed": deck_seed,
            "dealt_cards": dealt_cards,
            "first_discard": first_discard,
        },
    )


def round_ended(
    game_id: str,
    sequence_num: int,
    round_num: int,
    scores: dict[str, int],
    final_hands: dict[str, list[dict]],
    finisher_id: Optional[str] = None,
) -> GameEvent:
    """
    Create a RoundEnded event.

    Emitted when a round completes and scores are calculated.

    Args:
        game_id: Game UUID.
        sequence_num: Event sequence number.
        round_num: Round that just ended.
        scores: Map of player_id -> round score.
        final_hands: Map of player_id -> final 6 cards (all revealed).
        finisher_id: ID of player who went out first (if any).
    """
    return GameEvent(
        event_type=EventType.ROUND_ENDED,
        game_id=game_id,
        sequence_num=sequence_num,
        data={
            "round_num": round_num,
            "scores": scores,
            "final_hands": final_hands,
            "finisher_id": finisher_id,
        },
    )


def game_ended(
    game_id: str,
    sequence_num: int,
    final_scores: dict[str, int],
    rounds_won: dict[str, int],
    winner_id: Optional[str] = None,
) -> GameEvent:
    """
    Create a GameEnded event.

    Emitted when all rounds are complete.

    Args:
        game_id: Game UUID.
        sequence_num: Event sequence number.
        final_scores: Map of player_id -> total score.
        rounds_won: Map of player_id -> rounds won count.
        winner_id: ID of overall winner (lowest total score).
    """
    return GameEvent(
        event_type=EventType.GAME_ENDED,
        game_id=game_id,
        sequence_num=sequence_num,
        data={
            "final_scores": final_scores,
            "rounds_won": rounds_won,
            "winner_id": winner_id,
        },
    )


def initial_flip(
    game_id: str,
    sequence_num: int,
    player_id: str,
    positions: list[int],
    cards: list[dict],
) -> GameEvent:
    """
    Create an InitialFlip event.

    Emitted when a player flips their initial cards at round start.

    Args:
        game_id: Game UUID.
        sequence_num: Event sequence number.
        player_id: Player who flipped.
        positions: Card positions that were flipped (0-5).
        cards: The cards that were revealed [{rank, suit}, ...].
    """
    return GameEvent(
        event_type=EventType.INITIAL_FLIP,
        game_id=game_id,
        sequence_num=sequence_num,
        player_id=player_id,
        data={
            "positions": positions,
            "cards": cards,
        },
    )


def card_drawn(
    game_id: str,
    sequence_num: int,
    player_id: str,
    source: str,
    card: dict,
) -> GameEvent:
    """
    Create a CardDrawn event.

    Emitted when a player draws a card from deck or discard.

    Args:
        game_id: Game UUID.
        sequence_num: Event sequence number.
        player_id: Player who drew.
        source: "deck" or "discard".
        card: The card drawn {rank, suit}.
    """
    return GameEvent(
        event_type=EventType.CARD_DRAWN,
        game_id=game_id,
        sequence_num=sequence_num,
        player_id=player_id,
        data={
            "source": source,
            "card": card,
        },
    )


def card_swapped(
    game_id: str,
    sequence_num: int,
    player_id: str,
    position: int,
    new_card: dict,
    old_card: dict,
) -> GameEvent:
    """
    Create a CardSwapped event.

    Emitted when a player swaps their drawn card with a hand card.

    Args:
        game_id: Game UUID.
        sequence_num: Event sequence number.
        player_id: Player who swapped.
        position: Hand position (0-5) where swap occurred.
        new_card: Card placed into hand {rank, suit}.
        old_card: Card removed from hand {rank, suit}.
    """
    return GameEvent(
        event_type=EventType.CARD_SWAPPED,
        game_id=game_id,
        sequence_num=sequence_num,
        player_id=player_id,
        data={
            "position": position,
            "new_card": new_card,
            "old_card": old_card,
        },
    )


def card_discarded(
    game_id: str,
    sequence_num: int,
    player_id: str,
    card: dict,
) -> GameEvent:
    """
    Create a CardDiscarded event.

    Emitted when a player discards their drawn card without swapping.

    Args:
        game_id: Game UUID.
        sequence_num: Event sequence number.
        player_id: Player who discarded.
        card: The card discarded {rank, suit}.
    """
    return GameEvent(
        event_type=EventType.CARD_DISCARDED,
        game_id=game_id,
        sequence_num=sequence_num,
        player_id=player_id,
        data={"card": card},
    )


def card_flipped(
    game_id: str,
    sequence_num: int,
    player_id: str,
    position: int,
    card: dict,
) -> GameEvent:
    """
    Create a CardFlipped event.

    Emitted when a player flips a card after discarding (flip_on_discard mode).

    Args:
        game_id: Game UUID.
        sequence_num: Event sequence number.
        player_id: Player who flipped.
        position: Position of flipped card (0-5).
        card: The card revealed {rank, suit}.
    """
    return GameEvent(
        event_type=EventType.CARD_FLIPPED,
        game_id=game_id,
        sequence_num=sequence_num,
        player_id=player_id,
        data={
            "position": position,
            "card": card,
        },
    )


def flip_skipped(
    game_id: str,
    sequence_num: int,
    player_id: str,
) -> GameEvent:
    """
    Create a FlipSkipped event.

    Emitted when a player skips the optional flip (endgame mode).

    Args:
        game_id: Game UUID.
        sequence_num: Event sequence number.
        player_id: Player who skipped.
    """
    return GameEvent(
        event_type=EventType.FLIP_SKIPPED,
        game_id=game_id,
        sequence_num=sequence_num,
        player_id=player_id,
        data={},
    )


def flip_as_action(
    game_id: str,
    sequence_num: int,
    player_id: str,
    position: int,
    card: dict,
) -> GameEvent:
    """
    Create a FlipAsAction event.

    Emitted when a player uses their turn to flip a card (house rule).

    Args:
        game_id: Game UUID.
        sequence_num: Event sequence number.
        player_id: Player who used flip-as-action.
        position: Position of flipped card (0-5).
        card: The card revealed {rank, suit}.
    """
    return GameEvent(
        event_type=EventType.FLIP_AS_ACTION,
        game_id=game_id,
        sequence_num=sequence_num,
        player_id=player_id,
        data={
            "position": position,
            "card": card,
        },
    )


def knock_early(
    game_id: str,
    sequence_num: int,
    player_id: str,
    positions: list[int],
    cards: list[dict],
) -> GameEvent:
    """
    Create a KnockEarly event.

    Emitted when a player knocks early to reveal remaining cards.

    Args:
        game_id: Game UUID.
        sequence_num: Event sequence number.
        player_id: Player who knocked.
        positions: Positions of cards that were face-down.
        cards: The cards revealed [{rank, suit}, ...].
    """
    return GameEvent(
        event_type=EventType.KNOCK_EARLY,
        game_id=game_id,
        sequence_num=sequence_num,
        player_id=player_id,
        data={
            "positions": positions,
            "cards": cards,
        },
    )
