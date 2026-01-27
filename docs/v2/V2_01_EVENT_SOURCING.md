# V2-01: Event Sourcing Infrastructure

## Overview

This document covers the foundational event sourcing system. All game actions will be stored as immutable events, enabling replay, audit trails, and stats aggregation.

**Dependencies:** None (this is the foundation)
**Dependents:** All other V2 documents

---

## Goals

1. Define event classes for all game actions
2. Create PostgreSQL event store
3. Implement dual-write (events + current mutations)
4. Build state rebuilder from events
5. Validate that event replay produces identical state

---

## Current State

The game currently uses direct mutation:

```python
# Current approach in game.py
def draw_card(self, player_id: str, source: str) -> Optional[Card]:
    card = self.deck.pop() if source == "deck" else self.discard.pop()
    self.drawn_card = card
    self.phase = GamePhase.PLAY
    return card
```

Move logging exists in `game_logger.py` but stores denormalized state snapshots, not replayable events.

---

## Event Design

### Base Event Class

```python
# server/models/events.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any
from enum import Enum
import uuid

class EventType(str, Enum):
    # Lifecycle
    GAME_CREATED = "game_created"
    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    GAME_STARTED = "game_started"
    ROUND_STARTED = "round_started"
    ROUND_ENDED = "round_ended"
    GAME_ENDED = "game_ended"

    # Gameplay
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
    """Base class for all game events."""
    event_type: EventType
    game_id: str
    sequence_num: int
    timestamp: datetime = field(default_factory=datetime.utcnow)
    player_id: Optional[str] = None
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type.value,
            "game_id": self.game_id,
            "sequence_num": self.sequence_num,
            "timestamp": self.timestamp.isoformat(),
            "player_id": self.player_id,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GameEvent":
        return cls(
            event_type=EventType(d["event_type"]),
            game_id=d["game_id"],
            sequence_num=d["sequence_num"],
            timestamp=datetime.fromisoformat(d["timestamp"]),
            player_id=d.get("player_id"),
            data=d.get("data", {}),
        )
```

### Lifecycle Events

```python
# Lifecycle event data structures

@dataclass
class GameCreatedData:
    room_code: str
    host_id: str
    options: dict  # GameOptions as dict

@dataclass
class PlayerJoinedData:
    player_name: str
    is_cpu: bool
    cpu_profile: Optional[str] = None

@dataclass
class GameStartedData:
    deck_seed: int  # For deterministic replay
    player_order: list[str]  # Player IDs in turn order
    num_decks: int
    num_rounds: int
    dealt_cards: dict[str, list[dict]]  # player_id -> cards dealt

@dataclass
class RoundStartedData:
    round_num: int
    deck_seed: int
    dealt_cards: dict[str, list[dict]]

@dataclass
class RoundEndedData:
    scores: dict[str, int]  # player_id -> score
    winner_id: Optional[str]
    final_hands: dict[str, list[dict]]  # For verification

@dataclass
class GameEndedData:
    final_scores: dict[str, int]  # player_id -> total score
    winner_id: str
    rounds_won: dict[str, int]
```

### Gameplay Events

```python
# Gameplay event data structures

@dataclass
class InitialFlipData:
    positions: list[int]
    cards: list[dict]  # The cards revealed

@dataclass
class CardDrawnData:
    source: str  # "deck" or "discard"
    card: dict  # Card drawn

@dataclass
class CardSwappedData:
    position: int
    new_card: dict  # Card placed (was drawn)
    old_card: dict  # Card removed (goes to discard)

@dataclass
class CardDiscardedData:
    card: dict  # Card discarded

@dataclass
class CardFlippedData:
    position: int
    card: dict  # Card revealed

@dataclass
class FlipAsActionData:
    position: int
    card: dict  # Card revealed

@dataclass
class KnockEarlyData:
    positions: list[int]  # Positions flipped
    cards: list[dict]  # Cards revealed
```

---

## Event Store Schema

