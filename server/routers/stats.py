"""
Stats and Leaderboards API router for Golf game.

Provides public endpoints for viewing leaderboards and player stats,
and authenticated endpoints for viewing personal stats and achievements.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel

from models.user import User
from services.stats_service import StatsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stats", tags=["stats"])


# =============================================================================
# Request/Response Models
# =============================================================================


class LeaderboardEntryResponse(BaseModel):
    """Single leaderboard entry."""
    rank: int
    user_id: str
    username: str
    value: float
    games_played: int
    secondary_value: Optional[float] = None


class LeaderboardResponse(BaseModel):
    """Leaderboard response."""
    metric: str
    entries: list[LeaderboardEntryResponse]
    total_players: Optional[int] = None


class PlayerStatsResponse(BaseModel):
    """Player statistics response."""
    user_id: str
    username: str
    games_played: int
    games_won: int
    win_rate: float
    rounds_played: int
    rounds_won: int
    avg_score: float
    best_round_score: Optional[int]
    worst_round_score: Optional[int]
    knockouts: int
    perfect_rounds: int
    wolfpacks: int
    current_win_streak: int
    best_win_streak: int
    first_game_at: Optional[str]
    last_game_at: Optional[str]
    achievements: list[str]


class PlayerRankResponse(BaseModel):
    """Player rank response."""
    user_id: str
    metric: str
    rank: Optional[int]
    qualified: bool  # Whether player has enough games


class AchievementResponse(BaseModel):
    """Achievement definition response."""
    id: str
    name: str
    description: str
    icon: str
    category: str
    threshold: int


class UserAchievementResponse(BaseModel):
    """User achievement response."""
    id: str
    name: str
    description: str
    icon: str
    earned_at: str
    game_id: Optional[str]


# =============================================================================
# Dependencies
# =============================================================================

# Set by main.py during startup
_stats_service: Optional[StatsService] = None


def set_stats_service(service: StatsService) -> None:
    """Set the stats service instance (called from main.py)."""
    global _stats_service
    _stats_service = service


def get_stats_service_dep() -> StatsService:
    """Dependency to get stats service."""
    if _stats_service is None:
        raise HTTPException(status_code=503, detail="Stats service not initialized")
    return _stats_service


# Auth dependencies - imported from auth router
_auth_service = None


def set_auth_service(service) -> None:
    """Set auth service for user lookup."""
    global _auth_service
    _auth_service = service


async def get_current_user_optional(
    authorization: Optional[str] = Header(None),
) -> Optional[User]:
    """Get current user from Authorization header (optional)."""
    if not authorization or not _auth_service:
        return None

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    token = parts[1]
    return await _auth_service.get_user_from_token(token)


async def require_user(
    user: Optional[User] = Depends(get_current_user_optional),
) -> User:
    """Require authenticated user."""
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    return user


# =============================================================================
# Public Endpoints (No Auth Required)
# =============================================================================


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    metric: str = Query("wins", pattern="^(wins|win_rate|avg_score|knockouts|streak)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: StatsService = Depends(get_stats_service_dep),
):
    """
    Get leaderboard by metric.

    Metrics:
    - wins: Total games won
    - win_rate: Win percentage (requires 5+ games)
    - avg_score: Average points per round (lower is better)
    - knockouts: Times going out first
    - streak: Best win streak

    Players must have 5+ games to appear on leaderboards.
    """
    entries = await service.get_leaderboard(metric, limit, offset)

    return {
        "metric": metric,
        "entries": [
            {
                "rank": e.rank,
                "user_id": e.user_id,
                "username": e.username,
                "value": e.value,
                "games_played": e.games_played,
                "secondary_value": e.secondary_value,
            }
            for e in entries
        ],
    }


@router.get("/players/{user_id}", response_model=PlayerStatsResponse)
async def get_player_stats(
    user_id: str,
    service: StatsService = Depends(get_stats_service_dep),
):
    """Get stats for a specific player (public profile)."""
    stats = await service.get_player_stats(user_id)

    if not stats:
        raise HTTPException(status_code=404, detail="Player not found")

    return {
        "user_id": stats.user_id,
        "username": stats.username,
        "games_played": stats.games_played,
        "games_won": stats.games_won,
        "win_rate": stats.win_rate,
        "rounds_played": stats.rounds_played,
        "rounds_won": stats.rounds_won,
        "avg_score": stats.avg_score,
        "best_round_score": stats.best_round_score,
        "worst_round_score": stats.worst_round_score,
        "knockouts": stats.knockouts,
        "perfect_rounds": stats.perfect_rounds,
        "wolfpacks": stats.wolfpacks,
        "current_win_streak": stats.current_win_streak,
        "best_win_streak": stats.best_win_streak,
        "first_game_at": stats.first_game_at.isoformat() if stats.first_game_at else None,
        "last_game_at": stats.last_game_at.isoformat() if stats.last_game_at else None,
        "achievements": stats.achievements,
    }


@router.get("/players/{user_id}/rank", response_model=PlayerRankResponse)
async def get_player_rank(
    user_id: str,
    metric: str = Query("wins", pattern="^(wins|win_rate|avg_score|knockouts|streak)$"),
    service: StatsService = Depends(get_stats_service_dep),
):
    """Get player's rank on a leaderboard."""
    rank = await service.get_player_rank(user_id, metric)

    return {
        "user_id": user_id,
        "metric": metric,
        "rank": rank,
        "qualified": rank is not None,
    }


