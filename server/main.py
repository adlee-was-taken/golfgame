"""FastAPI WebSocket server for Golf card game."""

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import redis.asyncio as redis

from config import config
from room import RoomManager, Room
from game import GamePhase, GameOptions
from ai import GolfAI, process_cpu_turn, get_all_profiles, reset_all_profiles, cleanup_room_profiles
from handlers import HANDLERS, ConnectionContext
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
_rating_service = None
_matchmaking_service = None
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


async def _init_redis():
    """Initialize Redis client and rate limiter."""
    global _redis_client, _rate_limiter
    try:
        _redis_client = redis.from_url(config.REDIS_URL, decode_responses=False)
        await _redis_client.ping()
        logger.info("Redis client connected")

        if config.RATE_LIMIT_ENABLED:
            from services.ratelimit import get_rate_limiter
            _rate_limiter = await get_rate_limiter(_redis_client)
            logger.info("Rate limiter initialized")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e} - rate limiting disabled")
        _redis_client = None
        _rate_limiter = None


async def _init_database_services():
    """Initialize all PostgreSQL-dependent services."""
    global _user_store, _auth_service, _admin_service, _stats_service, _rating_service, _matchmaking_service
    global _replay_service, _spectator_manager, _leaderboard_refresh_task

    from stores.user_store import get_user_store
    from stores.event_store import get_event_store
    from services.auth_service import get_auth_service
    from services.admin_service import get_admin_service
    from services.stats_service import StatsService, set_stats_service
    from routers.auth import set_auth_service, set_admin_service_for_auth
    from routers.admin import set_admin_service
    from routers.stats import set_stats_service as set_stats_router_service
    from routers.stats import set_auth_service as set_stats_auth_service

    # Auth
    _user_store = await get_user_store(config.POSTGRES_URL)
    _auth_service = await get_auth_service(_user_store)
    set_auth_service(_auth_service)
    logger.info("Auth services initialized")

    # Admin
    _admin_service = await get_admin_service(
        pool=_user_store.pool,
        user_store=_user_store,
        state_cache=None,
    )
    set_admin_service(_admin_service)
    set_admin_service_for_auth(_admin_service)
    logger.info("Admin services initialized")

    # Stats + event store
    _event_store = await get_event_store(config.POSTGRES_URL)
    _stats_service = StatsService(_user_store.pool, _event_store)
    set_stats_service(_stats_service)
    set_stats_router_service(_stats_service)
    set_stats_auth_service(_auth_service)
    logger.info("Stats services initialized")

    # Rating service (Glicko-2)
    from services.rating_service import RatingService
    _rating_service = RatingService(_user_store.pool)
    logger.info("Rating service initialized")

    # Matchmaking service
    if config.MATCHMAKING_ENABLED:
        from services.matchmaking import MatchmakingService, MatchmakingConfig
        mm_config = MatchmakingConfig(
            enabled=True,
            min_players=config.MATCHMAKING_MIN_PLAYERS,
            max_players=config.MATCHMAKING_MAX_PLAYERS,
        )
        _matchmaking_service = MatchmakingService(_redis_client, mm_config)
        await _matchmaking_service.start(room_manager, broadcast_game_state)
        logger.info("Matchmaking service initialized")

    # Game logger
    _game_logger = GameLogger(_event_store)
    set_logger(_game_logger)
    logger.info("Game logger initialized")

    # Replay + spectator
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
    logger.info("Replay services initialized")

    # Periodic leaderboard refresh
    _leaderboard_refresh_task = asyncio.create_task(_periodic_leaderboard_refresh())
    logger.info("Leaderboard refresh task started")


