"""
Test suite for AI decision sub-functions extracted from ai.py.

Covers:
- _pair_improvement(): pair bonus / negative pair / spread bonus
- _point_gain(): face-up replacement, hidden card discount
- _reveal_and_bonus_score(): reveal scaling, comeback bonus
- _check_auto_take(): joker/king/one-eyed-jack/wolfpack auto-takes
- _has_good_swap_option(): good/bad swap previews
- calculate_swap_score(): go-out safety penalty
- should_take_discard(): integration of sub-decisions
- should_knock_early(): knock timing decisions

Run with: pytest test_ai_decisions.py -v
"""

import pytest
from game import (
    Card, Deck, Player, Game, GamePhase, GameOptions,
    Suit, Rank, RANK_VALUES
)
from ai import GolfAI, CPUProfile, get_ai_card_value


# =============================================================================
# Helpers (shared with test_v3_features.py pattern)
# =============================================================================

def make_game(num_players=2, options=None, rounds=1):
    """Create a game with N players, dealt and in PLAYING phase."""
    opts = options or GameOptions()
    game = Game(num_rounds=rounds, options=opts)
    for i in range(num_players):
        game.add_player(Player(id=f"p{i}", name=f"Player {i}"))
    game.start_round()
    if game.phase == GamePhase.INITIAL_FLIP:
        for p in game.players:
            game.flip_initial_cards(p.id, [0, 1])
    return game


def set_hand(player, ranks, face_up=True):
    """Set player hand to specific ranks (all hearts, all face-up by default)."""
    player.cards = [
        Card(Suit.HEARTS, rank, face_up=face_up) for rank in ranks
    ]


def flip_all_but(player, keep_down=0):
    """Flip all cards face-up except `keep_down` cards (from the end)."""
    for i, card in enumerate(player.cards):
        card.face_up = i < len(player.cards) - keep_down


def make_profile(**overrides):
    """Create a CPUProfile with sensible defaults, overridable."""
    defaults = dict(
        name="TestBot",
        style="balanced",
        pair_hope=0.5,
        aggression=0.5,
        swap_threshold=4,
        unpredictability=0.0,  # Deterministic by default for tests
    )
    defaults.update(overrides)
    return CPUProfile(**defaults)


# =============================================================================
# _pair_improvement
# =============================================================================

