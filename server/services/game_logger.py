"""
PostgreSQL-backed game logging for AI decision analysis.

Replaces SQLite game_log.py with unified event store integration.
Provides sync-compatible interface for existing callers (main.py, ai.py).

Usage:
    # Initialize in main.py lifespan
    from services.game_logger import GameLogger, set_logger
    game_logger = GameLogger(event_store)
    set_logger(game_logger)

    # Use in handlers
    from services.game_logger import get_logger
    logger = get_logger()
    if logger:
        logger.log_move(game_id, player, is_cpu=False, action="swap", ...)
"""

from dataclasses import asdict
from typing import Optional, TYPE_CHECKING
import asyncio
import uuid
import logging

if TYPE_CHECKING:
    from stores.event_store import EventStore
    from game import Card, Player, Game, GameOptions

log = logging.getLogger(__name__)


class GameLogger:
    """
    Logs game events and moves to PostgreSQL.

    Provides sync wrappers for compatibility with existing callers.
    Uses fire-and-forget async tasks to avoid blocking game logic.
    """

    def __init__(self, event_store: "EventStore"):
        """
        Initialize the game logger.

        Args:
            event_store: PostgreSQL event store instance.
        """
        self.event_store = event_store

    @staticmethod
    def _options_to_dict(options: "GameOptions") -> dict:
        """Convert GameOptions to dict for storage, excluding non-rule fields."""
        d = asdict(options)
        d.pop("deck_colors", None)
        return d

    # -------------------------------------------------------------------------
    # Game Lifecycle
    # -------------------------------------------------------------------------

    async def log_game_start_async(
        self,
        room_code: str,
        num_players: int,
        options: "GameOptions",
    ) -> str:
        """
        Log game start, return game_id.

        Creates a game record in games_v2 table.

        Args:
            room_code: Room code for the game.
            num_players: Number of players.
            options: Game options/house rules.

        Returns:
            Generated game UUID.
        """
        game_id = str(uuid.uuid4())

        try:
            await self.event_store.create_game(
                game_id=game_id,
                room_code=room_code,
                host_id="system",
                options=self._options_to_dict(options),
            )
            log.debug(f"Logged game start: {game_id} room={room_code}")
        except Exception as e:
            log.error(f"Failed to log game start: {e}")

        return game_id

    def log_game_start(
        self,
        room_code: str,
        num_players: int,
        options: "GameOptions",
    ) -> str:
        """
        Sync wrapper for log_game_start_async.

        In async context: fires task and returns generated ID immediately.
        In sync context: runs synchronously.
        """
        game_id = str(uuid.uuid4())

        try:
            loop = asyncio.get_running_loop()
            # Already in async context - fire task, return ID immediately
            asyncio.create_task(self._log_game_start_with_id(game_id, room_code, num_players, options))
            return game_id
        except RuntimeError:
            # Not in async context - run synchronously
            return asyncio.run(self.log_game_start_async(room_code, num_players, options))

    async def _log_game_start_with_id(
        self,
        game_id: str,
        room_code: str,
        num_players: int,
        options: "GameOptions",
    ) -> None:
        """Helper to log game start with pre-generated ID."""
        try:
            await self.event_store.create_game(
                game_id=game_id,
                room_code=room_code,
                host_id="system",
                options=self._options_to_dict(options),
            )
            log.debug(f"Logged game start: {game_id} room={room_code}")
        except Exception as e:
            log.error(f"Failed to log game start: {e}")

    async def log_game_end_async(self, game_id: str) -> None:
        """
        Mark game as ended.

        Args:
            game_id: Game UUID.
        """
        try:
            await self.event_store.update_game_completed(game_id)
            log.debug(f"Logged game end: {game_id}")
        except Exception as e:
            log.error(f"Failed to log game end: {e}")

    def log_game_end(self, game_id: str) -> None:
        """
        Sync wrapper for log_game_end_async.

        Fires async task in async context, skips in sync context.
        """
        if not game_id:
            return

        try:
            loop = asyncio.get_running_loop()
            asyncio.create_task(self.log_game_end_async(game_id))
        except RuntimeError:
            # Not in async context - skip (simulations don't need this)
            pass

    # -------------------------------------------------------------------------
    # Move Logging
    # -------------------------------------------------------------------------

    async def log_move_async(
        self,
        game_id: str,
        player: "Player",
        is_cpu: bool,
        action: str,
        card: Optional["Card"] = None,
        position: Optional[int] = None,
        game: Optional["Game"] = None,
        decision_reason: Optional[str] = None,
    ) -> None:
        """
        Log a move with AI context to PostgreSQL.

        Args:
            game_id: Game UUID.
            player: Player who made the move.
            is_cpu: Whether this is a CPU player.
            action: Action type (draw_deck, take_discard, swap, discard, flip, etc.).
            card: Card involved in the action.
            position: Hand position (0-5) for swaps/flips.
            game: Game instance for context capture.
            decision_reason: AI reasoning for the decision.
        """
        # Build AI context from game state
        hand_state = None
        discard_top = None
        visible_opponents = None

        if game:
            # Serialize player's hand
            hand_state = [
                {"rank": c.rank.value, "suit": c.suit.value, "face_up": c.face_up}
                for c in player.cards
            ]

            # Serialize discard top
            dt = game.discard_top()
            if dt:
                discard_top = {"rank": dt.rank.value, "suit": dt.suit.value}

            # Serialize visible opponent cards
            visible_opponents = {}
            for p in game.players:
                if p.id != player.id:
                    visible = [
                        {"rank": c.rank.value, "suit": c.suit.value}
                        for c in p.cards if c.face_up
                    ]
                    visible_opponents[p.name] = visible

        try:
            await self.event_store.append_move(
                game_id=game_id,
                player_id=player.id,
                player_name=player.name,
                is_cpu=is_cpu,
                action=action,
                card_rank=card.rank.value if card else None,
                card_suit=card.suit.value if card else None,
                position=position,
                hand_state=hand_state,
                discard_top=discard_top,
                visible_opponents=visible_opponents,
                decision_reason=decision_reason,
            )
        except Exception as e:
            log.error(f"Failed to log move: {e}")

    def log_move(
        self,
        game_id: str,
        player: "Player",
        is_cpu: bool,
        action: str,
        card: Optional["Card"] = None,
        position: Optional[int] = None,
        game: Optional["Game"] = None,
        decision_reason: Optional[str] = None,
    ) -> None:
        """
        Sync wrapper for log_move_async.

        Fires async task in async context. Does nothing if no game_id or not in async context.
        """
        if not game_id:
            return

        try:
            loop = asyncio.get_running_loop()
            asyncio.create_task(
                self.log_move_async(
                    game_id, player, is_cpu, action,
                    card=card, position=position, game=game, decision_reason=decision_reason
                )
            )
        except RuntimeError:
            # Not in async context - skip logging (simulations)
            pass


# -------------------------------------------------------------------------
# Global Instance Management
# -------------------------------------------------------------------------

_game_logger: Optional[GameLogger] = None


def get_logger() -> Optional[GameLogger]:
    """
    Get the global game logger instance.

    Returns:
        GameLogger if initialized, None otherwise.
    """
    return _game_logger


def set_logger(logger: GameLogger) -> None:
    """
    Set the global game logger instance.

    Called during application startup in main.py lifespan.

    Args:
        logger: GameLogger instance to use globally.
    """
    global _game_logger
    _game_logger = logger
    log.info("Game logger initialized with PostgreSQL backend")
