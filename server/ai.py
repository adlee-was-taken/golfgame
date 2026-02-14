"""AI personalities for CPU players in Golf."""

import logging
import os
import random
from dataclasses import dataclass
from typing import Optional
from enum import Enum

from game import Card, Player, Game, GamePhase, GameOptions, RANK_VALUES, Rank, Suit, get_card_value


# Debug logging configuration
# Set AI_DEBUG=1 environment variable to enable detailed AI decision logging
AI_DEBUG = os.environ.get("AI_DEBUG", "0") == "1"

# Create a dedicated logger for AI decisions
ai_logger = logging.getLogger("golf.ai")
if AI_DEBUG:
    ai_logger.setLevel(logging.DEBUG)
    # Add console handler if not already present
    if not ai_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [AI] %(message)s", datefmt="%H:%M:%S"
        ))
        ai_logger.addHandler(handler)


def ai_log(message: str):
    """Log AI decision info when AI_DEBUG is enabled."""
    if AI_DEBUG:
        ai_logger.debug(message)


# =============================================================================
# CPU Turn Timing Configuration (seconds)
# =============================================================================
# Centralized timing constants for all CPU turn delays.
# Adjust these values to tune the "feel" of CPU gameplay.

CPU_TIMING = {
    # Delay before CPU "looks at" the discard pile
    "initial_look": (0.3, 0.5),
    # Brief pause after draw broadcast - let draw animation complete
    # Must be >= client draw animation duration (~1s for deck, ~0.4s for discard)
    "post_draw_settle": 1.1,
    # Consideration time after drawing (before swap/discard decision)
    "post_draw_consider": (0.2, 0.4),
    # Variance multiplier range for chaotic personality players
    "thinking_multiplier_chaotic": (0.6, 1.4),
    # Pause after swap/discard to let animation complete and show result
    # Should match unified swap animation duration (~0.5s)
    "post_action_pause": (0.5, 0.7),
}

# Thinking time ranges by card difficulty (seconds)
THINKING_TIME = {
    # Obviously good cards (Jokers, Kings, 2s, Aces) - easy take
    "easy_good": (0.15, 0.3),
    # Obviously bad cards (10s, Jacks, Queens) - easy pass
    "easy_bad": (0.15, 0.3),
    # Medium difficulty (3, 4, 8, 9)
    "medium": (0.15, 0.3),
    # Hardest decisions (5, 6, 7 - middle of range)
    "hard": (0.15, 0.3),
    # No discard available - quick decision
    "no_card": (0.15, 0.3),
}


# =============================================================================
# AI Decision Constants
# =============================================================================

# Expected value of an unknown (face-down) card, based on deck distribution
EXPECTED_HIDDEN_VALUE = 4.5

# Pessimistic estimate for hidden cards (used in go-out safety checks)
PESSIMISTIC_HIDDEN_VALUE = 6.0

# Conservative estimate (used in opponent score estimation)
CONSERVATIVE_HIDDEN_VALUE = 2.5

# Cards at or above this value should never be swapped into unknown positions
HIGH_CARD_THRESHOLD = 8

# Maximum card value for unpredictability swaps
UNPREDICTABLE_MAX_VALUE = 7

# Pair potential discount when adjacent card matches (25% chance of pair)
PAIR_POTENTIAL_DISCOUNT = 0.25

# Blackjack target score
BLACKJACK_TARGET = 21

# Base acceptable score range for go-out decisions
GO_OUT_SCORE_BASE = 12
GO_OUT_SCORE_MAX = 20

# Personality tie-breaker threshold (options within this many points are "close")
TIE_BREAKER_THRESHOLD = 2.0

# Alias for backwards compatibility - use the centralized function from game.py
def get_ai_card_value(card: Card, options: GameOptions) -> int:
    """Get card value with house rules applied for AI decisions.

    This is an alias for game.get_card_value() for backwards compatibility.
    """
    return get_card_value(card, options)


def can_make_pair(card1: Card, card2: Card) -> bool:
    """Check if two cards can form a pair."""
    return card1.rank == card2.rank


def get_discard_thinking_time(card: Optional[Card], options: GameOptions) -> float:
    """Calculate CPU 'thinking time' based on how obvious the discard decision is.

    Easy decisions (obviously good or bad cards) = quick
    Hard decisions (medium value cards) = slower

    Returns time in seconds. Uses THINKING_TIME constants.
    """
    if not card:
        # No discard available - quick decision to draw from deck
        t = THINKING_TIME["no_card"]
        return random.uniform(t[0], t[1])

    value = get_card_value(card, options)

    # Obviously good cards (easy take): 2 (-2), Joker (-2/-5), K (0), A (1)
    if value <= 1:
        t = THINKING_TIME["easy_good"]
        return random.uniform(t[0], t[1])

    # Obviously bad cards (easy pass): 10, J, Q (value 10)
    if value >= 10:
        t = THINKING_TIME["easy_bad"]
        return random.uniform(t[0], t[1])

    # Medium cards require more thought: 3-9
    # 5, 6, 7 are the hardest decisions (middle of the range)
    if value in (5, 6, 7):
        t = THINKING_TIME["hard"]
        return random.uniform(t[0], t[1])

    # 3, 4, 8, 9 - moderate difficulty
    t = THINKING_TIME["medium"]
    return random.uniform(t[0], t[1])


def estimate_opponent_min_score(player: Player, game: Game, optimistic: bool = False) -> int:
    """Estimate minimum opponent score from visible cards.

    Args:
        player: The player making the estimation (excluded from opponents)
        game: The game state
        optimistic: If True, assume opponents' hidden cards are average (4.5).
                   If False, assume opponents could get lucky (lower estimate).
    """
    min_est = 999
    for p in game.players:
        if p.id == player.id:
            continue
        visible = sum(get_ai_card_value(c, game.options) for c in p.cards if c.face_up)
        hidden = sum(1 for c in p.cards if not c.face_up)

        if optimistic:
            # Assume average hidden cards
            estimate = visible + int(hidden * EXPECTED_HIDDEN_VALUE)
        else:
            # Assume opponents could get lucky - hidden cards might be low
            # or could complete pairs, so use lower estimate
            # Check for potential pairs in opponent's hand
            pair_potential = 0
            for col in range(3):
                top, bot = p.cards[col], p.cards[col + 3]
                # If one card is visible and the other is hidden, there's pair potential
                if top.face_up and not bot.face_up:
                    pair_potential += get_ai_card_value(top, game.options)
                elif bot.face_up and not top.face_up:
                    pair_potential += get_ai_card_value(bot, game.options)

            # Conservative estimate: assume low avg for hidden (could be low cards)
            # and subtract some pair potential (hidden cards might match visible)
            base_estimate = visible + int(hidden * CONSERVATIVE_HIDDEN_VALUE)
            estimate = base_estimate - int(pair_potential * PAIR_POTENTIAL_DISCOUNT)

        min_est = min(min_est, estimate)
    return min_est


def get_end_game_pressure(player: Player, game: Game) -> float:
    """
    Calculate pressure level based on how close opponents are to going out.
    Returns 0.0-1.0 where higher means more pressure to improve hand NOW.

    Pressure increases when:
    - Opponents have few hidden cards (close to going out)
    - We have many hidden cards (stuck with unknown values)
    """
    my_hidden = sum(1 for c in player.cards if not c.face_up)

    # Find the opponent closest to going out
    min_opponent_hidden = 6
    for p in game.players:
        if p.id == player.id:
            continue
        opponent_hidden = sum(1 for c in p.cards if not c.face_up)
        min_opponent_hidden = min(min_opponent_hidden, opponent_hidden)

    # No pressure if opponents have lots of hidden cards
    if min_opponent_hidden >= 4:
        return 0.0

    # Pressure scales based on how close opponent is to finishing
    # 3 hidden = mild pressure (0.4), 2 hidden = medium (0.7), 1 hidden = high (0.9), 0 = max (1.0)
    base_pressure = {0: 1.0, 1: 0.9, 2: 0.7, 3: 0.4}.get(min_opponent_hidden, 0.0)

    # Increase pressure further if WE have many hidden cards (more unknowns to worry about)
    hidden_risk_bonus = (my_hidden - 2) * 0.05  # +0.05 per hidden card above 2
    hidden_risk_bonus = max(0, hidden_risk_bonus)

    return min(1.0, base_pressure + hidden_risk_bonus)


def get_standings_pressure(player: Player, game: Game) -> float:
    """
    Calculate pressure based on player's position in standings.
    Returns 0.0-1.0 where higher = more behind, needs aggressive play.

    Factors:
    - How far behind the leader in total_score
    - How late in the game (current_round / num_rounds)
    """
    if len(game.players) < 2 or game.num_rounds <= 1:
        return 0.0

    # Calculate standings gap
    scores = [p.total_score for p in game.players]
    leader_score = min(scores)  # Lower is better in golf
    my_score = player.total_score
    gap = my_score - leader_score  # Positive = behind

    # Normalize gap (assume ~10 pts/round average, 20+ behind is dire)
    gap_pressure = min(gap / 20.0, 1.0) if gap > 0 else 0.0

    # Late-game multiplier (ramps up in final third of game)
    round_progress = game.current_round / game.num_rounds
    late_game_factor = max(0, (round_progress - 0.66) * 3)  # 0 until 66%, then ramps to 1

    return min(gap_pressure * (1 + late_game_factor), 1.0)


def count_rank_in_hand(player: Player, rank: Rank) -> int:
    """Count how many cards of a given rank the player has visible."""
    return sum(1 for c in player.cards if c.face_up and c.rank == rank)


def count_visible_cards_by_rank(game: Game) -> dict[Rank, int]:
    """
    Count all visible cards of each rank across the entire table.
    Includes: all face-up player cards + top of discard pile.

    Note: Buried discard cards are NOT counted because they reshuffle
    back into the deck when it empties.
    """
    counts: dict[Rank, int] = {rank: 0 for rank in Rank}

    # Count all face-up cards in all players' hands
    for player in game.players:
        for card in player.cards:
            if card.face_up:
                counts[card.rank] += 1

    # Count top of discard pile (the only visible discard)
    discard_top = game.discard_top()
    if discard_top:
        counts[discard_top.rank] += 1

    return counts