```sql
-- migrations/versions/001_create_events.sql

-- Events table (append-only log)
CREATE TABLE events (
    id BIGSERIAL PRIMARY KEY,
    game_id UUID NOT NULL,
    sequence_num INT NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    player_id VARCHAR(50),
    event_data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Ensure events are ordered and unique per game
    UNIQUE(game_id, sequence_num)
);

-- Games metadata (for queries, not source of truth)
CREATE TABLE games_v2 (
    id UUID PRIMARY KEY,
    room_code VARCHAR(10) NOT NULL,
    status VARCHAR(20) DEFAULT 'active',  -- active, completed, abandoned
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    num_players INT,
    num_rounds INT,
    options JSONB,
    winner_id VARCHAR(50),
    host_id VARCHAR(50),

    -- Denormalized for efficient queries
    player_ids VARCHAR(50)[] DEFAULT '{}'
);

-- Indexes
CREATE INDEX idx_events_game_seq ON events(game_id, sequence_num);
CREATE INDEX idx_events_type ON events(event_type);
CREATE INDEX idx_events_player ON events(player_id) WHERE player_id IS NOT NULL;
CREATE INDEX idx_events_created ON events(created_at);

CREATE INDEX idx_games_status ON games_v2(status);
CREATE INDEX idx_games_room ON games_v2(room_code) WHERE status = 'active';
CREATE INDEX idx_games_players ON games_v2 USING GIN(player_ids);
CREATE INDEX idx_games_completed ON games_v2(completed_at) WHERE status = 'completed';
```

---

## Event Store Implementation

```python
# server/stores/event_store.py
from typing import Optional, AsyncIterator
from datetime import datetime
import asyncpg
import json

from models.events import GameEvent, EventType


class EventStore:
    """PostgreSQL-backed event store."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def append(self, event: GameEvent) -> int:
        """
        Append an event to the store.
        Returns the event ID.
        Raises if sequence_num already exists (optimistic concurrency).
        """
        async with self.pool.acquire() as conn:
            try:
                row = await conn.fetchrow("""
                    INSERT INTO events (game_id, sequence_num, event_type, player_id, event_data)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id
                """,
                    event.game_id,
                    event.sequence_num,
                    event.event_type.value,
                    event.player_id,
                    json.dumps(event.data),
                )
                return row["id"]
            except asyncpg.UniqueViolationError:
                raise ConcurrencyError(
                    f"Event {event.sequence_num} already exists for game {event.game_id}"
                )

    async def append_batch(self, events: list[GameEvent]) -> list[int]:
        """Append multiple events atomically."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                ids = []
                for event in events:
                    row = await conn.fetchrow("""
                        INSERT INTO events (game_id, sequence_num, event_type, player_id, event_data)
                        VALUES ($1, $2, $3, $4, $5)
                        RETURNING id
                    """,
                        event.game_id,
                        event.sequence_num,
                        event.event_type.value,
                        event.player_id,
                        json.dumps(event.data),
                    )
                    ids.append(row["id"])
                return ids

    async def get_events(
        self,
        game_id: str,
        from_sequence: int = 0,
        to_sequence: Optional[int] = None,
    ) -> list[GameEvent]:
        """Get events for a game, optionally within a sequence range."""
        async with self.pool.acquire() as conn:
            if to_sequence is not None:
                rows = await conn.fetch("""
                    SELECT event_type, game_id, sequence_num, player_id, event_data, created_at
                    FROM events
                    WHERE game_id = $1 AND sequence_num >= $2 AND sequence_num <= $3
                    ORDER BY sequence_num
                """, game_id, from_sequence, to_sequence)
            else:
                rows = await conn.fetch("""
                    SELECT event_type, game_id, sequence_num, player_id, event_data, created_at
                    FROM events
                    WHERE game_id = $1 AND sequence_num >= $2
                    ORDER BY sequence_num
                """, game_id, from_sequence)

            return [
                GameEvent(
                    event_type=EventType(row["event_type"]),
                    game_id=row["game_id"],
                    sequence_num=row["sequence_num"],
                    player_id=row["player_id"],
                    data=json.loads(row["event_data"]),
                    timestamp=row["created_at"],
                )
                for row in rows
            ]

    async def get_latest_sequence(self, game_id: str) -> int:
        """Get the latest sequence number for a game."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT COALESCE(MAX(sequence_num), -1) as seq
                FROM events
                WHERE game_id = $1
            """, game_id)
            return row["seq"]

    async def stream_events(
        self,
        game_id: str,
        from_sequence: int = 0,
    ) -> AsyncIterator[GameEvent]:
        """Stream events for memory-efficient processing."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                async for row in conn.cursor("""
                    SELECT event_type, game_id, sequence_num, player_id, event_data, created_at
                    FROM events
                    WHERE game_id = $1 AND sequence_num >= $2
                    ORDER BY sequence_num
                """, game_id, from_sequence):
                    yield GameEvent(
                        event_type=EventType(row["event_type"]),
                        game_id=row["game_id"],
                        sequence_num=row["sequence_num"],
                        player_id=row["player_id"],
                        data=json.loads(row["event_data"]),
                        timestamp=row["created_at"],
                    )


class ConcurrencyError(Exception):
    """Raised when optimistic concurrency check fails."""
    pass
```

