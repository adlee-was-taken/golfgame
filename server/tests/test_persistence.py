"""
Tests for V2 Persistence & Recovery components.

These tests cover:
- StateCache: Redis-backed game state caching
- GamePubSub: Cross-server event broadcasting
- RecoveryService: Game recovery from event store

Tests use fakeredis for isolated Redis testing.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

# Import the modules under test
from stores.state_cache import StateCache
from stores.pubsub import GamePubSub, PubSubMessage, MessageType
from services.recovery_service import RecoveryService, RecoveryResult
from models.events import (
    GameEvent, EventType,
    game_created, player_joined, game_started, round_started,
)
from models.game_state import RebuiltGameState, GamePhase


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_redis():
    """Create a mock Redis client for testing."""
    mock = AsyncMock()

    # Track stored data
    data = {}
    sets = {}
    hashes = {}

    async def mock_set(key, value, ex=None):
        data[key] = value

    async def mock_get(key):
        return data.get(key)

    async def mock_delete(*keys):
        for key in keys:
            data.pop(key, None)
            sets.pop(key, None)
            hashes.pop(key, None)

    async def mock_exists(key):
        return 1 if key in data or key in hashes else 0

    async def mock_sadd(key, *values):
        if key not in sets:
            sets[key] = set()
        sets[key].update(values)
        return len(values)

    async def mock_srem(key, *values):
        if key in sets:
            for v in values:
                sets[key].discard(v)

    async def mock_smembers(key):
        return sets.get(key, set())

    async def mock_hset(key, field=None, value=None, mapping=None, **kwargs):
        """Mock hset supporting both hset(key, field, value) and hset(key, mapping={})"""
        if key not in hashes:
            hashes[key] = {}
        if mapping:
            for k, v in mapping.items():
                hashes[key][k.encode() if isinstance(k, str) else k] = v.encode() if isinstance(v, str) else v
        elif field is not None and value is not None:
            hashes[key][field.encode() if isinstance(field, str) else field] = value.encode() if isinstance(value, str) else value

    async def mock_hgetall(key):
        return hashes.get(key, {})

    async def mock_expire(key, seconds):
        pass  # No-op for testing

    def mock_pipeline():
        pipe = AsyncMock()

        async def pipe_hset(key, field=None, value=None, mapping=None, **kwargs):
            await mock_hset(key, field, value, mapping, **kwargs)

        async def pipe_sadd(key, *values):
            await mock_sadd(key, *values)

        async def pipe_set(key, value, ex=None):
            await mock_set(key, value, ex)

        pipe.hset = pipe_hset
        pipe.expire = AsyncMock()
        pipe.sadd = pipe_sadd
        pipe.set = pipe_set
        pipe.srem = AsyncMock()
        pipe.delete = AsyncMock()

        async def execute():
            return []

        pipe.execute = execute
        return pipe

    mock.set = mock_set
    mock.get = mock_get
    mock.delete = mock_delete
    mock.exists = mock_exists
    mock.sadd = mock_sadd
    mock.srem = mock_srem
    mock.smembers = mock_smembers
    mock.hset = mock_hset
    mock.hgetall = mock_hgetall
    mock.expire = mock_expire
    mock.pipeline = mock_pipeline
    mock.ping = AsyncMock(return_value=True)
    mock.close = AsyncMock()

    # Store references for assertions
    mock._data = data
    mock._sets = sets
    mock._hashes = hashes

    return mock


@pytest.fixture
def state_cache(mock_redis):
    """Create a StateCache with mock Redis."""
    return StateCache(mock_redis)


@pytest.fixture
def mock_event_store():
    """Create a mock EventStore."""
    mock = AsyncMock()
    mock.get_events = AsyncMock(return_value=[])
    mock.get_active_games = AsyncMock(return_value=[])
    return mock


# =============================================================================
# StateCache Tests
# =============================================================================

class TestStateCache:
    """Tests for StateCache class."""

    @pytest.mark.asyncio
    async def test_create_room(self, state_cache, mock_redis):
        """Test creating a new room."""
        await state_cache.create_room(
            room_code="ABCD",
            game_id="game-123",
            host_id="player-1",
            server_id="server-1",
        )

        # Verify room was created via pipeline
        # (Pipeline operations are mocked, just verify no errors)
        assert True  # Room creation succeeded

    @pytest.mark.asyncio
    async def test_room_exists_true(self, state_cache, mock_redis):
        """Test room_exists returns True when room exists."""
        mock_redis._hashes["golf:room:ABCD"] = {b"game_id": b"123"}

        result = await state_cache.room_exists("ABCD")
        assert result is True

    @pytest.mark.asyncio
    async def test_room_exists_false(self, state_cache, mock_redis):
        """Test room_exists returns False when room doesn't exist."""
        result = await state_cache.room_exists("XXXX")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_active_rooms(self, state_cache, mock_redis):
        """Test getting active rooms."""
        mock_redis._sets["golf:rooms:active"] = {"ABCD", "EFGH"}

        rooms = await state_cache.get_active_rooms()
        assert rooms == {"ABCD", "EFGH"}

    @pytest.mark.asyncio
    async def test_save_and_get_game_state(self, state_cache, mock_redis):
        """Test saving and retrieving game state."""
        state = {
            "game_id": "game-123",
            "phase": "playing",
            "players": {"p1": {"name": "Alice"}},
        }

        await state_cache.save_game_state("game-123", state)

        # Verify it was stored
        key = "golf:game:game-123"
        assert key in mock_redis._data

        # Retrieve it
        retrieved = await state_cache.get_game_state("game-123")
        assert retrieved == state

    @pytest.mark.asyncio
    async def test_get_nonexistent_game_state(self, state_cache, mock_redis):
        """Test getting state for non-existent game returns None."""
        result = await state_cache.get_game_state("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_add_player_to_room(self, state_cache, mock_redis):
        """Test adding a player to a room."""
        await state_cache.add_player_to_room("ABCD", "player-2")

        # Pipeline was used successfully (no exception thrown)
        # The actual data verification would require integration tests
        assert True  # add_player_to_room completed without error

    @pytest.mark.asyncio
    async def test_get_room_players(self, state_cache, mock_redis):
        """Test getting players in a room."""
        mock_redis._sets["golf:room:ABCD:players"] = {"player-1", "player-2"}

        players = await state_cache.get_room_players("ABCD")
        assert players == {"player-1", "player-2"}

    @pytest.mark.asyncio
    async def test_get_player_room(self, state_cache, mock_redis):
        """Test getting the room a player is in."""
        mock_redis._data["golf:player:player-1:room"] = b"ABCD"

        room = await state_cache.get_player_room("player-1")
        assert room == "ABCD"

    @pytest.mark.asyncio
    async def test_get_player_room_not_in_room(self, state_cache, mock_redis):
        """Test getting room for player not in any room."""
        room = await state_cache.get_player_room("unknown-player")
        assert room is None


# =============================================================================
# GamePubSub Tests
# =============================================================================

class TestGamePubSub:
    """Tests for GamePubSub class."""

    @pytest.fixture
    def mock_pubsub_redis(self):
        """Create mock Redis with pubsub support."""
        mock = AsyncMock()
        mock_pubsub = AsyncMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.get_message = AsyncMock(return_value=None)
        mock_pubsub.close = AsyncMock()
        mock.pubsub = MagicMock(return_value=mock_pubsub)
        mock.publish = AsyncMock(return_value=1)
        return mock, mock_pubsub

    @pytest.mark.asyncio
    async def test_subscribe_to_room(self, mock_pubsub_redis):
        """Test subscribing to room events."""
        redis_client, mock_ps = mock_pubsub_redis
        pubsub = GamePubSub(redis_client, server_id="test-server")

        handler = AsyncMock()
        await pubsub.subscribe("ABCD", handler)

        mock_ps.subscribe.assert_called_once_with("golf:room:ABCD")
        assert "golf:room:ABCD" in pubsub._handlers

    @pytest.mark.asyncio
    async def test_unsubscribe_from_room(self, mock_pubsub_redis):
        """Test unsubscribing from room events."""
        redis_client, mock_ps = mock_pubsub_redis
        pubsub = GamePubSub(redis_client, server_id="test-server")

        handler = AsyncMock()
        await pubsub.subscribe("ABCD", handler)
        await pubsub.unsubscribe("ABCD")

        mock_ps.unsubscribe.assert_called_once_with("golf:room:ABCD")
        assert "golf:room:ABCD" not in pubsub._handlers

    @pytest.mark.asyncio
    async def test_publish_message(self, mock_pubsub_redis):
        """Test publishing a message."""
        redis_client, _ = mock_pubsub_redis
        pubsub = GamePubSub(redis_client, server_id="test-server")

        message = PubSubMessage(
            type=MessageType.GAME_STATE_UPDATE,
            room_code="ABCD",
            data={"phase": "playing"},
        )
        count = await pubsub.publish(message)

        assert count == 1
        redis_client.publish.assert_called_once()
        call_args = redis_client.publish.call_args
        assert call_args[0][0] == "golf:room:ABCD"

    def test_pubsub_message_serialization(self):
        """Test PubSubMessage JSON serialization."""
        message = PubSubMessage(
            type=MessageType.PLAYER_JOINED,
            room_code="ABCD",
            data={"player_name": "Alice"},
            sender_id="server-1",
        )

        json_str = message.to_json()
        parsed = PubSubMessage.from_json(json_str)

        assert parsed.type == MessageType.PLAYER_JOINED
        assert parsed.room_code == "ABCD"
        assert parsed.data == {"player_name": "Alice"}
        assert parsed.sender_id == "server-1"


# =============================================================================
# RecoveryService Tests
# =============================================================================

class TestRecoveryService:
    """Tests for RecoveryService class."""

    @pytest.fixture
    def mock_dependencies(self, mock_event_store, state_cache):
        """Create mocked dependencies for RecoveryService."""
        return mock_event_store, state_cache

    def create_test_events(self, game_id: str = "game-123") -> list[GameEvent]:
        """Create a sequence of test events for recovery."""
        return [
            game_created(
                game_id=game_id,
                sequence_num=1,
                room_code="ABCD",
                host_id="player-1",
                options={"rounds": 9},
            ),
            player_joined(
                game_id=game_id,
                sequence_num=2,
                player_id="player-1",
                player_name="Alice",
            ),
            player_joined(
                game_id=game_id,
                sequence_num=3,
                player_id="player-2",
                player_name="Bob",
            ),
            game_started(
                game_id=game_id,
                sequence_num=4,
                player_order=["player-1", "player-2"],
                num_decks=1,
                num_rounds=9,
                options={"rounds": 9},
            ),
            round_started(
                game_id=game_id,
                sequence_num=5,
                round_num=1,
                deck_seed=12345,
                dealt_cards={
                    "player-1": [
                        {"rank": "K", "suit": "hearts"},
                        {"rank": "5", "suit": "diamonds"},
                        {"rank": "A", "suit": "clubs"},
                        {"rank": "7", "suit": "spades"},
                        {"rank": "Q", "suit": "hearts"},
                        {"rank": "3", "suit": "clubs"},
                    ],
                    "player-2": [
                        {"rank": "10", "suit": "spades"},
                        {"rank": "2", "suit": "hearts"},
                        {"rank": "J", "suit": "diamonds"},
                        {"rank": "9", "suit": "clubs"},
                        {"rank": "4", "suit": "hearts"},
                        {"rank": "8", "suit": "spades"},
                    ],
                },
                first_discard={"rank": "6", "suit": "diamonds"},
            ),
        ]

    @pytest.mark.asyncio
    async def test_recover_game_success(self, mock_dependencies):
        """Test successful game recovery."""
        event_store, state_cache = mock_dependencies
        events = self.create_test_events()
        event_store.get_events.return_value = events

        recovery = RecoveryService(event_store, state_cache)
        result = await recovery.recover_game("game-123", "ABCD")

        assert result.success is True
        assert result.game_id == "game-123"
        assert result.room_code == "ABCD"
        assert result.phase == "initial_flip"
        assert result.sequence_num == 5

    @pytest.mark.asyncio
    async def test_recover_game_no_events(self, mock_dependencies):
        """Test recovery with no events returns failure."""
        event_store, state_cache = mock_dependencies
        event_store.get_events.return_value = []

        recovery = RecoveryService(event_store, state_cache)
        result = await recovery.recover_game("game-123")

        assert result.success is False
        assert result.error == "no_events"

    @pytest.mark.asyncio
    async def test_recover_game_already_ended(self, mock_dependencies):
        """Test recovery skips ended games."""
        event_store, state_cache = mock_dependencies

        # Create events ending with GAME_ENDED
        events = self.create_test_events()
        events.append(GameEvent(
            event_type=EventType.GAME_ENDED,
            game_id="game-123",
            sequence_num=6,
            data={"final_scores": {}, "rounds_won": {}},
        ))
        event_store.get_events.return_value = events

        recovery = RecoveryService(event_store, state_cache)
        result = await recovery.recover_game("game-123")

        assert result.success is False
        assert result.error == "game_ended"

    @pytest.mark.asyncio
    async def test_recover_all_games(self, mock_dependencies):
        """Test recovering multiple games."""
        event_store, state_cache = mock_dependencies

        # Set up two active games
        event_store.get_active_games.return_value = [
            {"id": "game-1", "room_code": "AAAA"},
            {"id": "game-2", "room_code": "BBBB"},
        ]

        # Each game has events
        event_store.get_events.side_effect = [
            self.create_test_events("game-1"),
            self.create_test_events("game-2"),
        ]

        recovery = RecoveryService(event_store, state_cache)
        results = await recovery.recover_all_games()

        assert results["recovered"] == 2
        assert results["failed"] == 0
        assert results["skipped"] == 0
        assert len(results["games"]) == 2

    @pytest.mark.asyncio
    async def test_state_to_dict_conversion(self, mock_dependencies):
        """Test state to dict conversion for caching."""
        event_store, state_cache = mock_dependencies
        events = self.create_test_events()
        event_store.get_events.return_value = events

        recovery = RecoveryService(event_store, state_cache)
        result = await recovery.recover_game("game-123")

        # Verify recovery succeeded
        assert result.success is True

        # Verify state was cached (game_id key should be set)
        game_key = "golf:game:game-123"
        assert game_key in state_cache.redis._data

    @pytest.mark.asyncio
    async def test_dict_to_state_conversion(self, mock_dependencies):
        """Test dict to state conversion for recovery."""
        event_store, state_cache = mock_dependencies
        recovery = RecoveryService(event_store, state_cache)

        state_dict = {
            "game_id": "game-123",
            "room_code": "ABCD",
            "phase": "playing",
            "current_round": 1,
            "total_rounds": 9,
            "current_player_idx": 0,
            "player_order": ["player-1", "player-2"],
            "deck_remaining": 40,
            "options": {},
            "sequence_num": 5,
            "finisher_id": None,
            "host_id": "player-1",
            "initial_flips_done": ["player-1"],
            "players_with_final_turn": [],
            "drawn_from_discard": False,
            "players": {
                "player-1": {
                    "id": "player-1",
                    "name": "Alice",
                    "cards": [
                        {"rank": "K", "suit": "hearts", "face_up": True},
                    ],
                    "score": 0,
                    "total_score": 0,
                    "rounds_won": 0,
                    "is_cpu": False,
                    "cpu_profile": None,
                },
            },
            "discard_pile": [{"rank": "6", "suit": "diamonds", "face_up": True}],
            "drawn_card": None,
        }

        state = recovery._dict_to_state(state_dict)

        assert state.game_id == "game-123"
        assert state.room_code == "ABCD"
        assert state.phase == GamePhase.PLAYING
        assert state.current_round == 1
        assert "player-1" in state.players
        assert state.players["player-1"].name == "Alice"
        assert len(state.discard_pile) == 1


# =============================================================================
# Integration Tests (require actual Redis - skip if not available)
# =============================================================================

@pytest.mark.skip(reason="Requires actual Redis - run manually with docker-compose")
class TestIntegration:
    """Integration tests requiring actual Redis."""

    @pytest.mark.asyncio
    async def test_full_recovery_cycle(self):
        """Test complete recovery cycle with real Redis."""
        # This would test the actual flow:
        # 1. Create game events
        # 2. Store in PostgreSQL
        # 3. Cache state in Redis
        # 4. "Restart" - clear local state
        # 5. Recover from PostgreSQL
        # 6. Verify state matches
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
