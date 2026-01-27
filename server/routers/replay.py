"""
Replay API router for Golf game.

Provides endpoints for:
- Viewing game replays
- Creating and managing share links
- Exporting/importing games
- Spectating live games
"""

import hashlib
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends, Header, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/replay", tags=["replay"])

# Service instances (set during app startup)
_replay_service = None
_auth_service = None
_spectator_manager = None
_room_manager = None


def set_replay_service(service) -> None:
    """Set the replay service instance."""
    global _replay_service
    _replay_service = service


def set_auth_service(service) -> None:
    """Set the auth service instance."""
    global _auth_service
    _auth_service = service


def set_spectator_manager(manager) -> None:
    """Set the spectator manager instance."""
    global _spectator_manager
    _spectator_manager = manager


def set_room_manager(manager) -> None:
    """Set the room manager instance."""
    global _room_manager
    _room_manager = manager


# -------------------------------------------------------------------------
# Auth Dependencies
# -------------------------------------------------------------------------

async def get_current_user(authorization: Optional[str] = Header(None)):
    """Get current user from Authorization header."""
    if not authorization or not _auth_service:
        return None

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    token = parts[1]
    return await _auth_service.get_user_from_token(token)


async def require_auth(user=Depends(get_current_user)):
    """Require authenticated user."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


# -------------------------------------------------------------------------
# Request/Response Models
# -------------------------------------------------------------------------

class ShareLinkRequest(BaseModel):
    """Request to create a share link."""
    title: Optional[str] = None
    description: Optional[str] = None
    expires_days: Optional[int] = None


class ImportGameRequest(BaseModel):
    """Request to import a game."""
    export_data: dict


# -------------------------------------------------------------------------
# Replay Endpoints
# -------------------------------------------------------------------------

@router.get("/game/{game_id}")
async def get_replay(game_id: str, user=Depends(get_current_user)):
    """
    Get full replay for a game.

    Returns all frames with game state at each step.
    Requires authentication and permission to view the game.
    """
    if not _replay_service:
        raise HTTPException(status_code=503, detail="Replay service unavailable")

    # Check permission
    user_id = user.id if user else None
    if not await _replay_service.can_view_game(user_id, game_id):
        raise HTTPException(status_code=403, detail="Cannot view this game")

    try:
        replay = await _replay_service.build_replay(game_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {
        "game_id": replay.game_id,
        "room_code": replay.room_code,
        "frames": [
            {
                "index": f.event_index,
                "event_type": f.event_type,
                "event_data": f.event_data,
                "timestamp": f.timestamp,
                "state": f.game_state,
                "player_id": f.player_id,
            }
            for f in replay.frames
        ],
        "metadata": {
            "players": replay.player_names,
            "winner": replay.winner,
            "final_scores": replay.final_scores,
            "duration": replay.total_duration_seconds,
            "total_rounds": replay.total_rounds,
            "options": replay.options,
        },
    }


@router.get("/game/{game_id}/frame/{frame_index}")
async def get_replay_frame(game_id: str, frame_index: int, user=Depends(get_current_user)):
    """
    Get a specific frame from a replay.

    Useful for seeking without loading the entire replay.
    """
    if not _replay_service:
        raise HTTPException(status_code=503, detail="Replay service unavailable")

    user_id = user.id if user else None
    if not await _replay_service.can_view_game(user_id, game_id):
        raise HTTPException(status_code=403, detail="Cannot view this game")

    frame = await _replay_service.get_replay_frame(game_id, frame_index)
    if not frame:
        raise HTTPException(status_code=404, detail="Frame not found")

    return {
        "index": frame.event_index,
        "event_type": frame.event_type,
        "event_data": frame.event_data,
        "timestamp": frame.timestamp,
        "state": frame.game_state,
        "player_id": frame.player_id,
    }


# -------------------------------------------------------------------------
# Share Link Endpoints
# -------------------------------------------------------------------------

@router.post("/game/{game_id}/share")
async def create_share_link(
    game_id: str,
    request: ShareLinkRequest,
    user=Depends(require_auth),
):
    """
    Create shareable link for a game.

    Only users who played in the game can create share links.
    """
    if not _replay_service:
        raise HTTPException(status_code=503, detail="Replay service unavailable")

    # Validate expires_days
    if request.expires_days is not None and (request.expires_days < 1 or request.expires_days > 365):
        raise HTTPException(status_code=400, detail="expires_days must be between 1 and 365")

    # Check if user played in the game
    if not await _replay_service.can_view_game(user.id, game_id):
        raise HTTPException(status_code=403, detail="Can only share games you played in")

    try:
        share_code = await _replay_service.create_share_link(
            game_id=game_id,
            user_id=user.id,
            title=request.title,
            description=request.description,
            expires_days=request.expires_days,
        )
    except Exception as e:
        logger.error(f"Failed to create share link: {e}")
        raise HTTPException(status_code=500, detail="Failed to create share link")

    return {
        "share_code": share_code,
        "share_url": f"/replay/{share_code}",
        "expires_days": request.expires_days,
    }


@router.get("/shared/{share_code}")
async def get_shared_replay(share_code: str):
    """
    Get replay via share code (public endpoint).

    No authentication required for public share links.
    """
    if not _replay_service:
        raise HTTPException(status_code=503, detail="Replay service unavailable")

    shared = await _replay_service.get_shared_game(share_code)
    if not shared:
        raise HTTPException(status_code=404, detail="Shared game not found or expired")

    try:
        replay = await _replay_service.build_replay(str(shared["game_id"]))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {
        "title": shared.get("title"),
        "description": shared.get("description"),
        "view_count": shared["view_count"],
        "created_at": shared["created_at"].isoformat() if shared.get("created_at") else None,
        "game_id": str(shared["game_id"]),
        "room_code": replay.room_code,
        "frames": [
            {
                "index": f.event_index,
                "event_type": f.event_type,
                "event_data": f.event_data,
                "timestamp": f.timestamp,
                "state": f.game_state,
                "player_id": f.player_id,
            }
            for f in replay.frames
        ],
        "metadata": {
            "players": replay.player_names,
            "winner": replay.winner,
            "final_scores": replay.final_scores,
            "duration": replay.total_duration_seconds,
            "total_rounds": replay.total_rounds,
            "options": replay.options,
        },
    }


@router.get("/shared/{share_code}/info")
async def get_shared_info(share_code: str):
    """
    Get info about a shared game without full replay data.

    Useful for preview/metadata display.
    """
    if not _replay_service:
        raise HTTPException(status_code=503, detail="Replay service unavailable")

    shared = await _replay_service.get_shared_game(share_code)
    if not shared:
        raise HTTPException(status_code=404, detail="Shared game not found or expired")

    return {
        "title": shared.get("title"),
        "description": shared.get("description"),
        "view_count": shared["view_count"],
        "created_at": shared["created_at"].isoformat() if shared.get("created_at") else None,
        "room_code": shared.get("room_code"),
        "num_players": shared.get("num_players"),
        "num_rounds": shared.get("num_rounds"),
    }


@router.delete("/shared/{share_code}")
async def delete_share_link(share_code: str, user=Depends(require_auth)):
    """Delete a share link (creator only)."""
    if not _replay_service:
        raise HTTPException(status_code=503, detail="Replay service unavailable")

    deleted = await _replay_service.delete_share_link(share_code, user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Share link not found or not authorized")

    return {"deleted": True}


@router.get("/my-shares")
async def get_my_shares(user=Depends(require_auth)):
    """Get all share links created by the current user."""
    if not _replay_service:
        raise HTTPException(status_code=503, detail="Replay service unavailable")

    shares = await _replay_service.get_user_shared_games(user.id)
    return {
        "shares": [
            {
                "share_code": s["share_code"],
                "game_id": str(s["game_id"]),
                "title": s.get("title"),
                "view_count": s["view_count"],
                "created_at": s["created_at"].isoformat() if s.get("created_at") else None,
                "expires_at": s["expires_at"].isoformat() if s.get("expires_at") else None,
            }
            for s in shares
        ],
    }


# -------------------------------------------------------------------------
# Export/Import Endpoints
# -------------------------------------------------------------------------

@router.get("/game/{game_id}/export")
async def export_game(game_id: str, user=Depends(require_auth)):
    """
    Export game as downloadable JSON.

    Returns the complete game data suitable for backup or sharing.
    """
    if not _replay_service:
        raise HTTPException(status_code=503, detail="Replay service unavailable")

    if not await _replay_service.can_view_game(user.id, game_id):
        raise HTTPException(status_code=403, detail="Cannot export this game")

    try:
        export_data = await _replay_service.export_game(game_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Return as downloadable JSON
    return JSONResponse(
        content=export_data,
        headers={
            "Content-Disposition": f'attachment; filename="golf-game-{game_id[:8]}.json"'
        },
    )


@router.post("/import")
async def import_game(request: ImportGameRequest, user=Depends(require_auth)):
    """
    Import a game from JSON export.

    Creates a new game record from the exported data.
    """
    if not _replay_service:
        raise HTTPException(status_code=503, detail="Replay service unavailable")

    try:
        new_game_id = await _replay_service.import_game(request.export_data, user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Import failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to import game")

    return {
        "game_id": new_game_id,
        "message": "Game imported successfully",
    }


# -------------------------------------------------------------------------
# Game History
# -------------------------------------------------------------------------

@router.get("/history")
async def get_game_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user=Depends(require_auth),
):
    """Get game history for the current user."""
    if not _replay_service:
        raise HTTPException(status_code=503, detail="Replay service unavailable")

    games = await _replay_service.get_user_game_history(user.id, limit, offset)
    return {
        "games": [
            {
                "game_id": str(g["id"]),
                "room_code": g["room_code"],
                "status": g["status"],
                "completed_at": g["completed_at"].isoformat() if g.get("completed_at") else None,
                "num_players": g["num_players"],
                "num_rounds": g["num_rounds"],
                "won": g.get("winner_id") == user.id,
            }
            for g in games
        ],
        "limit": limit,
        "offset": offset,
    }


# -------------------------------------------------------------------------
# Spectator Endpoints
# -------------------------------------------------------------------------

@router.websocket("/spectate/{room_code}")
async def spectate_game(websocket: WebSocket, room_code: str):
    """
    WebSocket endpoint for spectating live games.

    Spectators receive real-time game state updates but cannot interact.
    """
    await websocket.accept()

    if not _spectator_manager or not _room_manager:
        await websocket.close(code=4003, reason="Spectator service unavailable")
        return

    # Find the game by room code
    room = _room_manager.get_room(room_code.upper())
    if not room:
        await websocket.close(code=4004, reason="Game not found")
        return

    game_id = room_code.upper()  # Use room code as identifier for spectators

    # Add spectator
    added = await _spectator_manager.add_spectator(game_id, websocket)
    if not added:
        await websocket.close(code=4005, reason="Spectator limit reached")
        return

    try:
        # Send initial game state
        game_state = room.game.get_state(None)  # No player perspective
        await websocket.send_json({
            "type": "spectator_joined",
            "game_state": game_state,
            "spectator_count": _spectator_manager.get_spectator_count(game_id),
            "players": room.player_list(),
        })

        # Keep connection alive
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"Spectator connection error: {e}")
    finally:
        await _spectator_manager.remove_spectator(game_id, websocket)


@router.get("/spectate/{room_code}/count")
async def get_spectator_count(room_code: str):
    """Get the number of spectators for a game."""
    if not _spectator_manager:
        return {"count": 0}

    count = _spectator_manager.get_spectator_count(room_code.upper())
    return {"count": count}


@router.get("/spectate/active")
async def get_active_spectated_games():
    """Get list of games with active spectators."""
    if not _spectator_manager:
        return {"games": []}

    games = _spectator_manager.get_games_with_spectators()
    return {
        "games": [
            {"room_code": game_id, "spectator_count": count}
            for game_id, count in games.items()
        ],
    }
