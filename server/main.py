"""FastAPI WebSocket server for Golf card game."""

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Header
from fastapi.responses import FileResponse
from pydantic import BaseModel
import redis.asyncio as redis

from config import config
from room import RoomManager, Room
from game import GamePhase, GameOptions
from ai import GolfAI, process_cpu_turn, get_all_profiles
from game_log import get_logger

# Import production components
from logging_config import setup_logging

# Configure logging based on environment
setup_logging(
    level=config.LOG_LEVEL,
    environment=config.ENVIRONMENT,
)
logger = logging.getLogger(__name__)


# =============================================================================
# Auth & Admin & Stats Services (initialized in lifespan)
# =============================================================================

_user_store = None
_auth_service = None
_admin_service = None
_stats_service = None
_replay_service = None
_spectator_manager = None
_leaderboard_refresh_task = None
_redis_client = None
_rate_limiter = None
_shutdown_event = asyncio.Event()


async def _periodic_leaderboard_refresh():
    """Periodic task to refresh the leaderboard materialized view."""
    import asyncio
    while True:
        try:
            await asyncio.sleep(300)  # 5 minutes
            if _stats_service:
                await _stats_service.refresh_leaderboard()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Leaderboard refresh failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for async service initialization."""
    global _user_store, _auth_service, _admin_service, _stats_service, _replay_service
    global _spectator_manager, _leaderboard_refresh_task, _redis_client, _rate_limiter

    # Note: Uvicorn handles SIGINT/SIGTERM and triggers lifespan cleanup automatically

    # Initialize Redis client (for rate limiting, health checks, etc.)
    if config.REDIS_URL:
        try:
            _redis_client = redis.from_url(config.REDIS_URL, decode_responses=False)
            await _redis_client.ping()
            logger.info("Redis client connected")

            # Initialize rate limiter
            if config.RATE_LIMIT_ENABLED:
                from services.ratelimit import get_rate_limiter
                _rate_limiter = await get_rate_limiter(_redis_client)
                logger.info("Rate limiter initialized")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e} - rate limiting disabled")
            _redis_client = None
            _rate_limiter = None

    # Initialize auth, admin, and stats services (requires PostgreSQL)
    if config.POSTGRES_URL:
        try:
            from stores.user_store import get_user_store
            from stores.event_store import get_event_store
            from services.auth_service import get_auth_service
            from services.admin_service import get_admin_service
            from services.stats_service import StatsService, set_stats_service
            from routers.auth import set_auth_service
            from routers.admin import set_admin_service
            from routers.stats import set_stats_service as set_stats_router_service
            from routers.stats import set_auth_service as set_stats_auth_service

            logger.info("Initializing auth services...")
            _user_store = await get_user_store(config.POSTGRES_URL)
            _auth_service = await get_auth_service(_user_store)
            set_auth_service(_auth_service)
            logger.info("Auth services initialized successfully")

            # Initialize admin service
            logger.info("Initializing admin services...")
            _admin_service = await get_admin_service(
                pool=_user_store.pool,
                user_store=_user_store,
                state_cache=None,  # Will add Redis state cache when available
            )
            set_admin_service(_admin_service)
            logger.info("Admin services initialized successfully")

            # Initialize stats service
            logger.info("Initializing stats services...")
            _event_store = await get_event_store(config.POSTGRES_URL)
            _stats_service = StatsService(_user_store.pool, _event_store)
            set_stats_service(_stats_service)
            set_stats_router_service(_stats_service)
            set_stats_auth_service(_auth_service)
            logger.info("Stats services initialized successfully")

            # Initialize replay service
            logger.info("Initializing replay services...")
            from services.replay_service import get_replay_service, set_replay_service
            from services.spectator import get_spectator_manager
            from routers.replay import (
                set_replay_service as set_replay_router_service,
                set_auth_service as set_replay_auth_service,
                set_spectator_manager as set_replay_spectator,
                set_room_manager as set_replay_room_manager,
            )
            _replay_service = await get_replay_service(_user_store.pool, _event_store)
            _spectator_manager = get_spectator_manager()
            set_replay_service(_replay_service)
            set_replay_router_service(_replay_service)
            set_replay_auth_service(_auth_service)
            set_replay_spectator(_spectator_manager)
            set_replay_room_manager(room_manager)
            logger.info("Replay services initialized successfully")

            # Start periodic leaderboard refresh task
            _leaderboard_refresh_task = asyncio.create_task(_periodic_leaderboard_refresh())
            logger.info("Leaderboard refresh task started")

        except Exception as e:
            logger.error(f"Failed to initialize services: {e}")
            raise
    else:
        logger.warning("POSTGRES_URL not configured - auth/admin/stats endpoints will not work")

    # Set up health check dependencies
    from routers.health import set_health_dependencies
    db_pool = _user_store.pool if _user_store else None
    set_health_dependencies(
        db_pool=db_pool,
        redis_client=_redis_client,
        room_manager=room_manager,
    )

    logger.info(f"Golf server started (environment={config.ENVIRONMENT})")

    yield

    # Graceful shutdown
    logger.info("Shutdown initiated...")

    # Signal shutdown to all components
    _shutdown_event.set()

    # Close all WebSocket connections gracefully
    await _close_all_websockets()

    # Cancel background tasks
    if _leaderboard_refresh_task:
        _leaderboard_refresh_task.cancel()
        try:
            await _leaderboard_refresh_task
        except asyncio.CancelledError:
            pass
        logger.info("Leaderboard refresh task stopped")

    if _replay_service:
        from services.replay_service import close_replay_service
        close_replay_service()

    if _spectator_manager:
        from services.spectator import close_spectator_manager
        close_spectator_manager()

    if _stats_service:
        from services.stats_service import close_stats_service
        close_stats_service()

    if _user_store:
        from stores.user_store import close_user_store
        from services.admin_service import close_admin_service
        close_admin_service()
        await close_user_store()

    # Close Redis connection
    if _redis_client:
        await _redis_client.close()
        logger.info("Redis connection closed")

    logger.info("Shutdown complete")


async def _close_all_websockets():
    """Close all active WebSocket connections gracefully."""
    for room in list(room_manager.rooms.values()):
        for player in room.players.values():
            if player.websocket and not player.is_cpu:
                try:
                    await player.websocket.close(code=1001, reason="Server shutting down")
                except Exception:
                    pass
    logger.info("All WebSocket connections closed")


app = FastAPI(
    title="Golf Card Game",
    debug=config.DEBUG,
    version="0.1.0",
    lifespan=lifespan,
)


# =============================================================================
# Middleware Setup (order matters: first added = outermost)
# =============================================================================

# Request ID middleware (outermost - generates/propagates request IDs)
from middleware.request_id import RequestIDMiddleware
app.add_middleware(RequestIDMiddleware)

# Security headers middleware
from middleware.security import SecurityHeadersMiddleware
app.add_middleware(
    SecurityHeadersMiddleware,
    environment=config.ENVIRONMENT,
)

# Note: Rate limiting middleware is added after app startup when Redis is available
# See _add_rate_limit_middleware() called from a startup event if needed

room_manager = RoomManager()

# Initialize game logger database at startup
_game_logger = get_logger()
logger.info(f"Game analytics database initialized at: {_game_logger.db_path}")


# =============================================================================
# Routers
# =============================================================================

from routers.auth import router as auth_router
from routers.admin import router as admin_router
from routers.stats import router as stats_router
from routers.replay import router as replay_router
from routers.health import router as health_router
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(stats_router)
app.include_router(replay_router)
app.include_router(health_router)


# =============================================================================
# Auth Dependencies (for use in other routes)
# =============================================================================

from models.user import User


async def get_current_user(authorization: Optional[str] = Header(None)) -> Optional[User]:
    """Get current user from Authorization header."""
    if not authorization or not _auth_service:
        return None

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    token = parts[1]
    return await _auth_service.get_user_from_token(token)


async def require_user(user: Optional[User] = Depends(get_current_user)) -> User:
    """Require authenticated user."""
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    return user


async def require_admin(user: User = Depends(require_user)) -> User:
    """Require admin user."""
    if not user.is_admin():
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    player_id = str(uuid.uuid4())
    current_room: Room | None = None

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "create_room":
                player_name = data.get("player_name", "Player")
                room = room_manager.create_room()
                room.add_player(player_id, player_name, websocket)
                current_room = room

                await websocket.send_json({
                    "type": "room_created",
                    "room_code": room.code,
                    "player_id": player_id,
                })

                await room.broadcast({
                    "type": "player_joined",
                    "players": room.player_list(),
                })

            elif msg_type == "join_room":
                room_code = data.get("room_code", "").upper()
                player_name = data.get("player_name", "Player")

                room = room_manager.get_room(room_code)
                if not room:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Room not found",
                    })
                    continue

                if len(room.players) >= 6:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Room is full",
                    })
                    continue

                if room.game.phase != GamePhase.WAITING:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Game already in progress",
                    })
                    continue

                room.add_player(player_id, player_name, websocket)
                current_room = room

                await websocket.send_json({
                    "type": "room_joined",
                    "room_code": room.code,
                    "player_id": player_id,
                })

                await room.broadcast({
                    "type": "player_joined",
                    "players": room.player_list(),
                })

            elif msg_type == "get_cpu_profiles":
                if not current_room:
                    continue

                await websocket.send_json({
                    "type": "cpu_profiles",
                    "profiles": get_all_profiles(),
                })

            elif msg_type == "add_cpu":
                if not current_room:
                    continue

                room_player = current_room.get_player(player_id)
                if not room_player or not room_player.is_host:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Only the host can add CPU players",
                    })
                    continue

                if len(current_room.players) >= 6:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Room is full",
                    })
                    continue

                cpu_id = f"cpu_{uuid.uuid4().hex[:8]}"
                profile_name = data.get("profile_name")

                cpu_player = current_room.add_cpu_player(cpu_id, profile_name)
                if not cpu_player:
                    await websocket.send_json({
                        "type": "error",
                        "message": "CPU profile not available",
                    })
                    continue

                await current_room.broadcast({
                    "type": "player_joined",
                    "players": current_room.player_list(),
                })

            elif msg_type == "remove_cpu":
                if not current_room:
                    continue

                room_player = current_room.get_player(player_id)
                if not room_player or not room_player.is_host:
                    continue

                # Remove the last CPU player
                cpu_players = current_room.get_cpu_players()
                if cpu_players:
                    current_room.remove_player(cpu_players[-1].id)
                    await current_room.broadcast({
                        "type": "player_joined",
                        "players": current_room.player_list(),
                    })

            elif msg_type == "start_game":
                if not current_room:
                    continue

                room_player = current_room.get_player(player_id)
                if not room_player or not room_player.is_host:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Only the host can start the game",
                    })
                    continue

                if len(current_room.players) < 2:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Need at least 2 players",
                    })
                    continue

                num_decks = data.get("decks", 1)
                num_rounds = data.get("rounds", 1)

                # Build game options
                options = GameOptions(
                    # Standard options
                    flip_mode=data.get("flip_mode", "never"),
                    initial_flips=max(0, min(2, data.get("initial_flips", 2))),
                    knock_penalty=data.get("knock_penalty", False),
                    use_jokers=data.get("use_jokers", False),
                    # House Rules - Point Modifiers
                    lucky_swing=data.get("lucky_swing", False),
                    super_kings=data.get("super_kings", False),
                    ten_penny=data.get("ten_penny", False),
                    # House Rules - Bonuses/Penalties
                    knock_bonus=data.get("knock_bonus", False),
                    underdog_bonus=data.get("underdog_bonus", False),
                    tied_shame=data.get("tied_shame", False),
                    blackjack=data.get("blackjack", False),
                    eagle_eye=data.get("eagle_eye", False),
                    wolfpack=data.get("wolfpack", False),
                    # House Rules - New Variants
                    flip_as_action=data.get("flip_as_action", False),
                    four_of_a_kind=data.get("four_of_a_kind", False),
                    negative_pairs_keep_value=data.get("negative_pairs_keep_value", False),
                    one_eyed_jacks=data.get("one_eyed_jacks", False),
                    knock_early=data.get("knock_early", False),
                )

                # Validate settings
                num_decks = max(1, min(3, num_decks))
                num_rounds = max(1, min(18, num_rounds))

                current_room.game.start_game(num_decks, num_rounds, options)

                # Log game start for AI analysis
                logger = get_logger()
                current_room.game_log_id = logger.log_game_start(
                    room_code=current_room.code,
                    num_players=len(current_room.players),
                    options=options,
                )

                # CPU players do their initial flips immediately (if required)
                if options.initial_flips > 0:
                    for cpu in current_room.get_cpu_players():
                        positions = GolfAI.choose_initial_flips(options.initial_flips)
                        current_room.game.flip_initial_cards(cpu.id, positions)

                # Send game started to all human players with their personal view
                for pid, player in current_room.players.items():
                    if player.websocket and not player.is_cpu:
                        game_state = current_room.game.get_state(pid)
                        await player.websocket.send_json({
                            "type": "game_started",
                            "game_state": game_state,
                        })

                # Check if it's a CPU's turn to start
                await check_and_run_cpu_turn(current_room)

            elif msg_type == "flip_initial":
                if not current_room:
                    continue

                positions = data.get("positions", [])
                if current_room.game.flip_initial_cards(player_id, positions):
                    await broadcast_game_state(current_room)

                    # Check if it's a CPU's turn
                    await check_and_run_cpu_turn(current_room)

            elif msg_type == "draw":
                if not current_room:
                    continue

                source = data.get("source", "deck")
                # Capture discard top before draw (for logging decision context)
                discard_before_draw = current_room.game.discard_top()
                card = current_room.game.draw_card(player_id, source)

                if card:
                    # Log draw decision for human player
                    if current_room.game_log_id:
                        game_logger = get_logger()
                        player = current_room.game.get_player(player_id)
                        if player:
                            reason = f"took {discard_before_draw.rank.value} from discard" if source == "discard" else "drew from deck"
                            game_logger.log_move(
                                game_id=current_room.game_log_id,
                                player=player,
                                is_cpu=False,
                                action="take_discard" if source == "discard" else "draw_deck",
                                card=card,
                                game=current_room.game,
                                decision_reason=reason,
                            )

                    # Send drawn card only to the player who drew
                    await websocket.send_json({
                        "type": "card_drawn",
                        "card": card.to_dict(reveal=True),
                        "source": source,
                    })

                    await broadcast_game_state(current_room)

            elif msg_type == "swap":
                if not current_room:
                    continue

                position = data.get("position", 0)
                # Capture drawn card before swap for logging
                drawn_card = current_room.game.drawn_card
                player = current_room.game.get_player(player_id)
                old_card = player.cards[position] if player and 0 <= position < len(player.cards) else None

                discarded = current_room.game.swap_card(player_id, position)

                if discarded:
                    # Log swap decision for human player
                    if current_room.game_log_id and drawn_card and player:
                        game_logger = get_logger()
                        old_rank = old_card.rank.value if old_card else "?"
                        game_logger.log_move(
                            game_id=current_room.game_log_id,
                            player=player,
                            is_cpu=False,
                            action="swap",
                            card=drawn_card,
                            position=position,
                            game=current_room.game,
                            decision_reason=f"swapped {drawn_card.rank.value} into position {position}, replaced {old_rank}",
                        )

                    await broadcast_game_state(current_room)
                    await check_and_run_cpu_turn(current_room)

            elif msg_type == "discard":
                if not current_room:
                    continue

                # Capture drawn card before discard for logging
                drawn_card = current_room.game.drawn_card
                player = current_room.game.get_player(player_id)

                if current_room.game.discard_drawn(player_id):
                    # Log discard decision for human player
                    if current_room.game_log_id and drawn_card and player:
                        game_logger = get_logger()
                        game_logger.log_move(
                            game_id=current_room.game_log_id,
                            player=player,
                            is_cpu=False,
                            action="discard",
                            card=drawn_card,
                            game=current_room.game,
                            decision_reason=f"discarded {drawn_card.rank.value}",
                        )

                    await broadcast_game_state(current_room)

                    if current_room.game.flip_on_discard:
                        # Check if player has face-down cards to flip
                        player = current_room.game.get_player(player_id)
                        has_face_down = player and any(not c.face_up for c in player.cards)

                        if has_face_down:
                            await websocket.send_json({
                                "type": "can_flip",
                                "optional": current_room.game.flip_is_optional,
                            })
                        else:
                            await check_and_run_cpu_turn(current_room)
                    else:
                        # Turn ended, check for CPU
                        await check_and_run_cpu_turn(current_room)

            elif msg_type == "flip_card":
                if not current_room:
                    continue

                position = data.get("position", 0)
                player = current_room.game.get_player(player_id)
                current_room.game.flip_and_end_turn(player_id, position)

                # Log flip decision for human player
                if current_room.game_log_id and player and 0 <= position < len(player.cards):
                    game_logger = get_logger()
                    flipped_card = player.cards[position]
                    game_logger.log_move(
                        game_id=current_room.game_log_id,
                        player=player,
                        is_cpu=False,
                        action="flip",
                        card=flipped_card,
                        position=position,
                        game=current_room.game,
                        decision_reason=f"flipped card at position {position}",
                    )

                await broadcast_game_state(current_room)
                await check_and_run_cpu_turn(current_room)

            elif msg_type == "skip_flip":
                if not current_room:
                    continue

                player = current_room.game.get_player(player_id)
                if current_room.game.skip_flip_and_end_turn(player_id):
                    # Log skip flip decision for human player
                    if current_room.game_log_id and player:
                        game_logger = get_logger()
                        game_logger.log_move(
                            game_id=current_room.game_log_id,
                            player=player,
                            is_cpu=False,
                            action="skip_flip",
                            card=None,
                            game=current_room.game,
                            decision_reason="skipped optional flip (endgame mode)",
                        )

                    await broadcast_game_state(current_room)
                    await check_and_run_cpu_turn(current_room)

            elif msg_type == "flip_as_action":
                if not current_room:
                    continue

                position = data.get("position", 0)
                player = current_room.game.get_player(player_id)
                if current_room.game.flip_card_as_action(player_id, position):
                    # Log flip-as-action for human player
                    if current_room.game_log_id and player and 0 <= position < len(player.cards):
                        game_logger = get_logger()
                        flipped_card = player.cards[position]
                        game_logger.log_move(
                            game_id=current_room.game_log_id,
                            player=player,
                            is_cpu=False,
                            action="flip_as_action",
                            card=flipped_card,
                            position=position,
                            game=current_room.game,
                            decision_reason=f"used flip-as-action to reveal position {position}",
                        )

                    await broadcast_game_state(current_room)
                    await check_and_run_cpu_turn(current_room)

            elif msg_type == "knock_early":
                if not current_room:
                    continue

                player = current_room.game.get_player(player_id)
                if current_room.game.knock_early(player_id):
                    # Log knock early for human player
                    if current_room.game_log_id and player:
                        game_logger = get_logger()
                        face_down_count = sum(1 for c in player.cards if not c.face_up)
                        game_logger.log_move(
                            game_id=current_room.game_log_id,
                            player=player,
                            is_cpu=False,
                            action="knock_early",
                            card=None,
                            game=current_room.game,
                            decision_reason=f"knocked early, revealing {face_down_count} hidden cards",
                        )

                    await broadcast_game_state(current_room)
                    await check_and_run_cpu_turn(current_room)

            elif msg_type == "next_round":
                if not current_room:
                    continue

                room_player = current_room.get_player(player_id)
                if not room_player or not room_player.is_host:
                    continue

                if current_room.game.start_next_round():
                    # CPU players do their initial flips
                    for cpu in current_room.get_cpu_players():
                        positions = GolfAI.choose_initial_flips()
                        current_room.game.flip_initial_cards(cpu.id, positions)

                    for pid, player in current_room.players.items():
                        if player.websocket and not player.is_cpu:
                            game_state = current_room.game.get_state(pid)
                            await player.websocket.send_json({
                                "type": "round_started",
                                "game_state": game_state,
                            })

                    await check_and_run_cpu_turn(current_room)
                else:
                    # Game over
                    await broadcast_game_state(current_room)

            elif msg_type == "leave_room":
                if current_room:
                    await handle_player_leave(current_room, player_id)
                    current_room = None

            elif msg_type == "leave_game":
                # Player leaves during an active game
                if current_room:
                    await handle_player_leave(current_room, player_id)
                    current_room = None

            elif msg_type == "end_game":
                # Host ends the game for everyone
                if not current_room:
                    continue

                room_player = current_room.get_player(player_id)
                if not room_player or not room_player.is_host:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Only the host can end the game",
                    })
                    continue

                # Notify all players that the game has ended
                await current_room.broadcast({
                    "type": "game_ended",
                    "reason": "Host ended the game",
                })

                # Clean up the room
                for cpu in list(current_room.get_cpu_players()):
                    current_room.remove_player(cpu.id)
                room_manager.remove_room(current_room.code)
                current_room = None

    except WebSocketDisconnect:
        if current_room:
            await handle_player_leave(current_room, player_id)


async def broadcast_game_state(room: Room):
    """Broadcast game state to all human players in a room."""
    # Notify spectators if spectator manager is available
    if _spectator_manager:
        spectator_state = room.game.get_state(None)  # No player perspective
        await _spectator_manager.send_game_state(room.code, spectator_state)

    for pid, player in room.players.items():
        # Skip CPU players
        if player.is_cpu or not player.websocket:
            continue

        game_state = room.game.get_state(pid)
        await player.websocket.send_json({
            "type": "game_state",
            "game_state": game_state,
        })

        # Check for round over
        if room.game.phase == GamePhase.ROUND_OVER:
            scores = [
                {"name": p.name, "score": p.score, "total": p.total_score, "rounds_won": p.rounds_won}
                for p in room.game.players
            ]
            # Build rankings
            by_points = sorted(scores, key=lambda x: x["total"])
            by_holes_won = sorted(scores, key=lambda x: -x["rounds_won"])
            await player.websocket.send_json({
                "type": "round_over",
                "scores": scores,
                "round": room.game.current_round,
                "total_rounds": room.game.num_rounds,
                "rankings": {
                    "by_points": by_points,
                    "by_holes_won": by_holes_won,
                },
            })

        # Check for game over
        elif room.game.phase == GamePhase.GAME_OVER:
            # Log game end
            if room.game_log_id:
                game_logger = get_logger()
                game_logger.log_game_end(room.game_log_id)
                room.game_log_id = None  # Clear to avoid duplicate logging

            # Process stats for authenticated players
            if _stats_service and room.game.players:
                try:
                    # Build mapping - for non-CPU players, the player_id is their user_id
                    # (assigned during authentication or as a session UUID)
                    player_user_ids = {}
                    for player_id, room_player in room.players.items():
                        if not room_player.is_cpu:
                            player_user_ids[player_id] = player_id

                    # Find winner
                    winner_id = None
                    if room.game.players:
                        winner = min(room.game.players, key=lambda p: p.total_score)
                        winner_id = winner.id

                    await _stats_service.process_game_from_state(
                        players=room.game.players,
                        winner_id=winner_id,
                        num_rounds=room.game.num_rounds,
                        player_user_ids=player_user_ids,
                    )
                except Exception as e:
                    logger.error(f"Failed to process game stats: {e}")

            scores = [
                {"name": p.name, "total": p.total_score, "rounds_won": p.rounds_won}
                for p in room.game.players
            ]
            by_points = sorted(scores, key=lambda x: x["total"])
            by_holes_won = sorted(scores, key=lambda x: -x["rounds_won"])
            await player.websocket.send_json({
                "type": "game_over",
                "final_scores": by_points,
                "rankings": {
                    "by_points": by_points,
                    "by_holes_won": by_holes_won,
                },
            })

        # Notify current player it's their turn (only if human)
        elif room.game.phase in (GamePhase.PLAYING, GamePhase.FINAL_TURN):
            current = room.game.current_player()
            if current and pid == current.id and not room.game.drawn_card:
                await player.websocket.send_json({
                    "type": "your_turn",
                })


async def check_and_run_cpu_turn(room: Room):
    """Check if current player is CPU and run their turn."""
    if room.game.phase not in (GamePhase.PLAYING, GamePhase.FINAL_TURN):
        return

    current = room.game.current_player()
    if not current:
        return

    room_player = room.get_player(current.id)
    if not room_player or not room_player.is_cpu:
        return

    # Run CPU turn
    async def broadcast_cb():
        await broadcast_game_state(room)

    await process_cpu_turn(room.game, current, broadcast_cb, game_id=room.game_log_id)

    # Check if next player is also CPU (chain CPU turns)
    await check_and_run_cpu_turn(room)


async def handle_player_leave(room: Room, player_id: str):
    """Handle a player leaving a room."""
    room_player = room.remove_player(player_id)

    # If no human players left, clean up the room entirely
    if room.is_empty() or room.human_player_count() == 0:
        # Remove all remaining CPU players to release their profiles
        for cpu in list(room.get_cpu_players()):
            room.remove_player(cpu.id)
        room_manager.remove_room(room.code)
    elif room_player:
        await room.broadcast({
            "type": "player_left",
            "player_id": player_id,
            "player_name": room_player.name,
            "players": room.player_list(),
        })


# Serve static files if client directory exists
client_path = os.path.join(os.path.dirname(__file__), "..", "client")
if os.path.exists(client_path):
    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(client_path, "index.html"))

    @app.get("/style.css")
    async def serve_css():
        return FileResponse(os.path.join(client_path, "style.css"), media_type="text/css")

    @app.get("/app.js")
    async def serve_js():
        return FileResponse(os.path.join(client_path, "app.js"), media_type="application/javascript")

    @app.get("/card-manager.js")
    async def serve_card_manager():
        return FileResponse(os.path.join(client_path, "card-manager.js"), media_type="application/javascript")

    @app.get("/state-differ.js")
    async def serve_state_differ():
        return FileResponse(os.path.join(client_path, "state-differ.js"), media_type="application/javascript")

    @app.get("/animation-queue.js")
    async def serve_animation_queue():
        return FileResponse(os.path.join(client_path, "animation-queue.js"), media_type="application/javascript")

    @app.get("/leaderboard.js")
    async def serve_leaderboard_js():
        return FileResponse(os.path.join(client_path, "leaderboard.js"), media_type="application/javascript")

    # Admin dashboard
    @app.get("/admin")
    async def serve_admin():
        return FileResponse(os.path.join(client_path, "admin.html"))

    @app.get("/admin.css")
    async def serve_admin_css():
        return FileResponse(os.path.join(client_path, "admin.css"), media_type="text/css")

    @app.get("/admin.js")
    async def serve_admin_js():
        return FileResponse(os.path.join(client_path, "admin.js"), media_type="application/javascript")

    @app.get("/replay.js")
    async def serve_replay_js():
        return FileResponse(os.path.join(client_path, "replay.js"), media_type="application/javascript")

    # Serve replay page for share links
    @app.get("/replay/{share_code}")
    async def serve_replay_page(share_code: str):
        return FileResponse(os.path.join(client_path, "index.html"))


def run():
    """Run the server using uvicorn."""
    import uvicorn

    logger.info(f"Starting Golf server on {config.HOST}:{config.PORT}")
    logger.info(f"Debug mode: {config.DEBUG}")

    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.DEBUG,
        log_level=config.LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    run()
