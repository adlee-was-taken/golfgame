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
from ai import GolfAI, process_cpu_turn, get_all_profiles, reset_all_profiles, cleanup_room_profiles
from services.game_logger import GameLogger, get_logger, set_logger

# Import production components
from logging_config import setup_logging

# Initialize Sentry if configured
if config.SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        sentry_sdk.init(
            dsn=config.SENTRY_DSN,
            environment=config.ENVIRONMENT,
            traces_sample_rate=0.1 if config.ENVIRONMENT == "production" else 1.0,
            integrations=[
                StarletteIntegration(transaction_style="endpoint"),
                FastApiIntegration(transaction_style="endpoint"),
            ],
        )
        logging.getLogger(__name__).info("Sentry error tracking initialized")
    except ImportError:
        logging.getLogger(__name__).warning("sentry-sdk not installed, error tracking disabled")

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

            # Initialize game logger (uses event_store for move logging)
            logger.info("Initializing game logger...")
            _game_logger = GameLogger(_event_store)
            set_logger(_game_logger)
            logger.info("Game logger initialized with PostgreSQL backend")

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

    # Clean up all rooms and release CPU profiles
    for room in list(room_manager.rooms.values()):
        for cpu in list(room.get_cpu_players()):
            room.remove_player(cpu.id)
    room_manager.rooms.clear()
    reset_all_profiles()
    logger.info("All rooms and CPU profiles cleaned up")

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
    version="2.0.1",
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