class TestPairImprovement:
    """Test pair bonus and spread bonus scoring."""

    def test_positive_pair_bonus(self):
        """Pairing two positive cards should yield a positive score."""
        game = make_game()
        player = game.players[0]
        # Position 0 has a 7, partner (pos 3) has a 7 face-up
        set_hand(player, [Rank.SEVEN, Rank.THREE, Rank.FIVE,
                          Rank.SEVEN, Rank.FOUR, Rank.SIX])
        profile = make_profile(pair_hope=0.5)
        drawn_card = Card(Suit.DIAMONDS, Rank.SEVEN)
        drawn_value = get_ai_card_value(drawn_card, game.options)

        score = GolfAI._pair_improvement(
            0, drawn_card, drawn_value, player, game.options, profile
        )
        # Pairing two 7s: bonus = (7+7) * pair_weight(1.5) = 21
        assert score > 0

    def test_negative_pair_penalty_standard(self):
        """Under standard rules, pairing negative cards is penalized."""
        game = make_game()
        player = game.players[0]
        set_hand(player, [Rank.TWO, Rank.THREE, Rank.FIVE,
                          Rank.TWO, Rank.FOUR, Rank.SIX])
        profile = make_profile(pair_hope=0.5)
        drawn_card = Card(Suit.DIAMONDS, Rank.TWO)
        drawn_value = get_ai_card_value(drawn_card, game.options)

        score = GolfAI._pair_improvement(
            0, drawn_card, drawn_value, player, game.options, profile
        )
        # Penalty for wasting negative cards under standard rules
        assert score < 0

    def test_eagle_eye_joker_pair_bonus(self):
        """Eagle Eye Joker pairs should get a large bonus."""
        opts = GameOptions(eagle_eye=True)
        game = make_game(options=opts)
        player = game.players[0]
        set_hand(player, [Rank.JOKER, Rank.THREE, Rank.FIVE,
                          Rank.JOKER, Rank.FOUR, Rank.SIX])
        profile = make_profile(pair_hope=0.5)
        drawn_card = Card(Suit.DIAMONDS, Rank.JOKER)
        drawn_value = get_ai_card_value(drawn_card, opts)

        score = GolfAI._pair_improvement(
            0, drawn_card, drawn_value, player, opts, profile
        )
        # Eagle Eye Joker pairs = 8 * pair_weight
        assert score > 0

    def test_negative_pairs_keep_value(self):
        """With negative_pairs_keep_value, pairing 2s should be good."""
        opts = GameOptions(negative_pairs_keep_value=True)
        game = make_game(options=opts)
        player = game.players[0]
        set_hand(player, [Rank.TWO, Rank.THREE, Rank.FIVE,
                          Rank.TWO, Rank.FOUR, Rank.SIX])
        profile = make_profile(pair_hope=0.5)
        drawn_card = Card(Suit.DIAMONDS, Rank.TWO)
        drawn_value = get_ai_card_value(drawn_card, opts)

        score = GolfAI._pair_improvement(
            0, drawn_card, drawn_value, player, opts, profile
        )
        assert score > 0

    def test_spread_bonus_for_excellent_card(self):
        """Spreading an Ace across columns should get a spread bonus."""
        game = make_game()
        player = game.players[0]
        set_hand(player, [Rank.SEVEN, Rank.THREE, Rank.FIVE,
                          Rank.EIGHT, Rank.FOUR, Rank.SIX])
        profile = make_profile(pair_hope=0.0)  # Spreader, not pair hunter
        drawn_card = Card(Suit.DIAMONDS, Rank.ACE)
        drawn_value = get_ai_card_value(drawn_card, game.options)

        score = GolfAI._pair_improvement(
            0, drawn_card, drawn_value, player, game.options, profile
        )
        # spread_weight = 2.0, bonus = 2.0 * 0.5 = 1.0
        assert score == pytest.approx(1.0)

    def test_no_spread_bonus_for_bad_card(self):
        """No spread bonus for high-value cards."""
        game = make_game()
        player = game.players[0]
        set_hand(player, [Rank.SEVEN, Rank.THREE, Rank.FIVE,
                          Rank.EIGHT, Rank.FOUR, Rank.SIX])
        profile = make_profile(pair_hope=0.0)
        drawn_card = Card(Suit.DIAMONDS, Rank.NINE)
        drawn_value = get_ai_card_value(drawn_card, game.options)

        score = GolfAI._pair_improvement(
            0, drawn_card, drawn_value, player, game.options, profile
        )
        assert score == 0.0


# =============================================================================
# _point_gain
# =============================================================================

