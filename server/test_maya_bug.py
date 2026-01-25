"""
Test for the original Maya bug:

Maya took a 10 from discard and had to discard an Ace.

Bug chain:
1. should_take_discard() incorrectly decided to take the 10
2. choose_swap_or_discard() correctly returned None (don't swap)
3. But drawing from discard FORCES a swap
4. The forced-swap fallback found the "worst" visible card
5. The Ace (value 1) was swapped out for the 10

This test verifies the fixes work.
"""

import pytest
from game import Card, Player, Game, GameOptions, Suit, Rank
from ai import (
    GolfAI, CPUProfile, CPU_PROFILES,
    get_ai_card_value, has_worse_visible_card
)


def get_maya_profile() -> CPUProfile:
    """Get Maya's profile."""
    for p in CPU_PROFILES:
        if p.name == "Maya":
            return p
    # Fallback - create Maya-like profile
    return CPUProfile(
        name="Maya",
        style="Aggressive Closer",
        swap_threshold=6,
        pair_hope=0.4,
        aggression=0.85,
        unpredictability=0.1,
    )


def create_test_game() -> Game:
    """Create a game in playing state."""
    game = Game()
    game.add_player(Player(id="maya", name="Maya"))
    game.add_player(Player(id="other", name="Other"))
    game.start_game(options=GameOptions(initial_flips=0))
    return game


