"""
Tests for event sourcing and state replay.

These tests verify that:
1. Events are emitted correctly from game actions
2. State can be rebuilt from events
3. Rebuilt state matches original game state
4. Events are applied in correct sequence order
"""

import pytest
from typing import Optional

from game import Game, GamePhase, GameOptions, Player
from models.events import GameEvent, EventType
from models.game_state import RebuiltGameState, rebuild_state


class EventCollector:
    """Helper class to collect events from a game."""

    def __init__(self):
        self.events: list[GameEvent] = []

    def collect(self, event: GameEvent) -> None:
        """Callback to collect an event."""
        self.events.append(event)

    def clear(self) -> None:
        """Clear collected events."""
        self.events = []


def create_test_game(
    num_players: int = 2,
    options: Optional[GameOptions] = None,
) -> tuple[Game, EventCollector]:
    """
    Create a game with event collection enabled.

    Returns:
        Tuple of (Game, EventCollector).
    """
    game = Game()
    collector = EventCollector()
    game.set_event_emitter(collector.collect)

    # Emit game created
    game.emit_game_created("TEST", "p1")

    # Add players
    for i in range(num_players):
        player = Player(id=f"p{i+1}", name=f"Player {i+1}")
        game.add_player(player)

    return game, collector


class TestEventEmission:
    """Test that events are emitted correctly."""

    def test_game_created_event(self):
        """Game created event should be first event."""
        game, collector = create_test_game(num_players=0)

        assert len(collector.events) == 1
        event = collector.events[0]
        assert event.event_type == EventType.GAME_CREATED
        assert event.sequence_num == 1
        assert event.data["room_code"] == "TEST"

    def test_player_joined_events(self):
        """Player joined events should be emitted for each player."""
        game, collector = create_test_game(num_players=3)

        # game_created + 3 player_joined
        assert len(collector.events) == 4

        joined_events = [e for e in collector.events if e.event_type == EventType.PLAYER_JOINED]
        assert len(joined_events) == 3

        for i, event in enumerate(joined_events):
            assert event.player_id == f"p{i+1}"
            assert event.data["player_name"] == f"Player {i+1}"

    def test_game_started_and_round_started_events(self):
        """Starting game should emit game_started and round_started."""
        game, collector = create_test_game(num_players=2)
        initial_count = len(collector.events)

        game.start_game(num_decks=1, num_rounds=3, options=GameOptions())

        new_events = collector.events[initial_count:]

        # Should have game_started and round_started
        event_types = [e.event_type for e in new_events]
        assert EventType.GAME_STARTED in event_types
        assert EventType.ROUND_STARTED in event_types

        # Verify round_started has deck_seed
        round_started = next(e for e in new_events if e.event_type == EventType.ROUND_STARTED)
        assert "deck_seed" in round_started.data
        assert "dealt_cards" in round_started.data
        assert "first_discard" in round_started.data

    def test_initial_flip_event(self):
        """Initial flip should emit event with card positions."""
        game, collector = create_test_game(num_players=2)
        game.start_game(num_decks=1, num_rounds=1, options=GameOptions(initial_flips=2))

        initial_count = len(collector.events)
        game.flip_initial_cards("p1", [0, 1])

        new_events = collector.events[initial_count:]
        flip_events = [e for e in new_events if e.event_type == EventType.INITIAL_FLIP]

        assert len(flip_events) == 1
        event = flip_events[0]
        assert event.player_id == "p1"
        assert event.data["positions"] == [0, 1]
        assert len(event.data["cards"]) == 2

    def test_draw_card_event(self):
        """Drawing a card should emit card_drawn event."""
        game, collector = create_test_game(num_players=2)
        game.start_game(num_decks=1, num_rounds=1, options=GameOptions(initial_flips=0))

        current = game.current_player()
        initial_count = len(collector.events)
        card = game.draw_card(current.id, "deck")

        assert card is not None
        new_events = collector.events[initial_count:]
        draw_events = [e for e in new_events if e.event_type == EventType.CARD_DRAWN]

        assert len(draw_events) == 1
        event = draw_events[0]
        assert event.player_id == current.id
        assert event.data["source"] == "deck"
        assert event.data["card"]["rank"] == card.rank.value

    def test_swap_card_event(self):
        """Swapping a card should emit card_swapped event."""
        game, collector = create_test_game(num_players=2)
        game.start_game(num_decks=1, num_rounds=1, options=GameOptions(initial_flips=0))

        current = game.current_player()
        game.draw_card(current.id, "deck")

        initial_count = len(collector.events)
        old_card = game.swap_card(current.id, 0)

        assert old_card is not None
        new_events = collector.events[initial_count:]
        swap_events = [e for e in new_events if e.event_type == EventType.CARD_SWAPPED]

        assert len(swap_events) == 1
        event = swap_events[0]
        assert event.player_id == current.id
        assert event.data["position"] == 0

    def test_discard_card_event(self):
        """Discarding drawn card should emit card_discarded event."""
        game, collector = create_test_game(num_players=2)
        game.start_game(num_decks=1, num_rounds=1, options=GameOptions(initial_flips=0))

        current = game.current_player()
        drawn = game.draw_card(current.id, "deck")

        initial_count = len(collector.events)
        game.discard_drawn(current.id)

        new_events = collector.events[initial_count:]
        discard_events = [e for e in new_events if e.event_type == EventType.CARD_DISCARDED]

        assert len(discard_events) == 1
        event = discard_events[0]
        assert event.player_id == current.id
        assert event.data["card"]["rank"] == drawn.rank.value