def get_pair_viability(rank: Rank, game: Game, exclude_discard_top: bool = False) -> float:
    """
    Calculate how viable it is to pair a card of this rank.
    Returns 0.0-1.0 where higher means better odds of finding a pair.

    In a standard deck: 4 of each rank (2 Jokers).
    If you can see N cards of that rank, only (4-N) remain.

    Args:
        rank: The rank we want to pair
        exclude_discard_top: If True, don't count discard top (useful when
                            evaluating taking that card - it won't be visible after)
    """
    counts = count_visible_cards_by_rank(game)
    visible = counts.get(rank, 0)

    # Adjust if we're evaluating the discard top card itself
    if exclude_discard_top:
        discard_top = game.discard_top()
        if discard_top and discard_top.rank == rank:
            visible = max(0, visible - 1)

    # Cards in deck for this rank
    max_copies = 2 if rank == Rank.JOKER else 4
    remaining = max(0, max_copies - visible)

    # Viability scales with remaining copies
    # 4 remaining = 1.0, 3 = 0.75, 2 = 0.5, 1 = 0.25, 0 = 0.0
    return remaining / max_copies


def get_game_phase(game: Game) -> str:
    """
    Determine current game phase based on average hidden cards.
    Returns: 'early', 'mid', or 'late'
    """
    total_hidden = sum(
        sum(1 for c in p.cards if not c.face_up)
        for p in game.players
    )
    avg_hidden = total_hidden / len(game.players) if game.players else 6

    if avg_hidden >= EXPECTED_HIDDEN_VALUE:
        return 'early'
    elif avg_hidden >= 2.5:
        return 'mid'
    else:
        return 'late'


def get_next_player(game: Game, current_player: Player) -> Optional[Player]:
    """Get the player who plays after current_player in turn order."""
    if len(game.players) <= 1:
        return None
    current_idx = next(
        (i for i, p in enumerate(game.players) if p.id == current_player.id),
        None
    )
    if current_idx is None:
        return None
    next_idx = (current_idx + 1) % len(game.players)
    return game.players[next_idx]


def would_help_opponent_pair(card: Card, opponent: Player) -> tuple[bool, Optional[int]]:
    """
    Check if discarding this card would give opponent a pair opportunity.

    Returns:
        (would_help, opponent_position) - True if opponent has an unpaired visible
        card of the same rank, along with the position of that card.
    """
    for i, opp_card in enumerate(opponent.cards):
        if opp_card.face_up and opp_card.rank == card.rank:
            # Check if this card is already paired
            partner_pos = get_column_partner_position(i)
            partner = opponent.cards[partner_pos]
            if partner.face_up and partner.rank == card.rank:
                continue  # Already paired, no benefit to them
            # They have an unpaired visible card of this rank!
            return True, i
    return False, None


def calculate_denial_value(
    card: Card,
    opponent: Player,
    game: Game,
    options: GameOptions
) -> float:
    """
    Calculate how valuable it would be to deny this card to the next opponent.

    Returns a score from 0 (no denial value) to ~15 (high denial value).
    Higher values mean we should consider NOT discarding this card.
    """
    would_help, opp_pos = would_help_opponent_pair(card, opponent)
    if not would_help or opp_pos is None:
        return 0.0

    card_value = get_ai_card_value(card, options)

    # Base denial value = how many points we'd save them by denying the pair
    # If they pair a 9, they save 18 points (9 + 9 -> 0)
    if card_value >= 0:
        denial_value = card_value * 2  # Pairing saves them 2x the card value
    else:
        # Negative cards (2s, Jokers) - pairing actually WASTES their value
        # Less denial value since we WANT them to waste their negative cards
        denial_value = 2.0  # Small denial value - pairing is still annoying

    # Adjust for game phase - denial matters more in late game
    phase = get_game_phase(game)
    if phase == 'late':
        denial_value *= 1.5
    elif phase == 'early':
        denial_value *= 0.7

    # Adjust for how close opponent is to going out
    opponent_hidden = sum(1 for c in opponent.cards if not c.face_up)
    if opponent_hidden <= 1:
        denial_value *= 1.8  # Critical to deny when they're about to go out
    elif opponent_hidden <= 2:
        denial_value *= 1.3

    return denial_value


def has_worse_visible_card(player: Player, card_value: int, options: GameOptions) -> bool:
    """Check if player has a visible card worse than the given value.

    Used to determine if taking a card from discard makes sense -
    we should only take if we have something worse to replace.
    """
    for c in player.cards:
        if c.face_up and get_ai_card_value(c, options) > card_value:
            return True
    return False


def get_column_partner_position(pos: int) -> int:
    """Get the column partner position for a given position.

    Column pairs: (0,3), (1,4), (2,5)
    """
    return (pos + 3) % 6 if pos < 3 else pos - 3


# =============================================================================
# Column/Pair Utility Functions
# =============================================================================

def iter_columns(player: Player):
    """Yield (col_index, top_idx, bot_idx, top_card, bot_card) for each column."""
    for col in range(3):
        top_idx = col
        bot_idx = col + 3
        yield col, top_idx, bot_idx, player.cards[top_idx], player.cards[bot_idx]


def project_score(player: Player, swap_pos: int, new_card: Card, options: GameOptions) -> int:
    """Calculate what the player's score would be if new_card were swapped into swap_pos.

    Handles pair cancellation correctly. Used by multiple decision paths.
    """
    total = 0
    for col, top_idx, bot_idx, top_card, bot_card in iter_columns(player):
        # Substitute the new card if it's in this column
        effective_top = new_card if top_idx == swap_pos else top_card
        effective_bot = new_card if bot_idx == swap_pos else bot_card

        if effective_top.rank == effective_bot.rank:
            # Pair cancels (standard rules)
            continue
        total += get_ai_card_value(effective_top, options)
        total += get_ai_card_value(effective_bot, options)
    return total


def count_hidden(player: Player) -> int:
    """Count face-down cards."""
    return sum(1 for c in player.cards if not c.face_up)


def hidden_positions(player: Player) -> list[int]:
    """Get indices of face-down cards."""
    return [i for i, c in enumerate(player.cards) if not c.face_up]


def visible_score_excluding_column(player: Player, exclude_col_pos: int, options: GameOptions) -> int:
    """Calculate score from visible columns, excluding the column containing exclude_col_pos.

    Used in go-out calculations where one column has special handling.
    """
    exclude_col = exclude_col_pos if exclude_col_pos < 3 else exclude_col_pos - 3
    total = 0
    for col, top_idx, bot_idx, top_card, bot_card in iter_columns(player):
        if col == exclude_col:
            continue
        if top_card.face_up and bot_card.face_up:
            if top_card.rank == bot_card.rank:
                continue  # Pair = 0
            total += get_ai_card_value(top_card, options)
            total += get_ai_card_value(bot_card, options)
        elif top_card.face_up:
            total += get_ai_card_value(top_card, options)
        elif bot_card.face_up:
            total += get_ai_card_value(bot_card, options)
    return total


def filter_bad_pair_positions(
    positions: list[int],
    drawn_card: Card,
    player: Player,
    options: GameOptions
) -> list[int]:
    """Filter out positions that would create wasteful pairs with negative cards.

    When placing a card (especially negative value cards like 2s or Jokers),
    we should avoid positions where the column partner is a visible card of
    the same rank - pairing negative cards wastes their value.

    Args:
        positions: List of candidate positions
        drawn_card: The card we're placing
        player: The player's hand
        options: Game options for house rules

    Returns:
        Filtered list excluding bad pair positions. If all positions are bad,
        returns the original list (we have to place somewhere).
    """
    drawn_value = get_ai_card_value(drawn_card, options)

    # Only filter if the drawn card has negative value (2s, Jokers, super_kings Kings)
    # Pairing positive cards is fine - it turns their value to 0
    if drawn_value >= 0:
        return positions

    # Exception: Eagle Eye makes pairing Jokers GOOD (-4 instead of 0)
    if options.eagle_eye and drawn_card.rank == Rank.JOKER:
        return positions

    # Exception: Negative Pairs Keep Value makes pairing negative cards GOOD
    if options.negative_pairs_keep_value:
        return positions

    filtered = []
    for pos in positions:
        partner_pos = get_column_partner_position(pos)
        partner = player.cards[partner_pos]

        # If partner is face-up and same rank, this would create a wasteful pair
        if partner.face_up and partner.rank == drawn_card.rank:
            continue  # Skip this position

        filtered.append(pos)

    # If all positions were filtered out, return original (must place somewhere)
    return filtered if filtered else positions


@dataclass
class CPUProfile:
    """Pre-defined CPU player profile with personality traits."""
    name: str
    style: str  # Brief description shown to players
    # Tipping point: swap if card value is at or above this (4-8)
    swap_threshold: int
    # How likely to hold high cards hoping for pairs (0.0-1.0)
    pair_hope: float
    # Screw your neighbor: tendency to go out early (0.0-1.0)
    aggression: float
    # Wildcard factor: chance of unexpected plays (0.0-0.3)
    unpredictability: float

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "style": self.style,
        }


