"""
Card value constants for 6-Card Golf.

This module is the single source of truth for all card point values.
House rule modifications are defined here and applied in game.py.

Standard Golf Scoring:
    - Ace: 1 point
    - Two: -2 points (special - only negative non-joker)
    - 3-9: Face value
    - 10, Jack, Queen: 10 points
    - King: 0 points
    - Joker: -2 points (when enabled)
"""

from typing import Optional

# Base card values (no house rules applied)
DEFAULT_CARD_VALUES: dict[str, int] = {
    'A': 1,
    '2': -2,
    '3': 3,
    '4': 4,
    '5': 5,
    '6': 6,
    '7': 7,
    '8': 8,
    '9': 9,
    '10': 10,
    'J': 10,
    'Q': 10,
    'K': 0,
    '★': -2,  # Joker (standard mode)
}

# --- House Rule Value Overrides ---
SUPER_KINGS_VALUE: int = -2        # Kings worth -2 instead of 0
TEN_PENNY_VALUE: int = 1           # 10s worth 1 instead of 10
LUCKY_SWING_JOKER_VALUE: int = -5  # Single joker worth -5


def get_card_value_for_rank(
    rank_str: str,
    options: Optional[dict] = None,
) -> int:
    """
    Get point value for a card rank string, with house rules applied.

    This is the single source of truth for card value calculations.
    Use this for string-based rank lookups (e.g., from JSON/logs).

    Args:
        rank_str: Card rank as string ('A', '2', ..., 'K', '★')
        options: Optional dict with house rule flags (lucky_swing, super_kings, etc.)

    Returns:
        Point value for the card
    """
    value = DEFAULT_CARD_VALUES.get(rank_str, 0)

    if options:
        if rank_str == '★' and options.get('lucky_swing'):
            value = LUCKY_SWING_JOKER_VALUE
        elif rank_str == 'K' and options.get('super_kings'):
            value = SUPER_KINGS_VALUE
        elif rank_str == '10' and options.get('ten_penny'):
            value = TEN_PENNY_VALUE

    return value