class TestPointGain:
    """Test point gain from replacing cards."""

    def test_replace_high_with_low(self):
        """Replacing a face-up 10 with a 3 should give positive point gain."""
        game = make_game()
        player = game.players[0]
        set_hand(player, [Rank.TEN, Rank.THREE, Rank.FIVE,
                          Rank.EIGHT, Rank.FOUR, Rank.SIX])
        profile = make_profile()
        drawn_card = Card(Suit.DIAMONDS, Rank.THREE)
        drawn_value = get_ai_card_value(drawn_card, game.options)

        gain = GolfAI._point_gain(
            0, drawn_card, drawn_value, player, game.options, profile
        )
        # 10 - 3 = 7
        assert gain == pytest.approx(7.0)

    def test_breaking_pair_is_bad(self):
        """Breaking an existing pair should produce a negative point gain."""
        game = make_game()
        player = game.players[0]
        # Column 0: positions 0 and 3 are both 5s (paired)
        set_hand(player, [Rank.FIVE, Rank.THREE, Rank.EIGHT,
                          Rank.FIVE, Rank.FOUR, Rank.SIX])
        profile = make_profile()
        drawn_card = Card(Suit.DIAMONDS, Rank.FOUR)
        drawn_value = get_ai_card_value(drawn_card, game.options)

        gain = GolfAI._point_gain(
            0, drawn_card, drawn_value, player, game.options, profile
        )
        # Breaking pair: old_column=0, new_column=4+5=9, gain=0-9=-9
        assert gain < 0

    def test_creating_pair(self):
        """Creating a new pair should produce a positive point gain."""
        game = make_game()
        player = game.players[0]
        # Position 0 has 9, partner (pos 3) has 5. Draw a 5 to pair with pos 3.
        set_hand(player, [Rank.NINE, Rank.THREE, Rank.EIGHT,
                          Rank.FIVE, Rank.FOUR, Rank.SIX])
        profile = make_profile()
        drawn_card = Card(Suit.DIAMONDS, Rank.FIVE)
        drawn_value = get_ai_card_value(drawn_card, game.options)

        gain = GolfAI._point_gain(
            0, drawn_card, drawn_value, player, game.options, profile
        )
        # Creating pair: old_column=9+5=14, new_column=0, gain=14
        assert gain > 0

    def test_hidden_card_discount(self):
        """Hidden card replacement should use expected value with discount."""
        game = make_game()
        player = game.players[0]
        set_hand(player, [Rank.TEN, Rank.THREE, Rank.FIVE,
                          Rank.EIGHT, Rank.FOUR, Rank.SIX])
        player.cards[0].face_up = False  # Position 0 is hidden
        profile = make_profile(swap_threshold=4)
        drawn_card = Card(Suit.DIAMONDS, Rank.ACE)
        drawn_value = get_ai_card_value(drawn_card, game.options)

        gain = GolfAI._point_gain(
            0, drawn_card, drawn_value, player, game.options, profile
        )
        # expected_hidden=4.5, drawn_value=1, gain=(4.5-1)*discount
        # discount = 0.5 + (4/16) = 0.75
        assert gain == pytest.approx((4.5 - 1) * 0.75)

    def test_hidden_card_negative_pair_no_bonus(self):
        """No point gain bonus when creating a negative pair on hidden card."""
        game = make_game()
        player = game.players[0]
        set_hand(player, [Rank.TWO, Rank.THREE, Rank.FIVE,
                          Rank.TWO, Rank.FOUR, Rank.SIX])
        player.cards[0].face_up = False  # Position 0 hidden
        # Partner (pos 3) is face-up TWO
        profile = make_profile()
        drawn_card = Card(Suit.DIAMONDS, Rank.TWO)
        drawn_value = get_ai_card_value(drawn_card, game.options)

        gain = GolfAI._point_gain(
            0, drawn_card, drawn_value, player, game.options, profile
        )
        # Creates negative pair → returns 0.0
        assert gain == 0.0


# =============================================================================
# _reveal_and_bonus_score
# =============================================================================

