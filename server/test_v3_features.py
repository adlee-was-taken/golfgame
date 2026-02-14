"""
Test suite for V3 features in 6-Card Golf.

Covers:
- V3_01: Dealer rotation
- V3_03/V3_05: Finisher tracking, knock penalty/bonus
- V3_09: Knock early

Run with: pytest test_v3_features.py -v
"""

import pytest
from game import (
    Card, Deck, Player, Game, GamePhase, GameOptions,
    Suit, Rank, RANK_VALUES
)


# =============================================================================
# Helper: create a game with N players in PLAYING phase
# =============================================================================

def make_game(num_players=2, options=None, rounds=1):
    """Create a game with N players, dealt and in PLAYING phase."""
    opts = options or GameOptions()
    game = Game(num_rounds=rounds, options=opts)
    for i in range(num_players):
        game.add_player(Player(id=f"p{i}", name=f"Player {i}"))
    game.start_round()
    # Force into PLAYING phase (skip initial flip)
    if game.phase == GamePhase.INITIAL_FLIP:
        for p in game.players:
            game.flip_initial_cards(p.id, [0, 1])
    return game


def flip_all_but(player, keep_down=0):
    """Flip all cards face-up except `keep_down` cards."""
    for i, card in enumerate(player.cards):
        if i < len(player.cards) - keep_down:
            card.face_up = True
        else:
            card.face_up = False


def set_hand(player, ranks):
    """Set player hand to specific ranks (all hearts, all face-up)."""
    player.cards = [
        Card(Suit.HEARTS, rank, face_up=True) for rank in ranks
    ]


# =============================================================================
# V3_01: Dealer Rotation
# =============================================================================

class TestDealerRotation:
    """Verify dealer rotates each round and first player is after dealer."""

    def test_initial_dealer_is_zero(self):
        game = make_game(3)
        assert game.dealer_idx == 0

    def test_first_player_is_after_dealer(self):
        game = make_game(3)
        # Dealer is 0, first player should be 1
        assert game.current_player_index == 1

    def test_dealer_rotates_after_round(self):
        game = make_game(3, rounds=3)
        assert game.dealer_idx == 0

        # End the round by having a player flip all cards
        player = game.players[game.current_player_index]
        for card in player.cards:
            card.face_up = True
        game.finisher_id = player.id
        game.phase = GamePhase.FINAL_TURN

        # Give remaining players their final turns
        game.players_with_final_turn = {p.id for p in game.players}
        game._end_round()

        # Start next round
        game.start_next_round()
        assert game.dealer_idx == 1
        # First player should be after new dealer
        assert game.current_player_index == 2

    def test_dealer_wraps_around(self):
        game = make_game(3, rounds=4)

        # Simulate 3 rounds to wrap dealer
        for expected_dealer in [0, 1, 2]:
            assert game.dealer_idx == expected_dealer

            # Force round end
            player = game.players[game.current_player_index]
            for card in player.cards:
                card.face_up = True
            game.finisher_id = player.id
            game.phase = GamePhase.FINAL_TURN
            game.players_with_final_turn = {p.id for p in game.players}
            game._end_round()
            game.start_next_round()

        # After 3 rotations with 3 players, wraps back to 0
        assert game.dealer_idx == 0

    def test_dealer_in_state_dict(self):
        game = make_game(3)
        state = game.get_state("p0")
        assert "dealer_id" in state
        assert "dealer_idx" in state
        assert state["dealer_id"] == "p0"
        assert state["dealer_idx"] == 0


# =============================================================================
# V3_03/V3_05: Finisher Tracking + Knock Penalty/Bonus
# =============================================================================

class TestFinisherTracking:
    """Verify finisher_id is set and penalties/bonuses apply."""

    def test_finisher_id_initially_none(self):
        game = make_game(2)
        assert game.finisher_id is None

    def test_finisher_set_when_all_flipped(self):
        game = make_game(2)
        # Get current player and flip all their cards
        player = game.players[game.current_player_index]
        for card in player.cards:
            card.face_up = True

        # Draw and discard to trigger _check_end_turn
        card = game.deck.draw()
        if card:
            game.drawn_card = card
            game.discard_drawn(player.id)

        assert game.finisher_id == player.id
        assert game.phase == GamePhase.FINAL_TURN

    def test_finisher_in_state_dict(self):
        game = make_game(2)
        game.finisher_id = "p0"
        state = game.get_state("p0")
        assert state["finisher_id"] == "p0"

    def test_knock_penalty_applied(self):
        """Finisher gets +10 if they don't have the lowest score."""
        opts = GameOptions(knock_penalty=True, initial_flips=0)
        game = make_game(2, options=opts)

        # Set hands with different ranks per column to avoid column pairing
        # Layout: [0][1][2] / [3][4][5], columns: (0,3),(1,4),(2,5)
        set_hand(game.players[0], [Rank.TEN, Rank.NINE, Rank.EIGHT,
                                    Rank.SEVEN, Rank.SIX, Rank.FIVE])  # 10+9+8+7+6+5 = 45
        set_hand(game.players[1], [Rank.ACE, Rank.THREE, Rank.FOUR,
                                    Rank.TWO, Rank.KING, Rank.ACE])  # 1+3+4+(-2)+0+1 = 7

        game.finisher_id = "p0"
        game.phase = GamePhase.FINAL_TURN
        game.players_with_final_turn = {"p0", "p1"}
        game._end_round()

        # p0 had score 45, gets +10 penalty = 55
        assert game.players[0].score == 55
        # p1 unaffected
        assert game.players[1].score == 7

    def test_knock_bonus_applied(self):
        """Finisher gets -5 bonus."""
        opts = GameOptions(knock_bonus=True, initial_flips=0)
        game = make_game(2, options=opts)

        # Different ranks per column to avoid pairing
        set_hand(game.players[0], [Rank.ACE, Rank.THREE, Rank.FOUR,
                                    Rank.TWO, Rank.KING, Rank.ACE])  # 1+3+4+(-2)+0+1 = 7
        set_hand(game.players[1], [Rank.TEN, Rank.NINE, Rank.EIGHT,
                                    Rank.SEVEN, Rank.SIX, Rank.FIVE])  # 10+9+8+7+6+5 = 45

        game.finisher_id = "p0"
        game.phase = GamePhase.FINAL_TURN
        game.players_with_final_turn = {"p0", "p1"}
        game._end_round()

        # p0 gets -5 bonus: 7 - 5 = 2
        assert game.players[0].score == 2
        assert game.players[1].score == 45


