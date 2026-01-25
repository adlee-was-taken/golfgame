"""
Tests for the GameAnalyzer decision evaluation logic.

Verifies that the analyzer correctly identifies:
- Optimal plays
- Mistakes
- Blunders

Run with: pytest test_analyzer.py -v
"""

import pytest
from game_analyzer import (
    DecisionEvaluator, DecisionQuality,
    get_card_value, rank_quality
)


# =============================================================================
# Card Value Tests
# =============================================================================

class TestCardValues:
    """Verify card value lookups."""

    def test_standard_values(self):
        assert get_card_value('A') == 1
        assert get_card_value('2') == -2
        assert get_card_value('5') == 5
        assert get_card_value('10') == 10
        assert get_card_value('J') == 10
        assert get_card_value('Q') == 10
        assert get_card_value('K') == 0
        assert get_card_value('★') == -2

    def test_house_rules(self):
        opts = {'lucky_swing': True}
        assert get_card_value('★', opts) == -5

        opts = {'super_kings': True}
        assert get_card_value('K', opts) == -2

        opts = {'ten_penny': True}
        assert get_card_value('10', opts) == 1


class TestRankQuality:
    """Verify card quality classification."""

    def test_excellent_cards(self):
        assert rank_quality('★') == "excellent"
        assert rank_quality('2') == "excellent"

    def test_good_cards(self):
        assert rank_quality('K') == "good"

    def test_decent_cards(self):
        assert rank_quality('A') == "decent"

    def test_neutral_cards(self):
        assert rank_quality('3') == "neutral"
        assert rank_quality('4') == "neutral"
        assert rank_quality('5') == "neutral"

    def test_bad_cards(self):
        assert rank_quality('6') == "bad"
        assert rank_quality('7') == "bad"

    def test_terrible_cards(self):
        assert rank_quality('8') == "terrible"
        assert rank_quality('9') == "terrible"
        assert rank_quality('10') == "terrible"
        assert rank_quality('J') == "terrible"
        assert rank_quality('Q') == "terrible"


# =============================================================================
# Take Discard Evaluation Tests
# =============================================================================

class TestTakeDiscardEvaluation:
    """Test evaluation of take discard vs draw deck decisions."""

    def setup_method(self):
        self.evaluator = DecisionEvaluator()
        # Hand with mix of cards
        self.hand = [
            {'rank': '7', 'face_up': True},
            {'rank': '5', 'face_up': True},
            {'rank': '?', 'face_up': False},
            {'rank': '9', 'face_up': True},
            {'rank': '?', 'face_up': False},
            {'rank': '?', 'face_up': False},
        ]

    def test_taking_joker_is_optimal(self):
        """Taking a Joker should always be optimal."""
        result = self.evaluator.evaluate_take_discard('★', self.hand, took_discard=True)
        assert result.quality == DecisionQuality.OPTIMAL

    def test_not_taking_joker_is_blunder(self):
        """Not taking a Joker is a blunder."""
        result = self.evaluator.evaluate_take_discard('★', self.hand, took_discard=False)
        assert result.quality == DecisionQuality.BLUNDER

    def test_taking_king_is_optimal(self):
        """Taking a King should be optimal."""
        result = self.evaluator.evaluate_take_discard('K', self.hand, took_discard=True)
        assert result.quality == DecisionQuality.OPTIMAL

    def test_not_taking_king_is_mistake(self):
        """Not taking a King is a mistake."""
        result = self.evaluator.evaluate_take_discard('K', self.hand, took_discard=False)
        assert result.quality == DecisionQuality.MISTAKE

    def test_taking_queen_is_blunder(self):
        """Taking a Queen (10 points) with decent hand is a blunder."""
        result = self.evaluator.evaluate_take_discard('Q', self.hand, took_discard=True)
        assert result.quality == DecisionQuality.BLUNDER

    def test_not_taking_queen_is_optimal(self):
        """Not taking a Queen is optimal."""
        result = self.evaluator.evaluate_take_discard('Q', self.hand, took_discard=False)
        assert result.quality == DecisionQuality.OPTIMAL

    def test_taking_card_better_than_worst(self):
        """Taking a card better than worst visible is optimal."""
        # Worst visible is 9
        result = self.evaluator.evaluate_take_discard('3', self.hand, took_discard=True)
        assert result.quality == DecisionQuality.OPTIMAL

    def test_neutral_card_better_than_worst(self):
        """A card better than worst visible should be taken."""
        # 4 is better than worst visible (9), so taking is correct
        result = self.evaluator.evaluate_take_discard('4', self.hand, took_discard=True)
        assert result.quality == DecisionQuality.OPTIMAL

        # Not taking a 4 when worst is 9 is suboptimal (but not terrible)
        result = self.evaluator.evaluate_take_discard('4', self.hand, took_discard=False)
        assert result.quality == DecisionQuality.QUESTIONABLE


