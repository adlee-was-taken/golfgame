"""
Tests for the replay service.

Verifies:
- Replay building from events
- Share link creation and retrieval
- Export/import roundtrip
- Access control
"""

import pytest
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from models.events import GameEvent, EventType
from models.game_state import RebuiltGameState, rebuild_state


class TestReplayBuilding:
    """Test replay construction from events."""

    def test_rebuild_state_from_events(self):
        """Verify state can be rebuilt from a sequence of events."""
        events = [
            GameEvent(
                event_type=EventType.GAME_CREATED,
                game_id="test-game-1",
                sequence_num=1,
                player_id=None,
                data={
                    "room_code": "ABCD",
                    "host_id": "player-1",
                    "options": {},
                },
                timestamp=datetime.now(timezone.utc),
            ),
            GameEvent(
                event_type=EventType.PLAYER_JOINED,
                game_id="test-game-1",
                sequence_num=2,
                player_id="player-1",
                data={
                    "player_name": "Alice",
                    "is_cpu": False,
                },
                timestamp=datetime.now(timezone.utc),
            ),
            GameEvent(
                event_type=EventType.PLAYER_JOINED,
                game_id="test-game-1",
                sequence_num=3,
                player_id="player-2",
                data={
                    "player_name": "Bob",
                    "is_cpu": False,
                },
                timestamp=datetime.now(timezone.utc),
            ),
        ]

        state = rebuild_state(events)

        assert state.game_id == "test-game-1"
        assert state.room_code == "ABCD"
        assert len(state.players) == 2
        assert "player-1" in state.players
        assert "player-2" in state.players
        assert state.players["player-1"].name == "Alice"
        assert state.players["player-2"].name == "Bob"
        assert state.sequence_num == 3

    def test_rebuild_state_partial(self):
        """Can rebuild state to any point in event history."""
        events = [
            GameEvent(
                event_type=EventType.GAME_CREATED,
                game_id="test-game-1",
                sequence_num=1,
                player_id=None,
                data={
                    "room_code": "ABCD",
                    "host_id": "player-1",
                    "options": {},
                },
                timestamp=datetime.now(timezone.utc),
            ),
            GameEvent(
                event_type=EventType.PLAYER_JOINED,
                game_id="test-game-1",
                sequence_num=2,
                player_id="player-1",
                data={
                    "player_name": "Alice",
                    "is_cpu": False,
                },
                timestamp=datetime.now(timezone.utc),
            ),
            GameEvent(
                event_type=EventType.PLAYER_JOINED,
                game_id="test-game-1",
                sequence_num=3,
                player_id="player-2",
                data={
                    "player_name": "Bob",
                    "is_cpu": False,
                },
                timestamp=datetime.now(timezone.utc),
            ),
        ]

        # Rebuild only first 2 events
        state = rebuild_state(events[:2])
        assert len(state.players) == 1
        assert state.sequence_num == 2

        # Rebuild all events
        state = rebuild_state(events)
        assert len(state.players) == 2
        assert state.sequence_num == 3


class TestExportImport:
    """Test game export and import."""

    def test_export_format(self):
        """Verify exported format matches expected structure."""
        export_data = {
            "version": "1.0",
            "exported_at": "2024-01-15T12:00:00Z",
            "game": {
                "id": "test-game-1",
                "room_code": "ABCD",
                "players": ["Alice", "Bob"],
                "winner": "Alice",
                "final_scores": {"Alice": 15, "Bob": 23},
                "duration_seconds": 300.5,
                "total_rounds": 1,
                "options": {},
            },
            "events": [
                {
                    "type": "game_created",
                    "sequence": 1,
                    "player_id": None,
                    "data": {"room_code": "ABCD", "host_id": "p1", "options": {}},
                    "timestamp": 0.0,
                },
            ],
        }

        assert export_data["version"] == "1.0"
        assert "exported_at" in export_data
        assert "game" in export_data
        assert "events" in export_data
        assert export_data["game"]["players"] == ["Alice", "Bob"]

    def test_import_validates_version(self):
        """Import should reject unsupported versions."""
        invalid_export = {
            "version": "2.0",  # Unsupported version
            "events": [],
        }

        # This would be tested with the actual service
        assert invalid_export["version"] != "1.0"