class TestDeckSeeding:
    """Test deterministic deck shuffling."""

    def test_same_seed_same_order(self):
        """Same seed should produce same card order."""
        from game import Deck

        deck1 = Deck(num_decks=1, seed=12345)
        deck2 = Deck(num_decks=1, seed=12345)

        cards1 = [deck1.draw() for _ in range(10)]
        cards2 = [deck2.draw() for _ in range(10)]

        for c1, c2 in zip(cards1, cards2):
            assert c1.rank == c2.rank
            assert c1.suit == c2.suit

    def test_different_seed_different_order(self):
        """Different seeds should produce different order."""
        from game import Deck

        deck1 = Deck(num_decks=1, seed=12345)
        deck2 = Deck(num_decks=1, seed=54321)

        cards1 = [deck1.draw() for _ in range(52)]
        cards2 = [deck2.draw() for _ in range(52)]

        # At least some cards should be different
        differences = sum(
            1 for c1, c2 in zip(cards1, cards2)
            if c1.rank != c2.rank or c1.suit != c2.suit
        )
        assert differences > 10  # Very unlikely to have <10 differences


class TestEventSequencing:
    """Test event sequence ordering."""

    def test_sequence_numbers_increment(self):
        """Event sequence numbers should increment monotonically."""
        game, collector = create_test_game(num_players=2)
        game.start_game(num_decks=1, num_rounds=1, options=GameOptions(initial_flips=0))

        # Play a few turns
        game.draw_card("p1", "deck")
        game.discard_drawn("p1")
        game.draw_card("p2", "deck")
        game.swap_card("p2", 0)

        sequences = [e.sequence_num for e in collector.events]
        for i in range(1, len(sequences)):
            assert sequences[i] == sequences[i-1] + 1, \
                f"Sequence gap: {sequences[i-1]} -> {sequences[i]}"

    def test_all_events_have_game_id(self):
        """All events should have the same game_id."""
        game, collector = create_test_game(num_players=2)
        game.start_game(num_decks=1, num_rounds=1, options=GameOptions(initial_flips=0))

        game_id = game.game_id
        for event in collector.events:
            assert event.game_id == game_id


class TestStateRebuilder:
    """Test rebuilding state from events."""

    def test_rebuild_empty_events_raises(self):
        """Cannot rebuild from empty event list."""
        with pytest.raises(ValueError):
            rebuild_state([])

    def test_rebuild_basic_game(self):
        """Can rebuild state from basic game events."""
        game, collector = create_test_game(num_players=2)
        game.start_game(num_decks=1, num_rounds=1, options=GameOptions(initial_flips=2))

        # Do initial flips
        game.flip_initial_cards("p1", [0, 1])
        game.flip_initial_cards("p2", [0, 1])

        # Rebuild state
        state = rebuild_state(collector.events)

        assert state.game_id == game.game_id
        assert state.room_code == "TEST"
        assert len(state.players) == 2
        # Compare enum values since they're from different modules
        assert state.phase.value == "playing"
        assert state.current_round == 1

    def test_rebuild_matches_player_cards(self):
        """Rebuilt player cards should match original."""
        game, collector = create_test_game(num_players=2)
        game.start_game(num_decks=1, num_rounds=1, options=GameOptions(initial_flips=2))

        game.flip_initial_cards("p1", [0, 1])
        game.flip_initial_cards("p2", [0, 1])

        # Rebuild and compare
        state = rebuild_state(collector.events)

        for player in game.players:
            rebuilt_player = state.get_player(player.id)
            assert rebuilt_player is not None
            assert len(rebuilt_player.cards) == 6

            for i, (orig, rebuilt) in enumerate(zip(player.cards, rebuilt_player.cards)):
                assert rebuilt.rank == orig.rank.value, f"Rank mismatch at position {i}"
                assert rebuilt.suit == orig.suit.value, f"Suit mismatch at position {i}"
                assert rebuilt.face_up == orig.face_up, f"Face up mismatch at position {i}"

    def test_rebuild_after_turns(self):
        """Rebuilt state should match after several turns."""
        game, collector = create_test_game(num_players=2)
        game.start_game(num_decks=1, num_rounds=1, options=GameOptions(initial_flips=0))

        # Play several turns
        for _ in range(5):
            current = game.current_player()
            if not current:
                break

            game.draw_card(current.id, "deck")
            game.discard_drawn(current.id)

            if game.phase == GamePhase.ROUND_OVER:
                break

        # Rebuild and verify
        state = rebuild_state(collector.events)

        assert state.current_player_idx == game.current_player_index
        assert len(state.discard_pile) > 0

    def test_rebuild_sequence_validation(self):
        """Applying events out of order should fail."""
        game, collector = create_test_game(num_players=2)
        game.start_game(num_decks=1, num_rounds=1, options=GameOptions(initial_flips=0))

        # Skip first event
        events = collector.events[1:]

        with pytest.raises(ValueError, match="Expected sequence"):
            rebuild_state(events)


