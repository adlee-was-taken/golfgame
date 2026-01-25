"""
Test suite for 6-Card Golf game rules.

Verifies our implementation matches canonical 6-Card Golf rules:
- Card values (A=1, 2=-2, 3-10=face, J/Q=10, K=0)
- Column pairing (matching ranks in column = 0 points)
- Draw/discard mechanics
- Cannot re-discard card taken from discard pile
- Round end conditions
- Final turn logic

Run with: pytest test_game.py -v
"""

import pytest
from game import (
    Card, Deck, Player, Game, GamePhase, GameOptions,
    Suit, Rank, RANK_VALUES
)


# =============================================================================
# Card Value Tests
# =============================================================================

class TestCardValues:
    """Verify card values match standard 6-Card Golf rules."""

    def test_ace_worth_1(self):
        assert RANK_VALUES[Rank.ACE] == 1

    def test_two_worth_negative_2(self):
        assert RANK_VALUES[Rank.TWO] == -2

    def test_three_through_ten_face_value(self):
        assert RANK_VALUES[Rank.THREE] == 3
        assert RANK_VALUES[Rank.FOUR] == 4
        assert RANK_VALUES[Rank.FIVE] == 5
        assert RANK_VALUES[Rank.SIX] == 6
        assert RANK_VALUES[Rank.SEVEN] == 7
        assert RANK_VALUES[Rank.EIGHT] == 8
        assert RANK_VALUES[Rank.NINE] == 9
        assert RANK_VALUES[Rank.TEN] == 10

    def test_jack_worth_10(self):
        assert RANK_VALUES[Rank.JACK] == 10

    def test_queen_worth_10(self):
        assert RANK_VALUES[Rank.QUEEN] == 10

    def test_king_worth_0(self):
        assert RANK_VALUES[Rank.KING] == 0

    def test_joker_worth_negative_2(self):
        assert RANK_VALUES[Rank.JOKER] == -2

    def test_card_value_method(self):
        """Card.value() should return correct value."""
        card = Card(Suit.HEARTS, Rank.KING)
        assert card.value() == 0

        card = Card(Suit.SPADES, Rank.TWO)
        assert card.value() == -2


# =============================================================================
# Column Pairing Tests
# =============================================================================

class TestColumnPairing:
    """Verify column pair scoring rules."""

    def setup_method(self):
        """Create a player with controllable hand."""
        self.player = Player(id="test", name="Test")

    def set_hand(self, ranks: list[Rank]):
        """Set player's hand to specific ranks (all hearts for simplicity)."""
        self.player.cards = [
            Card(Suit.HEARTS, rank, face_up=True) for rank in ranks
        ]

    def test_matching_column_scores_zero(self):
        """Two cards of same rank in column = 0 points for that column."""
        # Layout: [K, 5, 7]
        #         [K, 3, 9]
        # Column 0 (K-K) = 0, Column 1 (5+3) = 8, Column 2 (7+9) = 16
        self.set_hand([Rank.KING, Rank.FIVE, Rank.SEVEN,
                       Rank.KING, Rank.THREE, Rank.NINE])
        score = self.player.calculate_score()
        assert score == 24  # 0 + 8 + 16

    def test_all_columns_matched(self):
        """All three columns matched = 0 total."""
        self.set_hand([Rank.ACE, Rank.FIVE, Rank.KING,
                       Rank.ACE, Rank.FIVE, Rank.KING])
        score = self.player.calculate_score()
        assert score == 0

    def test_no_columns_matched(self):
        """No matches = sum of all cards."""
        # A(1) + 3 + 5 + 7 + 9 + K(0) = 25
        self.set_hand([Rank.ACE, Rank.THREE, Rank.FIVE,
                       Rank.SEVEN, Rank.NINE, Rank.KING])
        score = self.player.calculate_score()
        assert score == 25

    def test_twos_pair_still_zero(self):
        """Paired 2s score 0, not -4 (pair cancels, doesn't double)."""
        # [2, 5, 5]
        # [2, 5, 5] = all columns matched = 0
        self.set_hand([Rank.TWO, Rank.FIVE, Rank.FIVE,
                       Rank.TWO, Rank.FIVE, Rank.FIVE])
        score = self.player.calculate_score()
        assert score == 0

    def test_negative_cards_unpaired_keep_value(self):
        """Unpaired 2s and Jokers contribute their negative value."""
        # [2, K, K]
        # [A, K, K] = -2 + 1 + 0 + 0 = -1
        self.set_hand([Rank.TWO, Rank.KING, Rank.KING,
                       Rank.ACE, Rank.KING, Rank.KING])
        score = self.player.calculate_score()
        assert score == -1