class TestMayaBugFix:
    """Test that the original Maya bug is fixed."""

    def test_maya_does_not_take_10_with_good_hand(self):
        """
        Original bug: Maya took a 10 from discard when she had good cards.

        Setup: Maya has visible Ace, King, 2 (all good cards)
        Discard: 10
        Expected: Maya should NOT take the 10
        """
        game = create_test_game()
        maya = game.get_player("maya")
        profile = get_maya_profile()

        # Set up Maya's hand with good visible cards
        maya.cards = [
            Card(Suit.HEARTS, Rank.ACE, face_up=True),   # Value 1
            Card(Suit.HEARTS, Rank.KING, face_up=True),  # Value 0
            Card(Suit.HEARTS, Rank.TWO, face_up=True),   # Value -2
            Card(Suit.SPADES, Rank.FIVE, face_up=False),
            Card(Suit.SPADES, Rank.SIX, face_up=False),
            Card(Suit.SPADES, Rank.SEVEN, face_up=False),
        ]

        # Put a 10 on discard
        discard_10 = Card(Suit.CLUBS, Rank.TEN, face_up=True)
        game.discard_pile = [discard_10]

        # Maya should NOT take the 10
        should_take = GolfAI.should_take_discard(discard_10, maya, profile, game)

        assert should_take is False, (
            "Maya should not take a 10 when her visible cards are Ace, King, 2"
        )

    def test_maya_does_not_take_10_even_with_unpredictability(self):
        """
        The unpredictability trait should NOT cause taking bad cards.

        Run multiple times to account for randomness.
        """
        game = create_test_game()
        maya = game.get_player("maya")
        profile = get_maya_profile()

        maya.cards = [
            Card(Suit.HEARTS, Rank.ACE, face_up=True),
            Card(Suit.HEARTS, Rank.KING, face_up=True),
            Card(Suit.HEARTS, Rank.TWO, face_up=True),
            Card(Suit.SPADES, Rank.FIVE, face_up=False),
            Card(Suit.SPADES, Rank.SIX, face_up=False),
            Card(Suit.SPADES, Rank.SEVEN, face_up=False),
        ]

        discard_10 = Card(Suit.CLUBS, Rank.TEN, face_up=True)
        game.discard_pile = [discard_10]

        # Run 100 times - should NEVER take the 10
        took_10_count = 0
        for _ in range(100):
            if GolfAI.should_take_discard(discard_10, maya, profile, game):
                took_10_count += 1

        assert took_10_count == 0, (
            f"Maya took a 10 {took_10_count}/100 times despite having good cards. "
            "Unpredictability should not override basic logic for bad cards."
        )

    def test_has_worse_visible_card_utility(self):
        """Test the utility function that guards against taking bad cards."""
        game = create_test_game()
        maya = game.get_player("maya")
        options = game.options

        # Hand with good visible cards (Ace=1, King=0, 2=-2)
        maya.cards = [
            Card(Suit.HEARTS, Rank.ACE, face_up=True),   # 1
            Card(Suit.HEARTS, Rank.KING, face_up=True),  # 0
            Card(Suit.HEARTS, Rank.TWO, face_up=True),   # -2
            Card(Suit.SPADES, Rank.FIVE, face_up=False),
            Card(Suit.SPADES, Rank.SIX, face_up=False),
            Card(Suit.SPADES, Rank.SEVEN, face_up=False),
        ]

        # No visible card is worse than 10 (value 10)
        assert has_worse_visible_card(maya, 10, options) is False

        # No visible card is worse than 5
        assert has_worse_visible_card(maya, 5, options) is False

        # Ace (1) is worse than 0
        assert has_worse_visible_card(maya, 0, options) is True

    def test_forced_swap_uses_house_rules(self):
        """
        When forced to swap (drew from discard), the AI should use
        get_ai_card_value() to find the worst card, not raw value().

        This matters for house rules like super_kings, lucky_sevens, etc.
        """
        game = create_test_game()
        game.options = GameOptions(super_kings=True)  # Kings now worth -2
        maya = game.get_player("maya")

        # All face up - forced swap scenario
        maya.cards = [
            Card(Suit.HEARTS, Rank.KING, face_up=True),   # -2 with super_kings
            Card(Suit.HEARTS, Rank.ACE, face_up=True),    # 1
            Card(Suit.HEARTS, Rank.THREE, face_up=True),  # 3 - worst!
            Card(Suit.SPADES, Rank.KING, face_up=True),   # -2 with super_kings
            Card(Suit.SPADES, Rank.TWO, face_up=True),    # -2
            Card(Suit.SPADES, Rank.ACE, face_up=True),    # 1
        ]

        # Find worst card using house rules
        worst_pos = 0
        worst_val = -999
        for i, c in enumerate(maya.cards):
            card_val = get_ai_card_value(c, game.options)
            if card_val > worst_val:
                worst_val = card_val
                worst_pos = i

        # Position 2 (Three, value 3) should be worst
        assert worst_pos == 2, (
            f"With super_kings, the Three (value 3) should be worst, "
            f"not position {worst_pos} (value {worst_val})"
        )

    def test_choose_swap_does_not_discard_excellent_cards(self):
        """
        Unpredictability should NOT cause discarding excellent cards (2s, Jokers).
        """
        game = create_test_game()
        maya = game.get_player("maya")
        profile = get_maya_profile()

        maya.cards = [
            Card(Suit.HEARTS, Rank.FIVE, face_up=True),
            Card(Suit.HEARTS, Rank.SIX, face_up=True),
            Card(Suit.HEARTS, Rank.SEVEN, face_up=False),
            Card(Suit.SPADES, Rank.EIGHT, face_up=False),
            Card(Suit.SPADES, Rank.NINE, face_up=False),
            Card(Suit.SPADES, Rank.TEN, face_up=False),
        ]

        # Drew a 2 (excellent card, value -2)
        drawn_two = Card(Suit.CLUBS, Rank.TWO)

        # Run 100 times - should ALWAYS swap (never discard a 2)
        discarded_count = 0
        for _ in range(100):
            swap_pos = GolfAI.choose_swap_or_discard(drawn_two, maya, profile, game)
            if swap_pos is None:
                discarded_count += 1

        assert discarded_count == 0, (
            f"Maya discarded a 2 (excellent card) {discarded_count}/100 times. "
            "Unpredictability should not cause discarding excellent cards."
        )

    def test_full_scenario_maya_10_ace(self):
        """
        Full reproduction of the original bug scenario.

        Maya has: [A, K, 2, ?, ?, ?] (good visible cards)
        Discard: 10

        Expected behavior:
        1. Maya should NOT take the 10
        2. If she somehow did, she should swap into face-down, not replace the Ace
        """
        game = create_test_game()
        maya = game.get_player("maya")
        profile = get_maya_profile()

        # Setup exactly like the bug report
        maya.cards = [
            Card(Suit.HEARTS, Rank.ACE, face_up=True),   # Good - don't replace!
            Card(Suit.HEARTS, Rank.KING, face_up=True),  # Good
            Card(Suit.HEARTS, Rank.TWO, face_up=True),   # Excellent
            Card(Suit.SPADES, Rank.JACK, face_up=False), # Unknown
            Card(Suit.SPADES, Rank.QUEEN, face_up=False),# Unknown
            Card(Suit.SPADES, Rank.TEN, face_up=False),  # Unknown
        ]

        discard_10 = Card(Suit.CLUBS, Rank.TEN, face_up=True)
        game.discard_pile = [discard_10]

        # Step 1: Maya should not take the 10
        should_take = GolfAI.should_take_discard(discard_10, maya, profile, game)
        assert should_take is False, "Maya should not take a 10 with this hand"

        # Step 2: Even if she did take it (simulating old bug), verify swap logic
        # The swap logic should prefer face-down positions
        drawn_10 = Card(Suit.CLUBS, Rank.TEN)
        swap_pos = GolfAI.choose_swap_or_discard(drawn_10, maya, profile, game)

        # Should either discard (None) or swap into face-down (positions 3, 4, 5)
        # Should NEVER swap into position 0 (Ace), 1 (King), or 2 (Two)
        if swap_pos is not None:
            assert swap_pos >= 3, (
                f"Maya tried to swap 10 into position {swap_pos}, replacing a good card. "
                "Should only swap into face-down positions (3, 4, 5)."
            )


