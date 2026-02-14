"""
Test suite for Room and RoomManager CRUD operations.

Covers:
- Room creation and uniqueness
- Player add/remove with host reassignment
- CPU player management
- Case-insensitive room lookup
- Cross-room player search
- Message broadcast and send_to

Run with: pytest test_room.py -v
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from room import Room, RoomPlayer, RoomManager


# =============================================================================
# Mock helpers
# =============================================================================

class MockWebSocket:
    """Mock WebSocket that collects sent messages."""

    def __init__(self):
        self.messages: list[dict] = []

    async def send_json(self, data: dict):
        self.messages.append(data)


# =============================================================================
# RoomManager tests
# =============================================================================

class TestRoomManagerCreate:

    def test_create_room_returns_room(self):
        rm = RoomManager()
        room = rm.create_room()
        assert room is not None
        assert len(room.code) == 4
        assert room.code in rm.rooms

    def test_create_multiple_rooms_unique_codes(self):
        rm = RoomManager()
        codes = set()
        for _ in range(20):
            room = rm.create_room()
            codes.add(room.code)
        assert len(codes) == 20

    def test_remove_room(self):
        rm = RoomManager()
        room = rm.create_room()
        code = room.code
        rm.remove_room(code)
        assert code not in rm.rooms

    def test_remove_nonexistent_room(self):
        rm = RoomManager()
        rm.remove_room("ZZZZ")  # Should not raise


class TestRoomManagerLookup:

    def test_get_room_case_insensitive(self):
        rm = RoomManager()
        room = rm.create_room()
        code = room.code

        assert rm.get_room(code.lower()) is room
        assert rm.get_room(code.upper()) is room

    def test_get_room_not_found(self):
        rm = RoomManager()
        assert rm.get_room("ZZZZ") is None

    def test_find_player_room(self):
        rm = RoomManager()
        room = rm.create_room()
        ws = MockWebSocket()
        room.add_player("player1", "Alice", ws)

        found = rm.find_player_room("player1")
        assert found is room

    def test_find_player_room_not_found(self):
        rm = RoomManager()
        rm.create_room()
        assert rm.find_player_room("nobody") is None

    def test_find_player_room_cross_room(self):
        rm = RoomManager()
        room1 = rm.create_room()
        room2 = rm.create_room()

        room1.add_player("p1", "Alice", MockWebSocket())
        room2.add_player("p2", "Bob", MockWebSocket())

        assert rm.find_player_room("p1") is room1
        assert rm.find_player_room("p2") is room2


# =============================================================================
# Room player management
# =============================================================================

class TestRoomPlayers:

    def test_add_player_first_is_host(self):
        room = Room(code="TEST")
        ws = MockWebSocket()
        rp = room.add_player("p1", "Alice", ws)
        assert rp.is_host is True

    def test_add_player_second_is_not_host(self):
        room = Room(code="TEST")
        room.add_player("p1", "Alice", MockWebSocket())
        rp2 = room.add_player("p2", "Bob", MockWebSocket())
        assert rp2.is_host is False

    def test_remove_player(self):
        room = Room(code="TEST")
        room.add_player("p1", "Alice", MockWebSocket())
        removed = room.remove_player("p1")
        assert removed is not None
        assert removed.id == "p1"
        assert "p1" not in room.players

    def test_remove_nonexistent_player(self):
        room = Room(code="TEST")
        result = room.remove_player("nobody")
        assert result is None

    def test_host_reassignment_on_remove(self):
        room = Room(code="TEST")
        room.add_player("p1", "Alice", MockWebSocket())
        room.add_player("p2", "Bob", MockWebSocket())

        room.remove_player("p1")
        assert room.players["p2"].is_host is True

    def test_get_player(self):
        room = Room(code="TEST")
        room.add_player("p1", "Alice", MockWebSocket())
        assert room.get_player("p1") is not None
        assert room.get_player("p1").name == "Alice"
        assert room.get_player("nobody") is None

    def test_is_empty(self):
        room = Room(code="TEST")
        assert room.is_empty() is True
        room.add_player("p1", "Alice", MockWebSocket())
        assert room.is_empty() is False

    def test_player_list(self):
        room = Room(code="TEST")
        room.add_player("p1", "Alice", MockWebSocket())
        room.add_player("p2", "Bob", MockWebSocket())

        plist = room.player_list()
        assert len(plist) == 2
        assert plist[0]["name"] == "Alice"
        assert plist[0]["is_host"] is True
        assert plist[1]["is_cpu"] is False

    def test_human_player_count(self):
        room = Room(code="TEST")
        room.add_player("p1", "Alice", MockWebSocket())
        assert room.human_player_count() == 1

    def test_auth_user_id_stored(self):
        room = Room(code="TEST")
        rp = room.add_player("p1", "Alice", MockWebSocket(), auth_user_id="auth_123")
        assert rp.auth_user_id == "auth_123"


# =============================================================================
# CPU player management
# =============================================================================

class TestCPUPlayers:

    def test_add_cpu_player(self):
        room = Room(code="TEST")
        room.add_player("host", "Host", MockWebSocket())

        with patch("room.assign_profile") as mock_assign:
            from ai import CPUProfile
            mock_assign.return_value = CPUProfile(
                name="TestBot", style="balanced",
                pair_hope=0.5, aggression=0.5,
                swap_threshold=4, unpredictability=0.1,
            )
            rp = room.add_cpu_player("cpu_1")
            assert rp is not None
            assert rp.is_cpu is True
            assert rp.name == "TestBot"

    def test_add_cpu_player_no_profile(self):
        room = Room(code="TEST")
        room.add_player("host", "Host", MockWebSocket())

        with patch("room.assign_profile", return_value=None):
            rp = room.add_cpu_player("cpu_1")
            assert rp is None

    def test_get_cpu_players(self):
        room = Room(code="TEST")
        room.add_player("host", "Host", MockWebSocket())

        with patch("room.assign_profile") as mock_assign:
            from ai import CPUProfile
            mock_assign.return_value = CPUProfile(
                name="Bot", style="balanced",
                pair_hope=0.5, aggression=0.5,
                swap_threshold=4, unpredictability=0.1,
            )
            room.add_cpu_player("cpu_1")

        cpus = room.get_cpu_players()
        assert len(cpus) == 1
        assert cpus[0].is_cpu is True

    def test_remove_cpu_releases_profile(self):
        room = Room(code="TEST")
        room.add_player("host", "Host", MockWebSocket())

        with patch("room.assign_profile") as mock_assign:
            from ai import CPUProfile
            mock_assign.return_value = CPUProfile(
                name="Bot", style="balanced",
                pair_hope=0.5, aggression=0.5,
                swap_threshold=4, unpredictability=0.1,
            )
            room.add_cpu_player("cpu_1")

        with patch("room.release_profile") as mock_release:
            room.remove_player("cpu_1")
            mock_release.assert_called_once_with("Bot", "TEST")


# =============================================================================
# Broadcast / send_to
# =============================================================================

class TestMessaging:

    @pytest.mark.asyncio
    async def test_broadcast_to_all_humans(self):
        room = Room(code="TEST")
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()
        room.add_player("p1", "Alice", ws1)
        room.add_player("p2", "Bob", ws2)

        await room.broadcast({"type": "test_msg"})
        assert len(ws1.messages) == 1
        assert len(ws2.messages) == 1
        assert ws1.messages[0]["type"] == "test_msg"

    @pytest.mark.asyncio
    async def test_broadcast_excludes_player(self):
        room = Room(code="TEST")
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()
        room.add_player("p1", "Alice", ws1)
        room.add_player("p2", "Bob", ws2)

        await room.broadcast({"type": "test_msg"}, exclude="p1")
        assert len(ws1.messages) == 0
        assert len(ws2.messages) == 1

    @pytest.mark.asyncio
    async def test_broadcast_skips_cpu(self):
        room = Room(code="TEST")
        ws1 = MockWebSocket()
        room.add_player("p1", "Alice", ws1)

        # Add a CPU player manually (no websocket)
        room.players["cpu_1"] = RoomPlayer(
            id="cpu_1", name="Bot", websocket=None, is_cpu=True
        )

        await room.broadcast({"type": "test_msg"})
        assert len(ws1.messages) == 1
        # CPU has no websocket, no error

    @pytest.mark.asyncio
    async def test_send_to_specific_player(self):
        room = Room(code="TEST")
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()
        room.add_player("p1", "Alice", ws1)
        room.add_player("p2", "Bob", ws2)

        await room.send_to("p1", {"type": "private_msg"})
        assert len(ws1.messages) == 1
        assert len(ws2.messages) == 0

    @pytest.mark.asyncio
    async def test_send_to_nonexistent_player(self):
        room = Room(code="TEST")
        await room.send_to("nobody", {"type": "test"})  # Should not raise

    @pytest.mark.asyncio
    async def test_send_to_cpu_is_noop(self):
        room = Room(code="TEST")
        room.players["cpu_1"] = RoomPlayer(
            id="cpu_1", name="Bot", websocket=None, is_cpu=True
        )
        await room.send_to("cpu_1", {"type": "test"})  # Should not raise