---

## State Rebuilder

```python
# server/models/game_state.py
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

from models.events import GameEvent, EventType


class GamePhase(str, Enum):
    WAITING = "waiting"
    INITIAL_FLIP = "initial_flip"
    PLAYING = "playing"
    FINAL_TURN = "final_turn"
    ROUND_OVER = "round_over"
    GAME_OVER = "game_over"


@dataclass
class Card:
    rank: str
    suit: str
    face_up: bool = False

    def to_dict(self) -> dict:
        return {"rank": self.rank, "suit": self.suit, "face_up": self.face_up}

    @classmethod
    def from_dict(cls, d: dict) -> "Card":
        return cls(rank=d["rank"], suit=d["suit"], face_up=d.get("face_up", False))


@dataclass
class PlayerState:
    id: str
    name: str
    cards: list[Card] = field(default_factory=list)
    score: Optional[int] = None
    total_score: int = 0
    rounds_won: int = 0
    is_cpu: bool = False
    cpu_profile: Optional[str] = None


@dataclass
class RebuiltGameState:
    """Game state rebuilt from events."""
    game_id: str
    room_code: str = ""
    phase: GamePhase = GamePhase.WAITING
    players: dict[str, PlayerState] = field(default_factory=dict)
    player_order: list[str] = field(default_factory=list)
    current_player_idx: int = 0

    deck: list[Card] = field(default_factory=list)
    discard: list[Card] = field(default_factory=list)
    drawn_card: Optional[Card] = None

    current_round: int = 0
    total_rounds: int = 9
    options: dict = field(default_factory=dict)

    sequence_num: int = 0
    finisher_id: Optional[str] = None

    def apply(self, event: GameEvent) -> "RebuiltGameState":
        """
        Apply an event to produce new state.
        Returns self for chaining.
        """
        assert event.sequence_num == self.sequence_num + 1 or self.sequence_num == 0, \
            f"Expected sequence {self.sequence_num + 1}, got {event.sequence_num}"

        handler = getattr(self, f"_apply_{event.event_type.value}", None)
        if handler:
            handler(event)
        else:
            raise ValueError(f"Unknown event type: {event.event_type}")

        self.sequence_num = event.sequence_num
        return self

    def _apply_game_created(self, event: GameEvent):
        self.room_code = event.data["room_code"]
        self.options = event.data.get("options", {})
        self.players[event.data["host_id"]] = PlayerState(
            id=event.data["host_id"],
            name="Host",  # Will be updated by player_joined
        )

    def _apply_player_joined(self, event: GameEvent):
        self.players[event.player_id] = PlayerState(
            id=event.player_id,
            name=event.data["player_name"],
            is_cpu=event.data.get("is_cpu", False),
            cpu_profile=event.data.get("cpu_profile"),
        )

    def _apply_player_left(self, event: GameEvent):
        if event.player_id in self.players:
            del self.players[event.player_id]
        if event.player_id in self.player_order:
            self.player_order.remove(event.player_id)

    def _apply_game_started(self, event: GameEvent):
        self.player_order = event.data["player_order"]
        self.total_rounds = event.data["num_rounds"]
        self.current_round = 1
        self.phase = GamePhase.INITIAL_FLIP

        # Deal cards
        for player_id, cards_data in event.data["dealt_cards"].items():
            if player_id in self.players:
                self.players[player_id].cards = [
                    Card.from_dict(c) for c in cards_data
                ]

        # Rebuild deck from seed would go here for full determinism
        # For now, we trust the dealt_cards data

    def _apply_round_started(self, event: GameEvent):
        self.current_round = event.data["round_num"]
        self.phase = GamePhase.INITIAL_FLIP
        self.finisher_id = None
        self.drawn_card = None

        for player_id, cards_data in event.data["dealt_cards"].items():
            if player_id in self.players:
                self.players[player_id].cards = [
                    Card.from_dict(c) for c in cards_data
                ]
                self.players[player_id].score = None

    def _apply_initial_flip(self, event: GameEvent):
        player = self.players.get(event.player_id)
        if player:
            for pos, card_data in zip(event.data["positions"], event.data["cards"]):
                if 0 <= pos < len(player.cards):
                    player.cards[pos] = Card.from_dict(card_data)
                    player.cards[pos].face_up = True

        # Check if all players have flipped
        required = self.options.get("initial_flips", 2)
        all_flipped = all(
            sum(1 for c in p.cards if c.face_up) >= required
            for p in self.players.values()
        )
        if all_flipped and required > 0:
            self.phase = GamePhase.PLAYING

    def _apply_card_drawn(self, event: GameEvent):
        card = Card.from_dict(event.data["card"])
        card.face_up = True
        self.drawn_card = card

        if event.data["source"] == "discard" and self.discard:
            self.discard.pop()

    def _apply_card_swapped(self, event: GameEvent):
        player = self.players.get(event.player_id)
        if player and self.drawn_card:
            pos = event.data["position"]
            old_card = player.cards[pos]

            new_card = Card.from_dict(event.data["new_card"])
            new_card.face_up = True
            player.cards[pos] = new_card

            old_card.face_up = True
            self.discard.append(old_card)
            self.drawn_card = None

            self._advance_turn(player)

    def _apply_card_discarded(self, event: GameEvent):
        if self.drawn_card:
            self.discard.append(self.drawn_card)
            self.drawn_card = None

        player = self.players.get(event.player_id)
        if player:
            self._advance_turn(player)

    def _apply_card_flipped(self, event: GameEvent):
        player = self.players.get(event.player_id)
        if player:
            pos = event.data["position"]
            card = Card.from_dict(event.data["card"])
            card.face_up = True
            player.cards[pos] = card

            self._advance_turn(player)

    def _apply_flip_skipped(self, event: GameEvent):
        player = self.players.get(event.player_id)
        if player:
            self._advance_turn(player)

    def _apply_flip_as_action(self, event: GameEvent):
        player = self.players.get(event.player_id)
        if player:
            pos = event.data["position"]
            card = Card.from_dict(event.data["card"])
            card.face_up = True
            player.cards[pos] = card

            self._advance_turn(player)

    def _apply_knock_early(self, event: GameEvent):
        player = self.players.get(event.player_id)
        if player:
            for pos, card_data in zip(event.data["positions"], event.data["cards"]):
                card = Card.from_dict(card_data)
                card.face_up = True
                player.cards[pos] = card

            self._check_all_face_up(player)
            self._advance_turn(player)

    def _apply_round_ended(self, event: GameEvent):
        self.phase = GamePhase.ROUND_OVER
        for player_id, score in event.data["scores"].items():
            if player_id in self.players:
                self.players[player_id].score = score
                self.players[player_id].total_score += score

        winner_id = event.data.get("winner_id")
        if winner_id and winner_id in self.players:
            self.players[winner_id].rounds_won += 1

    def _apply_game_ended(self, event: GameEvent):
        self.phase = GamePhase.GAME_OVER

    def _advance_turn(self, player: PlayerState):
        """Advance to next player's turn."""
        self._check_all_face_up(player)

        if self.phase == GamePhase.ROUND_OVER:
            return

        self.current_player_idx = (self.current_player_idx + 1) % len(self.player_order)

        # Check if we've come back to finisher
        if self.finisher_id:
            current_id = self.player_order[self.current_player_idx]
            if current_id == self.finisher_id:
                self.phase = GamePhase.ROUND_OVER

    def _check_all_face_up(self, player: PlayerState):
        """Check if player has all cards face up (triggers final turn)."""
        if all(c.face_up for c in player.cards):
            if self.phase == GamePhase.PLAYING and not self.finisher_id:
                self.finisher_id = player.id
                self.phase = GamePhase.FINAL_TURN

    @property
    def current_player_id(self) -> Optional[str]:
        if self.player_order and 0 <= self.current_player_idx < len(self.player_order):
            return self.player_order[self.current_player_idx]
        return None


def rebuild_state(events: list[GameEvent]) -> RebuiltGameState:
    """Rebuild game state from a list of events."""
    if not events:
        raise ValueError("Cannot rebuild state from empty event list")

    state = RebuiltGameState(game_id=events[0].game_id)
    for event in events:
        state.apply(event)

    return state
```

