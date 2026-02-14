"""WebSocket message handlers for the Golf card game.

Each handler corresponds to a single message type from the client.
Handlers are dispatched via the HANDLERS dict in main.py.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from fastapi import WebSocket

from game import GamePhase, GameOptions
from ai import GolfAI, get_all_profiles
from room import Room
from services.game_logger import get_logger

logger = logging.getLogger(__name__)


@dataclass
class ConnectionContext:
    """State tracked per WebSocket connection."""

    websocket: WebSocket
    connection_id: str
    player_id: str
    auth_user_id: Optional[str]
    authenticated_user: object  # Optional[User]
    current_room: Optional[Room] = None


def log_human_action(room: Room, player, action: str, card=None, position=None, reason: str = ""):
    """Log a human player's game action (shared helper for all handlers)."""
    game_logger = get_logger()
    if game_logger and room.game_log_id and player:
        game_logger.log_move(
            game_id=room.game_log_id,
            player=player,
            is_cpu=False,
            action=action,
            card=card,
            position=position,
            game=room.game,
            decision_reason=reason,
        )


# ---------------------------------------------------------------------------
# Lobby / Room handlers
# ---------------------------------------------------------------------------

async def handle_create_room(data: dict, ctx: ConnectionContext, *, room_manager, count_user_games, max_concurrent, **kw) -> None:
    if ctx.auth_user_id and count_user_games(ctx.auth_user_id) >= max_concurrent:
        await ctx.websocket.send_json({
            "type": "error",
            "message": f"Maximum {max_concurrent} concurrent games allowed",
        })
        return

    player_name = data.get("player_name", "Player")
    if ctx.authenticated_user and ctx.authenticated_user.display_name:
        player_name = ctx.authenticated_user.display_name
    room = room_manager.create_room()
    room.add_player(ctx.player_id, player_name, ctx.websocket, ctx.auth_user_id)
    ctx.current_room = room

    await ctx.websocket.send_json({
        "type": "room_created",
        "room_code": room.code,
        "player_id": ctx.player_id,
        "authenticated": ctx.authenticated_user is not None,
    })

    await room.broadcast({
        "type": "player_joined",
        "players": room.player_list(),
    })


async def handle_join_room(data: dict, ctx: ConnectionContext, *, room_manager, count_user_games, max_concurrent, **kw) -> None:
    room_code = data.get("room_code", "").upper()
    player_name = data.get("player_name", "Player")

    if ctx.auth_user_id and count_user_games(ctx.auth_user_id) >= max_concurrent:
        await ctx.websocket.send_json({
            "type": "error",
            "message": f"Maximum {max_concurrent} concurrent games allowed",
        })
        return

    room = room_manager.get_room(room_code)
    if not room:
        await ctx.websocket.send_json({"type": "error", "message": "Room not found"})
        return

    if len(room.players) >= 6:
        await ctx.websocket.send_json({"type": "error", "message": "Room is full"})
        return

    if room.game.phase != GamePhase.WAITING:
        await ctx.websocket.send_json({"type": "error", "message": "Game already in progress"})
        return

    if ctx.authenticated_user and ctx.authenticated_user.display_name:
        player_name = ctx.authenticated_user.display_name
    room.add_player(ctx.player_id, player_name, ctx.websocket, ctx.auth_user_id)
    ctx.current_room = room

    await ctx.websocket.send_json({
        "type": "room_joined",
        "room_code": room.code,
        "player_id": ctx.player_id,
        "authenticated": ctx.authenticated_user is not None,
    })

    await room.broadcast({
        "type": "player_joined",
        "players": room.player_list(),
    })


async def handle_get_cpu_profiles(data: dict, ctx: ConnectionContext, **kw) -> None:
    if not ctx.current_room:
        return
    await ctx.websocket.send_json({
        "type": "cpu_profiles",
        "profiles": get_all_profiles(),
    })


async def handle_add_cpu(data: dict, ctx: ConnectionContext, **kw) -> None:
    if not ctx.current_room:
        return

    room_player = ctx.current_room.get_player(ctx.player_id)
    if not room_player or not room_player.is_host:
        await ctx.websocket.send_json({"type": "error", "message": "Only the host can add CPU players"})
        return

    if len(ctx.current_room.players) >= 6:
        await ctx.websocket.send_json({"type": "error", "message": "Room is full"})
        return

    cpu_id = f"cpu_{uuid.uuid4().hex[:8]}"
    profile_name = data.get("profile_name")

    cpu_player = ctx.current_room.add_cpu_player(cpu_id, profile_name)
    if not cpu_player:
        await ctx.websocket.send_json({"type": "error", "message": "CPU profile not available"})
        return

    await ctx.current_room.broadcast({
        "type": "player_joined",
        "players": ctx.current_room.player_list(),
    })