class TestRevealAndBonusScore:
    """Test reveal bonus, comeback bonus, and strategic bonuses."""

    def test_reveal_bonus_scales_by_quality(self):
        """Better cards get bigger reveal bonuses."""
        game = make_game()
        player = game.players[0]
        set_hand(player, [Rank.TEN, Rank.THREE, Rank.FIVE,
                          Rank.EIGHT, Rank.FOUR, Rank.SIX])
        player.cards[0].face_up = False
        player.cards[3].face_up = False
        profile = make_profile(aggression=0.5)

        # Excellent card (value 0)
        king = Card(Suit.DIAMONDS, Rank.KING)
        king_score = GolfAI._reveal_and_bonus_score(
            0, king, 0, player, game.options, game, profile
        )

        # Bad card (value 8)
        eight = Card(Suit.DIAMONDS, Rank.EIGHT)
        eight_score = GolfAI._reveal_and_bonus_score(
            0, eight, 8, player, game.options, game, profile
        )

        assert king_score > eight_score

    def test_comeback_bonus_when_behind(self):
        """Player behind in standings should get a comeback bonus."""
        opts = GameOptions()
        game = make_game(options=opts, rounds=5)
        player = game.players[0]
        player.total_score = 40  # Behind
        game.players[1].total_score = 10  # Leader
        game.current_round = 4  # Late game

        set_hand(player, [Rank.TEN, Rank.THREE, Rank.FIVE,
                          Rank.EIGHT, Rank.FOUR, Rank.SIX])
        player.cards[0].face_up = False
        profile = make_profile(aggression=0.8)

        drawn_card = Card(Suit.DIAMONDS, Rank.THREE)
        drawn_value = get_ai_card_value(drawn_card, game.options)

        score = GolfAI._reveal_and_bonus_score(
            0, drawn_card, drawn_value, player, game.options, game, profile
        )
        # Should include comeback bonus (standings_pressure > 0.3, hidden card, value < 8)
        assert score > 0

    def test_no_comeback_for_high_card(self):
        """No comeback bonus for cards with value >= 8."""
        opts = GameOptions()
        game = make_game(options=opts, rounds=5)
        player = game.players[0]
        player.total_score = 40
        game.players[1].total_score = 10
        game.current_round = 4

        set_hand(player, [Rank.TEN, Rank.THREE, Rank.FIVE,
                          Rank.EIGHT, Rank.FOUR, Rank.SIX])
        player.cards[0].face_up = False
        profile = make_profile(aggression=0.8)

        # Draw a Queen (value 10 >= 8)
        drawn_card = Card(Suit.DIAMONDS, Rank.QUEEN)
        drawn_value = get_ai_card_value(drawn_card, game.options)

        score_with_queen = GolfAI._reveal_and_bonus_score(
            0, drawn_card, drawn_value, player, game.options, game, profile
        )
        # Bad cards get no reveal bonus and no comeback bonus
        # So score should be 0 or very small (only future pair potential)
        assert score_with_queen < 2.0


# =============================================================================
# _check_auto_take
# =============================================================================