async def _bootstrap_admin():
    """Create bootstrap admin user if no admins exist yet."""
    import bcrypt
    from models.user import UserRole

    # Check if any admin already exists
    existing = await _user_store.get_user_by_username(config.BOOTSTRAP_ADMIN_USERNAME)
    if existing:
        return

    # Check if any admin exists at all
    async with _user_store.pool.acquire() as conn:
        admin_count = await conn.fetchval(
            "SELECT COUNT(*) FROM users_v2 WHERE role = 'admin' AND deleted_at IS NULL"
        )
        if admin_count > 0:
            return

    # Create the bootstrap admin
    password_hash = bcrypt.hashpw(
        config.BOOTSTRAP_ADMIN_PASSWORD.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")

    user = await _user_store.create_user(
        username=config.BOOTSTRAP_ADMIN_USERNAME,
        password_hash=password_hash,
        role=UserRole.ADMIN,
    )

    if user:
        logger.warning(
            f"Bootstrap admin '{config.BOOTSTRAP_ADMIN_USERNAME}' created. "
            "Change the password and remove BOOTSTRAP_ADMIN_* env vars."
        )
    else:
        logger.error("Failed to create bootstrap admin user")


async def _shutdown_services():
    """Gracefully shut down all services."""
    _shutdown_event.set()

    await _close_all_websockets()

    # Stop matchmaking
    if _matchmaking_service:
        await _matchmaking_service.stop()
        await _matchmaking_service.cleanup()

    # Clean up rooms and CPU profiles
    for room in list(room_manager.rooms.values()):
        for cpu in list(room.get_cpu_players()):
            room.remove_player(cpu.id)
    room_manager.rooms.clear()
    reset_all_profiles()
    logger.info("All rooms and CPU profiles cleaned up")

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

    if _redis_client:
        await _redis_client.close()
        logger.info("Redis connection closed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for async service initialization."""
    if config.REDIS_URL:
        await _init_redis()

    if config.POSTGRES_URL:
        try:
            await _init_database_services()
        except Exception as e:
            logger.error(f"Failed to initialize services: {e}")
            raise
    else:
        logger.warning("POSTGRES_URL not configured - auth/admin/stats endpoints will not work")

    # Bootstrap admin user if needed (for first-time setup with INVITE_ONLY)
    if config.POSTGRES_URL and config.BOOTSTRAP_ADMIN_USERNAME and config.BOOTSTRAP_ADMIN_PASSWORD:
        await _bootstrap_admin()

    # Set up health check dependencies
    from routers.health import set_health_dependencies
    set_health_dependencies(
        db_pool=_user_store.pool if _user_store else None,
        redis_client=_redis_client,
        room_manager=room_manager,
    )

    logger.info(f"Golf server started (environment={config.ENVIRONMENT})")

    yield

    logger.info("Shutdown initiated...")
    await _shutdown_services()
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
    version="3.1.1",
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

    # Extract token from query param for authentication
    token = websocket.query_params.get("token")
    authenticated_user = None
    if token and _auth_service:
        try:
            authenticated_user = await _auth_service.get_user_from_token(token)
        except Exception as e:
            logger.debug(f"WebSocket auth failed: {e}")

    # Reject unauthenticated connections when invite-only
    if config.INVITE_ONLY and not authenticated_user:
        await websocket.send_json({"type": "error", "message": "Authentication required. Please log in."})
        await websocket.close(code=4001, reason="Authentication required")
        return

    connection_id = str(uuid.uuid4())
    auth_user_id = str(authenticated_user.id) if authenticated_user else None

    if authenticated_user:
        logger.debug(f"WebSocket authenticated as user {auth_user_id}, connection {connection_id}")
    else:
        logger.debug(f"WebSocket connected anonymously as {connection_id}")

    ctx = ConnectionContext(
        websocket=websocket,
        connection_id=connection_id,
        player_id=connection_id,
        auth_user_id=auth_user_id,
        authenticated_user=authenticated_user,
    )

    # Shared dependencies passed to every handler
    handler_deps = dict(
        room_manager=room_manager,
        count_user_games=count_user_games,
        max_concurrent=MAX_CONCURRENT_GAMES,
        broadcast_game_state=broadcast_game_state,
        check_and_run_cpu_turn=check_and_run_cpu_turn,
        handle_player_leave=handle_player_leave,
        cleanup_room_profiles=cleanup_room_profiles,
        matchmaking_service=_matchmaking_service,
        rating_service=_rating_service,
    )

    try:
        while True:
            data = await websocket.receive_json()
            handler = HANDLERS.get(data.get("type"))
            if handler:
                await handler(data, ctx, **handler_deps)
    except WebSocketDisconnect:
        if ctx.current_room:
            await handle_player_leave(ctx.current_room, ctx.player_id)


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
            game_options=room.game.options,
        )
        logger.debug(f"Stats processed for room {room.code}")

        # Update Glicko-2 ratings for human players
        if _rating_service:
            player_results = []
            for game_player in room.game.players:
                if game_player.id in player_user_ids:
                    player_results.append((
                        player_user_ids[game_player.id],
                        game_player.total_score,
                    ))

            if len(player_results) >= 2:
                await _rating_service.update_ratings(
                    player_results=player_results,
                    is_standard_rules=room.game.options.is_standard_rules(),
                )

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

    @app.get("/admin")
    async def serve_admin():
        return FileResponse(os.path.join(client_path, "admin.html"))

    @app.get("/replay/{share_code}")
    async def serve_replay_page(share_code: str):
        return FileResponse(os.path.join(client_path, "index.html"))

    # Mount static files for everything else (JS, CSS, SVG, etc.)
    app.mount("/", StaticFiles(directory=client_path), name="static")


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