# Pre-defined CPU profiles (3 female, 3 male, 2 non-binary)
CPU_PROFILES = [
    # Female profiles
    CPUProfile(
        name="Sofia",
        style="Calculated & Patient",
        swap_threshold=4,
        pair_hope=0.2,
        aggression=0.2,
        unpredictability=0.02,
    ),
    CPUProfile(
        name="Maya",
        style="Aggressive Closer",
        swap_threshold=6,
        pair_hope=0.4,
        aggression=0.85,
        unpredictability=0.1,
    ),
    CPUProfile(
        name="Priya",
        style="Pair Hunter",
        swap_threshold=7,
        pair_hope=0.8,
        aggression=0.5,
        unpredictability=0.05,
    ),
    # Male profiles
    CPUProfile(
        name="Marcus",
        style="Steady Eddie",
        swap_threshold=5,
        pair_hope=0.35,
        aggression=0.4,
        unpredictability=0.03,
    ),
    CPUProfile(
        name="Kenji",
        style="Risk Taker",
        swap_threshold=8,
        pair_hope=0.7,
        aggression=0.75,
        unpredictability=0.12,
    ),
    CPUProfile(
        name="Diego",
        style="Chaotic Gambler",
        swap_threshold=6,
        pair_hope=0.5,
        aggression=0.6,
        unpredictability=0.28,
    ),
    # Non-binary profiles
    CPUProfile(
        name="River",
        style="Adaptive Strategist",
        swap_threshold=5,
        pair_hope=0.45,
        aggression=0.55,
        unpredictability=0.08,
    ),
    CPUProfile(
        name="Sage",
        style="Sneaky Finisher",
        swap_threshold=5,
        pair_hope=0.3,
        aggression=0.9,
        unpredictability=0.15,
    ),
]

# Track profiles per room (room_code -> set of used profile names)
_room_used_profiles: dict[str, set[str]] = {}
# Track cpu_id -> (room_code, profile) mapping
_cpu_profiles: dict[str, tuple[str, CPUProfile]] = {}


def get_available_profile(room_code: str) -> Optional[CPUProfile]:
    """Get a random available CPU profile for a specific room."""
    used_in_room = _room_used_profiles.get(room_code, set())
    available = [p for p in CPU_PROFILES if p.name not in used_in_room]
    if not available:
        return None
    profile = random.choice(available)
    if room_code not in _room_used_profiles:
        _room_used_profiles[room_code] = set()
    _room_used_profiles[room_code].add(profile.name)
    return profile


def release_profile(name: str, room_code: str):
    """Release a CPU profile back to the room's pool."""
    if room_code in _room_used_profiles:
        _room_used_profiles[room_code].discard(name)
        # Clean up empty room entries
        if not _room_used_profiles[room_code]:
            del _room_used_profiles[room_code]
    # Also remove from cpu_profiles by finding the cpu_id with this profile in this room
    to_remove = [
        cpu_id for cpu_id, (rc, profile) in _cpu_profiles.items()
        if profile.name == name and rc == room_code
    ]
    for cpu_id in to_remove:
        del _cpu_profiles[cpu_id]


def cleanup_room_profiles(room_code: str):
    """Clean up all profile tracking for a room when it's deleted."""
    if room_code in _room_used_profiles:
        del _room_used_profiles[room_code]
    # Remove all cpu_profiles for this room
    to_remove = [cpu_id for cpu_id, (rc, _) in _cpu_profiles.items() if rc == room_code]
    for cpu_id in to_remove:
        del _cpu_profiles[cpu_id]


def reset_all_profiles():
    """Reset all profile tracking (for cleanup)."""
    _room_used_profiles.clear()
    _cpu_profiles.clear()


def get_profile(cpu_id: str) -> Optional[CPUProfile]:
    """Get the profile for a CPU player."""
    entry = _cpu_profiles.get(cpu_id)
    return entry[1] if entry else None


def assign_profile(cpu_id: str, room_code: str) -> Optional[CPUProfile]:
    """Assign a random profile to a CPU player in a specific room."""
    profile = get_available_profile(room_code)
    if profile:
        _cpu_profiles[cpu_id] = (room_code, profile)
    return profile


def assign_specific_profile(cpu_id: str, profile_name: str, room_code: str) -> Optional[CPUProfile]:
    """Assign a specific profile to a CPU player by name in a specific room."""
    used_in_room = _room_used_profiles.get(room_code, set())
    # Check if profile exists and is available in this room
    for profile in CPU_PROFILES:
        if profile.name == profile_name and profile.name not in used_in_room:
            if room_code not in _room_used_profiles:
                _room_used_profiles[room_code] = set()
            _room_used_profiles[room_code].add(profile.name)
            _cpu_profiles[cpu_id] = (room_code, profile)
            return profile
    return None


def get_available_profiles(room_code: str) -> list[dict]:
    """Get available CPU profiles for a specific room."""
    used_in_room = _room_used_profiles.get(room_code, set())
    return [p.to_dict() for p in CPU_PROFILES if p.name not in used_in_room]


def get_all_profiles() -> list[dict]:
    """Get all CPU profiles for display."""
    return [p.to_dict() for p in CPU_PROFILES]