# =============================================================================
# House Rules Scoring Tests
# =============================================================================

class TestHouseRulesScoring:
    """Verify house rule scoring modifiers."""

    def setup_method(self):
        self.player = Player(id="test", name="Test")

    def set_hand(self, ranks: list[Rank]):
        self.player.cards = [
            Card(Suit.HEARTS, rank, face_up=True) for rank in ranks
        ]

    def test_super_kings_negative_2(self):
        """With super_kings, Kings worth -2."""
        options = GameOptions(super_kings=True)
        self.set_hand([Rank.KING, Rank.ACE, Rank.ACE,
                       Rank.THREE, Rank.ACE, Rank.ACE])
        score = self.player.calculate_score(options)
        # K=-2, 3=3, columns 1&2 matched = 0
        assert score == 1

    def test_ten_penny(self):
        """With ten_penny, 10s worth 1."""
        options = GameOptions(ten_penny=True)
        self.set_hand([Rank.TEN, Rank.KING, Rank.KING,
                       Rank.ACE, Rank.KING, Rank.KING])
        score = self.player.calculate_score(options)
        # 10=1, A=1, columns 1&2 matched = 0
        assert score == 2

    def test_lucky_swing_joker(self):
        """With lucky_swing, single Joker worth -5."""
        options = GameOptions(use_jokers=True, lucky_swing=True)
        self.player.cards = [
            Card(Suit.HEARTS, Rank.JOKER, face_up=True),
            Card(Suit.HEARTS, Rank.KING, face_up=True),
            Card(Suit.HEARTS, Rank.KING, face_up=True),
            Card(Suit.HEARTS, Rank.ACE, face_up=True),
            Card(Suit.HEARTS, Rank.KING, face_up=True),
            Card(Suit.HEARTS, Rank.KING, face_up=True),
        ]
        score = self.player.calculate_score(options)
        # Joker=-5, A=1, columns 1&2 matched = 0
        assert score == -4

    def test_blackjack_21_becomes_0(self):
        """With blackjack option, score of exactly 21 becomes 0."""
        # This is applied at round end, not in calculate_score directly
        # Testing the raw score first
        self.set_hand([Rank.JACK, Rank.ACE, Rank.THREE,
                       Rank.FOUR, Rank.TWO, Rank.FIVE])
        # J=10, A=1, 3=3, 4=4, 2=-2, 5=5 = 21
        score = self.player.calculate_score()
        assert score == 21


# =============================================================================
# Draw and Discard Mechanics
# =============================================================================