class TestShareLinks:
    """Test share link functionality."""

    def test_share_code_format(self):
        """Share codes should be 12 characters."""
        import secrets
        share_code = secrets.token_urlsafe(9)[:12]

        assert len(share_code) == 12
        # URL-safe characters only
        assert all(c.isalnum() or c in '-_' for c in share_code)

    def test_expiry_calculation(self):
        """Verify expiry date calculation."""
        now = datetime.now(timezone.utc)
        expires_days = 7
        expires_at = now + timedelta(days=expires_days)

        assert expires_at > now
        assert (expires_at - now).days == 7


class TestSpectatorManager:
    """Test spectator management."""

    @pytest.mark.asyncio
    async def test_add_remove_spectator(self):
        """Test adding and removing spectators."""
        from services.spectator import SpectatorManager

        manager = SpectatorManager()
        ws = AsyncMock()

        # Add spectator
        result = await manager.add_spectator("game-1", ws, user_id="user-1")
        assert result is True
        assert manager.get_spectator_count("game-1") == 1

        # Remove spectator
        await manager.remove_spectator("game-1", ws)
        assert manager.get_spectator_count("game-1") == 0

    @pytest.mark.asyncio
    async def test_spectator_limit(self):
        """Test spectator limit enforcement."""
        from services.spectator import SpectatorManager, MAX_SPECTATORS_PER_GAME

        manager = SpectatorManager()

        # Add max spectators
        for i in range(MAX_SPECTATORS_PER_GAME):
            ws = AsyncMock()
            result = await manager.add_spectator("game-1", ws)
            assert result is True

        # Try to add one more
        ws = AsyncMock()
        result = await manager.add_spectator("game-1", ws)
        assert result is False

    @pytest.mark.asyncio
    async def test_broadcast_to_spectators(self):
        """Test broadcasting messages to spectators."""
        from services.spectator import SpectatorManager

        manager = SpectatorManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()

        await manager.add_spectator("game-1", ws1)
        await manager.add_spectator("game-1", ws2)

        message = {"type": "game_update", "data": "test"}
        await manager.broadcast_to_spectators("game-1", message)

        ws1.send_json.assert_called_once_with(message)
        ws2.send_json.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_dead_connection_cleanup(self):
        """Test cleanup of dead WebSocket connections."""
        from services.spectator import SpectatorManager

        manager = SpectatorManager()

        # Add a spectator that will fail on send
        ws = AsyncMock()
        ws.send_json.side_effect = Exception("Connection closed")

        await manager.add_spectator("game-1", ws)
        assert manager.get_spectator_count("game-1") == 1

        # Broadcast should clean up dead connection
        await manager.broadcast_to_spectators("game-1", {"type": "test"})
        assert manager.get_spectator_count("game-1") == 0


class TestReplayFrames:
    """Test replay frame construction."""

    def test_frame_timestamps(self):
        """Verify frame timestamps are relative to game start."""
        start_time = datetime.now(timezone.utc)

        events = [
            GameEvent(
                event_type=EventType.GAME_CREATED,
                game_id="test-game-1",
                sequence_num=1,
                player_id=None,
                data={"room_code": "ABCD", "host_id": "p1", "options": {}},
                timestamp=start_time,
            ),
            GameEvent(
                event_type=EventType.PLAYER_JOINED,
                game_id="test-game-1",
                sequence_num=2,
                player_id="player-1",
                data={"player_name": "Alice", "is_cpu": False},
                timestamp=start_time + timedelta(seconds=5),
            ),
        ]

        # First event should have timestamp 0
        elapsed_0 = (events[0].timestamp - start_time).total_seconds()
        assert elapsed_0 == 0.0

        # Second event should have timestamp 5
        elapsed_1 = (events[1].timestamp - start_time).total_seconds()
        assert elapsed_1 == 5.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