class GolfAI:
    """AI decision-making for Golf game."""

    @staticmethod
    def choose_initial_flips(count: int = 2) -> list[int]:
        """Choose cards to flip at the start."""
        if count == 0:
            return []
        if count == 1:
            return [random.randint(0, 5)]

        # For 2 cards, prefer different columns for pair info
        options = [
            [0, 4], [2, 4], [3, 1], [5, 1],
            [0, 5], [2, 3],
        ]
        return random.choice(options)

    @staticmethod
    def _check_auto_take(
        discard_card: Card,
        discard_value: int,
        player: Player,
        options: GameOptions,
        profile: CPUProfile
    ) -> Optional[bool]:
        """Check auto-take rules for the discard card.

        Returns True (take), or None (no auto-take triggered, continue evaluation).
        Covers: Jokers, Kings, one-eyed Jacks, wolfpack Jacks, ten_penny 10s,
        four-of-a-kind pursuit, and pair potential.
        """
        # Always take Jokers and Kings (even better with house rules)
        if discard_card.rank == Rank.JOKER:
            if options.eagle_eye:
                for card in player.cards:
                    if card.face_up and card.rank == Rank.JOKER:
                        ai_log(f"  >> TAKE: Joker for Eagle Eye pair")
                        return True
            ai_log(f"  >> TAKE: Joker (always take)")
            return True

        if discard_card.rank == Rank.KING:
            ai_log(f"  >> TAKE: King (always take)")
            return True

        # One-eyed Jacks: J♥ and J♠ are worth 0, always take them
        if options.one_eyed_jacks:
            if discard_card.rank == Rank.JACK and discard_card.suit in (Suit.HEARTS, Suit.SPADES):
                ai_log(f"  >> TAKE: One-eyed Jack (worth 0)")
                return True

        # Wolfpack pursuit: Take Jacks when pursuing the bonus
        if options.wolfpack and discard_card.rank == Rank.JACK:
            jack_count = sum(1 for c in player.cards if c.face_up and c.rank == Rank.JACK)
            if jack_count >= 2 and profile.aggression > 0.5:
                ai_log(f"  >> TAKE: Jack for wolfpack pursuit ({jack_count} Jacks visible)")
                return True

        # Auto-take 10s when ten_penny enabled (they're worth 1)
        if discard_card.rank == Rank.TEN and options.ten_penny:
            ai_log(f"  >> TAKE: 10 (ten_penny rule)")
            return True

        # Four-of-a-kind pursuit: Take cards when building toward bonus
        if options.four_of_a_kind and profile.aggression > 0.5:
            rank_count = sum(1 for c in player.cards if c.face_up and c.rank == discard_card.rank)
            if rank_count >= 2:
                ai_log(f"  >> TAKE: {discard_card.rank.value} for four-of-a-kind ({rank_count} visible)")
                return True

        # Take card if it could make a column pair (but NOT for negative value cards)
        if discard_value > 0:
            for i, card in enumerate(player.cards):
                pair_pos = (i + 3) % 6 if i < 3 else i - 3
                pair_card = player.cards[pair_pos]

                if card.face_up and card.rank == discard_card.rank and not pair_card.face_up:
                    ai_log(f"  >> TAKE: can pair with visible {card.rank.value} at pos {i}")
                    return True

        return None  # No auto-take triggered

    @staticmethod
    def _has_good_swap_option(
        discard_card: Card,
        discard_value: int,
        player: Player,
        options: GameOptions,
        game: Game,
        profile: CPUProfile
    ) -> bool:
        """Preview swap scores to check if any position is worth swapping into."""
        for pos in range(6):
            score = GolfAI.calculate_swap_score(
                pos, discard_card, discard_value, player, options, game, profile
            )
            if score > 0:
                return True
        return False

    @staticmethod
    def should_take_discard(discard_card: Optional[Card], player: Player,
                            profile: CPUProfile, game: Game) -> bool:
        """Decide whether to take from discard pile or deck."""
        if not discard_card:
            return False

        options = game.options
        discard_value = get_ai_card_value(discard_card, options)

        ai_log(f"--- {profile.name} considering discard: {discard_card.rank.value}{discard_card.suit.value} (value={discard_value}) ---")

        # SAFEGUARD: If we have only 1 face-down card, taking from discard
        # forces us to swap and go out. Check if that would be acceptable.
        face_down = hidden_positions(player)
        if len(face_down) == 1:
            projected_score = project_score(player, face_down[0], discard_card, options)

            max_acceptable = 18 if profile.aggression > 0.6 else (16 if profile.aggression > 0.3 else 14)
            ai_log(f"  Go-out check: projected={projected_score}, max_acceptable={max_acceptable}")
            if projected_score > max_acceptable:
                if discard_value >= 0 and discard_card.rank not in (Rank.ACE, Rank.TWO, Rank.KING, Rank.JOKER):
                    ai_log(f"  >> REJECT: would force go-out with {projected_score} pts")
                    return False

        # Unpredictable players occasionally make random choice
        if random.random() < profile.unpredictability:
            if discard_value <= 5:
                return random.choice([True, False])

        # Auto-take rules (Jokers, Kings, one-eyed Jacks, wolfpack, etc.)
        auto_take = GolfAI._check_auto_take(discard_card, discard_value, player, options, profile)
        if auto_take is not None:
            return auto_take

        # Take low cards (threshold adjusts by game phase)
        phase = get_game_phase(game)
        base_threshold = {'early': 2, 'mid': 3, 'late': 4}.get(phase, 2)

        if discard_value <= base_threshold:
            ai_log(f"  >> TAKE: low card (value {discard_value} <= {base_threshold} threshold for {phase} game)")
            return True

        # For marginal cards, preview swap scores before committing.
        # Taking from discard FORCES a swap - don't take if no good swap exists.

        # Calculate end-game pressure from opponents close to going out
        pressure = get_end_game_pressure(player, game)

        # Under pressure, expand what we consider "worth taking"
        if pressure > 0.2:
            pressure_threshold = 3 + int(pressure * 6)  # 4 to 9 based on pressure
            pressure_threshold = min(pressure_threshold, 7)  # Cap at 7
            if discard_value <= pressure_threshold:
                if count_hidden(player) > 0:
                    if GolfAI._has_good_swap_option(discard_card, discard_value, player, options, game, profile):
                        ai_log(f"  >> TAKE: pressure={pressure:.2f}, threshold={pressure_threshold}")
                        return True
                    else:
                        ai_log(f"  >> SKIP: pressure would take, but no good swap position")

        # Check if we have cards worse than the discard
        worst_visible = -999
        for card in player.cards:
            if card.face_up:
                worst_visible = max(worst_visible, get_ai_card_value(card, options))

        if worst_visible > discard_value + 1:
            if has_worse_visible_card(player, discard_value, options):
                if GolfAI._has_good_swap_option(discard_card, discard_value, player, options, game, profile):
                    ai_log(f"  >> TAKE: have worse visible card ({worst_visible})")
                    return True
                else:
                    ai_log(f"  >> SKIP: have worse card, but no good swap position")

        ai_log(f"  >> PASS: drawing from deck instead")
        return False

    @staticmethod
    def _pair_improvement(
        pos: int,
        drawn_card: Card,
        drawn_value: int,
        player: Player,
        options: GameOptions,
        profile: CPUProfile
    ) -> float:
        """Calculate pair bonus and spread bonus score components.

        Section 1: Pair creation scoring (positive/negative/eagle_eye/negative_pairs_keep_value)
        Section 1b: Spread bonus for non-pairing excellent cards
        """
        partner_pos = get_column_partner_position(pos)
        partner_card = player.cards[partner_pos]

        score = 0.0

        # Personality-based weight modifiers
        pair_weight = 1.0 + profile.pair_hope  # Range: 1.0 to 2.0
        spread_weight = 2.0 - profile.pair_hope  # Range: 1.0 to 2.0 (inverse)

        # 1. PAIR BONUS - Creating a pair
        if partner_card.face_up and partner_card.rank == drawn_card.rank:
            partner_value = get_ai_card_value(partner_card, options)

            if drawn_value >= 0:
                # Good pair! Both cards cancel to 0
                pair_bonus = drawn_value + partner_value
                score += pair_bonus * pair_weight
            else:
                # Pairing negative cards
                if options.eagle_eye and drawn_card.rank == Rank.JOKER:
                    score += 8 * pair_weight  # Eagle Eye Joker pairs = -4
                elif options.negative_pairs_keep_value:
                    pair_benefit = abs(drawn_value + partner_value)
                    score += pair_benefit * pair_weight
                    ai_log(f"    Negative pair keep value bonus: +{pair_benefit * pair_weight:.1f}")
                else:
                    # Standard rules: penalty for wasting negative cards
                    penalty = abs(drawn_value) * 2 * (2.0 - profile.pair_hope)
                    score -= penalty
                    ai_log(f"    Negative pair penalty at pos {pos}: -{penalty:.1f} (score now={score:.2f})")

        # 1b. SPREAD BONUS - Not pairing good cards (spreading them out)
        if not partner_card.face_up or partner_card.rank != drawn_card.rank:
            if drawn_value <= 1:  # Excellent cards (K, 2, A, Joker)
                score += spread_weight * 0.5

        return score

    @staticmethod
    def _point_gain(
        pos: int,
        drawn_card: Card,
        drawn_value: int,
        player: Player,
        options: GameOptions,
        profile: CPUProfile
    ) -> float:
        """Calculate point gain score component from replacing a card.

        Handles face-up replacement (breaking pair, creating pair, normal swap)
        and hidden card expected-value calculation with discount.
        """
        current_card = player.cards[pos]
        partner_pos = get_column_partner_position(pos)
        partner_card = player.cards[partner_pos]

        if current_card.face_up:
            current_value = get_ai_card_value(current_card, options)

            # CRITICAL: Check if current card is part of an existing column pair
            if partner_card.face_up and partner_card.rank == current_card.rank:
                partner_value = get_ai_card_value(partner_card, options)

                if options.eagle_eye and current_card.rank == Rank.JOKER:
                    old_column_value = -4
                    new_column_value = drawn_value + 2
                    point_gain = old_column_value - new_column_value
                    ai_log(f"    Breaking Eagle Eye joker pair at pos {pos}: column {old_column_value} -> {new_column_value}, gain={point_gain}")
                elif options.negative_pairs_keep_value and (current_value < 0 or partner_value < 0):
                    old_column_value = current_value + partner_value
                    new_column_value = drawn_value + partner_value
                    point_gain = old_column_value - new_column_value
                    ai_log(f"    Breaking negative-keep pair at pos {pos}: column {old_column_value} -> {new_column_value}, gain={point_gain}")
                else:
                    old_column_value = 0
                    new_column_value = drawn_value + partner_value
                    point_gain = old_column_value - new_column_value
                    ai_log(f"    Breaking standard pair at pos {pos}: column 0 -> {new_column_value}, gain={point_gain}")
            elif partner_card.face_up and partner_card.rank == drawn_card.rank:
                # CREATING a new pair (drawn matches partner, but current doesn't)
                partner_value = get_ai_card_value(partner_card, options)
                old_column_value = current_value + partner_value
                if drawn_value < 0 and not options.negative_pairs_keep_value:
                    if options.eagle_eye and drawn_card.rank == Rank.JOKER:
                        new_column_value = -4
                    else:
                        new_column_value = 0
                elif options.negative_pairs_keep_value and (drawn_value < 0 or partner_value < 0):
                    new_column_value = drawn_value + partner_value
                else:
                    new_column_value = 0
                point_gain = old_column_value - new_column_value
                ai_log(f"    Creating pair at pos {pos}: column {old_column_value} -> {new_column_value}, gain={point_gain}")
            else:
                point_gain = current_value - drawn_value

            return float(point_gain)
        else:
            # Hidden card - expected value ~4.5
            creates_negative_pair = (
                partner_card.face_up and
                partner_card.rank == drawn_card.rank and
                drawn_value < 0 and
                not options.negative_pairs_keep_value and
                not (options.eagle_eye and drawn_card.rank == Rank.JOKER)
            )
            if not creates_negative_pair:
                expected_hidden = EXPECTED_HIDDEN_VALUE
                point_gain = expected_hidden - drawn_value
                discount = 0.5 + (profile.swap_threshold / 16)  # Range: 0.5 to 1.0
                return point_gain * discount
            return 0.0

    @staticmethod
    def _reveal_and_bonus_score(
        pos: int,
        drawn_card: Card,
        drawn_value: int,
        player: Player,
        options: GameOptions,
        game: Game,
        profile: CPUProfile
    ) -> float:
        """Calculate reveal bonus and strategic bonus score components.

        Sections 3-4d: reveal bonus, future pair potential, four-of-a-kind pursuit,
        wolfpack pursuit, and comeback aggression.
        """
        current_card = player.cards[pos]
        partner_pos = get_column_partner_position(pos)
        partner_card = player.cards[partner_pos]

        score = 0.0
        pair_weight = 1.0 + profile.pair_hope

        # 3. REVEAL BONUS - Value of revealing hidden cards
        if not current_card.face_up:
            reveal_bonus = min(count_hidden(player), 4)
            aggression_multiplier = 0.8 + profile.aggression * 0.4  # Range: 0.8 to 1.2

            if drawn_value <= 0:
                score += reveal_bonus * 1.2 * aggression_multiplier
            elif drawn_value == 1:
                score += reveal_bonus * 1.0 * aggression_multiplier
            elif drawn_value <= 4:
                score += reveal_bonus * 0.6 * aggression_multiplier
            elif drawn_value <= 6:
                score += reveal_bonus * 0.3 * aggression_multiplier

        # 4. FUTURE PAIR POTENTIAL
        if not current_card.face_up and not partner_card.face_up:
            pair_viability = get_pair_viability(drawn_card.rank, game)
            score += pair_viability * pair_weight * 0.5

        # 4b. FOUR OF A KIND PURSUIT
        if options.four_of_a_kind:
            rank_count = sum(
                1 for i, c in enumerate(player.cards)
                if c.face_up and c.rank == drawn_card.rank and i != pos
            )
            if rank_count >= 2:
                four_kind_bonus = rank_count * 4
                standings_pressure = get_standings_pressure(player, game)
                if standings_pressure > 0.3:
                    four_kind_bonus *= (1 + standings_pressure * 0.5)
                score += four_kind_bonus
                ai_log(f"    Four-of-a-kind pursuit bonus: +{four_kind_bonus:.1f}")

        # 4c. WOLFPACK PURSUIT
        if options.wolfpack and profile.aggression > 0.5:
            jack_pair_count = 0
            for col in range(3):
                top, bot = player.cards[col], player.cards[col + 3]
                if top.face_up and bot.face_up and top.rank == Rank.JACK and bot.rank == Rank.JACK:
                    jack_pair_count += 1

            visible_jacks = sum(1 for c in player.cards if c.face_up and c.rank == Rank.JACK)

            if drawn_card.rank == Rank.JACK:
                if jack_pair_count == 1:
                    if partner_card.face_up and partner_card.rank == Rank.JACK:
                        wolfpack_bonus = 15 * profile.aggression
                        score += wolfpack_bonus
                        ai_log(f"    Wolfpack pursuit: completing 2nd Jack pair! +{wolfpack_bonus:.1f}")
                    elif not partner_card.face_up:
                        wolfpack_bonus = 2 * profile.aggression
                        score += wolfpack_bonus
                        ai_log(f"    Wolfpack pursuit (speculative): +{wolfpack_bonus:.1f}")
                elif visible_jacks >= 1 and partner_card.face_up and partner_card.rank == Rank.JACK:
                    wolfpack_bonus = 8 * profile.aggression
                    score += wolfpack_bonus
                    ai_log(f"    Wolfpack pursuit: first Jack pair +{wolfpack_bonus:.1f}")

        # 4d. COMEBACK AGGRESSION
        standings_pressure = get_standings_pressure(player, game)
        if standings_pressure > 0.3 and not current_card.face_up and drawn_value < HIGH_CARD_THRESHOLD:
            comeback_bonus = standings_pressure * 3 * profile.aggression
            score += comeback_bonus
            ai_log(f"    Comeback aggression bonus: +{comeback_bonus:.1f} (pressure={standings_pressure:.2f})")

        return score

    @staticmethod
    def calculate_swap_score(
        pos: int,
        drawn_card: Card,
        drawn_value: int,
        player: Player,
        options: GameOptions,
        game: Game,
        profile: CPUProfile
    ) -> float:
        """
        Calculate a score for swapping into a specific position.
        Higher score = better swap. Weighs all incentives:
        - Pair bonus (highest priority for positive cards)
        - Point gain from replacement
        - Reveal bonus for hidden cards
        - Go-out safety check

        Personality traits affect weights:
        - pair_hope: higher = values pairing more, lower = prefers spreading
        - aggression: higher = more willing to go out, take risks
        - swap_threshold: affects how picky about card values
        """
        score = 0.0

        # 1/1b. Pair creation + spread bonus
        score += GolfAI._pair_improvement(pos, drawn_card, drawn_value, player, options, profile)

        # 2. Point gain from replacement
        score += GolfAI._point_gain(pos, drawn_card, drawn_value, player, options, profile)

        # 3-4d. Reveal bonus, future pair potential, four-of-a-kind, wolfpack, comeback
        score += GolfAI._reveal_and_bonus_score(pos, drawn_card, drawn_value, player, options, game, profile)

        # 5. GO-OUT SAFETY - Penalty for going out with bad score
        face_down_positions = hidden_positions(player)
        if len(face_down_positions) == 1 and pos == face_down_positions[0]:
            projected_score = project_score(player, pos, drawn_card, options)

            max_acceptable = GO_OUT_SCORE_BASE + int(profile.aggression * (GO_OUT_SCORE_MAX - GO_OUT_SCORE_BASE))
            if projected_score > max_acceptable:
                score -= 100

        return score

    @staticmethod
    def choose_swap_or_discard(drawn_card: Card, player: Player,
                                profile: CPUProfile, game: Game) -> Optional[int]:
        """
        Decide whether to swap the drawn card or discard.
        Returns position to swap with, or None to discard.

        Uses a unified scoring system that weighs all incentives:
        - Pair creation (best for positive cards, bad for negative)
        - Point gain from replacement
        - Revealing hidden cards (catching up, information)
        - Safety (don't go out with terrible score)
        """
        options = game.options
        drawn_value = get_ai_card_value(drawn_card, options)

        # Check if we should force a go-out swap (exactly 1 face-down card)
        go_out_pos = GolfAI._check_go_out_swap(drawn_card, drawn_value, player, profile, game)
        if go_out_pos is not None:
            return go_out_pos

        ai_log(f"=== {profile.name} deciding: drew {drawn_card.rank.value}{drawn_card.suit.value} (value={drawn_value}) ===")
        ai_log(f"  Personality: pair_hope={profile.pair_hope:.2f}, aggression={profile.aggression:.2f}, "
               f"swap_threshold={profile.swap_threshold}, unpredictability={profile.unpredictability:.2f}")

        # Log current hand state
        hand_str = " ".join(
            f"[{i}:{c.rank.value if c.face_up else '?'}]" for i, c in enumerate(player.cards)
        )
        ai_log(f"  Hand: {hand_str}")

        # Check for unpredictable random play
        unpredictable_pos = GolfAI._check_unpredictable_swap(
            drawn_card, drawn_value, player, profile, options
        )
        if unpredictable_pos is not None:
            return unpredictable_pos

        # Score all positions and select best candidate
        position_scores = GolfAI._score_all_positions(
            drawn_card, drawn_value, player, profile, options, game
        )
        best_pos, best_score = GolfAI._select_best_candidate(
            position_scores, drawn_card, drawn_value, player, profile, options, game
        )

        # Blackjack special case: chase exactly 21
        if options.blackjack and best_pos is None:
            blackjack_pos = GolfAI._check_blackjack_swap(drawn_card, drawn_value, player, profile, options)
            if blackjack_pos is not None:
                return blackjack_pos

        # Check if pair hunter wants to hold for future pair
        best_pos = GolfAI._check_hold_for_pair(
            best_pos, drawn_card, drawn_value, player, profile, game
        )

        # Final safety: force swap if about to go out with bad score
        best_pos = GolfAI._check_final_safety(
            best_pos, drawn_card, drawn_value, player, profile, options
        )

        # Opponent denial: consider keeping card to deny next player
        best_pos = GolfAI._check_denial_swap(
            best_pos, drawn_card, drawn_value, player, profile, game, options
        )

        # Log final decision
        if best_pos is not None:
            target_card = player.cards[best_pos]
            target_str = target_card.rank.value if target_card.face_up else "hidden"
            ai_log(f"  DECISION: SWAP into position {best_pos} (replacing {target_str}) [score={best_score:.2f}]")
        else:
            ai_log(f"  DECISION: DISCARD {drawn_card.rank.value} (no good swap options)")

        return best_pos

    @staticmethod
    def _check_go_out_swap(drawn_card: Card, drawn_value: int, player: Player,
                           profile: CPUProfile, game: Game) -> Optional[int]:
        """If player has exactly 1 face-down card, decide the best go-out swap.

        Returns position to swap into, or None to fall through to normal scoring.
        Uses a sentinel value of -1 (converted to None by caller) is not needed -
        we return None to indicate "no early decision, continue normal flow".
        """
        options = game.options
        face_down_positions = hidden_positions(player)
        if len(face_down_positions) != 1:
            return None

        last_pos = face_down_positions[0]
        last_partner_pos = get_column_partner_position(last_pos)
        last_partner = player.cards[last_partner_pos]

        # Calculate base visible score (EXCLUDING the column with hidden card entirely)
        visible_score = visible_score_excluding_column(player, last_pos, options)

        # Get partner value for calculations
        partner_value = get_ai_card_value(last_partner, options) if last_partner.face_up else 0

        # Calculate score if we SWAP drawn card into last position
        if last_partner.face_up and last_partner.rank == drawn_card.rank:
            # Would create a pair - calculate actual column contribution
            if drawn_value < 0 and not options.negative_pairs_keep_value:
                if options.eagle_eye and drawn_card.rank == Rank.JOKER:
                    pair_column_value = -4
                else:
                    pair_column_value = 0
                    ai_log(f"    GO-OUT: pairing negative cards would waste {abs(drawn_value + partner_value)} pts")
            elif options.negative_pairs_keep_value and (drawn_value < 0 or partner_value < 0):
                pair_column_value = drawn_value + partner_value
            else:
                pair_column_value = 0
            score_if_swap = visible_score + pair_column_value
        else:
            score_if_swap = visible_score + drawn_value + partner_value

        # Estimate score if we DISCARD and FLIP (hidden card is unknown)
        estimated_hidden = PESSIMISTIC_HIDDEN_VALUE
        score_if_flip = visible_score + estimated_hidden + partner_value

        # Check if swap would create a wasteful negative pair
        would_waste_negative = (
            last_partner.face_up and
            last_partner.rank == drawn_card.rank and
            drawn_value < 0 and
            not options.negative_pairs_keep_value and
            not (options.eagle_eye and drawn_card.rank == Rank.JOKER)
        )

        max_acceptable_go_out = 14 + int(profile.aggression * 4)

        ai_log(f"  Go-out safety check: visible_base={visible_score}, "
               f"score_if_swap={score_if_swap}, score_if_flip={score_if_flip}, "
               f"max_acceptable={max_acceptable_go_out}")

        # If BOTH options are bad, choose the better one
        if score_if_swap > max_acceptable_go_out and score_if_flip > max_acceptable_go_out:
            if score_if_swap <= score_if_flip:
                ai_log(f"  >> SAFETY: both options bad, but swap ({score_if_swap}) "
                       f"<= flip ({score_if_flip}), forcing swap")
                return last_pos
            else:
                ai_log(f"  >> WARNING: both options bad, flip ({score_if_flip}) "
                       f"< swap ({score_if_swap}), will try to find better swap")
                return None  # Fall through to normal scoring

        # If swap would waste negative cards, fall through to normal scoring
        elif would_waste_negative:
            ai_log(f"  >> SKIP GO-OUT SHORTCUT: would waste negative pair, checking other positions")
            return None

        # If swap is good, prefer it (known outcome vs unknown flip)
        elif score_if_swap <= max_acceptable_go_out and score_if_swap <= score_if_flip:
            ai_log(f"  >> SAFETY: swap gives acceptable score {score_if_swap}")
            return last_pos

        return None

    @staticmethod
    def _check_unpredictable_swap(drawn_card: Card, drawn_value: int, player: Player,
                                   profile: CPUProfile, options: GameOptions) -> Optional[int]:
        """Unpredictable players occasionally make surprising plays.

        Returns position to swap into, or None to continue normal scoring.
        """
        if random.random() >= profile.unpredictability:
            return None
        if drawn_value <= 1:
            return None  # Never discard excellent cards

        face_down = hidden_positions(player)
        if not face_down or random.random() >= 0.5:
            return None

        # SAFETY: Don't randomly go out with a bad score
        if len(face_down) == 1:
            last_pos = face_down[0]
            projected = drawn_value
            for i, c in enumerate(player.cards):
                if i != last_pos and c.face_up:
                    projected += get_ai_card_value(c, options)
            # Apply pair cancellation
            for col in range(3):
                top_idx, bot_idx = col, col + 3
                top_card = drawn_card if top_idx == last_pos else player.cards[top_idx]
                bot_card = drawn_card if bot_idx == last_pos else player.cards[bot_idx]
                if top_card.face_up or top_idx == last_pos:
                    if bot_card.face_up or bot_idx == last_pos:
                        if top_card.rank == bot_card.rank:
                            top_val = drawn_value if top_idx == last_pos else get_ai_card_value(player.cards[top_idx], options)
                            bot_val = drawn_value if bot_idx == last_pos else get_ai_card_value(player.cards[bot_idx], options)
                            projected -= (top_val + bot_val)
            max_acceptable = GO_OUT_SCORE_BASE + int(profile.aggression * (GO_OUT_SCORE_MAX - GO_OUT_SCORE_BASE))
            if projected > max_acceptable:
                ai_log(f"  >> UNPREDICTABLE: blocked - would go out with {projected} > {max_acceptable}")
                return None
            else:
                ai_log(f"  >> UNPREDICTABLE: randomly chose position {last_pos} (projected {projected})")
                return last_pos
        else:
            # Only allow random swaps for cards that aren't objectively bad
            if drawn_value <= UNPREDICTABLE_MAX_VALUE:
                choice = random.choice(face_down)
                ai_log(f"  >> UNPREDICTABLE: randomly chose position {choice} (value {drawn_value} <= {UNPREDICTABLE_MAX_VALUE})")
                return choice
            else:
                ai_log(f"  >> UNPREDICTABLE: blocked - value {drawn_value} > {UNPREDICTABLE_MAX_VALUE} threshold")
                return None

    @staticmethod
    def _score_all_positions(drawn_card: Card, drawn_value: int, player: Player,
                              profile: CPUProfile, options: GameOptions,
                              game: Game) -> list[tuple[int, float]]:
        """Calculate swap benefit score for each of the 6 positions.

        Returns list of (position, score) tuples.
        """
        position_scores: list[tuple[int, float]] = []
        for pos in range(6):
            score = GolfAI.calculate_swap_score(
                pos, drawn_card, drawn_value, player, options, game, profile
            )
            position_scores.append((pos, score))

        # Log all scores
        ai_log(f"  Position scores:")
        for pos, score in position_scores:
            card = player.cards[pos]
            partner_pos = get_column_partner_position(pos)
            partner = player.cards[partner_pos]
            card_str = card.rank.value if card.face_up else "?"
            partner_str = partner.rank.value if partner.face_up else "?"
            pair_indicator = " [PAIR]" if partner.face_up and partner.rank == drawn_card.rank else ""
            reveal_indicator = " [REVEAL]" if not card.face_up else ""
            ai_log(f"    pos {pos} ({card_str}, partner={partner_str}): {score:+.2f}{pair_indicator}{reveal_indicator}")

        return position_scores

    @staticmethod
    def _select_best_candidate(position_scores: list[tuple[int, float]],
                                drawn_card: Card, drawn_value: int, player: Player,
                                profile: CPUProfile, options: GameOptions,
                                game: Game) -> tuple[Optional[int], float]:
        """From scored positions, apply safety filters and personality tie-breaking.

        Returns (best_position, best_score) or (None, 0.0) if no good swap.
        """
        # Filter to positive scores only
        positive_scores = [(p, s) for p, s in position_scores if s > 0]

        # SAFETY: Never swap high cards into hidden positions
        if drawn_value >= HIGH_CARD_THRESHOLD:
            safe_positive = []
            for pos, score in positive_scores:
                card = player.cards[pos]
                partner_pos = get_column_partner_position(pos)
                partner = player.cards[partner_pos]
                creates_pair = partner.face_up and partner.rank == drawn_card.rank

                if card.face_up or creates_pair:
                    safe_positive.append((pos, score))
                else:
                    ai_log(f"    SAFETY: rejecting pos {pos} - high card ({drawn_value}) into hidden")

            positive_scores = safe_positive

        best_pos: Optional[int] = None
        best_score = 0.0

        if positive_scores:
            # Sort by score descending
            positive_scores.sort(key=lambda x: x[1], reverse=True)
            best_pos, best_score = positive_scores[0]

            # PERSONALITY TIE-BREAKER: When top options are close, let personality decide
            close_threshold = TIE_BREAKER_THRESHOLD
            close_options = [(p, s) for p, s in positive_scores if s >= best_score - close_threshold]

            if len(close_options) > 1:
                ai_log(f"  TIE-BREAKER: {len(close_options)} options within {close_threshold} pts of best ({best_score:.2f})")
                original_best = best_pos

                for pos, score in close_options:
                    partner_pos = get_column_partner_position(pos)
                    partner_card = player.cards[partner_pos]
                    is_pair_move = partner_card.face_up and partner_card.rank == drawn_card.rank
                    is_reveal_move = not player.cards[pos].face_up

                    if is_pair_move and profile.pair_hope > 0.6:
                        ai_log(f"    >> PAIR_HOPE ({profile.pair_hope:.2f}): chose pair move at pos {pos}")
                        best_pos = pos
                        break
                    if is_reveal_move and profile.aggression > 0.7:
                        ai_log(f"    >> AGGRESSION ({profile.aggression:.2f}): chose reveal move at pos {pos}")
                        best_pos = pos
                        break
                    if not is_reveal_move and profile.swap_threshold <= 4:
                        ai_log(f"    >> CONSERVATIVE (threshold={profile.swap_threshold}): chose safe move at pos {pos}")
                        best_pos = pos
                        break

                if profile.unpredictability > 0.1 and random.random() < profile.unpredictability:
                    best_pos = random.choice([p for p, s in close_options])
                    ai_log(f"    >> RANDOM (unpredictability={profile.unpredictability:.2f}): chose pos {best_pos}")

                if best_pos != original_best:
                    ai_log(f"  Tie-breaker changed choice: {original_best} -> {best_pos}")

        return best_pos, best_score

    @staticmethod
    def _check_blackjack_swap(drawn_card: Card, drawn_value: int, player: Player,
                               profile: CPUProfile, options: GameOptions) -> Optional[int]:
        """Check if we can chase exactly 21 for blackjack bonus."""
        current_score = player.calculate_score()
        if current_score >= 15:
            for i, card in enumerate(player.cards):
                if card.face_up:
                    potential_change = drawn_value - get_ai_card_value(card, options)
                    if current_score + potential_change == BLACKJACK_TARGET:
                        if random.random() < profile.aggression:
                            ai_log(f"  >> BLACKJACK: chasing 21 at position {i}")
                            return i
        return None

    @staticmethod
    def _check_hold_for_pair(best_pos: Optional[int], drawn_card: Card, drawn_value: int,
                              player: Player, profile: CPUProfile,
                              game: Game) -> Optional[int]:
        """Pair hunters might hold medium cards hoping for matches.

        Returns best_pos (unchanged) or None (discard to hold for pair).
        """
        face_down_count = count_hidden(player)
        # Only hold if best swap is into a hidden position and we have >1 face-down
        if best_pos is None or player.cards[best_pos].face_up or face_down_count <= 1:
            return best_pos
        if drawn_value < 5:
            return best_pos  # Only hold out for medium/high cards

        # DON'T hold if placing at best_pos would actually CREATE a pair right now!
        partner_pos = get_column_partner_position(best_pos)
        partner_card = player.cards[partner_pos]
        would_make_pair = partner_card.face_up and partner_card.rank == drawn_card.rank

        if would_make_pair:
            ai_log(f"  Skip hold-for-pair: placing at {best_pos} creates pair with {partner_card.rank.value}")
            return best_pos

        pair_viability = get_pair_viability(drawn_card.rank, game)
        phase = get_game_phase(game)
        pressure = get_end_game_pressure(player, game)

        effective_hope = profile.pair_hope * pair_viability
        if phase == 'late' or pressure > 0.5:
            effective_hope *= 0.3

        ai_log(f"  Hold-for-pair check: value={drawn_value}, viability={pair_viability:.2f}, "
               f"phase={phase}, effective_hope={effective_hope:.2f}")

        if effective_hope > 0.5 and random.random() < effective_hope:
            ai_log(f"  >> HOLDING: discarding {drawn_card.rank.value} hoping for future pair")
            return None  # Discard and hope for pair later

        return best_pos

    @staticmethod
    def _check_final_safety(best_pos: Optional[int], drawn_card: Card, drawn_value: int,
                             player: Player, profile: CPUProfile,
                             options: GameOptions) -> Optional[int]:
        """If we have exactly 1 face-down card and would discard, force a swap.

        Returns updated best_pos.
        """
        face_down_count = count_hidden(player)
        if best_pos is not None or face_down_count != 1:
            return best_pos

        last_pos = hidden_positions(player)[0]

        # Find the worst visible card we could replace instead
        worst_visible_pos = None
        worst_visible_val = -999
        for i, c in enumerate(player.cards):
            if c.face_up:
                val = get_ai_card_value(c, options)
                partner_pos = get_column_partner_position(i)
                partner = player.cards[partner_pos]
                if partner.face_up and partner.rank == c.rank:
                    continue  # Card is paired, don't replace
                if val > worst_visible_val:
                    worst_visible_val = val
                    worst_visible_pos = i

        if drawn_value < HIGH_CARD_THRESHOLD:
            ai_log(f"  >> FINAL SAFETY: forcing swap into hidden pos {last_pos} "
                   f"(drawn value {drawn_value} < {HIGH_CARD_THRESHOLD})")
            return last_pos
        elif worst_visible_pos is not None and drawn_value < worst_visible_val:
            ai_log(f"  >> FINAL SAFETY: swapping into visible pos {worst_visible_pos} "
                   f"(drawn {drawn_value} < worst visible {worst_visible_val})")
            return worst_visible_pos
        elif drawn_value >= HIGH_CARD_THRESHOLD:
            ai_log(f"  >> FINAL SAFETY: discarding bad card ({drawn_value}), will flip unknown")
            return None
        else:
            ai_log(f"  >> FINAL SAFETY: forcing swap into hidden pos {last_pos} "
                   f"(drawn value {drawn_value} is acceptable)")
            return last_pos

    @staticmethod
    def _check_denial_swap(best_pos: Optional[int], drawn_card: Card, drawn_value: int,
                            player: Player, profile: CPUProfile,
                            game: Game, options: GameOptions) -> Optional[int]:
        """Check if we should swap to deny opponents a useful card.

        Only triggers when we're about to discard (best_pos is None).
        Returns updated best_pos.
        """
        if best_pos is not None:
            return best_pos

        next_opponent = get_next_player(game, player)
        if not next_opponent:
            return best_pos

        denial_value = calculate_denial_value(drawn_card, next_opponent, game, options)
        if denial_value <= 0:
            return best_pos

        ai_log(f"  DENIAL CHECK: discarding {drawn_card.rank.value} would help "
               f"{next_opponent.name} (denial_value={denial_value:.1f})")

        denial_threshold = 4.0 + profile.aggression * 4

        if denial_value < denial_threshold:
            return best_pos

        # Find acceptable swap positions (minimize our loss)
        denial_candidates = []
        for pos in range(6):
            card = player.cards[pos]
            if not card.face_up:
                if drawn_value >= HIGH_CARD_THRESHOLD:
                    continue  # Never swap high cards into hidden for denial
                cost = drawn_value
                denial_candidates.append((pos, cost, "hidden"))
            else:
                replaced_val = get_ai_card_value(card, options)
                partner_pos = get_column_partner_position(pos)
                partner = player.cards[partner_pos]
                if partner.face_up and partner.rank == card.rank:
                    continue  # Don't break a pair
                cost = drawn_value - replaced_val
                denial_candidates.append((pos, cost, card.rank.value))

        denial_candidates.sort(key=lambda x: x[1])

        if denial_candidates:
            best_denial_pos, best_cost, card_desc = denial_candidates[0]
            max_acceptable_cost = denial_value / 2

            if best_cost <= max_acceptable_cost:
                ai_log(f"  >> DENIAL: swapping into pos {best_denial_pos} ({card_desc}) "
                       f"to deny pair (cost={best_cost:.1f}, denial={denial_value:.1f})")
                return best_denial_pos
            else:
                ai_log(f"  >> DENIAL REJECTED: best option cost {best_cost:.1f} > "
                       f"max acceptable {max_acceptable_cost:.1f}")

        return best_pos

    @staticmethod
    def choose_flip_after_discard(player: Player, profile: CPUProfile) -> int:
        """Choose which face-down card to flip after discarding."""
        face_down = [i for i, c in enumerate(player.cards) if not c.face_up]

        if not face_down:
            return 0

        # Prefer flipping cards that could reveal pair info
        for i in face_down:
            pair_pos = (i + 3) % 6 if i < 3 else i - 3
            if player.cards[pair_pos].face_up:
                return i

        return random.choice(face_down)

    @staticmethod
    def should_skip_optional_flip(player: Player, profile: CPUProfile, game: Game) -> bool:
        """
        Decide whether to skip the optional flip in endgame mode.

        In endgame (Suspense) mode, the flip is optional. AI should generally
        flip for information, but may skip if:
        - Already has good information about their hand
        - Wants to keep cards hidden for suspense
        - Random unpredictability factor

        Returns True if AI should skip the flip, False if it should flip.
        """
        face_down = [i for i, c in enumerate(player.cards) if not c.face_up]

        if not face_down:
            return True  # No cards to flip

        # Very conservative players (low aggression) might skip to keep hidden
        # But information is usually valuable, so mostly flip
        skip_chance = 0.1  # Base 10% chance to skip

        # More hidden cards = more value in flipping for information
        if len(face_down) >= 3:
            skip_chance = 0.05  # Less likely to skip with many hidden cards

        # If only 1 hidden card, we might skip to keep opponents guessing
        if len(face_down) == 1:
            skip_chance = 0.2 + (1.0 - profile.aggression) * 0.2

        # Unpredictable players are more random about this
        skip_chance += profile.unpredictability * 0.15

        ai_log(f"  Optional flip decision: {len(face_down)} face-down cards, skip_chance={skip_chance:.2f}")

        if random.random() < skip_chance:
            ai_log(f"  >> SKIP: choosing not to flip (endgame mode)")
            return True

        ai_log(f"  >> FLIP: choosing to reveal for information")
        return False

    @staticmethod
    def should_knock_early(game: Game, player: Player, profile: CPUProfile) -> bool:
        """
        Decide whether to use knock_early to flip all remaining cards at once.

        Only available when knock_early house rule is enabled and player
        has 1-2 face-down cards. This is a gamble - aggressive players
        with good visible cards may take the risk.
        """
        if not game.options.knock_early:
            return False

        face_down = [c for c in player.cards if not c.face_up]
        if len(face_down) == 0 or len(face_down) > 2:
            return False

        # Calculate current visible score
        visible_score = 0
        for col in range(3):
            top_idx, bot_idx = col, col + 3
            top = player.cards[top_idx]
            bot = player.cards[bot_idx]

            # Only count if both are visible
            if top.face_up and bot.face_up:
                if top.rank == bot.rank:
                    continue  # Pair = 0
                visible_score += get_ai_card_value(top, game.options)
                visible_score += get_ai_card_value(bot, game.options)
            elif top.face_up:
                visible_score += get_ai_card_value(top, game.options)
            elif bot.face_up:
                visible_score += get_ai_card_value(bot, game.options)

        # Aggressive players with low visible scores might knock early
        # Expected value of hidden card is ~4.5
        expected_hidden_total = len(face_down) * EXPECTED_HIDDEN_VALUE
        projected_score = visible_score + expected_hidden_total

        # Tighter threshold: range 5 to 9 based on aggression
        max_acceptable = 5 + int(profile.aggression * 4)

        # Exception: if all opponents are showing terrible scores, relax threshold
        all_opponents_bad = all(
            sum(get_ai_card_value(c, game.options) for c in p.cards if c.face_up) >= 25
            for p in game.players if p.id != player.id
        )
        if all_opponents_bad:
            max_acceptable += 5  # Willing to knock at higher score when winning big

        if projected_score <= max_acceptable:
            # Scale knock chance by how good the projected score is
            if projected_score <= 5:
                knock_chance = profile.aggression * 0.3  # Max 30%
            elif projected_score <= 7:
                knock_chance = profile.aggression * 0.15  # Max 15%
            else:
                knock_chance = profile.aggression * 0.05  # Max 5% (very rare)

            if random.random() < knock_chance:
                ai_log(f"  Knock early: taking the gamble! (projected {projected_score:.1f})")
                return True

        return False

    @staticmethod
    def should_use_flip_action(game: Game, player: Player, profile: CPUProfile) -> Optional[int]:
        """
        Decide whether to use flip-as-action instead of drawing.

        Returns card index to flip, or None to draw normally.

        Only available when flip_as_action house rule is enabled.
        Conservative players may prefer this to avoid risky deck draws.
        """
        if not game.options.flip_as_action:
            return None

        # Find face-down cards
        face_down = [(i, c) for i, c in enumerate(player.cards) if not c.face_up]
        if not face_down:
            return None  # No cards to flip

        # Check if discard has a good card we want - if so, don't use flip action
        discard_top = game.discard_top()
        if discard_top:
            discard_value = get_ai_card_value(discard_top, game.options)
            if discard_value <= 2:  # Good card available
                ai_log(f"  Flip-as-action: skipping, good discard available ({discard_value})")
                return None

        # Aggressive players prefer drawing (more action, chance to improve)
        if profile.aggression > 0.6:
            ai_log(f"  Flip-as-action: skipping, too aggressive ({profile.aggression:.2f})")
            return None

        # Consider flip action with probability based on personality
        # Conservative players (low aggression) are more likely to use it
        flip_chance = (1.0 - profile.aggression) * 0.25  # Max 25% for most conservative

        # Increase chance if we have many hidden cards (info is valuable)
        if len(face_down) >= 4:
            flip_chance *= 1.5

        if random.random() > flip_chance:
            return None

        ai_log(f"  Flip-as-action: choosing to flip instead of draw")

        # Prioritize positions where column partner is visible (pair info)
        for idx, card in face_down:
            partner_idx = idx + 3 if idx < 3 else idx - 3
            if player.cards[partner_idx].face_up:
                ai_log(f"    Flipping position {idx} (partner visible)")
                return idx

        # Random face-down card
        choice = random.choice(face_down)[0]
        ai_log(f"    Flipping position {choice} (random)")
        return choice

    @staticmethod
    def should_go_out_early(player: Player, game: Game, profile: CPUProfile) -> bool:
        """
        Decide if CPU should try to go out (reveal all cards) to screw neighbors.
        """
        options = game.options
        face_down_count = sum(1 for c in player.cards if not c.face_up)

        if face_down_count > 2:
            return False

        estimated_score = player.calculate_score()

        # Blackjack: If score is exactly 21, definitely go out (becomes 0!)
        if options.blackjack and estimated_score == BLACKJACK_TARGET:
            return True

        # Base threshold based on aggression
        go_out_threshold = 8 if profile.aggression > 0.7 else (12 if profile.aggression > 0.4 else 16)

        # COMEBACK MODE: Accept higher scores when significantly behind
        standings_pressure = get_standings_pressure(player, game)
        if standings_pressure > 0.5:
            # Behind and late - swing for the fences
            go_out_threshold += int(standings_pressure * 6)  # Up to +6 points tolerance
            ai_log(f"  Comeback mode: raised go-out threshold to {go_out_threshold}")

        # Knock Bonus (-5 for going out): Can afford to go out with higher score
        if options.knock_bonus:
            go_out_threshold += 5

        # Knock Penalty (+10 if not lowest): Need to be confident we're lowest
        if options.knock_penalty:
            opponent_min = estimate_opponent_min_score(player, game, optimistic=False)
            # Conservative players require bigger lead
            safety_margin = 5 if profile.aggression < 0.4 else 2
            if estimated_score > opponent_min - safety_margin:
                # We might not have the lowest score - be cautious
                go_out_threshold -= 4

        # Tied Shame: Estimate if we might tie someone
        if options.tied_shame:
            for p in game.players:
                if p.id == player.id:
                    continue
                visible = sum(get_ai_card_value(c, options) for c in p.cards if c.face_up)
                hidden_count = sum(1 for c in p.cards if not c.face_up)
                # Rough estimate - if visible scores are close, be cautious
                if hidden_count <= 2 and abs(visible - estimated_score) <= 3:
                    go_out_threshold -= 2
                    break

        # Underdog Bonus: Minor factor - you get -3 for lowest regardless
        # This slightly reduces urgency to go out first
        if options.underdog_bonus:
            go_out_threshold -= 1

        # HIGH SCORE CAUTION: When our score is >10, be extra careful
        # Opponents' hidden cards could easily beat us with pairs or low cards
        if estimated_score > 10:
            # Get pessimistic estimate of opponent's potential score
            opponent_min_pessimistic = estimate_opponent_min_score(player, game, optimistic=False)
            opponent_min_optimistic = estimate_opponent_min_score(player, game, optimistic=True)

            ai_log(f"  High score caution: our score={estimated_score}, "
                   f"opponent estimates: optimistic={opponent_min_optimistic}, pessimistic={opponent_min_pessimistic}")

            # If opponents could potentially beat us, reduce our willingness to go out
            if opponent_min_pessimistic < estimated_score:
                # Calculate how risky this is
                risk_margin = estimated_score - opponent_min_pessimistic
                # Reduce threshold based on risk (more risk = lower threshold)
                risk_penalty = min(risk_margin, 8)  # Cap at 8 point penalty
                go_out_threshold -= risk_penalty
                ai_log(f"  Risk penalty: -{risk_penalty} (opponents could score {opponent_min_pessimistic})")

            # Additional penalty for very high scores (>15) - almost never go out
            if estimated_score > 15:
                extra_penalty = (estimated_score - 15) * 2
                go_out_threshold -= extra_penalty
                ai_log(f"  Very high score penalty: -{extra_penalty}")

        ai_log(f"  Go-out decision: score={estimated_score}, threshold={go_out_threshold}, "
               f"aggression={profile.aggression:.2f}")

        if estimated_score <= go_out_threshold:
            if random.random() < profile.aggression:
                ai_log(f"  >> GOING OUT with score {estimated_score}")
                return True

        return False