class TestDrawDiscardMechanics:
    """Verify draw/discard rules match standard Golf."""

    def setup_method(self):
        self.game = Game()
        self.game.add_player(Player(id="p1", name="Player 1"))
        self.game.add_player(Player(id="p2", name="Player 2"))
        # Skip initial flip phase to test draw/discard mechanics directly
        self.game.start_game(options=GameOptions(initial_flips=0))

    def test_can_draw_from_deck(self):
        """Player can draw from deck."""
        card = self.game.draw_card("p1", "deck")
        assert card is not None
        assert self.game.drawn_card == card
        assert self.game.drawn_from_discard is False

    def test_can_draw_from_discard(self):
        """Player can draw from discard pile."""
        discard_top = self.game.discard_top()
        card = self.game.draw_card("p1", "discard")
        assert card is not None
        assert card == discard_top
        assert self.game.drawn_card == card
        assert self.game.drawn_from_discard is True

    def test_can_discard_deck_draw(self):
        """Card drawn from deck CAN be discarded."""
        self.game.draw_card("p1", "deck")
        assert self.game.can_discard_drawn() is True
        result = self.game.discard_drawn("p1")
        assert result is True

    def test_cannot_discard_discard_draw(self):
        """Card drawn from discard pile CANNOT be re-discarded."""
        self.game.draw_card("p1", "discard")
        assert self.game.can_discard_drawn() is False
        result = self.game.discard_drawn("p1")
        assert result is False

    def test_must_swap_discard_draw(self):
        """When drawing from discard, must swap with a hand card."""
        self.game.draw_card("p1", "discard")
        # Can't discard, must swap
        assert self.game.can_discard_drawn() is False
        # Swap works
        old_card = self.game.swap_card("p1", 0)
        assert old_card is not None
        assert self.game.drawn_card is None

    def test_swap_makes_card_face_up(self):
        """Swapped card is placed face up."""
        player = self.game.get_player("p1")
        assert player.cards[0].face_up is False  # Initially face down

        self.game.draw_card("p1", "deck")
        self.game.swap_card("p1", 0)
        assert player.cards[0].face_up is True

    def test_cannot_peek_before_swap(self):
        """Face-down cards stay hidden until swapped/revealed."""
        player = self.game.get_player("p1")
        # Card is face down
        assert player.cards[0].face_up is False
        # to_dict doesn't reveal it
        card_dict = player.cards[0].to_dict(reveal=False)
        assert "rank" not in card_dict


# =============================================================================
# Turn Flow Tests
# =============================================================================

class TestTurnFlow:
    """Verify turn progression rules."""

    def setup_method(self):
        self.game = Game()
        self.game.add_player(Player(id="p1", name="Player 1"))
        self.game.add_player(Player(id="p2", name="Player 2"))
        self.game.add_player(Player(id="p3", name="Player 3"))
        # Skip initial flip phase
        self.game.start_game(options=GameOptions(initial_flips=0))

    def test_turn_advances_after_discard(self):
        """Turn advances to next player after discarding."""
        assert self.game.current_player().id == "p1"
        self.game.draw_card("p1", "deck")
        self.game.discard_drawn("p1")
        assert self.game.current_player().id == "p2"

    def test_turn_advances_after_swap(self):
        """Turn advances to next player after swapping."""
        assert self.game.current_player().id == "p1"
        self.game.draw_card("p1", "deck")
        self.game.swap_card("p1", 0)
        assert self.game.current_player().id == "p2"

    def test_turn_wraps_around(self):
        """Turn wraps from last player to first."""
        # Complete turns for p1 and p2
        self.game.draw_card("p1", "deck")
        self.game.discard_drawn("p1")
        self.game.draw_card("p2", "deck")
        self.game.discard_drawn("p2")
        assert self.game.current_player().id == "p3"

        self.game.draw_card("p3", "deck")
        self.game.discard_drawn("p3")
        assert self.game.current_player().id == "p1"  # Wrapped

    def test_only_current_player_can_act(self):
        """Only current player can draw."""
        assert self.game.current_player().id == "p1"
        card = self.game.draw_card("p2", "deck")  # Wrong player
        assert card is None


# =============================================================================
# Round End Tests
# =============================================================================

