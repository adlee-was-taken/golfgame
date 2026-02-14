"""
Test suite for WebSocket message handlers.

Tests handler basic flows and validation using mock WebSocket/Room.

Run with: pytest test_handlers.py -v
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from game import Game, GamePhase, GameOptions, Player
from room import Room, RoomPlayer, RoomManager
from handlers import (
    ConnectionContext,
    handle_create_room,
    handle_join_room,
    handle_draw,
    handle_swap,
    handle_discard,
)


# =============================================================================
# Mock helpers
# =============================================================================

class MockWebSocket:
    """Mock WebSocket that collects sent messages."""

    def __init__(self):
        self.messages: list[dict] = []

    async def send_json(self, data: dict):
        self.messages.append(data)

    def last_message(self) -> dict:
        return self.messages[-1] if self.messages else {}

    def messages_of_type(self, msg_type: str) -> list[dict]:
        return [m for m in self.messages if m.get("type") == msg_type]


def make_ctx(websocket=None, player_id="test_player", room=None):
    """Create a ConnectionContext with sensible defaults."""
    ws = websocket or MockWebSocket()
    return ConnectionContext(
        websocket=ws,
        connection_id="conn_123",
        player_id=player_id,
        auth_user_id=None,
        authenticated_user=None,
        current_room=room,
    )


def make_room_manager():
    """Create a RoomManager for testing."""
    return RoomManager()


def make_room_with_game(num_players=2):
    """Create a Room with players and a game in PLAYING phase."""
    room = Room(code="TEST")
    for i in range(num_players):
        ws = MockWebSocket()
        room.add_player(f"p{i}", f"Player {i}", ws)

    room.game.start_game(num_decks=1, num_rounds=1, options=GameOptions(initial_flips=0))
    # Skip initial flip phase
    for p in room.game.players:
        room.game.flip_initial_cards(p.id, [0, 1])

    return room


# =============================================================================
# Lobby handlers
# =============================================================================

class TestHandleCreateRoom:

    @pytest.mark.asyncio
    async def test_creates_room(self):
        ws = MockWebSocket()
        ctx = make_ctx(websocket=ws)
        rm = make_room_manager()

        await handle_create_room(
            {"player_name": "Alice"},
            ctx,
            room_manager=rm,
            count_user_games=lambda uid: 0,
            max_concurrent=5,
        )

        assert ctx.current_room is not None
        assert len(rm.rooms) == 1
        assert ws.messages_of_type("room_created")

    @pytest.mark.asyncio
    async def test_max_concurrent_rejects(self):
        ws = MockWebSocket()
        ctx = make_ctx(websocket=ws)
        ctx.auth_user_id = "user1"
        rm = make_room_manager()

        await handle_create_room(
            {"player_name": "Alice"},
            ctx,
            room_manager=rm,
            count_user_games=lambda uid: 5,
            max_concurrent=5,
        )

        assert ctx.current_room is None
        assert ws.messages_of_type("error")


class TestHandleJoinRoom:

    @pytest.mark.asyncio
    async def test_join_existing_room(self):
        rm = make_room_manager()
        room = rm.create_room()
        host_ws = MockWebSocket()
        room.add_player("host", "Host", host_ws)

        ws = MockWebSocket()
        ctx = make_ctx(websocket=ws, player_id="joiner")

        await handle_join_room(
            {"room_code": room.code, "player_name": "Bob"},
            ctx,
            room_manager=rm,
            count_user_games=lambda uid: 0,
            max_concurrent=5,
        )

        assert ctx.current_room is room
        assert ws.messages_of_type("room_joined")
        assert len(room.players) == 2

    @pytest.mark.asyncio
    async def test_join_nonexistent_room(self):
        rm = make_room_manager()
        ws = MockWebSocket()
        ctx = make_ctx(websocket=ws)

        await handle_join_room(
            {"room_code": "ZZZZ", "player_name": "Bob"},
            ctx,
            room_manager=rm,
            count_user_games=lambda uid: 0,
            max_concurrent=5,
        )

        assert ctx.current_room is None
        assert ws.messages_of_type("error")
        assert "not found" in ws.last_message().get("message", "").lower()

    @pytest.mark.asyncio
    async def test_join_full_room(self):
        rm = make_room_manager()
        room = rm.create_room()
        for i in range(6):
            room.add_player(f"p{i}", f"Player {i}", MockWebSocket())

        ws = MockWebSocket()
        ctx = make_ctx(websocket=ws, player_id="extra")

        await handle_join_room(
            {"room_code": room.code, "player_name": "Extra"},
            ctx,
            room_manager=rm,
            count_user_games=lambda uid: 0,
            max_concurrent=5,
        )

        assert ws.messages_of_type("error")
        assert "full" in ws.last_message().get("message", "").lower()

    @pytest.mark.asyncio
    async def test_join_in_progress_game(self):
        rm = make_room_manager()
        room = rm.create_room()
        room.add_player("host", "Host", MockWebSocket())
        room.add_player("p2", "Player 2", MockWebSocket())
        room.game.start_game(1, 1, GameOptions(initial_flips=0))

        ws = MockWebSocket()
        ctx = make_ctx(websocket=ws, player_id="late")

        await handle_join_room(
            {"room_code": room.code, "player_name": "Late"},
            ctx,
            room_manager=rm,
            count_user_games=lambda uid: 0,
            max_concurrent=5,
        )

        assert ws.messages_of_type("error")
        assert "in progress" in ws.last_message().get("message", "").lower()


# =============================================================================
# Turn action handlers
# =============================================================================

class TestHandleDraw:

    @pytest.mark.asyncio
    async def test_draw_from_deck(self):
        room = make_room_with_game()
        current_pid = room.game.players[room.game.current_player_index].id
        ws = room.players[current_pid].websocket

        ctx = make_ctx(websocket=ws, player_id=current_pid, room=room)
        broadcast = AsyncMock()

        await handle_draw(
            {"source": "deck"},
            ctx,
            broadcast_game_state=broadcast,
        )

        assert ws.messages_of_type("card_drawn")
        broadcast.assert_called_once()

    @pytest.mark.asyncio
    async def test_draw_no_room(self):
        ws = MockWebSocket()
        ctx = make_ctx(websocket=ws, room=None)
        broadcast = AsyncMock()

        await handle_draw(
            {"source": "deck"},
            ctx,
            broadcast_game_state=broadcast,
        )

        assert len(ws.messages) == 0
        broadcast.assert_not_called()


class TestHandleSwap:

    @pytest.mark.asyncio
    async def test_swap_card(self):
        room = make_room_with_game()
        current_pid = room.game.players[room.game.current_player_index].id
        ws = room.players[current_pid].websocket

        # Draw a card first
        room.game.draw_card(current_pid, "deck")

        ctx = make_ctx(websocket=ws, player_id=current_pid, room=room)
        broadcast = AsyncMock()
        check_cpu = AsyncMock()

        await handle_swap(
            {"position": 0},
            ctx,
            broadcast_game_state=broadcast,
            check_and_run_cpu_turn=check_cpu,
        )

        broadcast.assert_called_once()


class TestHandleDiscard:

    @pytest.mark.asyncio
    async def test_discard_drawn_card(self):
        room = make_room_with_game()
        current_pid = room.game.players[room.game.current_player_index].id
        ws = room.players[current_pid].websocket

        room.game.draw_card(current_pid, "deck")

        ctx = make_ctx(websocket=ws, player_id=current_pid, room=room)
        broadcast = AsyncMock()
        check_cpu = AsyncMock()

        await handle_discard(
            {},
            ctx,
            broadcast_game_state=broadcast,
            check_and_run_cpu_turn=check_cpu,
        )

        broadcast.assert_called_once()
