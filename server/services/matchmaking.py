"""
Matchmaking service for public skill-based games.

Uses Redis sorted sets to maintain a queue of players looking for games,
grouped by rating. A background task periodically scans the queue and
creates matches when enough similar-skill players are available.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class QueuedPlayer:
    """A player waiting in the matchmaking queue."""
    user_id: str
    username: str
    rating: float
    queued_at: float  # time.time()
    connection_id: str


@dataclass
class MatchmakingConfig:
    """Configuration for the matchmaking system."""
    enabled: bool = True
    min_players: int = 2
    max_players: int = 4
    initial_rating_window: int = 100  # +/- rating range to start
    expand_interval: int = 15  # seconds between range expansions
    expand_amount: int = 50  # rating points to expand by
    max_rating_window: int = 500  # maximum +/- range
    match_check_interval: float = 3.0  # seconds between match attempts
    countdown_seconds: int = 5  # countdown before matched game starts


class MatchmakingService:
    """
    Manages the matchmaking queue and creates matches.

    Players join the queue with their rating. A background task
    periodically scans for groups of similarly-rated players and
    creates games when matches are found.
    """

    def __init__(self, redis_client, config: Optional[MatchmakingConfig] = None):
        self.redis = redis_client
        self.config = config or MatchmakingConfig()
        self._queue: dict[str, QueuedPlayer] = {}  # user_id -> QueuedPlayer
        self._websockets: dict[str, WebSocket] = {}  # user_id -> WebSocket
        self._connection_ids: dict[str, str] = {}  # user_id -> connection_id
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def join_queue(
        self,
        user_id: str,
        username: str,
        rating: float,
        websocket: WebSocket,
        connection_id: str,
    ) -> dict:
        """
        Add a player to the matchmaking queue.

        Returns:
            Queue status dict.
        """
        if user_id in self._queue:
            return {"position": self._get_position(user_id), "queue_size": len(self._queue)}

        player = QueuedPlayer(
            user_id=user_id,
            username=username,
            rating=rating,
            queued_at=time.time(),
            connection_id=connection_id,
        )

        self._queue[user_id] = player
        self._websockets[user_id] = websocket
        self._connection_ids[user_id] = connection_id

        # Also add to Redis for persistence across restarts
        if self.redis:
            try:
                await self.redis.zadd("matchmaking:queue", {user_id: rating})
                await self.redis.hset(
                    "matchmaking:players",
                    user_id,
                    json.dumps({
                        "username": username,
                        "rating": rating,
                        "queued_at": player.queued_at,
                        "connection_id": connection_id,
                    }),
                )
            except Exception as e:
                logger.warning(f"Redis matchmaking write failed: {e}")

        position = self._get_position(user_id)
        logger.info(f"Player {username} ({user_id[:8]}) joined queue (rating={rating:.0f}, pos={position})")

        return {"position": position, "queue_size": len(self._queue)}

    async def leave_queue(self, user_id: str) -> bool:
        """Remove a player from the matchmaking queue."""
        if user_id not in self._queue:
            return False

        player = self._queue.pop(user_id, None)
        self._websockets.pop(user_id, None)
        self._connection_ids.pop(user_id, None)

        if self.redis:
            try:
                await self.redis.zrem("matchmaking:queue", user_id)
                await self.redis.hdel("matchmaking:players", user_id)
            except Exception as e:
                logger.warning(f"Redis matchmaking remove failed: {e}")

        if player:
            logger.info(f"Player {player.username} ({user_id[:8]}) left queue")

        return True

    async def get_queue_status(self, user_id: str) -> dict:
        """Get current queue status for a player."""
        if user_id not in self._queue:
            return {"in_queue": False}

        player = self._queue[user_id]
        wait_time = time.time() - player.queued_at
        current_window = self._get_rating_window(wait_time)

        return {
            "in_queue": True,
            "position": self._get_position(user_id),
            "queue_size": len(self._queue),
            "wait_time": int(wait_time),
            "rating_window": current_window,
        }

    async def find_matches(self, room_manager, broadcast_game_state_fn) -> list[dict]:
        """
        Scan the queue and create matches.

        Returns:
            List of match info dicts for matches created.
        """
        if len(self._queue) < self.config.min_players:
            return []

        matches_created = []
        matched_user_ids = set()

        # Sort players by rating
        sorted_players = sorted(self._queue.values(), key=lambda p: p.rating)

        for player in sorted_players:
            if player.user_id in matched_user_ids:
                continue

            wait_time = time.time() - player.queued_at
            window = self._get_rating_window(wait_time)

            # Find compatible players
            candidates = []
            for other in sorted_players:
                if other.user_id == player.user_id or other.user_id in matched_user_ids:
                    continue
                if abs(other.rating - player.rating) <= window:
                    candidates.append(other)

            # Include the player themselves
            group = [player] + candidates

            if len(group) >= self.config.min_players:
                # Take up to max_players
                match_group = group[:self.config.max_players]
                matched_user_ids.update(p.user_id for p in match_group)

                # Create the match
                match_info = await self._create_match(match_group, room_manager)
                if match_info:
                    matches_created.append(match_info)

        return matches_created

    async def _create_match(self, players: list[QueuedPlayer], room_manager) -> Optional[dict]:
        """
        Create a room for matched players and notify them.

        Returns:
            Match info dict, or None if creation failed.
        """
        try:
            # Create room
            room = room_manager.create_room()

            # Add all matched players to the room
            for player in players:
                ws = self._websockets.get(player.user_id)
                if not ws:
                    continue

                room.add_player(
                    player.connection_id,
                    player.username,
                    ws,
                    player.user_id,
                )

            # Remove matched players from queue
            for player in players:
                await self.leave_queue(player.user_id)

            # Notify all matched players
            match_info = {
                "room_code": room.code,
                "players": [
                    {"username": p.username, "rating": round(p.rating)}
                    for p in players
                ],
            }

            for player in players:
                ws = self._websockets.get(player.user_id)
                if ws:
                    try:
                        await ws.send_json({
                            "type": "queue_matched",
                            "room_code": room.code,
                            "players": match_info["players"],
                            "countdown": self.config.countdown_seconds,
                        })
                    except Exception as e:
                        logger.warning(f"Failed to notify matched player {player.user_id[:8]}: {e}")

            # Also send room_joined to each player so the client switches screens
            for player in players:
                ws = self._websockets.get(player.user_id)
                if ws:
                    try:
                        await ws.send_json({
                            "type": "room_joined",
                            "room_code": room.code,
                            "player_id": player.connection_id,
                            "authenticated": True,
                        })
                        # Send player list
                        await ws.send_json({
                            "type": "player_joined",
                            "players": room.player_list(),
                        })
                    except Exception:
                        pass

            avg_rating = sum(p.rating for p in players) / len(players)
            logger.info(
                f"Match created: room={room.code}, "
                f"players={[p.username for p in players]}, "
                f"avg_rating={avg_rating:.0f}"
            )

            # Schedule auto-start after countdown
            asyncio.create_task(self._auto_start_game(room, self.config.countdown_seconds))

            return match_info

        except Exception as e:
            logger.error(f"Failed to create match: {e}")
            return None

    async def _auto_start_game(self, room, countdown: int):
        """Auto-start a matched game after countdown."""
        from game import GamePhase, GameOptions

        await asyncio.sleep(countdown)

        if room.game.phase != GamePhase.WAITING:
            return  # Game already started or room closed

        if len(room.players) < 2:
            return  # Not enough players

        # Standard rules for ranked games
        options = GameOptions()
        options.flip_mode = "never"
        options.initial_flips = 2

        try:
            async with room.game_lock:
                room.game.start_game(1, 9, options)  # 1 deck, 9 rounds, standard rules

                # Send game started to all players
                for pid, rp in room.players.items():
                    if rp.websocket and not rp.is_cpu:
                        try:
                            state = room.game.get_state(pid)
                            await rp.websocket.send_json({
                                "type": "game_started",
                                "game_state": state,
                            })
                        except Exception:
                            pass

            logger.info(f"Auto-started matched game in room {room.code}")
        except Exception as e:
            logger.error(f"Failed to auto-start matched game: {e}")

    def _get_rating_window(self, wait_time: float) -> int:
        """Calculate the current rating window based on wait time."""
        expansions = int(wait_time / self.config.expand_interval)
        window = self.config.initial_rating_window + (expansions * self.config.expand_amount)
        return min(window, self.config.max_rating_window)

    def _get_position(self, user_id: str) -> int:
        """Get a player's position in the queue (1-indexed)."""
        sorted_ids = sorted(
            self._queue.keys(),
            key=lambda uid: self._queue[uid].queued_at,
        )
        try:
            return sorted_ids.index(user_id) + 1
        except ValueError:
            return 0

    async def start(self, room_manager, broadcast_fn):
        """Start the matchmaking background task."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(
            self._matchmaking_loop(room_manager, broadcast_fn)
        )
        logger.info("Matchmaking service started")

    async def stop(self):
        """Stop the matchmaking background task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Matchmaking service stopped")

    async def _matchmaking_loop(self, room_manager, broadcast_fn):
        """Background task that periodically checks for matches."""
        while self._running:
            try:
                matches = await self.find_matches(room_manager, broadcast_fn)
                if matches:
                    logger.info(f"Created {len(matches)} match(es)")

                # Send queue status updates to all queued players
                for user_id in list(self._queue.keys()):
                    ws = self._websockets.get(user_id)
                    if ws:
                        try:
                            status = await self.get_queue_status(user_id)
                            await ws.send_json({
                                "type": "queue_status",
                                **status,
                            })
                        except Exception:
                            # Player disconnected, remove from queue
                            await self.leave_queue(user_id)

            except Exception as e:
                logger.error(f"Matchmaking error: {e}")

            await asyncio.sleep(self.config.match_check_interval)

    async def cleanup(self):
        """Clean up Redis queue data on shutdown."""
        if self.redis:
            try:
                await self.redis.delete("matchmaking:queue")
                await self.redis.delete("matchmaking:players")
            except Exception:
                pass