async def handle_remove_cpu(data: dict, ctx: ConnectionContext, **kw) -> None:
    if not ctx.current_room:
        return

    room_player = ctx.current_room.get_player(ctx.player_id)
    if not room_player or not room_player.is_host:
        return

    cpu_players = ctx.current_room.get_cpu_players()
    if cpu_players:
        ctx.current_room.remove_player(cpu_players[-1].id)
        await ctx.current_room.broadcast({
            "type": "player_joined",
            "players": ctx.current_room.player_list(),
        })


# ---------------------------------------------------------------------------
# Game lifecycle handlers
# ---------------------------------------------------------------------------

async def handle_start_game(data: dict, ctx: ConnectionContext, *, broadcast_game_state, check_and_run_cpu_turn, **kw) -> None:
    if not ctx.current_room:
        return

    room_player = ctx.current_room.get_player(ctx.player_id)
    if not room_player or not room_player.is_host:
        await ctx.websocket.send_json({"type": "error", "message": "Only the host can start the game"})
        return

    if len(ctx.current_room.players) < 2:
        await ctx.websocket.send_json({"type": "error", "message": "Need at least 2 players"})
        return

    num_decks = max(1, min(3, data.get("decks", 1)))
    num_rounds = max(1, min(18, data.get("rounds", 1)))
    options = GameOptions.from_client_data(data)

    async with ctx.current_room.game_lock:
        ctx.current_room.game.start_game(num_decks, num_rounds, options)

        game_logger = get_logger()
        if game_logger:
            ctx.current_room.game_log_id = game_logger.log_game_start(
                room_code=ctx.current_room.code,
                num_players=len(ctx.current_room.players),
                options=options,
            )

        # CPU players do their initial flips immediately
        if options.initial_flips > 0:
            for cpu in ctx.current_room.get_cpu_players():
                positions = GolfAI.choose_initial_flips(options.initial_flips)
                ctx.current_room.game.flip_initial_cards(cpu.id, positions)

        # Send game started to all human players
        for pid, player in ctx.current_room.players.items():
            if player.websocket and not player.is_cpu:
                game_state = ctx.current_room.game.get_state(pid)
                await player.websocket.send_json({
                    "type": "game_started",
                    "game_state": game_state,
                })

        await check_and_run_cpu_turn(ctx.current_room)


async def handle_flip_initial(data: dict, ctx: ConnectionContext, *, broadcast_game_state, check_and_run_cpu_turn, **kw) -> None:
    if not ctx.current_room:
        return

    positions = data.get("positions", [])
    async with ctx.current_room.game_lock:
        if ctx.current_room.game.flip_initial_cards(ctx.player_id, positions):
            await broadcast_game_state(ctx.current_room)
            await check_and_run_cpu_turn(ctx.current_room)


# ---------------------------------------------------------------------------
# Turn action handlers
# ---------------------------------------------------------------------------

async def handle_draw(data: dict, ctx: ConnectionContext, *, broadcast_game_state, **kw) -> None:
    if not ctx.current_room:
        return

    source = data.get("source", "deck")
    async with ctx.current_room.game_lock:
        discard_before_draw = ctx.current_room.game.discard_top()
        card = ctx.current_room.game.draw_card(ctx.player_id, source)

        if card:
            player = ctx.current_room.game.get_player(ctx.player_id)
            reason = f"took {discard_before_draw.rank.value} from discard" if source == "discard" else "drew from deck"
            log_human_action(
                ctx.current_room, player,
                "take_discard" if source == "discard" else "draw_deck",
                card=card, reason=reason,
            )

            await ctx.websocket.send_json({
                "type": "card_drawn",
                "card": card.to_dict(),
                "source": source,
            })

            await broadcast_game_state(ctx.current_room)


