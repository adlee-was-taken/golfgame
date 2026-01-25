"""FastAPI WebSocket server for Golf card game."""

import uuid
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from room import RoomManager, Room
from game import GamePhase, GameOptions
from ai import GolfAI, process_cpu_turn, get_all_profiles
from game_log import get_logger

app = FastAPI(title="Golf Card Game")

room_manager = RoomManager()


@app.get("/health")
async def health_check():
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