---

## Dual-Write Integration

Modify existing game.py to emit events alongside mutations:

```python
# server/game.py additions

class Game:
    def __init__(self):
        # ... existing init ...
        self._event_emitter: Optional[Callable[[GameEvent], None]] = None
        self._sequence_num = 0

    def set_event_emitter(self, emitter: Callable[[GameEvent], None]):
        """Set callback for event emission."""
        self._event_emitter = emitter

    def _emit(self, event_type: EventType, player_id: Optional[str] = None, **data):
        """Emit an event if emitter is configured."""
        if self._event_emitter:
            self._sequence_num += 1
            event = GameEvent(
                event_type=event_type,
                game_id=self.game_id,
                sequence_num=self._sequence_num,
                player_id=player_id,
                data=data,
            )
            self._event_emitter(event)

    # Example: modify draw_card
    def draw_card(self, player_id: str, source: str) -> Optional[Card]:
        # ... existing validation ...

        if source == "deck":
            card = self.deck.pop()
        else:
            card = self.discard_pile.pop()

        self.drawn_card = card

        # NEW: Emit event
        self._emit(
            EventType.CARD_DRAWN,
            player_id=player_id,
            source=source,
            card=card.to_dict(),
        )

        return card
```

---

## Validation Test

```python
# server/tests/test_event_replay.py
import pytest
from game import Game, GameOptions
from models.events import GameEvent, rebuild_state


class TestEventReplay:
    """Verify that event replay produces identical state."""

    def test_full_game_replay(self):
        """Play a complete game and verify replay matches."""
        events = []

        def collect_events(event: GameEvent):
            events.append(event)

        # Play a real game
        game = Game()
        game.set_event_emitter(collect_events)

        game.add_player("p1", "Alice")
        game.add_player("p2", "Bob")
        game.start_game(num_decks=1, num_rounds=1, options=GameOptions())

        # Play through initial flips
        game.flip_initial_cards("p1", [0, 1])
        game.flip_initial_cards("p2", [0, 1])

        # Play some turns
        while game.phase not in (GamePhase.ROUND_OVER, GamePhase.GAME_OVER):
            current = game.current_player()
            if not current:
                break

            # Simple bot: always draw from deck and discard
            game.draw_card(current.id, "deck")
            game.discard_drawn(current.id)

            if len(events) > 100:  # Safety limit
                break

        # Get final state
        final_state = game.get_state("p1")

        # Rebuild from events
        rebuilt = rebuild_state(events)

        # Verify key state matches
        assert rebuilt.phase == game.phase
        assert rebuilt.current_round == game.current_round
        assert len(rebuilt.players) == len(game.players)

        for player_id, player in rebuilt.players.items():
            original = game.get_player(player_id)
            assert player.score == original.score
            assert player.total_score == original.total_score
            assert len(player.cards) == len(original.cards)

            for i, card in enumerate(player.cards):
                orig_card = original.cards[i]
                assert card.rank == orig_card.rank
                assert card.suit == orig_card.suit
                assert card.face_up == orig_card.face_up

    def test_partial_replay(self):
        """Verify we can replay to any point in the game."""
        events = []

        def collect_events(event: GameEvent):
            events.append(event)

        game = Game()
        game.set_event_emitter(collect_events)

        # ... setup and play ...

        # Replay only first N events
        for n in range(1, len(events) + 1):
            partial = rebuild_state(events[:n])
            assert partial.sequence_num == n

    def test_event_order_enforced(self):
        """Verify events must be applied in order."""
        events = []

        # ... collect some events ...

        state = RebuiltGameState(game_id="test")

        # Skip an event - should fail
        with pytest.raises(AssertionError):
            state.apply(events[1])  # Skipping events[0]
```

