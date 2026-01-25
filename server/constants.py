# Card values - Single source of truth for all card scoring
# Per RULES.md: A=1, 2=-2, 3-10=face, J/Q=10, K=0, Joker=-2
DEFAULT_CARD_VALUES = {
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
    '★': -2,  # Joker (standard)
}

# House rule modifications (per RULES.md House Rules section)
SUPER_KINGS_VALUE = -2        # K worth -2 instead of 0
LUCKY_SEVENS_VALUE = 0        # 7 worth 0 instead of 7
TEN_PENNY_VALUE = 1           # 10 worth 1 instead of 10
LUCKY_SWING_JOKER_VALUE = -5  # Joker worth -5 in Lucky Swing mode


def get_card_value_for_rank(rank_str: str, options: dict | None = None) -> int:
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
        elif rank_str == '7' and options.get('lucky_sevens'):
            value = LUCKY_SEVENS_VALUE
        elif rank_str == '10' and options.get('ten_penny'):
            value = TEN_PENNY_VALUE

    return value