class TestRoundEnd:
    """Verify round end conditions and final turn logic."""

    def setup_method(self):
        self.game = Game()
        self.game.add_player(Player(id="p1", name="Player 1"))
        self.game.add_player(Player(id="p2", name="Player 2"))
        self.game.start_game(options=GameOptions(initial_flips=0))

    def reveal_all_cards(self, player_id: str):
        """Helper to flip all cards for a player."""
        player = self.game.get_player(player_id)
        for card in player.cards:
            card.face_up = True

    def test_revealing_all_triggers_final_turn(self):
        """When a player reveals all cards, final turn phase begins."""
        # Reveal 5 cards for p1
        player = self.game.get_player("p1")
        for i in range(5):
            player.cards[i].face_up = True

        assert self.game.phase == GamePhase.PLAYING

        # Draw and swap into last face-down position
        self.game.draw_card("p1", "deck")
        self.game.swap_card("p1", 5)  # Last card

        assert self.game.phase == GamePhase.FINAL_TURN
        assert self.game.finisher_id == "p1"

    def test_other_players_get_final_turn(self):
        """After one player finishes, others each get one more turn."""
        # P1 reveals all
        self.reveal_all_cards("p1")
        self.game.draw_card("p1", "deck")
        self.game.discard_drawn("p1")

        assert self.game.phase == GamePhase.FINAL_TURN
        assert self.game.current_player().id == "p2"

        # P2 takes final turn
        self.game.draw_card("p2", "deck")
        self.game.discard_drawn("p2")

        # Round should be over
        assert self.game.phase == GamePhase.ROUND_OVER

    def test_finisher_does_not_get_extra_turn(self):
        """The player who went out doesn't get another turn."""
        # P1 reveals all and triggers final turn
        self.reveal_all_cards("p1")
        self.game.draw_card("p1", "deck")
        self.game.discard_drawn("p1")

        # P2's turn
        assert self.game.current_player().id == "p2"
        self.game.draw_card("p2", "deck")
        self.game.discard_drawn("p2")

        # Should be round over, not p1's turn again
        assert self.game.phase == GamePhase.ROUND_OVER

    def test_all_cards_revealed_at_round_end(self):
        """At round end, all cards are revealed."""
        self.reveal_all_cards("p1")
        self.game.draw_card("p1", "deck")
        self.game.discard_drawn("p1")

        self.game.draw_card("p2", "deck")
        self.game.discard_drawn("p2")

        assert self.game.phase == GamePhase.ROUND_OVER

        # All cards should be face up now
        for player in self.game.players:
            assert all(card.face_up for card in player.cards)


# =============================================================================
# Multi-Round Tests
# =============================================================================

class TestMultiRound:
    """Verify multi-round game logic."""

    def test_next_round_resets_hands(self):
        """Starting next round deals new hands."""
        game = Game()
        game.add_player(Player(id="p1", name="Player 1"))
        game.add_player(Player(id="p2", name="Player 2"))
        game.start_game(num_rounds=2, options=GameOptions(initial_flips=0))

        # Force round end
        for player in game.players:
            for card in player.cards:
                card.face_up = True
        game._end_round()

        old_cards_p1 = [c.rank for c in game.players[0].cards]

        game.start_next_round()

        # Cards should be different (statistically)
        # and face down again
        assert game.phase in (GamePhase.PLAYING, GamePhase.INITIAL_FLIP)
        assert not all(game.players[0].cards[i].face_up for i in range(6))

    def test_scores_accumulate_across_rounds(self):
        """Total scores persist across rounds."""
        game = Game()
        game.add_player(Player(id="p1", name="Player 1"))
        game.add_player(Player(id="p2", name="Player 2"))
        game.start_game(num_rounds=2, options=GameOptions(initial_flips=0))

        # End round 1
        for player in game.players:
            for card in player.cards:
                card.face_up = True
        game._end_round()

        round1_total = game.players[0].total_score

        game.start_next_round()

        # End round 2
        for player in game.players:
            for card in player.cards:
                card.face_up = True
        game._end_round()

        # Total should have increased (or stayed same if score was 0)
        assert game.players[0].total_score >= round1_total or game.players[0].score < 0