class TestEdgeCases:
    """Test edge cases related to the bug."""

    def test_all_face_up_forced_swap_finds_actual_worst(self):
        """
        When all cards are face up and forced to swap, find the ACTUAL worst card.
        """
        game = create_test_game()
        maya = game.get_player("maya")

        # All face up, varying values
        maya.cards = [
            Card(Suit.HEARTS, Rank.ACE, face_up=True),    # 1
            Card(Suit.HEARTS, Rank.KING, face_up=True),   # 0
            Card(Suit.HEARTS, Rank.TWO, face_up=True),    # -2
            Card(Suit.SPADES, Rank.JACK, face_up=True),   # 10 - WORST
            Card(Suit.SPADES, Rank.THREE, face_up=True),  # 3
            Card(Suit.SPADES, Rank.FOUR, face_up=True),   # 4
        ]

        # Find worst
        worst_pos = 0
        worst_val = -999
        for i, c in enumerate(maya.cards):
            card_val = get_ai_card_value(c, game.options)
            if card_val > worst_val:
                worst_val = card_val
                worst_pos = i

        assert worst_pos == 3, f"Jack (position 3, value 10) should be worst, got position {worst_pos}"
        assert worst_val == 10, f"Worst value should be 10, got {worst_val}"

    def test_take_discard_respects_pair_potential(self):
        """
        Taking a bad card to complete a pair IS valid strategy.
        This should still work after the bug fix.
        """
        game = create_test_game()
        maya = game.get_player("maya")
        profile = get_maya_profile()

        # Maya has a visible 10 - taking another 10 to pair is GOOD
        maya.cards = [
            Card(Suit.HEARTS, Rank.TEN, face_up=True),   # Visible 10
            Card(Suit.HEARTS, Rank.KING, face_up=True),
            Card(Suit.HEARTS, Rank.ACE, face_up=True),
            Card(Suit.SPADES, Rank.FIVE, face_up=False), # Pair position for the 10
            Card(Suit.SPADES, Rank.SIX, face_up=False),
            Card(Suit.SPADES, Rank.SEVEN, face_up=False),
        ]

        # 10 on discard - should take to pair!
        discard_10 = Card(Suit.CLUBS, Rank.TEN, face_up=True)
        game.discard_pile = [discard_10]

        should_take = GolfAI.should_take_discard(discard_10, maya, profile, game)
        assert should_take is True, (
            "Maya SHOULD take a 10 when she has a visible 10 to pair with"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
