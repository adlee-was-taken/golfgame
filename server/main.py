"""FastAPI WebSocket server for Golf card game."""

import logging
import os
import uuid
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Header
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config import config
from room import RoomManager, Room
from game import GamePhase, GameOptions
from ai import GolfAI, process_cpu_turn, get_all_profiles
from game_log import get_logger
from auth import get_auth_manager, User, UserRole

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Golf Card Game",
    debug=config.DEBUG,
    version="0.1.0",
)

room_manager = RoomManager()


@app.get("/health")
async def health_check():
    return {"status": "ok"}


# =============================================================================
# Auth Models
# =============================================================================

class RegisterRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    invite_code: str  # Room code or explicit invite code


class LoginRequest(BaseModel):
    username: str
    password: str


class SetupPasswordRequest(BaseModel):
    username: str
    new_password: str


class UpdateUserRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class ChangePasswordRequest(BaseModel):
    new_password: str


class CreateInviteRequest(BaseModel):
    max_uses: int = 1
    expires_in_days: Optional[int] = 7


# =============================================================================
# Auth Dependencies
# =============================================================================

async def get_current_user(authorization: Optional[str] = Header(None)) -> Optional[User]:
    """Get current user from Authorization header."""
    if not authorization:
        return None

    # Expect "Bearer <token>"
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    token = parts[1]
    auth = get_auth_manager()
    return auth.get_user_from_session(token)


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
# Auth Endpoints
# =============================================================================

@app.post("/api/auth/register")
async def register(request: RegisterRequest):
    """Register a new user with an invite code."""
    auth = get_auth_manager()

    # Validate invite code
    invite_valid = False
    inviter_username = None

    # Check if it's an explicit invite code
    invite = auth.get_invite_code(request.invite_code)
    if invite and invite.is_valid():
        invite_valid = True
        inviter = auth.get_user_by_id(invite.created_by)
        inviter_username = inviter.username if inviter else None

    # Check if it's a valid room code
    if not invite_valid:
        room = room_manager.get_room(request.invite_code.upper())
        if room:
            invite_valid = True
            # Room codes are like open invites

    if not invite_valid:
        raise HTTPException(status_code=400, detail="Invalid invite code")

    # Create user
    user = auth.create_user(
        username=request.username,
        password=request.password,
        email=request.email,
        invited_by=inviter_username,
    )

    if not user:
        raise HTTPException(status_code=400, detail="Username or email already taken")

    # Mark invite code as used (if it was an explicit invite)
    if invite:
        auth.use_invite_code(request.invite_code)

    # Create session
    session = auth.create_session(user)

    return {
        "user": user.to_dict(),
        "token": session.token,
        "expires_at": session.expires_at.isoformat(),
    }


