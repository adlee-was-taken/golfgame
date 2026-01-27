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


# Alias for backwards compatibility - use the centralized function from game.py
def get_ai_card_value(card: Card, options: GameOptions) -> int:
    """Get card value with house rules applied for AI decisions.

    This is an alias for game.get_card_value() for backwards compatibility.
    """
    return get_card_value(card, options)


def can_make_pair(card1: Card, card2: Card) -> bool:
    """Check if two cards can form a pair."""
    return card1.rank == card2.rank


def estimate_opponent_min_score(player: Player, game: Game) -> int:
    """Estimate minimum opponent score from visible cards."""
    min_est = 999
    for p in game.players:
        if p.id == player.id:
            continue
        visible = sum(get_ai_card_value(c, game.options) for c in p.cards if c.face_up)
        hidden = sum(1 for c in p.cards if not c.face_up)
        estimate = visible + int(hidden * 4.5)  # Assume ~4.5 avg for hidden
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

    if avg_hidden >= 4.5:
        return 'early'
    elif avg_hidden >= 2.5:
        return 'mid'
    else:
        return 'late'


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

# Track which profiles are in use
_used_profiles: set[str] = set()
_cpu_profiles: dict[str, CPUProfile] = {}


def get_available_profile() -> Optional[CPUProfile]:
    """Get a random available CPU profile."""
    available = [p for p in CPU_PROFILES if p.name not in _used_profiles]
    if not available:
        return None
    profile = random.choice(available)
    _used_profiles.add(profile.name)
    return profile


def release_profile(name: str):
    """Release a CPU profile back to the pool."""
    _used_profiles.discard(name)
    # Also remove from cpu_profiles by finding the cpu_id with this profile
    to_remove = [cpu_id for cpu_id, profile in _cpu_profiles.items() if profile.name == name]
    for cpu_id in to_remove:
        del _cpu_profiles[cpu_id]


def reset_all_profiles():
    """Reset all profile tracking (for cleanup)."""
    _used_profiles.clear()
    _cpu_profiles.clear()


def get_profile(cpu_id: str) -> Optional[CPUProfile]:
    """Get the profile for a CPU player."""
    return _cpu_profiles.get(cpu_id)


def assign_profile(cpu_id: str) -> Optional[CPUProfile]:
    """Assign a random profile to a CPU player."""
    profile = get_available_profile()
    if profile:
        _cpu_profiles[cpu_id] = profile
    return profile


