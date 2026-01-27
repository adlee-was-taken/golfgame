"""
Spectator manager for Golf game.

Enables spectators to watch live games in progress via WebSocket connections.
Spectators receive game state updates but cannot interact with the game.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime, timezone

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# Maximum spectators per game to prevent resource exhaustion
MAX_SPECTATORS_PER_GAME = 50


@dataclass
class SpectatorInfo:
    """Information about a spectator connection."""
    websocket: WebSocket
    joined_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    user_id: Optional[str] = None
    username: Optional[str] = None


class SpectatorManager:
    """
    Manage spectators watching live games.

    Spectators can join any active game and receive real-time updates.
    They see the same state as players but cannot take actions.
    """

    def __init__(self):
        # game_id -> list of SpectatorInfo
        self._spectators: Dict[str, List[SpectatorInfo]] = {}
        # websocket -> game_id (for reverse lookup on disconnect)
        self._ws_to_game: Dict[WebSocket, str] = {}

    async def add_spectator(
        self,
        game_id: str,
        websocket: WebSocket,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
    ) -> bool:
        """
        Add spectator to a game.

        Args:
            game_id: Game UUID.
            websocket: Spectator's WebSocket connection.
            user_id: Optional user ID.
            username: Optional display name.

        Returns:
            True if added, False if game is at spectator limit.
        """
        if game_id not in self._spectators:
            self._spectators[game_id] = []

        # Check spectator limit
        if len(self._spectators[game_id]) >= MAX_SPECTATORS_PER_GAME:
            logger.warning(f"Game {game_id} at spectator limit ({MAX_SPECTATORS_PER_GAME})")
            return False

        info = SpectatorInfo(
            websocket=websocket,
            user_id=user_id,
            username=username or "Spectator",
        )
        self._spectators[game_id].append(info)
        self._ws_to_game[websocket] = game_id

        logger.info(f"Spectator joined game {game_id} (total: {len(self._spectators[game_id])})")
        return True

    async def remove_spectator(self, game_id: str, websocket: WebSocket) -> None:
        """
        Remove spectator from a game.

        Args:
            game_id: Game UUID.
            websocket: Spectator's WebSocket connection.
        """
        if game_id in self._spectators:
            # Find and remove the spectator
            self._spectators[game_id] = [
                info for info in self._spectators[game_id]
                if info.websocket != websocket
            ]
            logger.info(f"Spectator left game {game_id} (remaining: {len(self._spectators[game_id])})")

            # Clean up empty games
            if not self._spectators[game_id]:
                del self._spectators[game_id]

        # Clean up reverse lookup
        self._ws_to_game.pop(websocket, None)

    async def remove_spectator_by_ws(self, websocket: WebSocket) -> None:
        """
        Remove spectator by WebSocket (for disconnect handling).

        Args:
            websocket: Spectator's WebSocket connection.
        """
        game_id = self._ws_to_game.get(websocket)
        if game_id:
            await self.remove_spectator(game_id, websocket)

    async def broadcast_to_spectators(self, game_id: str, message: dict) -> None:
        """
        Send update to all spectators of a game.

        Args:
            game_id: Game UUID.
            message: Message to broadcast.
        """
        if game_id not in self._spectators:
            return

        dead_connections: List[SpectatorInfo] = []

        for info in self._spectators[game_id]:
            try:
                await info.websocket.send_json(message)
            except Exception as e:
                logger.debug(f"Failed to send to spectator: {e}")
                dead_connections.append(info)

        # Clean up dead connections
        for info in dead_connections:
            self._spectators[game_id] = [
                s for s in self._spectators[game_id]
                if s.websocket != info.websocket
            ]
            self._ws_to_game.pop(info.websocket, None)

        # Clean up empty games
        if game_id in self._spectators and not self._spectators[game_id]:
            del self._spectators[game_id]

    async def send_game_state(
        self,
        game_id: str,
        game_state: dict,
        event_type: Optional[str] = None,
    ) -> None:
        """
        Send current game state to all spectators.

        Args:
            game_id: Game UUID.
            game_state: Current game state dict.
            event_type: Optional event type that triggered this update.
        """
        message = {
            "type": "game_state",
            "game_state": game_state,
            "spectator_count": self.get_spectator_count(game_id),
        }
        if event_type:
            message["event_type"] = event_type

        await self.broadcast_to_spectators(game_id, message)

    def get_spectator_count(self, game_id: str) -> int:
        """
        Get number of spectators for a game.

        Args:
            game_id: Game UUID.

        Returns:
            Spectator count.
        """
        return len(self._spectators.get(game_id, []))

    def get_spectator_usernames(self, game_id: str) -> list[str]:
        """
        Get list of spectator usernames.

        Args:
            game_id: Game UUID.

        Returns:
            List of spectator usernames.
        """
        if game_id not in self._spectators:
            return []
        return [
            info.username or "Anonymous"
            for info in self._spectators[game_id]
        ]

    def get_games_with_spectators(self) -> dict[str, int]:
        """
        Get all games that have spectators.

        Returns:
            Dict of game_id -> spectator count.
        """
        return {
            game_id: len(spectators)
            for game_id, spectators in self._spectators.items()
            if spectators
        }

    async def notify_game_ended(self, game_id: str, final_state: dict) -> None:
        """
        Notify spectators that a game has ended.

        Args:
            game_id: Game UUID.
            final_state: Final game state with scores.
        """
        await self.broadcast_to_spectators(game_id, {
            "type": "game_ended",
            "final_state": final_state,
        })

    async def close_all_for_game(self, game_id: str) -> None:
        """
        Close all spectator connections for a game.

        Use when a game is being cleaned up.

        Args:
            game_id: Game UUID.
        """
        if game_id not in self._spectators:
            return

        for info in list(self._spectators[game_id]):
            try:
                await info.websocket.close(code=1000, reason="Game ended")
            except Exception:
                pass
            self._ws_to_game.pop(info.websocket, None)

        del self._spectators[game_id]
        logger.info(f"Closed all spectators for game {game_id}")


# Global instance
_spectator_manager: Optional[SpectatorManager] = None


def get_spectator_manager() -> SpectatorManager:
    """Get the global spectator manager instance."""
    global _spectator_manager
    if _spectator_manager is None:
        _spectator_manager = SpectatorManager()
    return _spectator_manager


def close_spectator_manager() -> None:
    """Close the spectator manager."""
    global _spectator_manager
    _spectator_manager = None
