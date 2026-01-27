"""
Redis-backed live game state cache.

The state cache stores live game state for fast access during gameplay.
Redis provides:
- Sub-millisecond reads/writes for active game state
- TTL expiration for abandoned games
- Pub/sub for multi-server synchronization
- Atomic operations via pipelines

This is a CACHE, not the source of truth. Events in PostgreSQL are authoritative.
If Redis data is lost, games can be recovered from the event store.

Key patterns:
- golf:room:{room_code}          -> Hash (room metadata)
- golf:game:{game_id}            -> JSON (full game state)
- golf:room:{room_code}:players  -> Set (connected player IDs)
- golf:rooms:active              -> Set (active room codes)
- golf:player:{player_id}:room   -> String (player's current room)
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class StateCache:
    """Redis-backed live game state cache."""

    # Key patterns
    ROOM_KEY = "golf:room:{room_code}"
    GAME_KEY = "golf:game:{game_id}"
    ROOM_PLAYERS_KEY = "golf:room:{room_code}:players"
    ACTIVE_ROOMS_KEY = "golf:rooms:active"
    PLAYER_ROOM_KEY = "golf:player:{player_id}:room"

    # TTLs - extended to 24 hours to prevent active games from expiring
    ROOM_TTL = timedelta(hours=24)  # Inactive rooms expire
    GAME_TTL = timedelta(hours=24)

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize state cache with Redis client.

        Args:
            redis_client: Async Redis client.
        """
        self.redis = redis_client

    @classmethod
    async def create(cls, redis_url: str) -> "StateCache":
        """
        Create a StateCache with a new Redis connection.

        Args:
            redis_url: Redis connection URL.

        Returns:
            Configured StateCache instance.
        """
        client = redis.from_url(redis_url, decode_responses=False)
        # Test connection
        await client.ping()
        logger.info("StateCache connected to Redis")
        return cls(client)

    async def close(self) -> None:
        """Close the Redis connection."""
        await self.redis.close()

    # -------------------------------------------------------------------------
    # Room Operations
    # -------------------------------------------------------------------------

    async def create_room(
        self,
        room_code: str,
        game_id: str,
        host_id: str,
        server_id: str = "default",
    ) -> None:
        """
        Create a new room.

        Args:
            room_code: 4-letter room code.
            game_id: UUID of the game.
            host_id: Player ID of the host.
            server_id: Server instance ID (for multi-server).
        """
        pipe = self.redis.pipeline()

        room_key = self.ROOM_KEY.format(room_code=room_code)
        now = datetime.now(timezone.utc).isoformat()

        # Room metadata
        pipe.hset(
            room_key,
            mapping={
                "game_id": game_id,
                "host_id": host_id,
                "status": "waiting",
                "server_id": server_id,
                "created_at": now,
            },
        )
        pipe.expire(room_key, int(self.ROOM_TTL.total_seconds()))

        # Add to active rooms
        pipe.sadd(self.ACTIVE_ROOMS_KEY, room_code)

        # Track host's room
        pipe.set(
            self.PLAYER_ROOM_KEY.format(player_id=host_id),
            room_code,
            ex=int(self.ROOM_TTL.total_seconds()),
        )

        await pipe.execute()
        logger.debug(f"Created room {room_code} with game {game_id}")

    async def get_room(self, room_code: str) -> Optional[dict]:
        """
        Get room metadata.

        Args:
            room_code: Room code to look up.

        Returns:
            Room metadata dict, or None if not found.
        """
        data = await self.redis.hgetall(self.ROOM_KEY.format(room_code=room_code))
        if not data:
            return None
        # Decode bytes to strings
        return {k.decode(): v.decode() for k, v in data.items()}

    async def room_exists(self, room_code: str) -> bool:
        """
        Check if a room exists.

        Args:
            room_code: Room code to check.

        Returns:
            True if room exists.
        """
        return await self.redis.exists(self.ROOM_KEY.format(room_code=room_code)) > 0

    async def delete_room(self, room_code: str) -> None:
        """
        Delete a room and all associated data.

        Args:
            room_code: Room code to delete.
        """
        room = await self.get_room(room_code)
        if not room:
            return

        pipe = self.redis.pipeline()

        # Get players to clean up their mappings
        players_key = self.ROOM_PLAYERS_KEY.format(room_code=room_code)
        players = await self.redis.smembers(players_key)
        for player_id in players:
            pid = player_id.decode() if isinstance(player_id, bytes) else player_id
            pipe.delete(self.PLAYER_ROOM_KEY.format(player_id=pid))

        # Delete room data
        pipe.delete(self.ROOM_KEY.format(room_code=room_code))
        pipe.delete(players_key)
        pipe.srem(self.ACTIVE_ROOMS_KEY, room_code)

        # Delete game state if exists
        if "game_id" in room:
            pipe.delete(self.GAME_KEY.format(game_id=room["game_id"]))

        await pipe.execute()
        logger.debug(f"Deleted room {room_code}")

    async def get_active_rooms(self) -> set[str]:
        """
        Get all active room codes.

        Returns:
            Set of active room codes.
        """
        rooms = await self.redis.smembers(self.ACTIVE_ROOMS_KEY)
        return {r.decode() if isinstance(r, bytes) else r for r in rooms}

    # -------------------------------------------------------------------------
    # Player Operations
    # -------------------------------------------------------------------------

    async def add_player_to_room(self, room_code: str, player_id: str) -> None:
        """
        Add a player to a room.

        Args:
            room_code: Room to add player to.
            player_id: Player to add.
        """
        pipe = self.redis.pipeline()
        pipe.sadd(self.ROOM_PLAYERS_KEY.format(room_code=room_code), player_id)
        pipe.set(
            self.PLAYER_ROOM_KEY.format(player_id=player_id),
            room_code,
            ex=int(self.ROOM_TTL.total_seconds()),
        )
        # Refresh room TTL on activity
        pipe.expire(
            self.ROOM_KEY.format(room_code=room_code),
            int(self.ROOM_TTL.total_seconds()),
        )
        await pipe.execute()

    async def remove_player_from_room(self, room_code: str, player_id: str) -> None:
        """
        Remove a player from a room.

        Args:
            room_code: Room to remove player from.
            player_id: Player to remove.
        """
        pipe = self.redis.pipeline()
        pipe.srem(self.ROOM_PLAYERS_KEY.format(room_code=room_code), player_id)
        pipe.delete(self.PLAYER_ROOM_KEY.format(player_id=player_id))
        await pipe.execute()

    async def get_room_players(self, room_code: str) -> set[str]:
        """
        Get player IDs in a room.

        Args:
            room_code: Room to query.

        Returns:
            Set of player IDs.
        """
        players = await self.redis.smembers(
            self.ROOM_PLAYERS_KEY.format(room_code=room_code)
        )
        return {p.decode() if isinstance(p, bytes) else p for p in players}

    async def get_player_room(self, player_id: str) -> Optional[str]:
        """
        Get the room a player is in.

        Args:
            player_id: Player to look up.

        Returns:
            Room code, or None if not in a room.
        """
        room = await self.redis.get(self.PLAYER_ROOM_KEY.format(player_id=player_id))
        if room is None:
            return None
        return room.decode() if isinstance(room, bytes) else room

    # -------------------------------------------------------------------------
    # Game State Operations
    # -------------------------------------------------------------------------

    async def save_game_state(self, game_id: str, state: dict) -> None:
        """
        Save full game state.

        Args:
            game_id: Game UUID.
            state: Game state dict (will be JSON serialized).
        """
        await self.redis.set(
            self.GAME_KEY.format(game_id=game_id),
            json.dumps(state),
            ex=int(self.GAME_TTL.total_seconds()),
        )

    async def get_game_state(self, game_id: str) -> Optional[dict]:
        """
        Get full game state.

        Args:
            game_id: Game UUID.

        Returns:
            Game state dict, or None if not found.
        """
        data = await self.redis.get(self.GAME_KEY.format(game_id=game_id))
        if not data:
            return None
        if isinstance(data, bytes):
            data = data.decode()
        return json.loads(data)

    async def update_game_state(self, game_id: str, updates: dict) -> None:
        """
        Partial update to game state (get, merge, set).

        Args:
            game_id: Game UUID.
            updates: Fields to update.
        """
        state = await self.get_game_state(game_id)
        if state:
            state.update(updates)
            await self.save_game_state(game_id, state)

    async def delete_game_state(self, game_id: str) -> None:
        """
        Delete game state.

        Args:
            game_id: Game UUID.
        """
        await self.redis.delete(self.GAME_KEY.format(game_id=game_id))

    # -------------------------------------------------------------------------
    # Room Status
    # -------------------------------------------------------------------------

    async def set_room_status(self, room_code: str, status: str) -> None:
        """
        Update room status.

        Args:
            room_code: Room to update.
            status: New status (waiting, playing, finished).
        """
        await self.redis.hset(
            self.ROOM_KEY.format(room_code=room_code),
            "status",
            status,
        )

    async def refresh_room_ttl(self, room_code: str) -> None:
        """
        Refresh room TTL on activity.

        Args:
            room_code: Room to refresh.
        """
        pipe = self.redis.pipeline()
        pipe.expire(
            self.ROOM_KEY.format(room_code=room_code),
            int(self.ROOM_TTL.total_seconds()),
        )

        room = await self.get_room(room_code)
        if room and "game_id" in room:
            pipe.expire(
                self.GAME_KEY.format(game_id=room["game_id"]),
                int(self.GAME_TTL.total_seconds()),
            )

        await pipe.execute()

    async def touch_game(self, game_id: str) -> None:
        """
        Refresh game TTL on any activity.

        Call this on game actions to prevent active games from expiring.

        Args:
            game_id: Game UUID to refresh.
        """
        key = self.GAME_KEY.format(game_id=game_id)
        await self.redis.expire(key, int(self.GAME_TTL.total_seconds()))


# Global state cache instance (initialized on first use)
_state_cache: Optional[StateCache] = None


async def get_state_cache(redis_url: str) -> StateCache:
    """
    Get or create the global state cache instance.

    Args:
        redis_url: Redis connection URL.

    Returns:
        StateCache instance.
    """
    global _state_cache
    if _state_cache is None:
        _state_cache = await StateCache.create(redis_url)
    return _state_cache


async def close_state_cache() -> None:
    """Close the global state cache connection."""
    global _state_cache
    if _state_cache is not None:
        await _state_cache.close()
        _state_cache = None