async def handle_swap(data: dict, ctx: ConnectionContext, *, broadcast_game_state, check_and_run_cpu_turn, **kw) -> None:
    if not ctx.current_room:
        return

    position = data.get("position", 0)
    async with ctx.current_room.game_lock:
        drawn_card = ctx.current_room.game.drawn_card
        player = ctx.current_room.game.get_player(ctx.player_id)
        old_card = player.cards[position] if player and 0 <= position < len(player.cards) else None

        discarded = ctx.current_room.game.swap_card(ctx.player_id, position)

        if discarded:
            if drawn_card and player:
                old_rank = old_card.rank.value if old_card else "?"
                log_human_action(
                    ctx.current_room, player, "swap",
                    card=drawn_card, position=position,
                    reason=f"swapped {drawn_card.rank.value} into position {position}, replaced {old_rank}",
                )

            await broadcast_game_state(ctx.current_room)
            await asyncio.sleep(1.0)
            await check_and_run_cpu_turn(ctx.current_room)


async def handle_discard(data: dict, ctx: ConnectionContext, *, broadcast_game_state, check_and_run_cpu_turn, **kw) -> None:
    if not ctx.current_room:
        return

    async with ctx.current_room.game_lock:
        drawn_card = ctx.current_room.game.drawn_card
        player = ctx.current_room.game.get_player(ctx.player_id)

        if ctx.current_room.game.discard_drawn(ctx.player_id):
            if drawn_card and player:
                log_human_action(
                    ctx.current_room, player, "discard",
                    card=drawn_card,
                    reason=f"discarded {drawn_card.rank.value}",
                )

            await broadcast_game_state(ctx.current_room)

            if ctx.current_room.game.flip_on_discard:
                player = ctx.current_room.game.get_player(ctx.player_id)
                has_face_down = player and any(not c.face_up for c in player.cards)

                if has_face_down:
                    await ctx.websocket.send_json({
                        "type": "can_flip",
                        "optional": ctx.current_room.game.flip_is_optional,
                    })
                else:
                    await asyncio.sleep(0.5)
                    await check_and_run_cpu_turn(ctx.current_room)
            else:
                logger.debug("Player discarded, waiting 0.5s before CPU turn")
                await asyncio.sleep(0.5)
                logger.debug("Post-discard delay complete, checking for CPU turn")
                await check_and_run_cpu_turn(ctx.current_room)


async def handle_cancel_draw(data: dict, ctx: ConnectionContext, *, broadcast_game_state, **kw) -> None:
    if not ctx.current_room:
        return

    async with ctx.current_room.game_lock:
        if ctx.current_room.game.cancel_discard_draw(ctx.player_id):
            await broadcast_game_state(ctx.current_room)


async def handle_flip_card(data: dict, ctx: ConnectionContext, *, broadcast_game_state, check_and_run_cpu_turn, **kw) -> None:
    if not ctx.current_room:
        return

    position = data.get("position", 0)
    async with ctx.current_room.game_lock:
        player = ctx.current_room.game.get_player(ctx.player_id)
        ctx.current_room.game.flip_and_end_turn(ctx.player_id, position)

        if player and 0 <= position < len(player.cards):
            flipped_card = player.cards[position]
            log_human_action(
                ctx.current_room, player, "flip",
                card=flipped_card, position=position,
                reason=f"flipped card at position {position}",
            )

        await broadcast_game_state(ctx.current_room)
        await check_and_run_cpu_turn(ctx.current_room)


async def handle_skip_flip(data: dict, ctx: ConnectionContext, *, broadcast_game_state, check_and_run_cpu_turn, **kw) -> None:
    if not ctx.current_room:
        return

    async with ctx.current_room.game_lock:
        player = ctx.current_room.game.get_player(ctx.player_id)
        if ctx.current_room.game.skip_flip_and_end_turn(ctx.player_id):
            log_human_action(
                ctx.current_room, player, "skip_flip",
                reason="skipped optional flip (endgame mode)",
            )

            await broadcast_game_state(ctx.current_room)
            await check_and_run_cpu_turn(ctx.current_room)