def assign_specific_profile(cpu_id: str, profile_name: str) -> Optional[CPUProfile]:
    """Assign a specific profile to a CPU player by name."""
    # Check if profile exists and is available
    for profile in CPU_PROFILES:
        if profile.name == profile_name and profile.name not in _used_profiles:
            _used_profiles.add(profile.name)
            _cpu_profiles[cpu_id] = profile
            return profile
    return None


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
        face_down = [i for i, c in enumerate(player.cards) if not c.face_up]
        if len(face_down) == 1:
            # Calculate projected score if we swap into the last face-down position
            projected_score = 0
            for i, c in enumerate(player.cards):
                if i == face_down[0]:
                    projected_score += discard_value
                elif c.face_up:
                    projected_score += get_ai_card_value(c, options)

            # Apply column pair cancellation
            for col in range(3):
                top_idx, bot_idx = col, col + 3
                top_card = discard_card if top_idx == face_down[0] else player.cards[top_idx]
                bot_card = discard_card if bot_idx == face_down[0] else player.cards[bot_idx]
                if top_card.rank == bot_card.rank:
                    top_val = discard_value if top_idx == face_down[0] else get_ai_card_value(player.cards[top_idx], options)
                    bot_val = discard_value if bot_idx == face_down[0] else get_ai_card_value(player.cards[bot_idx], options)
                    projected_score -= (top_val + bot_val)

            # Don't take if score would be terrible
            max_acceptable = 18 if profile.aggression > 0.6 else (16 if profile.aggression > 0.3 else 14)
            ai_log(f"  Go-out check: projected={projected_score}, max_acceptable={max_acceptable}")
            if projected_score > max_acceptable:
                # Exception: still take if it's an excellent card (Joker, 2, King, Ace)
                # and we have a visible bad card to replace instead
                if discard_value >= 0 and discard_card.rank not in (Rank.ACE, Rank.TWO, Rank.KING, Rank.JOKER):
                    ai_log(f"  >> REJECT: would force go-out with {projected_score} pts")
                    return False  # Don't take - would force bad go-out

        # Unpredictable players occasionally make random choice
        # BUT only for reasonable cards (value <= 5) - never randomly take bad cards
        if random.random() < profile.unpredictability:
            if discard_value <= 5:
                return random.choice([True, False])

        # Always take Jokers and Kings (even better with house rules)
        if discard_card.rank == Rank.JOKER:
            # Eagle Eye: If we have a visible Joker, take to pair them (doubled negative!)
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

        # Auto-take 10s when ten_penny enabled (they're worth 1)
        if discard_card.rank == Rank.TEN and options.ten_penny:
            ai_log(f"  >> TAKE: 10 (ten_penny rule)")
            return True

        # Take card if it could make a column pair (but NOT for negative value cards)
        # Pairing negative cards is bad - you lose the negative benefit
        if discard_value > 0:
            for i, card in enumerate(player.cards):
                pair_pos = (i + 3) % 6 if i < 3 else i - 3
                pair_card = player.cards[pair_pos]

                # Direct rank match
                if card.face_up and card.rank == discard_card.rank and not pair_card.face_up:
                    ai_log(f"  >> TAKE: can pair with visible {card.rank.value} at pos {i}")
                    return True

        # Take low cards (using house rule adjusted values)
        # Threshold adjusts by game phase - early game be picky, late game less so
        phase = get_game_phase(game)
        base_threshold = {'early': 2, 'mid': 3, 'late': 4}.get(phase, 2)

        if discard_value <= base_threshold:
            ai_log(f"  >> TAKE: low card (value {discard_value} <= {base_threshold} threshold for {phase} game)")
            return True

        # Calculate end-game pressure from opponents close to going out
        pressure = get_end_game_pressure(player, game)

        # Under pressure, expand what we consider "worth taking"
        # When opponents are close to going out, take decent cards to avoid
        # getting stuck with unknown bad cards when the round ends
        if pressure > 0.2:
            # Scale threshold: at pressure 0.2 take 4s, at 0.5+ take 6s
            pressure_threshold = 3 + int(pressure * 6)  # 4 to 9 based on pressure
            pressure_threshold = min(pressure_threshold, 7)  # Cap at 7
            if discard_value <= pressure_threshold:
                # Only take if we have hidden cards that could be worse
                my_hidden = sum(1 for c in player.cards if not c.face_up)
                if my_hidden > 0:
                    ai_log(f"  >> TAKE: pressure={pressure:.2f}, threshold={pressure_threshold}")
                    return True

        # Check if we have cards worse than the discard
        worst_visible = -999
        for card in player.cards:
            if card.face_up:
                worst_visible = max(worst_visible, get_ai_card_value(card, options))

        if worst_visible > discard_value + 1:
            # Sanity check: only take if we actually have something worse to replace
            # This prevents taking a bad card when all visible cards are better
            if has_worse_visible_card(player, discard_value, options):
                ai_log(f"  >> TAKE: have worse visible card ({worst_visible})")
                return True

        ai_log(f"  >> PASS: drawing from deck instead")
        return False

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
        current_card = player.cards[pos]
        partner_pos = get_column_partner_position(pos)
        partner_card = player.cards[partner_pos]

        score = 0.0

        # Personality-based weight modifiers
        # pair_hope: 0.0-1.0, affects how much we value pairing vs spreading
        pair_weight = 1.0 + profile.pair_hope  # Range: 1.0 to 2.0
        spread_weight = 2.0 - profile.pair_hope  # Range: 1.0 to 2.0 (inverse)

        # 1. PAIR BONUS - Creating a pair
        #    pair_hope affects how much we value this
        if partner_card.face_up and partner_card.rank == drawn_card.rank:
            partner_value = get_ai_card_value(partner_card, options)

            if drawn_value >= 0:
                # Good pair! Both cards cancel to 0
                pair_bonus = drawn_value + partner_value
                score += pair_bonus * pair_weight  # Pair hunters value this more
            else:
                # Pairing negative cards
                if options.eagle_eye and drawn_card.rank == Rank.JOKER:
                    score += 8 * pair_weight  # Eagle Eye Joker pairs = -4
                elif options.negative_pairs_keep_value:
                    # Negative Pairs Keep Value: pairing 2s/Jokers is NOW good!
                    # Pair of 2s = -4, pair of Jokers = -4 (instead of 0)
                    pair_benefit = abs(drawn_value + partner_value)
                    score += pair_benefit * pair_weight
                    ai_log(f"    Negative pair keep value bonus: +{pair_benefit * pair_weight:.1f}")
                else:
                    # Standard rules: penalty for wasting negative cards
                    penalty = abs(drawn_value) * 2 * (2.0 - profile.pair_hope)
                    score -= penalty

        # 1b. SPREAD BONUS - Not pairing good cards (spreading them out)
        #     Players with low pair_hope prefer spreading aces/2s across columns
        if not partner_card.face_up or partner_card.rank != drawn_card.rank:
            if drawn_value <= 1:  # Excellent cards (K, 2, A, Joker)
                # Small bonus for spreading - scales with spread preference
                score += spread_weight * 0.5

        # 2. POINT GAIN - Direct value improvement
        if current_card.face_up:
            current_value = get_ai_card_value(current_card, options)
            point_gain = current_value - drawn_value
            score += point_gain
        else:
            # Hidden card - expected value ~4.5
            expected_hidden = 4.5
            point_gain = expected_hidden - drawn_value
            # Conservative players (low swap_threshold) discount uncertain gains more
            discount = 0.5 + (profile.swap_threshold / 16)  # Range: 0.5 to 1.0
            score += point_gain * discount

        # 3. REVEAL BONUS - Value of revealing hidden cards
        #    More aggressive players want to reveal faster to go out
        if not current_card.face_up:
            hidden_count = sum(1 for c in player.cards if not c.face_up)
            reveal_bonus = min(hidden_count, 4)

            # Aggressive players get bigger reveal bonus (want to go out faster)
            aggression_multiplier = 0.8 + profile.aggression * 0.4  # Range: 0.8 to 1.2

            # Scale by card quality
            if drawn_value <= 0:  # Excellent
                score += reveal_bonus * 1.2 * aggression_multiplier
            elif drawn_value == 1:  # Great
                score += reveal_bonus * 1.0 * aggression_multiplier
            elif drawn_value <= 4:  # Good
                score += reveal_bonus * 0.6 * aggression_multiplier
            elif drawn_value <= 6:  # Medium
                score += reveal_bonus * 0.3 * aggression_multiplier
            # Bad cards: no reveal bonus

        # 4. FUTURE PAIR POTENTIAL
        #    Pair hunters value positions where both cards are hidden
        if not current_card.face_up and not partner_card.face_up:
            pair_viability = get_pair_viability(drawn_card.rank, game)
            score += pair_viability * pair_weight * 0.5

        # 4b. FOUR OF A KIND PURSUIT
        #     When four_of_a_kind rule is enabled, boost score for collecting 3rd/4th card
        if options.four_of_a_kind:
            # Count how many of this rank player already has visible (excluding current position)
            rank_count = sum(
                1 for i, c in enumerate(player.cards)
                if c.face_up and c.rank == drawn_card.rank and i != pos
            )
            if rank_count >= 2:
                # Already have 2+ of this rank, getting more is great for 4-of-a-kind
                four_kind_bonus = rank_count * 4  # 8 for 2 cards, 12 for 3 cards
                score += four_kind_bonus
                ai_log(f"    Four-of-a-kind pursuit bonus: +{four_kind_bonus}")

        # 5. GO-OUT SAFETY - Penalty for going out with bad score
        face_down_positions = [i for i, c in enumerate(player.cards) if not c.face_up]
        if len(face_down_positions) == 1 and pos == face_down_positions[0]:
            projected_score = drawn_value
            for i, c in enumerate(player.cards):
                if i != pos and c.face_up:
                    projected_score += get_ai_card_value(c, options)

            # Apply pair cancellation
            for col in range(3):
                top_idx, bot_idx = col, col + 3
                top_card = drawn_card if top_idx == pos else player.cards[top_idx]
                bot_card = drawn_card if bot_idx == pos else player.cards[bot_idx]
                if top_card.rank == bot_card.rank:
                    top_val = drawn_value if top_idx == pos else get_ai_card_value(player.cards[top_idx], options)
                    bot_val = drawn_value if bot_idx == pos else get_ai_card_value(player.cards[bot_idx], options)
                    projected_score -= (top_val + bot_val)

            # Aggressive players accept higher scores when going out
            max_acceptable = 12 + int(profile.aggression * 8)  # Range: 12 to 20
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

        ai_log(f"=== {profile.name} deciding: drew {drawn_card.rank.value}{drawn_card.suit.value} (value={drawn_value}) ===")
        ai_log(f"  Personality: pair_hope={profile.pair_hope:.2f}, aggression={profile.aggression:.2f}, "
               f"swap_threshold={profile.swap_threshold}, unpredictability={profile.unpredictability:.2f}")

        # Log current hand state
        hand_str = " ".join(
            f"[{i}:{c.rank.value if c.face_up else '?'}]" for i, c in enumerate(player.cards)
        )
        ai_log(f"  Hand: {hand_str}")

        # Unpredictable players occasionally make surprising plays
        # But never discard excellent cards (Jokers, 2s, Kings, Aces)
        if random.random() < profile.unpredictability:
            if drawn_value > 1:
                face_down = [i for i, c in enumerate(player.cards) if not c.face_up]
                if face_down and random.random() < 0.5:
                    choice = random.choice(face_down)
                    ai_log(f"  >> UNPREDICTABLE: randomly chose position {choice}")
                    return choice

        # Calculate score for each position
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

        # Filter to positive scores only
        positive_scores = [(p, s) for p, s in position_scores if s > 0]

        best_pos: Optional[int] = None
        best_score = 0.0

        if positive_scores:
            # Sort by score descending
            positive_scores.sort(key=lambda x: x[1], reverse=True)
            best_pos, best_score = positive_scores[0]

            # PERSONALITY TIE-BREAKER: When top options are close, let personality decide
            close_threshold = 2.0  # Options within 2 points are "close"
            close_options = [(p, s) for p, s in positive_scores if s >= best_score - close_threshold]

            if len(close_options) > 1:
                ai_log(f"  TIE-BREAKER: {len(close_options)} options within {close_threshold} pts of best ({best_score:.2f})")
                original_best = best_pos

                # Multiple close options - personality decides
                # Categorize each option
                for pos, score in close_options:
                    partner_pos = get_column_partner_position(pos)
                    partner_card = player.cards[partner_pos]
                    is_pair_move = partner_card.face_up and partner_card.rank == drawn_card.rank
                    is_reveal_move = not player.cards[pos].face_up

                    # Pair hunters prefer pair moves
                    if is_pair_move and profile.pair_hope > 0.6:
                        ai_log(f"    >> PAIR_HOPE ({profile.pair_hope:.2f}): chose pair move at pos {pos}")
                        best_pos = pos
                        break
                    # Aggressive players prefer reveal moves (to go out faster)
                    if is_reveal_move and profile.aggression > 0.7:
                        ai_log(f"    >> AGGRESSION ({profile.aggression:.2f}): chose reveal move at pos {pos}")
                        best_pos = pos
                        break
                    # Conservative players prefer safe visible card replacements
                    if not is_reveal_move and profile.swap_threshold <= 4:
                        ai_log(f"    >> CONSERVATIVE (threshold={profile.swap_threshold}): chose safe move at pos {pos}")
                        best_pos = pos
                        break

                # If still tied, add small random factor based on unpredictability
                if profile.unpredictability > 0.1 and random.random() < profile.unpredictability:
                    best_pos = random.choice([p for p, s in close_options])
                    ai_log(f"    >> RANDOM (unpredictability={profile.unpredictability:.2f}): chose pos {best_pos}")

                if best_pos != original_best:
                    ai_log(f"  Tie-breaker changed choice: {original_best} -> {best_pos}")

        # Blackjack special case: chase exactly 21
        if options.blackjack and best_pos is None:
            current_score = player.calculate_score()
            if current_score >= 15:
                for i, card in enumerate(player.cards):
                    if card.face_up:
                        potential_change = drawn_value - get_ai_card_value(card, options)
                        if current_score + potential_change == 21:
                            if random.random() < profile.aggression:
                                ai_log(f"  >> BLACKJACK: chasing 21 at position {i}")
                                return i

        # Pair hunters might hold medium cards hoping for matches
        if best_pos is not None and not player.cards[best_pos].face_up:
            if drawn_value >= 5:  # Only hold out for medium/high cards
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

        # Log final decision
        if best_pos is not None:
            target_card = player.cards[best_pos]
            target_str = target_card.rank.value if target_card.face_up else "hidden"
            ai_log(f"  DECISION: SWAP into position {best_pos} (replacing {target_str}) [score={best_score:.2f}]")
        else:
            ai_log(f"  DECISION: DISCARD {drawn_card.rank.value} (no good swap options)")

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
        expected_hidden_total = len(face_down) * 4.5
        projected_score = visible_score + expected_hidden_total

        # More aggressive players accept higher risk
        max_acceptable = 8 + int(profile.aggression * 10)  # Range: 8 to 18

        if projected_score <= max_acceptable:
            # Add some randomness based on aggression
            knock_chance = profile.aggression * 0.4  # Max 40% for most aggressive
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
        if options.blackjack and estimated_score == 21:
            return True

        # Base threshold based on aggression
        go_out_threshold = 8 if profile.aggression > 0.7 else (12 if profile.aggression > 0.4 else 16)

        # Knock Bonus (-5 for going out): Can afford to go out with higher score
        if options.knock_bonus:
            go_out_threshold += 5

        # Knock Penalty (+10 if not lowest): Need to be confident we're lowest
        if options.knock_penalty:
            opponent_min = estimate_opponent_min_score(player, game)
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

        if estimated_score <= go_out_threshold:
            if random.random() < profile.aggression:
                return True

        return False