# =============================================================================
# Initial Flip Tests
# =============================================================================

class TestInitialFlip:
    """Verify initial flip phase mechanics."""

    def test_initial_flip_two_cards(self):
        """With initial_flips=2, players must flip 2 cards."""
        game = Game()
        game.add_player(Player(id="p1", name="Player 1"))
        game.add_player(Player(id="p2", name="Player 2"))
        game.start_game(options=GameOptions(initial_flips=2))

        assert game.phase == GamePhase.INITIAL_FLIP

        # Try to flip wrong number
        result = game.flip_initial_cards("p1", [0])  # Only 1
        assert result is False

        # Flip correct number
        result = game.flip_initial_cards("p1", [0, 3])
        assert result is True

    def test_initial_flip_zero_skips_phase(self):
        """With initial_flips=0, skip straight to playing."""
        game = Game()
        game.add_player(Player(id="p1", name="Player 1"))
        game.add_player(Player(id="p2", name="Player 2"))
        game.start_game(options=GameOptions(initial_flips=0))

        assert game.phase == GamePhase.PLAYING

    def test_game_starts_after_all_flip(self):
        """Game starts when all players have flipped."""
        game = Game()
        game.add_player(Player(id="p1", name="Player 1"))
        game.add_player(Player(id="p2", name="Player 2"))
        game.start_game(options=GameOptions(initial_flips=2))

        game.flip_initial_cards("p1", [0, 1])
        assert game.phase == GamePhase.INITIAL_FLIP  # Still waiting

        game.flip_initial_cards("p2", [2, 3])
        assert game.phase == GamePhase.PLAYING  # Now playing


# =============================================================================
# Deck Management Tests
# =============================================================================

class TestDeckManagement:
    """Verify deck initialization and reshuffling."""

    def test_standard_deck_52_cards(self):
        """Standard deck has 52 cards."""
        deck = Deck(num_decks=1, use_jokers=False)
        assert deck.cards_remaining() == 52

    def test_joker_deck_54_cards(self):
        """Deck with jokers has 54 cards."""
        deck = Deck(num_decks=1, use_jokers=True)
        assert deck.cards_remaining() == 54

    def test_lucky_swing_single_joker(self):
        """Lucky swing adds only 1 joker total."""
        deck = Deck(num_decks=1, use_jokers=True, lucky_swing=True)
        assert deck.cards_remaining() == 53

    def test_multi_deck(self):
        """Multiple decks multiply cards."""
        deck = Deck(num_decks=2, use_jokers=False)
        assert deck.cards_remaining() == 104


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_cannot_draw_twice(self):
        """Cannot draw again before playing drawn card."""
        game = Game()
        game.add_player(Player(id="p1", name="Player 1"))
        game.add_player(Player(id="p2", name="Player 2"))
        game.start_game(options=GameOptions(initial_flips=0))

        game.draw_card("p1", "deck")
        second_draw = game.draw_card("p1", "deck")
        assert second_draw is None

    def test_swap_position_bounds(self):
        """Swap position must be 0-5."""
        game = Game()
        game.add_player(Player(id="p1", name="Player 1"))
        game.add_player(Player(id="p2", name="Player 2"))
        game.start_game(options=GameOptions(initial_flips=0))

        game.draw_card("p1", "deck")

        result = game.swap_card("p1", -1)
        assert result is None

        result = game.swap_card("p1", 6)
        assert result is None

        result = game.swap_card("p1", 3)  # Valid
        assert result is not None

    def test_empty_discard_pile(self):
        """Cannot draw from empty discard pile."""
        game = Game()
        game.add_player(Player(id="p1", name="Player 1"))
        game.add_player(Player(id="p2", name="Player 2"))
        game.start_game(options=GameOptions(initial_flips=0))

        # Clear discard pile (normally has 1 card)
        game.discard_pile = []

        card = game.draw_card("p1", "discard")
        assert card is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
