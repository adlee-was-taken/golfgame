"""
PostgreSQL-backed event store for Golf game.

The event store is an append-only log of all game events.
Events are immutable and ordered by sequence number within each game.

Features:
- Optimistic concurrency via unique constraint on (game_id, sequence_num)
- Batch appends for atomic multi-event writes
- Streaming for memory-efficient large game replay
- Game metadata table for efficient queries
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional, AsyncIterator

import asyncpg

from models.events import GameEvent, EventType

logger = logging.getLogger(__name__)


class ConcurrencyError(Exception):
    """Raised when optimistic concurrency check fails."""
    pass


# SQL schema for event store
SCHEMA_SQL = """
-- Events table (append-only log)
CREATE TABLE IF NOT EXISTS events (
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

-- Games metadata (denormalized for queries, not source of truth)
CREATE TABLE IF NOT EXISTS games_v2 (
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

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_events_game_seq ON events(game_id, sequence_num);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_player ON events(player_id) WHERE player_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);

CREATE INDEX IF NOT EXISTS idx_games_status ON games_v2(status);
CREATE INDEX IF NOT EXISTS idx_games_room ON games_v2(room_code) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_games_players ON games_v2 USING GIN(player_ids);
CREATE INDEX IF NOT EXISTS idx_games_completed ON games_v2(completed_at) WHERE status = 'completed';
"""


class EventStore:
    """
    PostgreSQL-backed event store.

    Provides methods for appending events and querying event history.
    Uses asyncpg for async database access.
    """

    def __init__(self, pool: asyncpg.Pool):
        """
        Initialize event store with connection pool.

        Args:
            pool: asyncpg connection pool.
        """
        self.pool = pool

    @classmethod
    async def create(cls, postgres_url: str) -> "EventStore":
        """
        Create an EventStore with a new connection pool.

        Args:
            postgres_url: PostgreSQL connection URL.

        Returns:
            Configured EventStore instance.
        """
        pool = await asyncpg.create_pool(postgres_url, min_size=2, max_size=10)
        store = cls(pool)
        await store.initialize_schema()
        return store

    async def initialize_schema(self) -> None:
        """Create database tables if they don't exist."""
        async with self.pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)
        logger.info("Event store schema initialized")

    async def close(self) -> None:
        """Close the connection pool."""
        await self.pool.close()

    # -------------------------------------------------------------------------
    # Event Writes
    # -------------------------------------------------------------------------

    async def append(self, event: GameEvent) -> int:
        """
        Append an event to the store.

        Args:
            event: The event to append.

        Returns:
            The database ID of the inserted event.

        Raises:
            ConcurrencyError: If sequence_num already exists for this game.
        """
        async with self.pool.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    """
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
        """
        Append multiple events atomically.

        All events are inserted in a single transaction.
        If any event fails (e.g., duplicate sequence), all are rolled back.

        Args:
            events: List of events to append.

        Returns:
            List of database IDs for inserted events.

        Raises:
            ConcurrencyError: If any sequence_num already exists.
        """
        if not events:
            return []

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                ids = []
                for event in events:
                    try:
                        row = await conn.fetchrow(
                            """
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
                    except asyncpg.UniqueViolationError:
                        raise ConcurrencyError(
                            f"Event {event.sequence_num} already exists for game {event.game_id}"
                        )
                return ids

    # -------------------------------------------------------------------------
    # Event Reads
    # -------------------------------------------------------------------------

    async def get_events(
        self,
        game_id: str,
        from_sequence: int = 0,
        to_sequence: Optional[int] = None,
    ) -> list[GameEvent]:
        """
        Get events for a game, optionally within a sequence range.

        Args:
            game_id: Game UUID.
            from_sequence: Start sequence (inclusive).
            to_sequence: End sequence (inclusive), or None for all.

        Returns:
            List of events in sequence order.
        """
        async with self.pool.acquire() as conn:
            if to_sequence is not None:
                rows = await conn.fetch(
                    """
                    SELECT event_type, game_id, sequence_num, player_id, event_data, created_at
                    FROM events
                    WHERE game_id = $1 AND sequence_num >= $2 AND sequence_num <= $3
                    ORDER BY sequence_num
                    """,
                    game_id,
                    from_sequence,
                    to_sequence,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT event_type, game_id, sequence_num, player_id, event_data, created_at
                    FROM events
                    WHERE game_id = $1 AND sequence_num >= $2
                    ORDER BY sequence_num
                    """,
                    game_id,
                    from_sequence,
                )

            return [self._row_to_event(row) for row in rows]

    async def get_latest_sequence(self, game_id: str) -> int:
        """
        Get the latest sequence number for a game.

        Args:
            game_id: Game UUID.

        Returns:
            Latest sequence number, or -1 if no events exist.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT COALESCE(MAX(sequence_num), -1) as seq
                FROM events
                WHERE game_id = $1
                """,
                game_id,
            )
            return row["seq"]

    async def stream_events(
        self,
        game_id: str,
        from_sequence: int = 0,
    ) -> AsyncIterator[GameEvent]:
        """
        Stream events for memory-efficient processing.

        Use this for replaying large games without loading all events into memory.

        Args:
            game_id: Game UUID.
            from_sequence: Start sequence (inclusive).

        Yields:
            Events in sequence order.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                async for row in conn.cursor(
                    """
                    SELECT event_type, game_id, sequence_num, player_id, event_data, created_at
                    FROM events
                    WHERE game_id = $1 AND sequence_num >= $2
                    ORDER BY sequence_num
                    """,
                    game_id,
                    from_sequence,
                ):
                    yield self._row_to_event(row)

    async def get_event_count(self, game_id: str) -> int:
        """
        Get the total number of events for a game.

        Args:
            game_id: Game UUID.

        Returns:
            Event count.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COUNT(*) as count FROM events WHERE game_id = $1",
                game_id,
            )
            return row["count"]

    # -------------------------------------------------------------------------
    # Game Metadata
    # -------------------------------------------------------------------------

    async def create_game(
        self,
        game_id: str,
        room_code: str,
        host_id: str,
        options: Optional[dict] = None,
    ) -> None:
        """
        Create a game metadata record.

        Args:
            game_id: Game UUID.
            room_code: 4-letter room code.
            host_id: Host player ID.
            options: GameOptions as dict.
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO games_v2 (id, room_code, host_id, options)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (id) DO NOTHING
                """,
                game_id,
                room_code,
                host_id,
                json.dumps(options) if options else None,
            )

    async def update_game_started(
        self,
        game_id: str,
        num_players: int,
        num_rounds: int,
        player_ids: list[str],
    ) -> None:
        """
        Update game metadata when game starts.

        Args:
            game_id: Game UUID.
            num_players: Number of players.
            num_rounds: Number of rounds.
            player_ids: List of player IDs.
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE games_v2
                SET started_at = NOW(), num_players = $2, num_rounds = $3, player_ids = $4
                WHERE id = $1
                """,
                game_id,
                num_players,
                num_rounds,
                player_ids,
            )

    async def update_game_completed(
        self,
        game_id: str,
        winner_id: Optional[str] = None,
    ) -> None:
        """
        Update game metadata when game completes.

        Args:
            game_id: Game UUID.
            winner_id: ID of the winner.
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE games_v2
                SET status = 'completed', completed_at = NOW(), winner_id = $2
                WHERE id = $1
                """,
                game_id,
                winner_id,
            )

    async def get_active_games(self) -> list[dict]:
        """
        Get all active games for recovery on server restart.

        Returns:
            List of active game metadata dicts.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, room_code, status, created_at, started_at, num_players,
                       num_rounds, options, host_id, player_ids
                FROM games_v2
                WHERE status = 'active'
                ORDER BY created_at DESC
                """
            )
            return [dict(row) for row in rows]

    async def get_game(self, game_id: str) -> Optional[dict]:
        """
        Get game metadata by ID.

        Args:
            game_id: Game UUID.

        Returns:
            Game metadata dict, or None if not found.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, room_code, status, created_at, started_at, completed_at,
                       num_players, num_rounds, options, winner_id, host_id, player_ids
                FROM games_v2
                WHERE id = $1
                """,
                game_id,
            )
            return dict(row) if row else None

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _row_to_event(self, row: asyncpg.Record) -> GameEvent:
        """Convert a database row to a GameEvent."""
        return GameEvent(
            event_type=EventType(row["event_type"]),
            game_id=str(row["game_id"]),
            sequence_num=row["sequence_num"],
            player_id=row["player_id"],
            data=json.loads(row["event_data"]) if row["event_data"] else {},
            timestamp=row["created_at"].replace(tzinfo=timezone.utc),
        )


# Global event store instance (initialized on first use)
_event_store: Optional[EventStore] = None


async def get_event_store(postgres_url: str) -> EventStore:
    """
    Get or create the global event store instance.

    Args:
        postgres_url: PostgreSQL connection URL.

    Returns:
        EventStore instance.
    """
    global _event_store
    if _event_store is None:
        _event_store = await EventStore.create(postgres_url)
    return _event_store


async def close_event_store() -> None:
    """Close the global event store connection pool."""
    global _event_store
    if _event_store is not None:
        await _event_store.close()
        _event_store = None
