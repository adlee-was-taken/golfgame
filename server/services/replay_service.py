"""
Replay service for Golf game.

Provides game replay functionality, share link generation, and game export/import.
Leverages the event-sourced architecture for perfect game reconstruction.
"""

import json
import logging
import secrets
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from typing import Optional, List

import asyncpg

from stores.event_store import EventStore
from models.events import GameEvent, EventType
from models.game_state import rebuild_state, RebuiltGameState, CardState

logger = logging.getLogger(__name__)


# SQL schema for replay/sharing tables
REPLAY_SCHEMA_SQL = """
-- Public share links for completed games
CREATE TABLE IF NOT EXISTS shared_games (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id UUID NOT NULL,
    share_code VARCHAR(12) UNIQUE NOT NULL,
    created_by VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    view_count INTEGER DEFAULT 0,
    is_public BOOLEAN DEFAULT true,
    title VARCHAR(100),
    description TEXT
);

CREATE INDEX IF NOT EXISTS idx_shared_games_code ON shared_games(share_code);
CREATE INDEX IF NOT EXISTS idx_shared_games_game ON shared_games(game_id);

-- Track replay views for analytics
CREATE TABLE IF NOT EXISTS replay_views (
    id SERIAL PRIMARY KEY,
    shared_game_id UUID REFERENCES shared_games(id),
    viewer_id VARCHAR(50),
    viewed_at TIMESTAMPTZ DEFAULT NOW(),
    ip_hash VARCHAR(64),
    watch_duration_seconds INTEGER
);

CREATE INDEX IF NOT EXISTS idx_replay_views_shared ON replay_views(shared_game_id);
"""


@dataclass
class ReplayFrame:
    """Single frame in a replay."""
    event_index: int
    event_type: str
    event_data: dict
    game_state: dict
    timestamp: float  # Seconds from start
    player_id: Optional[str] = None


@dataclass
class GameReplay:
    """Complete replay of a game."""
    game_id: str
    frames: List[ReplayFrame]
    total_duration_seconds: float
    player_names: List[str]
    final_scores: dict
    winner: Optional[str]
    options: dict
    room_code: str
    total_rounds: int