class TestCheckAutoTake:
    """Test auto-take rules for discard pile decisions."""

    def test_always_take_joker(self):
        game = make_game()
        player = game.players[0]
        set_hand(player, [Rank.SEVEN, Rank.THREE, Rank.FIVE,
                          Rank.EIGHT, Rank.FOUR, Rank.SIX])
        profile = make_profile()
        joker = Card(Suit.HEARTS, Rank.JOKER)
        value = get_ai_card_value(joker, game.options)

        result = GolfAI._check_auto_take(joker, value, player, game.options, profile)
        assert result is True

    def test_always_take_king(self):
        game = make_game()
        player = game.players[0]
        set_hand(player, [Rank.SEVEN, Rank.THREE, Rank.FIVE,
                          Rank.EIGHT, Rank.FOUR, Rank.SIX])
        profile = make_profile()
        king = Card(Suit.HEARTS, Rank.KING)
        value = get_ai_card_value(king, game.options)

        result = GolfAI._check_auto_take(king, value, player, game.options, profile)
        assert result is True

    def test_one_eyed_jack_auto_take(self):
        opts = GameOptions(one_eyed_jacks=True)
        game = make_game(options=opts)
        player = game.players[0]
        set_hand(player, [Rank.SEVEN, Rank.THREE, Rank.FIVE,
                          Rank.EIGHT, Rank.FOUR, Rank.SIX])
        profile = make_profile()

        # J♥ is one-eyed
        jack_hearts = Card(Suit.HEARTS, Rank.JACK)
        value = get_ai_card_value(jack_hearts, opts)
        result = GolfAI._check_auto_take(jack_hearts, value, player, opts, profile)
        assert result is True

        # J♦ is NOT one-eyed
        jack_diamonds = Card(Suit.DIAMONDS, Rank.JACK)
        value = get_ai_card_value(jack_diamonds, opts)
        result = GolfAI._check_auto_take(jack_diamonds, value, player, opts, profile)
        assert result is None  # No auto-take

    def test_wolfpack_jack_pursuit(self):
        opts = GameOptions(wolfpack=True)
        game = make_game(options=opts)
        player = game.players[0]
        # Player has 2 visible Jacks
        set_hand(player, [Rank.JACK, Rank.JACK, Rank.FIVE,
                          Rank.EIGHT, Rank.FOUR, Rank.SIX])
        profile = make_profile(aggression=0.8)

        jack = Card(Suit.DIAMONDS, Rank.JACK)
        value = get_ai_card_value(jack, opts)
        result = GolfAI._check_auto_take(jack, value, player, opts, profile)
        assert result is True

    def test_wolfpack_jack_not_aggressive_enough(self):
        opts = GameOptions(wolfpack=True)
        game = make_game(options=opts)
        player = game.players[0]
        set_hand(player, [Rank.JACK, Rank.JACK, Rank.FIVE,
                          Rank.EIGHT, Rank.FOUR, Rank.SIX])
        profile = make_profile(aggression=0.3)  # Too passive

        jack = Card(Suit.DIAMONDS, Rank.JACK)
        value = get_ai_card_value(jack, opts)
        result = GolfAI._check_auto_take(jack, value, player, opts, profile)
        assert result is None

    def test_ten_penny_auto_take(self):
        opts = GameOptions(ten_penny=True)
        game = make_game(options=opts)
        player = game.players[0]
        set_hand(player, [Rank.SEVEN, Rank.THREE, Rank.FIVE,
                          Rank.EIGHT, Rank.FOUR, Rank.SIX])
        profile = make_profile()

        ten = Card(Suit.HEARTS, Rank.TEN)
        value = get_ai_card_value(ten, opts)
        result = GolfAI._check_auto_take(ten, value, player, opts, profile)
        assert result is True

    def test_pair_potential_auto_take(self):
        """Take card that can pair with a visible card."""
        game = make_game()
        player = game.players[0]
        # Position 0 has a 7 face-up, partner (pos 3) is face-down
        set_hand(player, [Rank.SEVEN, Rank.THREE, Rank.FIVE,
                          Rank.EIGHT, Rank.FOUR, Rank.SIX])
        player.cards[3].face_up = False
        profile = make_profile()

        seven = Card(Suit.DIAMONDS, Rank.SEVEN)
        value = get_ai_card_value(seven, game.options)
        result = GolfAI._check_auto_take(seven, value, player, game.options, profile)
        assert result is True

    def test_no_auto_take_for_mediocre_card(self):
        """A random 8 should not be auto-taken."""
        game = make_game()
        player = game.players[0]
        set_hand(player, [Rank.SEVEN, Rank.THREE, Rank.FIVE,
                          Rank.FOUR, Rank.FOUR, Rank.SIX])
        profile = make_profile()

        eight = Card(Suit.HEARTS, Rank.EIGHT)
        value = get_ai_card_value(eight, game.options)
        result = GolfAI._check_auto_take(eight, value, player, game.options, profile)
        assert result is None


# =============================================================================
# _has_good_swap_option
# =============================================================================