# =============================================================================
# Swap Evaluation Tests
# =============================================================================

class TestSwapEvaluation:
    """Test evaluation of swap vs discard decisions."""

    def setup_method(self):
        self.evaluator = DecisionEvaluator()
        self.hand = [
            {'rank': '7', 'face_up': True},
            {'rank': '5', 'face_up': True},
            {'rank': '?', 'face_up': False},
            {'rank': '9', 'face_up': True},
            {'rank': '?', 'face_up': False},
            {'rank': '?', 'face_up': False},
        ]

    def test_discarding_joker_is_blunder(self):
        """Discarding a Joker is a severe blunder."""
        result = self.evaluator.evaluate_swap(
            drawn_rank='★',
            hand=self.hand,
            swapped=False,
            swap_position=None,
            was_from_discard=False
        )
        assert result.quality == DecisionQuality.BLUNDER

    def test_discarding_2_is_blunder(self):
        """Discarding a 2 is a severe blunder."""
        result = self.evaluator.evaluate_swap(
            drawn_rank='2',
            hand=self.hand,
            swapped=False,
            swap_position=None,
            was_from_discard=False
        )
        assert result.quality == DecisionQuality.BLUNDER

    def test_discarding_king_is_mistake(self):
        """Discarding a King is a mistake."""
        result = self.evaluator.evaluate_swap(
            drawn_rank='K',
            hand=self.hand,
            swapped=False,
            swap_position=None,
            was_from_discard=False
        )
        assert result.quality == DecisionQuality.MISTAKE

    def test_discarding_queen_is_optimal(self):
        """Discarding a Queen is optimal."""
        result = self.evaluator.evaluate_swap(
            drawn_rank='Q',
            hand=self.hand,
            swapped=False,
            swap_position=None,
            was_from_discard=False
        )
        assert result.quality == DecisionQuality.OPTIMAL

    def test_swap_good_for_bad_is_optimal(self):
        """Swapping a good card for a bad card is optimal."""
        # Swap King (0) for 9 (9 points)
        result = self.evaluator.evaluate_swap(
            drawn_rank='K',
            hand=self.hand,
            swapped=True,
            swap_position=3,  # Position of the 9
            was_from_discard=False
        )
        assert result.quality == DecisionQuality.OPTIMAL
        assert result.expected_value > 0

    def test_swap_bad_for_good_is_mistake(self):
        """Swapping a bad card for a good card is a mistake."""
        # Swap 9 for 5
        hand_with_known = [
            {'rank': '7', 'face_up': True},
            {'rank': '5', 'face_up': True},
            {'rank': 'K', 'face_up': True},  # Good card
            {'rank': '9', 'face_up': True},
            {'rank': '?', 'face_up': False},
            {'rank': '?', 'face_up': False},
        ]
        result = self.evaluator.evaluate_swap(
            drawn_rank='9',
            hand=hand_with_known,
            swapped=True,
            swap_position=2,  # Position of King
            was_from_discard=False
        )
        assert result.quality == DecisionQuality.MISTAKE
        assert result.expected_value < 0

    def test_swap_into_facedown_with_good_card(self):
        """Swapping a good card into face-down position is optimal."""
        result = self.evaluator.evaluate_swap(
            drawn_rank='K',
            hand=self.hand,
            swapped=True,
            swap_position=2,  # Face-down position
            was_from_discard=False
        )
        assert result.quality == DecisionQuality.OPTIMAL

    def test_must_swap_from_discard(self):
        """Failing to swap when drawing from discard is invalid."""
        result = self.evaluator.evaluate_swap(
            drawn_rank='5',
            hand=self.hand,
            swapped=False,
            swap_position=None,
            was_from_discard=True
        )
        assert result.quality == DecisionQuality.BLUNDER


# =============================================================================
# House Rules Evaluation Tests
# =============================================================================

class TestHouseRulesEvaluation:
    """Test that house rules affect evaluation correctly."""

    def test_lucky_swing_joker_more_valuable(self):
        """With lucky_swing, Joker is worth -5, so discarding is worse."""
        evaluator = DecisionEvaluator({'lucky_swing': True})
        hand = [{'rank': '5', 'face_up': True}] * 6

        result = evaluator.evaluate_swap(
            drawn_rank='★',
            hand=hand,
            swapped=False,
            swap_position=None,
            was_from_discard=False
        )
        assert result.quality == DecisionQuality.BLUNDER
        # EV loss should be higher with lucky_swing
        assert result.expected_value > 5

    def test_super_kings_more_valuable(self):
        """With super_kings, King is -2, so not taking is worse."""
        evaluator = DecisionEvaluator({'super_kings': True})
        hand = [{'rank': '5', 'face_up': True}] * 6

        result = evaluator.evaluate_take_discard('K', hand, took_discard=False)
        # King is now "excellent" tier
        assert result.quality in (DecisionQuality.MISTAKE, DecisionQuality.BLUNDER)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