class ReplayService:
    """
    Service for game replay, export, and sharing.

    Provides:
    - Replay building from event store
    - Share link creation and retrieval
    - Game export/import
    """

    EXPORT_VERSION = "1.0"

    def __init__(self, pool: asyncpg.Pool, event_store: EventStore):
        """
        Initialize replay service.

        Args:
            pool: asyncpg connection pool.
            event_store: Event store for retrieving game events.
        """
        self.pool = pool
        self.event_store = event_store

    async def initialize_schema(self) -> None:
        """Create replay tables if they don't exist."""
        async with self.pool.acquire() as conn:
            await conn.execute(REPLAY_SCHEMA_SQL)
        logger.info("Replay schema initialized")

    # -------------------------------------------------------------------------
    # Replay Building
    # -------------------------------------------------------------------------

    async def build_replay(self, game_id: str) -> GameReplay:
        """
        Build complete replay from event store.

        Args:
            game_id: Game UUID.

        Returns:
            GameReplay with all frames and metadata.

        Raises:
            ValueError: If no events found for game.
        """
        events = await self.event_store.get_events(game_id)
        if not events:
            raise ValueError(f"No events found for game {game_id}")

        frames = []
        state = RebuiltGameState(game_id=game_id)
        start_time = None

        for i, event in enumerate(events):
            if start_time is None:
                start_time = event.timestamp

            # Apply event to get state
            state.apply(event)

            # Calculate timestamp relative to start
            elapsed = (event.timestamp - start_time).total_seconds()

            frames.append(ReplayFrame(
                event_index=i,
                event_type=event.event_type.value,
                event_data=event.data,
                game_state=self._state_to_dict(state),
                timestamp=elapsed,
                player_id=event.player_id,
            ))

        # Extract final game info
        player_names = [p.name for p in state.players.values()]
        final_scores = {p.name: p.total_score for p in state.players.values()}

        # Determine winner (lowest total score)
        winner = None
        if state.phase.value == "game_over" and state.players:
            winner_player = min(state.players.values(), key=lambda p: p.total_score)
            winner = winner_player.name

        return GameReplay(
            game_id=game_id,
            frames=frames,
            total_duration_seconds=frames[-1].timestamp if frames else 0,
            player_names=player_names,
            final_scores=final_scores,
            winner=winner,
            options=state.options,
            room_code=state.room_code,
            total_rounds=state.total_rounds,
        )

    async def get_replay_frame(
        self,
        game_id: str,
        frame_index: int
    ) -> Optional[ReplayFrame]:
        """
        Get a specific frame from a replay.

        Useful for seeking to a specific point without loading entire replay.

        Args:
            game_id: Game UUID.
            frame_index: Index of frame to retrieve (0-based).

        Returns:
            ReplayFrame or None if index out of range.
        """
        events = await self.event_store.get_events(
            game_id,
            from_sequence=1,
            to_sequence=frame_index + 1
        )

        if not events or len(events) <= frame_index:
            return None

        state = RebuiltGameState(game_id=game_id)
        start_time = events[0].timestamp if events else None

        for event in events:
            state.apply(event)

        last_event = events[-1]
        elapsed = (last_event.timestamp - start_time).total_seconds() if start_time else 0

        return ReplayFrame(
            event_index=frame_index,
            event_type=last_event.event_type.value,
            event_data=last_event.data,
            game_state=self._state_to_dict(state),
            timestamp=elapsed,
            player_id=last_event.player_id,
        )

    def _state_to_dict(self, state: RebuiltGameState) -> dict:
        """Convert RebuiltGameState to serializable dict."""
        players = []
        for pid in state.player_order:
            if pid in state.players:
                p = state.players[pid]
                players.append({
                    "id": p.id,
                    "name": p.name,
                    "cards": [c.to_dict() for c in p.cards],
                    "score": p.score,
                    "total_score": p.total_score,
                    "rounds_won": p.rounds_won,
                    "is_cpu": p.is_cpu,
                    "all_face_up": p.all_face_up(),
                })

        return {
            "phase": state.phase.value,
            "players": players,
            "current_player_idx": state.current_player_idx,
            "current_player_id": state.player_order[state.current_player_idx] if state.player_order else None,
            "deck_remaining": state.deck_remaining,
            "discard_pile": [c.to_dict() for c in state.discard_pile],
            "discard_top": state.discard_pile[-1].to_dict() if state.discard_pile else None,
            "drawn_card": state.drawn_card.to_dict() if state.drawn_card else None,
            "current_round": state.current_round,
            "total_rounds": state.total_rounds,
            "finisher_id": state.finisher_id,
            "options": state.options,
        }

    # -------------------------------------------------------------------------
    # Share Links
    # -------------------------------------------------------------------------

    async def create_share_link(
        self,
        game_id: str,
        user_id: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        expires_days: Optional[int] = None,
    ) -> str:
        """
        Generate shareable link for a game.

        Args:
            game_id: Game UUID.
            user_id: ID of user creating the share.
            title: Optional custom title.
            description: Optional description.
            expires_days: Days until link expires (None = never).

        Returns:
            12-character share code.
        """
        share_code = secrets.token_urlsafe(9)[:12]

        expires_at = None
        if expires_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)

        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO shared_games
                    (game_id, share_code, created_by, title, description, expires_at)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, game_id, share_code, user_id, title, description, expires_at)

        logger.info(f"Created share link {share_code} for game {game_id}")
        return share_code

    async def get_shared_game(self, share_code: str) -> Optional[dict]:
        """
        Retrieve shared game by code.

        Args:
            share_code: 12-character share code.

        Returns:
            Shared game metadata dict, or None if not found/expired.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT sg.*, g.room_code, g.completed_at, g.num_players, g.num_rounds
                FROM shared_games sg
                JOIN games_v2 g ON sg.game_id = g.id
                WHERE sg.share_code = $1
                  AND sg.is_public = true
                  AND (sg.expires_at IS NULL OR sg.expires_at > NOW())
            """, share_code)

            if row:
                # Increment view count
                await conn.execute("""
                    UPDATE shared_games SET view_count = view_count + 1
                    WHERE share_code = $1
                """, share_code)

                return dict(row)
        return None

    async def record_replay_view(
        self,
        shared_game_id: str,
        viewer_id: Optional[str] = None,
        ip_hash: Optional[str] = None,
        duration_seconds: Optional[int] = None,
    ) -> None:
        """
        Record a replay view for analytics.

        Args:
            shared_game_id: UUID of the shared_games record.
            viewer_id: Optional user ID of viewer.
            ip_hash: Optional hashed IP for rate limiting.
            duration_seconds: Optional watch duration.
        """
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO replay_views
                    (shared_game_id, viewer_id, ip_hash, watch_duration_seconds)
                VALUES ($1, $2, $3, $4)
            """, shared_game_id, viewer_id, ip_hash, duration_seconds)

    async def get_user_shared_games(self, user_id: str) -> List[dict]:
        """
        Get all shared games created by a user.

        Args:
            user_id: User ID.

        Returns:
            List of shared game metadata dicts.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT sg.*, g.room_code, g.completed_at
                FROM shared_games sg
                JOIN games_v2 g ON sg.game_id = g.id
                WHERE sg.created_by = $1
                ORDER BY sg.created_at DESC
            """, user_id)
            return [dict(row) for row in rows]

    async def delete_share_link(self, share_code: str, user_id: str) -> bool:
        """
        Delete a share link.

        Args:
            share_code: Share code to delete.
            user_id: User requesting deletion (must be creator).

        Returns:
            True if deleted, False if not found or not authorized.
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM shared_games
                WHERE share_code = $1 AND created_by = $2
            """, share_code, user_id)
            return result == "DELETE 1"

    # -------------------------------------------------------------------------
    # Export/Import
    # -------------------------------------------------------------------------

    async def export_game(self, game_id: str) -> dict:
        """
        Export game as portable JSON format.

        Args:
            game_id: Game UUID.

        Returns:
            Export data dict suitable for JSON serialization.
        """
        replay = await self.build_replay(game_id)

        # Get raw events for export
        events = await self.event_store.get_events(game_id)
        start_time = events[0].timestamp if events else datetime.now(timezone.utc)

        return {
            "version": self.EXPORT_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "game": {
                "id": replay.game_id,
                "room_code": replay.room_code,
                "players": replay.player_names,
                "winner": replay.winner,
                "final_scores": replay.final_scores,
                "duration_seconds": replay.total_duration_seconds,
                "total_rounds": replay.total_rounds,
                "options": replay.options,
            },
            "events": [
                {
                    "type": event.event_type.value,
                    "sequence": event.sequence_num,
                    "player_id": event.player_id,
                    "data": event.data,
                    "timestamp": (event.timestamp - start_time).total_seconds(),
                }
                for event in events
            ],
        }

    async def import_game(self, export_data: dict, user_id: str) -> str:
        """
        Import a game from exported JSON.

        Creates a new game record with the imported events.

        Args:
            export_data: Exported game data.
            user_id: User performing the import.

        Returns:
            New game ID.

        Raises:
            ValueError: If export format is invalid.
        """
        version = export_data.get("version")
        if version != self.EXPORT_VERSION:
            raise ValueError(f"Unsupported export version: {version}")

        if "events" not in export_data or not export_data["events"]:
            raise ValueError("Export contains no events")

        # Generate new game ID
        import uuid
        new_game_id = str(uuid.uuid4())

        # Calculate base timestamp
        base_time = datetime.now(timezone.utc)

        # Import events with new game ID
        events = []
        for event_data in export_data["events"]:
            event = GameEvent(
                event_type=EventType(event_data["type"]),
                game_id=new_game_id,
                sequence_num=event_data["sequence"],
                player_id=event_data.get("player_id"),
                data=event_data["data"],
                timestamp=base_time + timedelta(seconds=event_data.get("timestamp", 0)),
            )
            events.append(event)

        # Batch insert events
        await self.event_store.append_batch(events)

        # Create game metadata record
        game_info = export_data.get("game", {})
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO games_v2
                    (id, room_code, status, num_rounds, options, completed_at)
                VALUES ($1, $2, 'imported', $3, $4, NOW())
            """,
                new_game_id,
                f"IMP-{secrets.token_hex(2).upper()}",  # Generate room code for imported games
                game_info.get("total_rounds", 1),
                json.dumps(game_info.get("options", {})),
            )

        logger.info(f"Imported game as {new_game_id} by user {user_id}")
        return new_game_id

    # -------------------------------------------------------------------------
    # Game History Queries
    # -------------------------------------------------------------------------

    async def get_user_game_history(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> List[dict]:
        """
        Get game history for a user.

        Args:
            user_id: User ID.
            limit: Max games to return.
            offset: Pagination offset.

        Returns:
            List of game summary dicts.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT g.id, g.room_code, g.status, g.completed_at,
                       g.num_players, g.num_rounds, g.winner_id,
                       $1 = ANY(g.player_ids) as participated
                FROM games_v2 g
                WHERE $1 = ANY(g.player_ids)
                  AND g.status IN ('completed', 'imported')
                ORDER BY g.completed_at DESC NULLS LAST
                LIMIT $2 OFFSET $3
            """, user_id, limit, offset)

            return [dict(row) for row in rows]

    async def can_view_game(self, user_id: Optional[str], game_id: str) -> bool:
        """
        Check if user can view a game replay.

        Users can view games they played in or games that are shared publicly.

        Args:
            user_id: User ID (None for anonymous).
            game_id: Game UUID.

        Returns:
            True if user can view the game.
        """
        async with self.pool.acquire() as conn:
            # Check if user played in the game
            if user_id:
                row = await conn.fetchrow("""
                    SELECT 1 FROM games_v2
                    WHERE id = $1 AND $2 = ANY(player_ids)
                """, game_id, user_id)
                if row:
                    return True

            # Check if game has a public share link
            row = await conn.fetchrow("""
                SELECT 1 FROM shared_games
                WHERE game_id = $1
                  AND is_public = true
                  AND (expires_at IS NULL OR expires_at > NOW())
            """, game_id)
            return row is not None


# Global instance
_replay_service: Optional[ReplayService] = None


async def get_replay_service(pool: asyncpg.Pool, event_store: EventStore) -> ReplayService:
    """Get or create the replay service instance."""
    global _replay_service
    if _replay_service is None:
        _replay_service = ReplayService(pool, event_store)
        await _replay_service.initialize_schema()
    return _replay_service


def set_replay_service(service: ReplayService) -> None:
    """Set the global replay service instance."""
    global _replay_service
    _replay_service = service


def close_replay_service() -> None:
    """Close the replay service."""
    global _replay_service
    _replay_service = None