def _log_cpu_action(logger, game_id: Optional[str], cpu_player: Player, game: Game,
                    action: str, card=None, position: Optional[int] = None,
                    decision_reason: str = ""):
    """Log a CPU action if logger is available."""
    if logger and game_id:
        logger.log_move(
            game_id=game_id,
            player=cpu_player,
            is_cpu=True,
            action=action,
            card=card,
            position=position,
            game=game,
            decision_reason=decision_reason,
        )


async def process_cpu_turn(
    game: Game, cpu_player: Player, broadcast_callback, game_id: Optional[str] = None
) -> None:
    """Process a complete turn for a CPU player."""
    import asyncio
    from services.game_logger import get_logger

    profile = get_profile(cpu_player.id)
    if not profile:
        profile = CPUProfile("CPU", "Balanced", 5, 0.4, 0.5, 0.1)

    logger = get_logger() if game_id else None

    # Brief initial delay before CPU "looks at" the discard pile
    initial_look = CPU_TIMING["initial_look"]
    await asyncio.sleep(random.uniform(initial_look[0], initial_look[1]))

    # "Thinking" delay based on how obvious the discard decision is
    discard_top = game.discard_top()
    thinking_time = get_discard_thinking_time(discard_top, game.options)

    # Adjust for personality - chaotic players have more variance
    if profile.unpredictability > 0.2:
        chaos_mult = CPU_TIMING["thinking_multiplier_chaotic"]
        thinking_time *= random.uniform(chaos_mult[0], chaos_mult[1])

    discard_str = f"{discard_top.rank.value}" if discard_top else "empty"
    ai_log(f"{cpu_player.name} thinking for {thinking_time:.2f}s (discard: {discard_str})")
    await asyncio.sleep(thinking_time)
    ai_log(f"{cpu_player.name} done thinking, making decision")

    # Check if we should try to go out early
    GolfAI.should_go_out_early(cpu_player, game, profile)

    # Check if we should knock early (flip all remaining cards at once)
    if GolfAI.should_knock_early(game, cpu_player, profile):
        if game.knock_early(cpu_player.id):
            _log_cpu_action(logger, game_id, cpu_player, game,
                            action="knock_early",
                            decision_reason=f"knocked early, revealing {count_hidden(cpu_player)} hidden cards")
            await broadcast_callback()
            return

    # Check if we should use flip-as-action instead of drawing
    flip_action_pos = GolfAI.should_use_flip_action(game, cpu_player, profile)
    if flip_action_pos is not None:
        if game.flip_card_as_action(cpu_player.id, flip_action_pos):
            _log_cpu_action(logger, game_id, cpu_player, game,
                            action="flip_as_action",
                            card=cpu_player.cards[flip_action_pos],
                            position=flip_action_pos,
                            decision_reason=f"used flip-as-action to reveal position {flip_action_pos}")
            await broadcast_callback()
            return

    # Decide whether to draw from discard or deck
    take_discard = GolfAI.should_take_discard(discard_top, cpu_player, profile, game)

    source = "discard" if take_discard else "deck"
    drawn = game.draw_card(cpu_player.id, source)

    if drawn:
        reason = f"took {discard_top.rank.value} from discard" if take_discard else "drew from deck"
        _log_cpu_action(logger, game_id, cpu_player, game,
                        action="take_discard" if take_discard else "draw_deck",
                        card=drawn, decision_reason=reason)

    if not drawn:
        return

    await broadcast_callback()
    await asyncio.sleep(CPU_TIMING["post_draw_settle"])
    consider = CPU_TIMING["post_draw_consider"]
    await asyncio.sleep(consider[0] + random.uniform(0, consider[1] - consider[0]))

    # Decide whether to swap or discard
    swap_pos = GolfAI.choose_swap_or_discard(drawn, cpu_player, profile, game)

    # If drawn from discard, must swap (always enforced)
    if swap_pos is None and game.drawn_from_discard:
        face_down = hidden_positions(cpu_player)
        if face_down:
            safe_positions = filter_bad_pair_positions(face_down, drawn, cpu_player, game.options)
            swap_pos = random.choice(safe_positions)
        else:
            # All cards are face up - find worst card to replace
            worst_pos = 0
            worst_effective_val = -999
            for i, c in enumerate(cpu_player.cards):
                card_val = get_ai_card_value(c, game.options)
                partner_pos = get_column_partner_position(i)
                partner = cpu_player.cards[partner_pos]

                if partner.rank == c.rank:
                    if card_val >= 0 or not game.options.negative_pairs_keep_value:
                        effective_val = -get_ai_card_value(partner, game.options)
                    elif game.options.eagle_eye and c.rank == Rank.JOKER:
                        effective_val = -2
                    else:
                        effective_val = card_val
                else:
                    effective_val = card_val

                if effective_val > worst_effective_val:
                    worst_effective_val = effective_val
                    worst_pos = i
            swap_pos = worst_pos

            drawn_val = get_ai_card_value(drawn, game.options)
            if worst_effective_val < drawn_val:
                logging.warning(
                    f"AI {cpu_player.name} forced to swap good card (value={worst_effective_val}) "
                    f"for bad card {drawn.rank.value} (value={drawn_val})"
                )

    if swap_pos is not None:
        old_card = cpu_player.cards[swap_pos]
        game.swap_card(cpu_player.id, swap_pos)
        _log_cpu_action(logger, game_id, cpu_player, game,
                        action="swap", card=drawn, position=swap_pos,
                        decision_reason=f"swapped {drawn.rank.value} into position {swap_pos}, replaced {old_card.rank.value}")
    else:
        game.discard_drawn(cpu_player.id)
        _log_cpu_action(logger, game_id, cpu_player, game,
                        action="discard", card=drawn,
                        decision_reason=f"discarded {drawn.rank.value}")

        if game.flip_on_discard:
            if game.flip_is_optional:
                if GolfAI.should_skip_optional_flip(cpu_player, profile, game):
                    game.skip_flip_and_end_turn(cpu_player.id)
                    _log_cpu_action(logger, game_id, cpu_player, game,
                                    action="skip_flip",
                                    decision_reason="skipped optional flip (endgame mode)")
                else:
                    flip_pos = GolfAI.choose_flip_after_discard(cpu_player, profile)
                    game.flip_and_end_turn(cpu_player.id, flip_pos)
                    _log_cpu_action(logger, game_id, cpu_player, game,
                                    action="flip", card=cpu_player.cards[flip_pos],
                                    position=flip_pos,
                                    decision_reason=f"flipped card at position {flip_pos} (chose to flip in endgame mode)")
            else:
                flip_pos = GolfAI.choose_flip_after_discard(cpu_player, profile)
                game.flip_and_end_turn(cpu_player.id, flip_pos)
                _log_cpu_action(logger, game_id, cpu_player, game,
                                action="flip", card=cpu_player.cards[flip_pos],
                                position=flip_pos,
                                decision_reason=f"flipped card at position {flip_pos}")

    await broadcast_callback()

    post_action = CPU_TIMING["post_action_pause"]
    await asyncio.sleep(random.uniform(post_action[0], post_action[1]))