async def process_cpu_turn(
    game: Game, cpu_player: Player, broadcast_callback, game_id: Optional[str] = None
) -> None:
    """Process a complete turn for a CPU player."""
    import asyncio
    from game_log import get_logger

    profile = get_profile(cpu_player.id)
    if not profile:
        # Fallback to balanced profile
        profile = CPUProfile("CPU", "Balanced", 5, 0.4, 0.5, 0.1)

    # Get logger if game_id provided
    logger = get_logger() if game_id else None

    # Add delay based on unpredictability (chaotic players are faster/slower)
    delay = 0.8 + random.uniform(0, 0.5)
    if profile.unpredictability > 0.2:
        delay = random.uniform(0.3, 1.2)
    await asyncio.sleep(delay)

    # Check if we should try to go out early
    GolfAI.should_go_out_early(cpu_player, game, profile)

    # Check if we should knock early (flip all remaining cards at once)
    if GolfAI.should_knock_early(game, cpu_player, profile):
        if game.knock_early(cpu_player.id):
            # Log knock early
            if logger and game_id:
                face_down_count = sum(1 for c in cpu_player.cards if not c.face_up)
                logger.log_move(
                    game_id=game_id,
                    player=cpu_player,
                    is_cpu=True,
                    action="knock_early",
                    card=None,
                    game=game,
                    decision_reason=f"knocked early, revealing {face_down_count} hidden cards",
                )
            await broadcast_callback()
            return  # Turn is over

    # Check if we should use flip-as-action instead of drawing
    flip_action_pos = GolfAI.should_use_flip_action(game, cpu_player, profile)
    if flip_action_pos is not None:
        if game.flip_card_as_action(cpu_player.id, flip_action_pos):
            # Log flip-as-action
            if logger and game_id:
                flipped_card = cpu_player.cards[flip_action_pos]
                logger.log_move(
                    game_id=game_id,
                    player=cpu_player,
                    is_cpu=True,
                    action="flip_as_action",
                    card=flipped_card,
                    position=flip_action_pos,
                    game=game,
                    decision_reason=f"used flip-as-action to reveal position {flip_action_pos}",
                )
            await broadcast_callback()
            return  # Turn is over

    # Decide whether to draw from discard or deck
    discard_top = game.discard_top()
    take_discard = GolfAI.should_take_discard(discard_top, cpu_player, profile, game)

    source = "discard" if take_discard else "deck"
    drawn = game.draw_card(cpu_player.id, source)

    # Log draw decision
    if logger and game_id and drawn:
        reason = f"took {discard_top.rank.value} from discard" if take_discard else "drew from deck"
        logger.log_move(
            game_id=game_id,
            player=cpu_player,
            is_cpu=True,
            action="take_discard" if take_discard else "draw_deck",
            card=drawn,
            game=game,
            decision_reason=reason,
        )

    if not drawn:
        return

    await broadcast_callback()
    # Brief pause after draw to let the flash animation register visually
    await asyncio.sleep(0.08)
    await asyncio.sleep(0.35 + random.uniform(0, 0.35))

    # Decide whether to swap or discard
    swap_pos = GolfAI.choose_swap_or_discard(drawn, cpu_player, profile, game)

    # If drawn from discard, must swap (always enforced)
    if swap_pos is None and game.drawn_from_discard:
        face_down = [i for i, c in enumerate(cpu_player.cards) if not c.face_up]
        if face_down:
            # Filter out positions that would create bad pairs with negative cards
            safe_positions = filter_bad_pair_positions(face_down, drawn, cpu_player, game.options)
            swap_pos = random.choice(safe_positions)
        else:
            # All cards are face up - find worst card to replace (using house rules)
            worst_pos = 0
            worst_val = -999
            for i, c in enumerate(cpu_player.cards):
                card_val = get_ai_card_value(c, game.options)  # Apply house rules
                if card_val > worst_val:
                    worst_val = card_val
                    worst_pos = i
            swap_pos = worst_pos

            # Sanity check: warn if we're swapping out a good card for a bad one
            drawn_val = get_ai_card_value(drawn, game.options)
            if worst_val < drawn_val:
                logging.warning(
                    f"AI {cpu_player.name} forced to swap good card (value={worst_val}) "
                    f"for bad card {drawn.rank.value} (value={drawn_val})"
                )

    if swap_pos is not None:
        old_card = cpu_player.cards[swap_pos]  # Card being replaced
        game.swap_card(cpu_player.id, swap_pos)

        # Log swap decision
        if logger and game_id:
            logger.log_move(
                game_id=game_id,
                player=cpu_player,
                is_cpu=True,
                action="swap",
                card=drawn,
                position=swap_pos,
                game=game,
                decision_reason=f"swapped {drawn.rank.value} into position {swap_pos}, replaced {old_card.rank.value}",
            )
    else:
        game.discard_drawn(cpu_player.id)

        # Log discard decision
        if logger and game_id:
            logger.log_move(
                game_id=game_id,
                player=cpu_player,
                is_cpu=True,
                action="discard",
                card=drawn,
                game=game,
                decision_reason=f"discarded {drawn.rank.value}",
            )

        if game.flip_on_discard:
            # Check if flip is optional (endgame mode) and decide whether to skip
            if game.flip_is_optional:
                if GolfAI.should_skip_optional_flip(cpu_player, profile, game):
                    game.skip_flip_and_end_turn(cpu_player.id)

                    # Log skip decision
                    if logger and game_id:
                        logger.log_move(
                            game_id=game_id,
                            player=cpu_player,
                            is_cpu=True,
                            action="skip_flip",
                            card=None,
                            game=game,
                            decision_reason="skipped optional flip (endgame mode)",
                        )
                else:
                    # Choose to flip
                    flip_pos = GolfAI.choose_flip_after_discard(cpu_player, profile)
                    game.flip_and_end_turn(cpu_player.id, flip_pos)

                    # Log flip decision
                    if logger and game_id:
                        flipped_card = cpu_player.cards[flip_pos]
                        logger.log_move(
                            game_id=game_id,
                            player=cpu_player,
                            is_cpu=True,
                            action="flip",
                            card=flipped_card,
                            position=flip_pos,
                            game=game,
                            decision_reason=f"flipped card at position {flip_pos} (chose to flip in endgame mode)",
                        )
            else:
                # Mandatory flip (always mode)
                flip_pos = GolfAI.choose_flip_after_discard(cpu_player, profile)
                game.flip_and_end_turn(cpu_player.id, flip_pos)

                # Log flip decision
                if logger and game_id:
                    flipped_card = cpu_player.cards[flip_pos]
                    logger.log_move(
                        game_id=game_id,
                        player=cpu_player,
                        is_cpu=True,
                        action="flip",
                        card=flipped_card,
                        position=flip_pos,
                        game=game,
                        decision_reason=f"flipped card at position {flip_pos}",
                    )

    await broadcast_callback()