---

## Acceptance Criteria

1. **Event Classes Complete**
   - [ ] All lifecycle events defined (created, joined, left, started, ended)
   - [ ] All gameplay events defined (draw, swap, discard, flip, etc.)
   - [ ] Events are serializable to/from JSON
   - [ ] Events include all data needed for replay

2. **Event Store Working**
   - [ ] PostgreSQL schema created via migration
   - [ ] Can append single events
   - [ ] Can append batches atomically
   - [ ] Can retrieve events by game_id
   - [ ] Can retrieve events by sequence range
   - [ ] Concurrent writes to same sequence fail cleanly

3. **State Rebuilder Working**
   - [ ] Can rebuild state from any event sequence
   - [ ] Handles all event types
   - [ ] Enforces event ordering
   - [ ] Matches original game state exactly

4. **Dual-Write Enabled**
   - [ ] Game class has event emitter hook
   - [ ] All state-changing methods emit events
   - [ ] Events don't affect existing game behavior
   - [ ] Can be enabled/disabled via config

5. **Validation Tests Pass**
   - [ ] Full game replay test
   - [ ] Partial replay test
   - [ ] Event order enforcement test
   - [ ] At least 95% of games replay correctly

---

## Implementation Order

1. Create event dataclasses (`models/events.py`)
2. Create database migration for events table
3. Implement EventStore class
4. Implement RebuiltGameState class
5. Add event emitter to Game class
6. Add `_emit()` calls to all game methods
7. Write validation tests
8. Run tests until 100% pass

---

## Notes for Agent

- The existing `game.py` has good test coverage - don't break existing tests
- Start with lifecycle events, then gameplay events
- The deck seed is important for deterministic replay
- Consider edge cases: player disconnects, CPU players, house rules
- Events should be immutable - never modify after creation
