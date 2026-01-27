"""
Health check endpoints for production deployment.

Provides:
- /health - Basic liveness check (is the app running?)
- /ready - Readiness check (can the app handle requests?)
- /metrics - Application metrics for monitoring
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Response

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

# Service references (set during app initialization)
_db_pool = None
_redis_client = None
_room_manager = None


def set_health_dependencies(
    db_pool=None,
    redis_client=None,
    room_manager=None,
):
    """Set dependencies for health checks."""
    global _db_pool, _redis_client, _room_manager
    _db_pool = db_pool
    _redis_client = redis_client
    _room_manager = room_manager


@router.get("/health")
async def health_check():
    """
    Basic liveness check - is the app running?

    This endpoint should always return 200 if the process is alive.
    Used by container orchestration for restart decisions.
    """
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready")
async def readiness_check():
    """
    Readiness check - can the app handle requests?

    Checks connectivity to required services (database, Redis).
    Returns 503 if any critical service is unavailable.
    """
    checks = {}
    overall_healthy = True

    # Check PostgreSQL
    if _db_pool is not None:
        try:
            async with _db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            checks["database"] = {"status": "ok"}
        except Exception as e:
            logger.warning(f"Database health check failed: {e}")
            checks["database"] = {"status": "error", "message": str(e)}
            overall_healthy = False
    else:
        checks["database"] = {"status": "not_configured"}

    # Check Redis
    if _redis_client is not None:
        try:
            await _redis_client.ping()
            checks["redis"] = {"status": "ok"}
        except Exception as e:
            logger.warning(f"Redis health check failed: {e}")
            checks["redis"] = {"status": "error", "message": str(e)}
            overall_healthy = False
    else:
        checks["redis"] = {"status": "not_configured"}

    status_code = 200 if overall_healthy else 503
    return Response(
        content=json.dumps({
            "status": "ok" if overall_healthy else "degraded",
            "checks": checks,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }),
        status_code=status_code,
        media_type="application/json",
    )


@router.get("/metrics")
async def metrics():
    """
    Expose application metrics for monitoring.

    Returns operational metrics useful for dashboards and alerting.
    """
    metrics_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Room/game metrics from room manager
    if _room_manager is not None:
        try:
            rooms = _room_manager.rooms
            active_rooms = len(rooms)
            total_players = sum(len(r.players) for r in rooms.values())
            games_in_progress = sum(
                1 for r in rooms.values()
                if hasattr(r.game, 'phase') and r.game.phase.name not in ('WAITING', 'GAME_OVER')
            )
            metrics_data.update({
                "active_rooms": active_rooms,
                "total_players": total_players,
                "games_in_progress": games_in_progress,
            })
        except Exception as e:
            logger.warning(f"Failed to collect room metrics: {e}")

    # Database metrics
    if _db_pool is not None:
        try:
            async with _db_pool.acquire() as conn:
                # Count active games (if games table exists)
                try:
                    games_today = await conn.fetchval(
                        "SELECT COUNT(*) FROM game_events WHERE timestamp > NOW() - INTERVAL '1 day'"
                    )
                    metrics_data["events_today"] = games_today
                except Exception:
                    pass  # Table might not exist

                # Count users (if users table exists)
                try:
                    total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
                    metrics_data["total_users"] = total_users
                except Exception:
                    pass  # Table might not exist
        except Exception as e:
            logger.warning(f"Failed to collect database metrics: {e}")

    # Redis metrics
    if _redis_client is not None:
        try:
            # Get connected players from Redis set if tracking
            try:
                connected = await _redis_client.scard("golf:connected_players")
                metrics_data["connected_websockets"] = connected
            except Exception:
                pass

            # Get active rooms from Redis
            try:
                active_rooms_redis = await _redis_client.scard("golf:rooms:active")
                metrics_data["active_rooms_redis"] = active_rooms_redis
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"Failed to collect Redis metrics: {e}")

    return metrics_data