class TestHasGoodSwapOption:

    def test_good_swap_available(self):
        """With high cards in hand and a low card to swap, should return True."""
        game = make_game()
        player = game.players[0]
        set_hand(player, [Rank.TEN, Rank.QUEEN, Rank.NINE,
                          Rank.EIGHT, Rank.JACK, Rank.SEVEN])
        profile = make_profile()
        drawn_card = Card(Suit.DIAMONDS, Rank.ACE)
        drawn_value = get_ai_card_value(drawn_card, game.options)

        result = GolfAI._has_good_swap_option(
            drawn_card, drawn_value, player, game.options, game, profile
        )
        assert result is True

    def test_no_good_swap(self):
        """With all low cards in hand and a high card, should return False."""
        game = make_game()
        player = game.players[0]
        set_hand(player, [Rank.ACE, Rank.TWO, Rank.KING,
                          Rank.ACE, Rank.TWO, Rank.KING])
        profile = make_profile()
        drawn_card = Card(Suit.DIAMONDS, Rank.QUEEN)
        drawn_value = get_ai_card_value(drawn_card, game.options)

        result = GolfAI._has_good_swap_option(
            drawn_card, drawn_value, player, game.options, game, profile
        )
        assert result is False


# =============================================================================
# calculate_swap_score (integration: go-out safety)
# =============================================================================

class TestCalculateSwapScore:

    def test_go_out_safety_penalty(self):
        """Going out with a bad score should apply a -100 penalty."""
        game = make_game()
        player = game.players[0]
        # All face-up except position 5, hand is all high cards
        set_hand(player, [Rank.TEN, Rank.QUEEN, Rank.NINE,
                          Rank.EIGHT, Rank.JACK, Rank.SEVEN])
        player.cards[5].face_up = False  # Only pos 5 is hidden
        profile = make_profile(aggression=0.0)  # Conservative

        # Draw a Queen (bad card) - swapping into the only hidden pos would go out
        drawn_card = Card(Suit.DIAMONDS, Rank.QUEEN)
        drawn_value = get_ai_card_value(drawn_card, game.options)

        score = GolfAI.calculate_swap_score(
            5, drawn_card, drawn_value, player, game.options, game, profile
        )
        # Should be heavily penalized (projected score would be terrible)
        assert score < -50

    def test_components_sum_correctly(self):
        """Verify calculate_swap_score equals sum of sub-functions plus go-out check."""
        game = make_game()
        player = game.players[0]
        set_hand(player, [Rank.TEN, Rank.THREE, Rank.FIVE,
                          Rank.EIGHT, Rank.FOUR, Rank.SIX])
        profile = make_profile()

        drawn_card = Card(Suit.DIAMONDS, Rank.ACE)
        drawn_value = get_ai_card_value(drawn_card, game.options)

        total = GolfAI.calculate_swap_score(
            0, drawn_card, drawn_value, player, game.options, game, profile
        )
        pair = GolfAI._pair_improvement(
            0, drawn_card, drawn_value, player, game.options, profile
        )
        point = GolfAI._point_gain(
            0, drawn_card, drawn_value, player, game.options, profile
        )
        bonus = GolfAI._reveal_and_bonus_score(
            0, drawn_card, drawn_value, player, game.options, game, profile
        )

        # No go-out safety penalty here (not the last hidden card)
        assert total == pytest.approx(pair + point + bonus)


# =============================================================================
# should_take_discard (integration)
# =============================================================================

class TestShouldTakeDiscard:

    def test_take_joker(self):
        game = make_game()
        player = game.players[0]
        set_hand(player, [Rank.SEVEN, Rank.THREE, Rank.FIVE,
                          Rank.EIGHT, Rank.FOUR, Rank.SIX])
        profile = make_profile()
        joker = Card(Suit.HEARTS, Rank.JOKER)

        result = GolfAI.should_take_discard(joker, player, profile, game)
        assert result is True

    def test_pass_on_none(self):
        game = make_game()
        player = game.players[0]
        profile = make_profile()

        result = GolfAI.should_take_discard(None, player, profile, game)
        assert result is False

    def test_go_out_safeguard_rejects_bad_card(self):
        """With 1 hidden card and bad projected score, should reject mediocre discard."""
        game = make_game()
        player = game.players[0]
        # All face-up except position 5, hand is all high cards
        set_hand(player, [Rank.TEN, Rank.QUEEN, Rank.NINE,
                          Rank.EIGHT, Rank.JACK, Rank.SEVEN])
        player.cards[5].face_up = False
        profile = make_profile(aggression=0.0)

        # A 6 is mediocre - go-out check should reject since projected score is terrible
        six = Card(Suit.HEARTS, Rank.SIX)
        result = GolfAI.should_take_discard(six, player, profile, game)
        assert result is False