@router.get("/achievements", response_model=dict)
async def get_achievements(
    service: StatsService = Depends(get_stats_service_dep),
):
    """Get all available achievements."""
    achievements = await service.get_achievements()

    return {
        "achievements": [
            {
                "id": a.id,
                "name": a.name,
                "description": a.description,
                "icon": a.icon,
                "category": a.category,
                "threshold": a.threshold,
            }
            for a in achievements
        ]
    }


@router.get("/players/{user_id}/achievements", response_model=dict)
async def get_user_achievements(
    user_id: str,
    service: StatsService = Depends(get_stats_service_dep),
):
    """Get achievements earned by a player."""
    achievements = await service.get_user_achievements(user_id)

    return {
        "user_id": user_id,
        "achievements": [
            {
                "id": a.id,
                "name": a.name,
                "description": a.description,
                "icon": a.icon,
                "earned_at": a.earned_at.isoformat(),
                "game_id": a.game_id,
            }
            for a in achievements
        ],
    }


# =============================================================================
# Authenticated Endpoints
# =============================================================================


@router.get("/me", response_model=PlayerStatsResponse)
async def get_my_stats(
    user: User = Depends(require_user),
    service: StatsService = Depends(get_stats_service_dep),
):
    """Get current user's stats."""
    stats = await service.get_player_stats(user.id)

    if not stats:
        # Return empty stats for new user
        return {
            "user_id": user.id,
            "username": user.username,
            "games_played": 0,
            "games_won": 0,
            "win_rate": 0.0,
            "rounds_played": 0,
            "rounds_won": 0,
            "avg_score": 0.0,
            "best_round_score": None,
            "worst_round_score": None,
            "knockouts": 0,
            "perfect_rounds": 0,
            "wolfpacks": 0,
            "current_win_streak": 0,
            "best_win_streak": 0,
            "first_game_at": None,
            "last_game_at": None,
            "achievements": [],
        }

    return {
        "user_id": stats.user_id,
        "username": stats.username,
        "games_played": stats.games_played,
        "games_won": stats.games_won,
        "win_rate": stats.win_rate,
        "rounds_played": stats.rounds_played,
        "rounds_won": stats.rounds_won,
        "avg_score": stats.avg_score,
        "best_round_score": stats.best_round_score,
        "worst_round_score": stats.worst_round_score,
        "knockouts": stats.knockouts,
        "perfect_rounds": stats.perfect_rounds,
        "wolfpacks": stats.wolfpacks,
        "current_win_streak": stats.current_win_streak,
        "best_win_streak": stats.best_win_streak,
        "first_game_at": stats.first_game_at.isoformat() if stats.first_game_at else None,
        "last_game_at": stats.last_game_at.isoformat() if stats.last_game_at else None,
        "achievements": stats.achievements,
    }


@router.get("/me/rank", response_model=PlayerRankResponse)
async def get_my_rank(
    metric: str = Query("wins", pattern="^(wins|win_rate|avg_score|knockouts|streak)$"),
    user: User = Depends(require_user),
    service: StatsService = Depends(get_stats_service_dep),
):
    """Get current user's rank on a leaderboard."""
    rank = await service.get_player_rank(user.id, metric)

    return {
        "user_id": user.id,
        "metric": metric,
        "rank": rank,
        "qualified": rank is not None,
    }


@router.get("/me/achievements", response_model=dict)
async def get_my_achievements(
    user: User = Depends(require_user),
    service: StatsService = Depends(get_stats_service_dep),
):
    """Get current user's achievements."""
    achievements = await service.get_user_achievements(user.id)

    return {
        "user_id": user.id,
        "achievements": [
            {
                "id": a.id,
                "name": a.name,
                "description": a.description,
                "icon": a.icon,
                "earned_at": a.earned_at.isoformat(),
                "game_id": a.game_id,
            }
            for a in achievements
        ],
    }