# =============================================================================
# V3_09: Knock Early
# =============================================================================

class TestKnockEarly:
    """Verify knock_early house rule mechanics."""

    def test_knock_early_disabled_by_default(self):
        opts = GameOptions()
        assert opts.knock_early is False

    def test_knock_early_requires_option(self):
        game = make_game(2)
        player = game.players[game.current_player_index]
        # Flip 4 cards, leave 2 face-down
        for i in range(4):
            player.cards[i].face_up = True

        result = game.knock_early(player.id)
        assert result is False

    def test_knock_early_with_option_enabled(self):
        opts = GameOptions(knock_early=True, initial_flips=0)
        game = make_game(2, options=opts)

        player = game.players[game.current_player_index]
        # Flip 4 cards, leave 2 face-down
        for i in range(4):
            player.cards[i].face_up = True
        for i in range(4, 6):
            player.cards[i].face_up = False

        result = game.knock_early(player.id)
        assert result is True

    def test_knock_early_requires_face_up_cards(self):
        """Must have at least 4 face-up (at most 2 face-down) to knock."""
        opts = GameOptions(knock_early=True, initial_flips=0)
        game = make_game(2, options=opts)

        player = game.players[game.current_player_index]
        # Only 3 face-up, 3 face-down — too many hidden
        for i in range(3):
            player.cards[i].face_up = True
        for i in range(3, 6):
            player.cards[i].face_up = False

        result = game.knock_early(player.id)
        assert result is False

    def test_knock_early_triggers_final_turn(self):
        opts = GameOptions(knock_early=True, initial_flips=0)
        game = make_game(2, options=opts)

        player = game.players[game.current_player_index]
        flip_all_but(player, keep_down=2)

        game.knock_early(player.id)
        assert game.phase == GamePhase.FINAL_TURN

    def test_knock_early_sets_finisher(self):
        opts = GameOptions(knock_early=True, initial_flips=0)
        game = make_game(2, options=opts)

        player = game.players[game.current_player_index]
        flip_all_but(player, keep_down=1)

        game.knock_early(player.id)
        assert game.finisher_id == player.id

    def test_knock_early_not_during_initial_flip(self):
        """Knock early should fail during initial flip phase."""
        opts = GameOptions(knock_early=True, initial_flips=2)
        game = Game(num_rounds=1, options=opts)
        game.add_player(Player(id="p0", name="Player 0"))
        game.add_player(Player(id="p1", name="Player 1"))
        game.start_round()
        # Should be in INITIAL_FLIP
        assert game.phase == GamePhase.INITIAL_FLIP

        player = game.players[0]
        flip_all_but(player, keep_down=2)

        result = game.knock_early(player.id)
        assert result is False

    def test_knock_early_fails_with_drawn_card(self):
        """Can't knock if you've already drawn a card."""
        opts = GameOptions(knock_early=True, initial_flips=0)
        game = make_game(2, options=opts)

        player = game.players[game.current_player_index]
        flip_all_but(player, keep_down=2)

        # Simulate having drawn a card
        game.drawn_card = Card(Suit.HEARTS, Rank.ACE)

        result = game.knock_early(player.id)
        assert result is False

    def test_knock_early_fails_all_face_up(self):
        """Can't knock early if all cards are already face-up (0 face-down)."""
        opts = GameOptions(knock_early=True, initial_flips=0)
        game = make_game(2, options=opts)

        player = game.players[game.current_player_index]
        for card in player.cards:
            card.face_up = True

        result = game.knock_early(player.id)
        assert result is False

    def test_knock_early_in_state_dict(self):
        opts = GameOptions(knock_early=True)
        game = make_game(2, options=opts)
        state = game.get_state("p0")
        assert state["knock_early"] is True

    def test_knock_early_active_rules(self):
        """Knock early should appear in active_rules list."""
        opts = GameOptions(knock_early=True)
        game = make_game(2, options=opts)
        state = game.get_state("p0")
        assert "Early Knock" in state["active_rules"]
