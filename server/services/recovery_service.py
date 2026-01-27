"""
Game recovery service for rebuilding active games from event store.

On server restart, all in-memory game state is lost. This service:
1. Queries the event store for active games
2. Rebuilds game state by replaying events
3. Caches the rebuilt state in Redis
4. Handles partial recovery (applying only new events to cached state)

This ensures games can survive server restarts without data loss.

Usage:
    recovery = RecoveryService(event_store, state_cache)
    results = await recovery.recover_all_games()
    print(f"Recovered {results['recovered']} games")
"""

import logging
from dataclasses import dataclass
from typing import Optional, Any

from stores.event_store import EventStore
from stores.state_cache import StateCache
from models.events import EventType
from models.game_state import RebuiltGameState, rebuild_state, CardState

logger = logging.getLogger(__name__)


@dataclass
class RecoveryResult:
    """Result of a game recovery attempt."""

    game_id: str
    room_code: str
    success: bool
    phase: Optional[str] = None
    sequence_num: int = 0
    error: Optional[str] = None


class RecoveryService:
    """
    Recovers games from event store on startup.

    Works with the event store (PostgreSQL) as source of truth
    and state cache (Redis) for fast access during gameplay.
    """

    def __init__(
        self,
        event_store: EventStore,
        state_cache: StateCache,
    ):
        """
        Initialize recovery service.

        Args:
            event_store: PostgreSQL event store.
            state_cache: Redis state cache.
        """
        self.event_store = event_store
        self.state_cache = state_cache

    async def recover_all_games(self) -> dict[str, Any]:
        """
        Recover all active games from event store.

        Queries PostgreSQL for active games and rebuilds their state
        from events, then caches in Redis.

        Returns:
            Dict with recovery statistics:
            - recovered: Number of games successfully recovered
            - failed: Number of games that failed recovery
            - skipped: Number of games skipped (already ended)
            - games: List of recovered game info
        """
        results = {
            "recovered": 0,
            "failed": 0,
            "skipped": 0,
            "games": [],
        }

        # Get active games from PostgreSQL
        active_games = await self.event_store.get_active_games()
        logger.info(f"Found {len(active_games)} active games to recover")

        for game_meta in active_games:
            game_id = str(game_meta["id"])
            room_code = game_meta["room_code"]

            try:
                result = await self.recover_game(game_id, room_code)

                if result.success:
                    results["recovered"] += 1
                    results["games"].append({
                        "game_id": game_id,
                        "room_code": room_code,
                        "phase": result.phase,
                        "sequence": result.sequence_num,
                    })
                else:
                    if result.error == "game_ended":
                        results["skipped"] += 1
                    else:
                        results["failed"] += 1
                        logger.warning(f"Failed to recover {game_id}: {result.error}")

            except Exception as e:
                logger.error(f"Error recovering game {game_id}: {e}", exc_info=True)
                results["failed"] += 1

        return results

    async def recover_game(
        self,
        game_id: str,
        room_code: Optional[str] = None,
    ) -> RecoveryResult:
        """
        Recover a single game from event store.

        Args:
            game_id: Game UUID.
            room_code: Room code (optional, will be read from events).

        Returns:
            RecoveryResult with success status and game info.
        """
        # Get all events for this game
        events = await self.event_store.get_events(game_id)

        if not events:
            return RecoveryResult(
                game_id=game_id,
                room_code=room_code or "",
                success=False,
                error="no_events",
            )

        # Check if game is actually active (not ended)
        last_event = events[-1]
        if last_event.event_type == EventType.GAME_ENDED:
            return RecoveryResult(
                game_id=game_id,
                room_code=room_code or "",
                success=False,
                error="game_ended",
            )

        # Rebuild state from events
        state = rebuild_state(events)

        # Get room code from state if not provided
        if not room_code:
            room_code = state.room_code

        # Convert state to cacheable dict
        state_dict = self._state_to_dict(state)

        # Save to Redis cache
        await self.state_cache.save_game_state(game_id, state_dict)

        # Also create/update room in cache
        await self._ensure_room_in_cache(state)

        logger.info(
            f"Recovered game {game_id} (room {room_code}) "
            f"at sequence {state.sequence_num}, phase {state.phase.value}"
        )

        return RecoveryResult(
            game_id=game_id,
            room_code=room_code,
            success=True,
            phase=state.phase.value,
            sequence_num=state.sequence_num,
        )

    async def recover_from_sequence(
        self,
        game_id: str,
        cached_state: dict,
        cached_sequence: int,
    ) -> Optional[dict]:
        """
        Recover game by applying only new events to cached state.

        More efficient than full rebuild when we have a recent cache.

        Args:
            game_id: Game UUID.
            cached_state: Previously cached state dict.
            cached_sequence: Sequence number of cached state.

        Returns:
            Updated state dict, or None if no new events.
        """
        # Get events after cached sequence
        new_events = await self.event_store.get_events(
            game_id,
            from_sequence=cached_sequence + 1,
        )

        if not new_events:
            return None  # No new events

        # Rebuild state from cache + new events
        state = self._dict_to_state(cached_state)
        for event in new_events:
            state.apply(event)

        # Convert back to dict
        new_state = self._state_to_dict(state)

        # Update cache
        await self.state_cache.save_game_state(game_id, new_state)

        return new_state

    async def _ensure_room_in_cache(self, state: RebuiltGameState) -> None:
        """
        Ensure room exists in Redis cache after recovery.

        Args:
            state: Rebuilt game state.
        """
        room_code = state.room_code
        if not room_code:
            return

        # Check if room already exists
        if await self.state_cache.room_exists(room_code):
            return

        # Create room in cache
        await self.state_cache.create_room(
            room_code=room_code,
            game_id=state.game_id,
            host_id=state.host_id or "",
            server_id="recovered",
        )

        # Set room status based on game phase
        if state.phase.value == "waiting":
            status = "waiting"
        elif state.phase.value in ("game_over", "round_over"):
            status = "finished"
        else:
            status = "playing"

        await self.state_cache.set_room_status(room_code, status)

    def _state_to_dict(self, state: RebuiltGameState) -> dict:
        """
        Convert RebuiltGameState to dict for caching.

        Args:
            state: Game state to convert.

        Returns:
            Cacheable dict representation.
        """
        return {
            "game_id": state.game_id,
            "room_code": state.room_code,
            "phase": state.phase.value,
            "current_round": state.current_round,
            "total_rounds": state.total_rounds,
            "current_player_idx": state.current_player_idx,
            "player_order": state.player_order,
            "players": {
                pid: {
                    "id": p.id,
                    "name": p.name,
                    "cards": [c.to_dict() for c in p.cards],
                    "score": p.score,
                    "total_score": p.total_score,
                    "rounds_won": p.rounds_won,
                    "is_cpu": p.is_cpu,
                    "cpu_profile": p.cpu_profile,
                }
                for pid, p in state.players.items()
            },
            "deck_remaining": state.deck_remaining,
            "discard_pile": [c.to_dict() for c in state.discard_pile],
            "discard_top": state.discard_pile[-1].to_dict() if state.discard_pile else None,
            "drawn_card": state.drawn_card.to_dict() if state.drawn_card else None,
            "drawn_from_discard": state.drawn_from_discard,
            "options": state.options,
            "sequence_num": state.sequence_num,
            "finisher_id": state.finisher_id,
            "host_id": state.host_id,
            "initial_flips_done": list(state.initial_flips_done),
            "players_with_final_turn": list(state.players_with_final_turn),
        }

    def _dict_to_state(self, d: dict) -> RebuiltGameState:
        """
        Convert dict back to RebuiltGameState.

        Args:
            d: Cached state dict.

        Returns:
            Reconstructed game state.
        """
        from models.game_state import GamePhase, PlayerState
        from game import GameOptions

        state = RebuiltGameState(game_id=d["game_id"])
        state.room_code = d.get("room_code", "")
        state.phase = GamePhase(d.get("phase", "waiting"))
        state.current_round = d.get("current_round", 0)
        state.total_rounds = d.get("total_rounds", 1)
        state.current_player_idx = d.get("current_player_idx", 0)
        state.player_order = d.get("player_order", [])
        state.deck_remaining = d.get("deck_remaining", 0)
        # Reconstruct GameOptions as proper object for attribute access
        options_dict = d.get("options", {})
        if isinstance(options_dict, dict):
            state.options = GameOptions(**options_dict)
        else:
            state.options = options_dict
        state.sequence_num = d.get("sequence_num", 0)
        state.finisher_id = d.get("finisher_id")
        state.host_id = d.get("host_id")
        state.initial_flips_done = set(d.get("initial_flips_done", []))
        state.players_with_final_turn = set(d.get("players_with_final_turn", []))
        state.drawn_from_discard = d.get("drawn_from_discard", False)

        # Rebuild players
        players_data = d.get("players", {})
        for pid, pdata in players_data.items():
            player = PlayerState(
                id=pdata["id"],
                name=pdata["name"],
                is_cpu=pdata.get("is_cpu", False),
                cpu_profile=pdata.get("cpu_profile"),
                score=pdata.get("score", 0),
                total_score=pdata.get("total_score", 0),
                rounds_won=pdata.get("rounds_won", 0),
            )
            player.cards = [CardState.from_dict(c) for c in pdata.get("cards", [])]
            state.players[pid] = player

        # Rebuild discard pile
        discard_data = d.get("discard_pile", [])
        state.discard_pile = [CardState.from_dict(c) for c in discard_data]

        # Rebuild drawn card
        drawn = d.get("drawn_card")
        if drawn:
            state.drawn_card = CardState.from_dict(drawn)

        return state