class TestFullGameReplay:
    """Test complete game replay scenarios."""

    def test_play_and_replay_single_round(self):
        """Play a full round and verify replay matches."""
        game, collector = create_test_game(num_players=2)
        game.start_game(num_decks=1, num_rounds=1, options=GameOptions(initial_flips=2))

        # Initial flips
        game.flip_initial_cards("p1", [0, 1])
        game.flip_initial_cards("p2", [0, 1])

        # Play until round ends
        turn_count = 0
        max_turns = 100
        while game.phase not in (GamePhase.ROUND_OVER, GamePhase.GAME_OVER) and turn_count < max_turns:
            current = game.current_player()
            if not current:
                break

            game.draw_card(current.id, "deck")
            game.discard_drawn(current.id)
            turn_count += 1

        # Rebuild and verify final state
        state = rebuild_state(collector.events)

        # Phase should match
        assert state.phase.value == game.phase.value

        # Scores should match (if round is over)
        if game.phase == GamePhase.ROUND_OVER:
            for player in game.players:
                rebuilt_player = state.get_player(player.id)
                assert rebuilt_player is not None
                assert rebuilt_player.score == player.score

    def test_partial_replay(self):
        """Can replay to any point in the game."""
        game, collector = create_test_game(num_players=2)
        game.start_game(num_decks=1, num_rounds=1, options=GameOptions(initial_flips=0))

        # Play several turns
        for _ in range(10):
            current = game.current_player()
            if not current or game.phase == GamePhase.ROUND_OVER:
                break
            game.draw_card(current.id, "deck")
            game.discard_drawn(current.id)

        # Replay to different points
        for n in range(1, len(collector.events) + 1):
            partial_events = collector.events[:n]
            state = rebuild_state(partial_events)
            assert state.sequence_num == n

    def test_swap_action_replay(self):
        """Verify swap actions are correctly replayed."""
        game, collector = create_test_game(num_players=2)
        game.start_game(num_decks=1, num_rounds=1, options=GameOptions(initial_flips=0))

        # Do a swap
        current = game.current_player()
        drawn = game.draw_card(current.id, "deck")
        old_card = game.get_player(current.id).cards[0]
        game.swap_card(current.id, 0)

        # Rebuild and verify
        state = rebuild_state(collector.events)
        rebuilt_player = state.get_player(current.id)

        # The swapped card should be in the hand
        assert rebuilt_player.cards[0].rank == drawn.rank.value
        assert rebuilt_player.cards[0].face_up is True

        # The old card should be on discard pile
        assert state.discard_pile[-1].rank == old_card.rank.value


class TestEventSerialization:
    """Test event serialization/deserialization."""

    def test_event_to_dict_roundtrip(self):
        """Events can be serialized and deserialized."""
        game, collector = create_test_game(num_players=2)
        game.start_game(num_decks=1, num_rounds=1, options=GameOptions(initial_flips=0))

        for event in collector.events:
            event_dict = event.to_dict()
            restored = GameEvent.from_dict(event_dict)

            assert restored.event_type == event.event_type
            assert restored.game_id == event.game_id
            assert restored.sequence_num == event.sequence_num
            assert restored.player_id == event.player_id
            assert restored.data == event.data

    def test_event_to_json_roundtrip(self):
        """Events can be JSON serialized and deserialized."""
        game, collector = create_test_game(num_players=2)
        game.start_game(num_decks=1, num_rounds=1, options=GameOptions(initial_flips=0))

        for event in collector.events:
            json_str = event.to_json()
            restored = GameEvent.from_json(json_str)

            assert restored.event_type == event.event_type
            assert restored.game_id == event.game_id
            assert restored.sequence_num == event.sequence_num