@app.post("/api/auth/login")
async def login(request: LoginRequest):
    """Login with username and password."""
    auth = get_auth_manager()

    # Check if user needs password setup (first login)
    if auth.needs_password_setup(request.username):
        raise HTTPException(
            status_code=428,  # Precondition Required
            detail="Password setup required. Use /api/auth/setup-password endpoint."
        )

    user = auth.authenticate(request.username, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    session = auth.create_session(user)

    return {
        "user": user.to_dict(),
        "token": session.token,
        "expires_at": session.expires_at.isoformat(),
    }


@app.post("/api/auth/setup-password")
async def setup_password(request: SetupPasswordRequest):
    """Set password for first-time login (admin accounts created without password)."""
    auth = get_auth_manager()

    # Verify user exists and needs setup
    if not auth.needs_password_setup(request.username):
        raise HTTPException(
            status_code=400,
            detail="Password setup not available for this account"
        )

    # Set the password
    user = auth.setup_password(request.username, request.new_password)
    if not user:
        raise HTTPException(status_code=400, detail="Setup failed")

    # Create session
    session = auth.create_session(user)

    return {
        "user": user.to_dict(),
        "token": session.token,
        "expires_at": session.expires_at.isoformat(),
    }


@app.get("/api/auth/check-setup/{username}")
async def check_setup_needed(username: str):
    """Check if a username needs password setup."""
    auth = get_auth_manager()
    needs_setup = auth.needs_password_setup(username)

    return {
        "username": username,
        "needs_password_setup": needs_setup,
    }


@app.post("/api/auth/logout")
async def logout(authorization: Optional[str] = Header(None)):
    """Logout current session."""
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            auth = get_auth_manager()
            auth.invalidate_session(parts[1])

    return {"status": "ok"}


@app.get("/api/auth/me")
async def get_me(user: User = Depends(require_user)):
    """Get current user info."""
    return {"user": user.to_dict()}


@app.put("/api/auth/password")
async def change_own_password(
    request: ChangePasswordRequest,
    user: User = Depends(require_user)
):
    """Change own password."""
    auth = get_auth_manager()
    auth.change_password(user.id, request.new_password)
    # Invalidate all other sessions
    auth.invalidate_user_sessions(user.id)
    # Create new session
    session = auth.create_session(user)

    return {
        "status": "ok",
        "token": session.token,
        "expires_at": session.expires_at.isoformat(),
    }


# =============================================================================
# Admin Endpoints
# =============================================================================

@app.get("/api/admin/users")
async def list_users(
    include_inactive: bool = False,
    admin: User = Depends(require_admin)
):
    """List all users (admin only)."""
    auth = get_auth_manager()
    users = auth.list_users(include_inactive=include_inactive)
    return {"users": [u.to_dict() for u in users]}


@app.get("/api/admin/users/{user_id}")
async def get_user(user_id: str, admin: User = Depends(require_admin)):
    """Get user by ID (admin only)."""
    auth = get_auth_manager()
    user = auth.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user": user.to_dict()}


@app.put("/api/admin/users/{user_id}")
async def update_user(
    user_id: str,
    request: UpdateUserRequest,
    admin: User = Depends(require_admin)
):
    """Update user (admin only)."""
    auth = get_auth_manager()

    # Convert role string to enum if provided
    role = UserRole(request.role) if request.role else None

    user = auth.update_user(
        user_id=user_id,
        username=request.username,
        email=request.email,
        role=role,
        is_active=request.is_active,
    )

    if not user:
        raise HTTPException(status_code=400, detail="Update failed (duplicate username/email?)")

    return {"user": user.to_dict()}


@app.put("/api/admin/users/{user_id}/password")
async def admin_change_password(
    user_id: str,
    request: ChangePasswordRequest,
    admin: User = Depends(require_admin)
):
    """Change user password (admin only)."""
    auth = get_auth_manager()

    if not auth.change_password(user_id, request.new_password):
        raise HTTPException(status_code=404, detail="User not found")

    # Invalidate all user sessions
    auth.invalidate_user_sessions(user_id)

    return {"status": "ok"}


@app.delete("/api/admin/users/{user_id}")
async def delete_user(user_id: str, admin: User = Depends(require_admin)):
    """Deactivate user (admin only)."""
    auth = get_auth_manager()

    # Don't allow deleting yourself
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    if not auth.delete_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")

    return {"status": "ok"}


@app.post("/api/admin/invites")
async def create_invite(
    request: CreateInviteRequest,
    admin: User = Depends(require_admin)
):
    """Create an invite code (admin only)."""
    auth = get_auth_manager()

    invite = auth.create_invite_code(
        created_by=admin.id,
        max_uses=request.max_uses,
        expires_in_days=request.expires_in_days,
    )

    return {
        "code": invite.code,
        "max_uses": invite.max_uses,
        "expires_at": invite.expires_at.isoformat() if invite.expires_at else None,
    }


@app.get("/api/admin/invites")
async def list_invites(admin: User = Depends(require_admin)):
    """List all invite codes (admin only)."""
    auth = get_auth_manager()
    invites = auth.list_invite_codes()

    return {
        "invites": [
            {
                "code": i.code,
                "created_by": i.created_by,
                "created_at": i.created_at.isoformat(),
                "expires_at": i.expires_at.isoformat() if i.expires_at else None,
                "max_uses": i.max_uses,
                "use_count": i.use_count,
                "is_active": i.is_active,
                "is_valid": i.is_valid(),
            }
            for i in invites
        ]
    }


@app.delete("/api/admin/invites/{code}")
async def deactivate_invite(code: str, admin: User = Depends(require_admin)):
    """Deactivate an invite code (admin only)."""
    auth = get_auth_manager()

    if not auth.deactivate_invite_code(code):
        raise HTTPException(status_code=404, detail="Invite code not found")

    return {"status": "ok"}


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
                    flip_on_discard=data.get("flip_on_discard", False),
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
                card = current_room.game.draw_card(player_id, source)

                if card:
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
                discarded = current_room.game.swap_card(player_id, position)

                if discarded:
                    await broadcast_game_state(current_room)
                    await check_and_run_cpu_turn(current_room)

            elif msg_type == "discard":
                if not current_room:
                    continue

                if current_room.game.discard_drawn(player_id):
                    await broadcast_game_state(current_room)

                    if current_room.game.flip_on_discard:
                        # Version 1: Check if player has face-down cards to flip
                        player = current_room.game.get_player(player_id)
                        has_face_down = player and any(not c.face_up for c in player.cards)

                        if has_face_down:
                            await websocket.send_json({
                                "type": "can_flip",
                            })
                        else:
                            await check_and_run_cpu_turn(current_room)
                    else:
                        # Version 2 (default): Turn ended, check for CPU
                        await check_and_run_cpu_turn(current_room)

            elif msg_type == "flip_card":
                if not current_room:
                    continue

                position = data.get("position", 0)
                current_room.game.flip_and_end_turn(player_id, position)
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
                logger = get_logger()
                logger.log_game_end(room.game_log_id)
                room.game_log_id = None  # Clear to avoid duplicate logging

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