async def handle_flip_as_action(data: dict, ctx: ConnectionContext, *, broadcast_game_state, check_and_run_cpu_turn, **kw) -> None:
    if not ctx.current_room:
        return

    position = data.get("position", 0)
    async with ctx.current_room.game_lock:
        player = ctx.current_room.game.get_player(ctx.player_id)
        if ctx.current_room.game.flip_card_as_action(ctx.player_id, position):
            if player and 0 <= position < len(player.cards):
                flipped_card = player.cards[position]
                log_human_action(
                    ctx.current_room, player, "flip_as_action",
                    card=flipped_card, position=position,
                    reason=f"used flip-as-action to reveal position {position}",
                )

            await broadcast_game_state(ctx.current_room)
            await check_and_run_cpu_turn(ctx.current_room)


async def handle_knock_early(data: dict, ctx: ConnectionContext, *, broadcast_game_state, check_and_run_cpu_turn, **kw) -> None:
    if not ctx.current_room:
        return

    async with ctx.current_room.game_lock:
        player = ctx.current_room.game.get_player(ctx.player_id)
        if ctx.current_room.game.knock_early(ctx.player_id):
            if player:
                face_down_count = sum(1 for c in player.cards if not c.face_up)
                log_human_action(
                    ctx.current_room, player, "knock_early",
                    reason=f"knocked early, revealing {face_down_count} hidden cards",
                )

            await broadcast_game_state(ctx.current_room)
            await check_and_run_cpu_turn(ctx.current_room)


async def handle_next_round(data: dict, ctx: ConnectionContext, *, broadcast_game_state, check_and_run_cpu_turn, **kw) -> None:
    if not ctx.current_room:
        return

    room_player = ctx.current_room.get_player(ctx.player_id)
    if not room_player or not room_player.is_host:
        return

    async with ctx.current_room.game_lock:
        if ctx.current_room.game.start_next_round():
            for cpu in ctx.current_room.get_cpu_players():
                positions = GolfAI.choose_initial_flips()
                ctx.current_room.game.flip_initial_cards(cpu.id, positions)

            for pid, player in ctx.current_room.players.items():
                if player.websocket and not player.is_cpu:
                    game_state = ctx.current_room.game.get_state(pid)
                    await player.websocket.send_json({
                        "type": "round_started",
                        "game_state": game_state,
                    })

            await check_and_run_cpu_turn(ctx.current_room)
        else:
            await broadcast_game_state(ctx.current_room)


# ---------------------------------------------------------------------------
# Leave / End handlers
# ---------------------------------------------------------------------------

async def handle_leave_room(data: dict, ctx: ConnectionContext, *, handle_player_leave, **kw) -> None:
    if ctx.current_room:
        await handle_player_leave(ctx.current_room, ctx.player_id)
        ctx.current_room = None


async def handle_leave_game(data: dict, ctx: ConnectionContext, *, handle_player_leave, **kw) -> None:
    if ctx.current_room:
        await handle_player_leave(ctx.current_room, ctx.player_id)
        ctx.current_room = None


async def handle_end_game(data: dict, ctx: ConnectionContext, *, room_manager, cleanup_room_profiles, **kw) -> None:
    if not ctx.current_room:
        return

    room_player = ctx.current_room.get_player(ctx.player_id)
    if not room_player or not room_player.is_host:
        await ctx.websocket.send_json({"type": "error", "message": "Only the host can end the game"})
        return

    await ctx.current_room.broadcast({
        "type": "game_ended",
        "reason": "Host ended the game",
    })

    room_code = ctx.current_room.code
    for cpu in list(ctx.current_room.get_cpu_players()):
        ctx.current_room.remove_player(cpu.id)
    cleanup_room_profiles(room_code)
    room_manager.remove_room(room_code)
    ctx.current_room = None


# ---------------------------------------------------------------------------
# Handler dispatch table
# ---------------------------------------------------------------------------

HANDLERS = {
    "create_room": handle_create_room,
    "join_room": handle_join_room,
    "get_cpu_profiles": handle_get_cpu_profiles,
    "add_cpu": handle_add_cpu,
    "remove_cpu": handle_remove_cpu,
    "start_game": handle_start_game,
    "flip_initial": handle_flip_initial,
    "draw": handle_draw,
    "swap": handle_swap,
    "discard": handle_discard,
    "cancel_draw": handle_cancel_draw,
    "flip_card": handle_flip_card,
    "skip_flip": handle_skip_flip,
    "flip_as_action": handle_flip_as_action,
    "knock_early": handle_knock_early,
    "next_round": handle_next_round,
    "leave_room": handle_leave_room,
    "leave_game": handle_leave_game,
    "end_game": handle_end_game,
}