# =============================================================================
# should_knock_early
# =============================================================================

class TestShouldKnockEarly:

    def test_requires_knock_early_option(self):
        game = make_game()
        player = game.players[0]
        flip_all_but(player, keep_down=1)
        profile = make_profile(aggression=1.0)

        result = GolfAI.should_knock_early(game, player, profile)
        assert result is False

    def test_no_knock_with_many_hidden(self):
        """Should not knock with more than 2 face-down cards."""
        opts = GameOptions(knock_early=True)
        game = make_game(options=opts)
        player = game.players[0]
        flip_all_but(player, keep_down=3)
        profile = make_profile(aggression=1.0)

        result = GolfAI.should_knock_early(game, player, profile)
        assert result is False

    def test_no_knock_all_face_up(self):
        """Should not knock with 0 face-down cards."""
        opts = GameOptions(knock_early=True)
        game = make_game(options=opts)
        player = game.players[0]
        for card in player.cards:
            card.face_up = True
        profile = make_profile(aggression=1.0)

        result = GolfAI.should_knock_early(game, player, profile)
        assert result is False

    def test_low_aggression_unlikely_to_knock(self):
        """Conservative players should almost never knock early."""
        opts = GameOptions(knock_early=True, initial_flips=0)
        game = make_game(options=opts)
        player = game.players[0]
        # Good hand but passive player
        set_hand(player, [Rank.ACE, Rank.TWO, Rank.KING,
                          Rank.ACE, Rank.TWO, Rank.THREE])
        player.cards[5].face_up = False  # 1 hidden
        profile = make_profile(aggression=0.0)

        # With aggression=0.0, knock_chance = 0.0 → never knocks
        result = GolfAI.should_knock_early(game, player, profile)
        assert result is False

    def test_high_projected_score_never_knocks(self):
        """Projected score >9 with normal opponents should always reject."""
        opts = GameOptions(knock_early=True, initial_flips=0)
        game = make_game(options=opts)
        player = game.players[0]
        # Mediocre hand: visible 8+7+6 = 21, plus 1 hidden (~4.5) → ~25.5
        set_hand(player, [Rank.EIGHT, Rank.SEVEN, Rank.SIX,
                          Rank.FOUR, Rank.FIVE, Rank.NINE])
        player.cards[5].face_up = False  # 1 hidden
        profile = make_profile(aggression=1.0)

        # max_acceptable = 5 + 4 = 9, projected ~25.5 >> 9
        for _ in range(50):
            result = GolfAI.should_knock_early(game, player, profile)
            assert result is False

    def test_low_aggression_mediocre_hand_never_knocks(self):
        """Low aggression with a middling hand should never knock."""
        opts = GameOptions(knock_early=True, initial_flips=0)
        game = make_game(options=opts)
        player = game.players[0]
        # Decent but not great: visible 1+2+5 = 8, plus 1 hidden (~4.5) → ~12.5
        set_hand(player, [Rank.ACE, Rank.TWO, Rank.FIVE,
                          Rank.THREE, Rank.FOUR, Rank.SIX])
        player.cards[5].face_up = False  # 1 hidden
        profile = make_profile(aggression=0.2)

        # max_acceptable = 5 + 0 = 5, projected ~12.5 >> 5
        for _ in range(50):
            result = GolfAI.should_knock_early(game, player, profile)
            assert result is False