# Rate limiting middleware (uses global _rate_limiter set in lifespan)
# We create a wrapper that safely handles the case when rate limiter isn't ready
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class LazyRateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware that uses the global _rate_limiter when available."""

    async def dispatch(self, request, call_next):
        global _rate_limiter

        # Skip if rate limiter not initialized or disabled
        if not _rate_limiter or not config.RATE_LIMIT_ENABLED:
            return await call_next(request)

        # Import here to avoid circular imports
        from services.ratelimit import RATE_LIMITS

        path = request.url.path

        # Skip health checks and static files
        if path in ("/health", "/ready", "/metrics"):
            return await call_next(request)
        if path.endswith((".js", ".css", ".html", ".ico", ".png", ".jpg", ".svg")):
            return await call_next(request)

        # Determine rate limit tier
        if path.startswith("/api/auth"):
            limit, window = RATE_LIMITS["api_auth"]
        elif path == "/api/rooms" and request.method == "POST":
            limit, window = RATE_LIMITS["api_create_room"]
        elif "email" in path or "verify" in path:
            limit, window = RATE_LIMITS["email_send"]
        elif path.startswith("/api"):
            limit, window = RATE_LIMITS["api_general"]
        else:
            return await call_next(request)

        # Get client key and check rate limit
        client_key = _rate_limiter.get_client_key(request)
        full_key = f"{path}:{client_key}"

        allowed, info = await _rate_limiter.is_allowed(full_key, limit, window)

        if allowed:
            response = await call_next(request)
        else:
            response = JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "message": f"Too many requests. Please wait {info['reset']} seconds.",
                    "retry_after": info["reset"],
                },
            )

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
        response.headers["X-RateLimit-Reset"] = str(info["reset"])

        if not allowed:
            response.headers["Retry-After"] = str(info["reset"])

        return response


app.add_middleware(LazyRateLimitMiddleware)

room_manager = RoomManager()

# Game logger is initialized in lifespan after event_store is available
# The get_logger() function returns None until set_logger() is called


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


# =============================================================================
# Debug Endpoints (CPU Profile Management)
# =============================================================================

@app.get("/api/debug/cpu-profiles")
async def get_cpu_profile_status():
    """Get current CPU profile allocation status."""
    from ai import _room_used_profiles, _cpu_profiles, CPU_PROFILES
    return {
        "total_profiles": len(CPU_PROFILES),
        "room_profiles": {
            room_code: list(profiles)
            for room_code, profiles in _room_used_profiles.items()
        },
        "cpu_mappings": {
            cpu_id: {"room": room_code, "profile": profile.name}
            for cpu_id, (room_code, profile) in _cpu_profiles.items()
        },
        "active_rooms": len(room_manager.rooms),
        "rooms": {
            code: {
                "players": len(room.players),
                "cpu_players": [p.name for p in room.get_cpu_players()],
            }
            for code, room in room_manager.rooms.items()
        },
    }


@app.post("/api/debug/reset-cpu-profiles")
async def reset_cpu_profiles():
    """Reset all CPU profiles (emergency cleanup)."""
    reset_all_profiles()
    return {"status": "ok", "message": "All CPU profiles reset"}


MAX_CONCURRENT_GAMES = 4


def count_user_games(user_id: str) -> int:
    """Count how many games this authenticated user is currently in."""
    count = 0
    for room in room_manager.rooms.values():
        for player in room.players.values():
            if player.auth_user_id == user_id:
                count += 1
    return count


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    # Extract token from query param for optional authentication
    token = websocket.query_params.get("token")
    authenticated_user = None
    if token and _auth_service:
        try:
            authenticated_user = await _auth_service.get_user_from_token(token)
        except Exception as e:
            logger.debug(f"WebSocket auth failed: {e}")

    # Each connection gets a unique ID (allows multi-tab play)
    connection_id = str(uuid.uuid4())
    player_id = connection_id

    # Track auth user separately for stats/limits (can be None)
    auth_user_id = str(authenticated_user.id) if authenticated_user else None

    if authenticated_user:
        logger.debug(f"WebSocket authenticated as user {auth_user_id}, connection {connection_id}")
    else:
        logger.debug(f"WebSocket connected anonymously as {connection_id}")

    current_room: Room | None = None

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "create_room":
                # Check concurrent game limit for authenticated users
                if auth_user_id and count_user_games(auth_user_id) >= MAX_CONCURRENT_GAMES:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Maximum {MAX_CONCURRENT_GAMES} concurrent games allowed",
                    })
                    continue

                player_name = data.get("player_name", "Player")
                # Use authenticated user's name if available
                if authenticated_user and authenticated_user.display_name:
                    player_name = authenticated_user.display_name
                room = room_manager.create_room()
                room.add_player(player_id, player_name, websocket, auth_user_id)
                current_room = room

                await websocket.send_json({
                    "type": "room_created",
                    "room_code": room.code,
                    "player_id": player_id,
                    "authenticated": authenticated_user is not None,
                })

                await room.broadcast({
                    "type": "player_joined",
                    "players": room.player_list(),
                })

            elif msg_type == "join_room":
                room_code = data.get("room_code", "").upper()
                player_name = data.get("player_name", "Player")

                # Check concurrent game limit for authenticated users
                if auth_user_id and count_user_games(auth_user_id) >= MAX_CONCURRENT_GAMES:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Maximum {MAX_CONCURRENT_GAMES} concurrent games allowed",
                    })
                    continue

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

                # Use authenticated user's name if available
                if authenticated_user and authenticated_user.display_name:
                    player_name = authenticated_user.display_name
                room.add_player(player_id, player_name, websocket, auth_user_id)
                current_room = room

                await websocket.send_json({
                    "type": "room_joined",
                    "room_code": room.code,
                    "player_id": player_id,
                    "authenticated": authenticated_user is not None,
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

                # Parse deck colors (validate against allowed colors)
                allowed_colors = {
                    "red", "blue", "gold", "teal", "purple", "orange", "yellow",
                    "green", "pink", "cyan", "brown", "slate"
                }
                raw_deck_colors = data.get("deck_colors", ["red", "blue", "gold"])
                deck_colors = [c for c in raw_deck_colors if c in allowed_colors]
                if not deck_colors:
                    deck_colors = ["red", "blue", "gold"]

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
                    # Multi-deck card back colors
                    deck_colors=deck_colors,
                )

                # Validate settings
                num_decks = max(1, min(3, num_decks))
                num_rounds = max(1, min(18, num_rounds))

                async with current_room.game_lock:
                    current_room.game.start_game(num_decks, num_rounds, options)

                    # Log game start for AI analysis
                    game_logger = get_logger()
                    if game_logger:
                        current_room.game_log_id = game_logger.log_game_start(
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
                async with current_room.game_lock:
                    if current_room.game.flip_initial_cards(player_id, positions):
                        await broadcast_game_state(current_room)

                        # Check if it's a CPU's turn
                        await check_and_run_cpu_turn(current_room)

            elif msg_type == "draw":
                if not current_room:
                    continue

                source = data.get("source", "deck")
                async with current_room.game_lock:
                    # Capture discard top before draw (for logging decision context)
                    discard_before_draw = current_room.game.discard_top()
                    card = current_room.game.draw_card(player_id, source)

                    if card:
                        # Log draw decision for human player
                        game_logger = get_logger()
                        if game_logger and current_room.game_log_id:
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
                            "card": card.to_dict(),
                            "source": source,
                        })

                        await broadcast_game_state(current_room)

            elif msg_type == "swap":
                if not current_room:
                    continue

                position = data.get("position", 0)
                async with current_room.game_lock:
                    # Capture drawn card before swap for logging
                    drawn_card = current_room.game.drawn_card
                    player = current_room.game.get_player(player_id)
                    old_card = player.cards[position] if player and 0 <= position < len(player.cards) else None

                    discarded = current_room.game.swap_card(player_id, position)

                    if discarded:
                        # Log swap decision for human player
                        game_logger = get_logger()
                        if game_logger and current_room.game_log_id and drawn_card and player:
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
                        # Let client swap animation complete (~550ms), then pause to show result
                        # Total 1.0s = 550ms animation + 450ms visible pause
                        await asyncio.sleep(1.0)
                        await check_and_run_cpu_turn(current_room)

            elif msg_type == "discard":
                if not current_room:
                    continue

                async with current_room.game_lock:
                    # Capture drawn card before discard for logging
                    drawn_card = current_room.game.drawn_card
                    player = current_room.game.get_player(player_id)

                    if current_room.game.discard_drawn(player_id):
                        # Log discard decision for human player
                        game_logger = get_logger()
                        if game_logger and current_room.game_log_id and drawn_card and player:
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
                                # Let client animation complete before CPU turn
                                await asyncio.sleep(0.5)
                                await check_and_run_cpu_turn(current_room)
                        else:
                            # Turn ended - let client animation complete before CPU turn
                            # (player discard swoop animation is ~500ms: 350ms swoop + 150ms settle)
                            logger.debug(f"Player discarded, waiting 0.5s before CPU turn")
                            await asyncio.sleep(0.5)
                            logger.debug(f"Post-discard delay complete, checking for CPU turn")
                            await check_and_run_cpu_turn(current_room)

            elif msg_type == "cancel_draw":
                if not current_room:
                    continue

                async with current_room.game_lock:
                    if current_room.game.cancel_discard_draw(player_id):
                        await broadcast_game_state(current_room)

            elif msg_type == "flip_card":
                if not current_room:
                    continue

                position = data.get("position", 0)
                async with current_room.game_lock:
                    player = current_room.game.get_player(player_id)
                    current_room.game.flip_and_end_turn(player_id, position)

                    # Log flip decision for human player
                    game_logger = get_logger()
                    if game_logger and current_room.game_log_id and player and 0 <= position < len(player.cards):
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

                async with current_room.game_lock:
                    player = current_room.game.get_player(player_id)
                    if current_room.game.skip_flip_and_end_turn(player_id):
                        # Log skip flip decision for human player
                        game_logger = get_logger()
                        if game_logger and current_room.game_log_id and player:
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
                async with current_room.game_lock:
                    player = current_room.game.get_player(player_id)
                    if current_room.game.flip_card_as_action(player_id, position):
                        # Log flip-as-action for human player
                        game_logger = get_logger()
                        if game_logger and current_room.game_log_id and player and 0 <= position < len(player.cards):
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

                async with current_room.game_lock:
                    player = current_room.game.get_player(player_id)
                    if current_room.game.knock_early(player_id):
                        # Log knock early for human player
                        game_logger = get_logger()
                        if game_logger and current_room.game_log_id and player:
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

                async with current_room.game_lock:
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
                room_code = current_room.code
                for cpu in list(current_room.get_cpu_players()):
                    current_room.remove_player(cpu.id)
                cleanup_room_profiles(room_code)
                room_manager.remove_room(room_code)
                current_room = None

    except WebSocketDisconnect:
        if current_room:
            await handle_player_leave(current_room, player_id)


async def _process_stats_safe(room: Room):
    """
    Process game stats in a fire-and-forget manner.

    This is called via asyncio.create_task to avoid blocking game completion
    notifications while stats are being processed.
    """
    try:
        # Build mapping - use auth_user_id for authenticated players
        # Only authenticated players get their stats tracked
        player_user_ids = {}
        for player_id, room_player in room.players.items():
            if not room_player.is_cpu and room_player.auth_user_id:
                player_user_ids[player_id] = room_player.auth_user_id

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
        logger.debug(f"Stats processed for room {room.code}")
    except Exception as e:
        logger.error(f"Failed to process game stats: {e}")


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
            game_logger = get_logger()
            if game_logger and room.game_log_id:
                game_logger.log_game_end(room.game_log_id)
                room.game_log_id = None  # Clear to avoid duplicate logging

            # Process stats asynchronously (fire-and-forget) to avoid delaying game over notifications
            if _stats_service and room.game.players:
                asyncio.create_task(_process_stats_safe(room))

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

    # Brief pause before CPU starts - animations are faster now
    await asyncio.sleep(0.25)

    # Run CPU turn
    async def broadcast_cb():
        await broadcast_game_state(room)

    await process_cpu_turn(room.game, current, broadcast_cb, game_id=room.game_log_id)

    # Check if next player is also CPU (chain CPU turns)
    await check_and_run_cpu_turn(room)


async def handle_player_leave(room: Room, player_id: str):
    """Handle a player leaving a room."""
    room_code = room.code
    room_player = room.remove_player(player_id)

    # If no human players left, clean up the room entirely
    if room.is_empty() or room.human_player_count() == 0:
        # Remove all remaining CPU players to release their profiles
        for cpu in list(room.get_cpu_players()):
            room.remove_player(cpu.id)
        # Clean up any remaining profile tracking for this room
        cleanup_room_profiles(room_code)
        room_manager.remove_room(room_code)
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

    @app.get("/timing-config.js")
    async def serve_timing_config():
        return FileResponse(os.path.join(client_path, "timing-config.js"), media_type="application/javascript")

    @app.get("/leaderboard.js")
    async def serve_leaderboard_js():
        return FileResponse(os.path.join(client_path, "leaderboard.js"), media_type="application/javascript")

    @app.get("/golfball-logo.svg")
    async def serve_golfball_logo():
        return FileResponse(os.path.join(client_path, "golfball-logo.svg"), media_type="image/svg+xml")

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

    @app.get("/card-animations.js")
    async def serve_card_animations_js():
        return FileResponse(os.path.join(client_path, "card-animations.js"), media_type="application/javascript")

    @app.get("/anime.min.js")
    async def serve_anime_js():
        return FileResponse(os.path.join(client_path, "anime.min.js"), media_type="application/javascript")

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
