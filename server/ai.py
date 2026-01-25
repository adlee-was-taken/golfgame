"""AI personalities for CPU players in Golf."""

import logging
import random
from dataclasses import dataclass
from typing import Optional
from enum import Enum

from game import Card, Player, Game, GamePhase, GameOptions, RANK_VALUES, Rank


def get_ai_card_value(card: Card, options: GameOptions) -> int:
    """Get card value with house rules applied for AI decisions."""
    if card.rank == Rank.JOKER:
        return -5 if options.lucky_swing else -2
    if card.rank == Rank.KING and options.super_kings:
        return -2
    if card.rank == Rank.SEVEN and options.lucky_sevens:
        return 0
    if card.rank == Rank.TEN and options.ten_penny:
        return 0
    return card.value()


def can_make_pair(card1: Card, card2: Card, options: GameOptions) -> bool:
    """Check if two cards can form a pair (with Queens Wild support)."""
    if card1.rank == card2.rank:
        return True
    if options.queens_wild:
        if card1.rank == Rank.QUEEN or card2.rank == Rank.QUEEN:
            return True
    return False


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


def count_rank_in_hand(player: Player, rank: Rank) -> int:
    """Count how many cards of a given rank the player has visible."""
    return sum(1 for c in player.cards if c.face_up and c.rank == rank)


def has_worse_visible_card(player: Player, card_value: int, options: GameOptions) -> bool:
    """Check if player has a visible card worse than the given value.

    Used to determine if taking a card from discard makes sense -
    we should only take if we have something worse to replace.
    """
    for c in player.cards:
        if c.face_up and get_ai_card_value(c, options) > card_value:
            return True
    return False


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
                        return True
            return True

        if discard_card.rank == Rank.KING:
            return True

        # Auto-take 7s when lucky_sevens enabled (they're worth 0)
        if discard_card.rank == Rank.SEVEN and options.lucky_sevens:
            return True

        # Auto-take 10s when ten_penny enabled (they're worth 0)
        if discard_card.rank == Rank.TEN and options.ten_penny:
            return True

        # Queens Wild: Queen can complete ANY pair
        if options.queens_wild and discard_card.rank == Rank.QUEEN:
            for i, card in enumerate(player.cards):
                if card.face_up:
                    pair_pos = (i + 3) % 6 if i < 3 else i - 3
                    if not player.cards[pair_pos].face_up:
                        # We have an incomplete column - Queen could pair it
                        return True

        # Four of a Kind: If we have 2+ of this rank, consider taking
        if options.four_of_a_kind:
            rank_count = count_rank_in_hand(player, discard_card.rank)
            if rank_count >= 2:
                return True

        # Take card if it could make a column pair (but NOT for negative value cards)
        # Pairing negative cards is bad - you lose the negative benefit
        if discard_value > 0:
            for i, card in enumerate(player.cards):
                pair_pos = (i + 3) % 6 if i < 3 else i - 3
                pair_card = player.cards[pair_pos]

                # Direct rank match
                if card.face_up and card.rank == discard_card.rank and not pair_card.face_up:
                    return True

                # Queens Wild: check if we can pair with Queen
                if options.queens_wild:
                    if card.face_up and can_make_pair(card, discard_card, options) and not pair_card.face_up:
                        return True

        # Take low cards (using house rule adjusted values)
        if discard_value <= 2:
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
                return True

        return False

    @staticmethod
    def choose_swap_or_discard(drawn_card: Card, player: Player,
                                profile: CPUProfile, game: Game) -> Optional[int]:
        """
        Decide whether to swap the drawn card or discard.
        Returns position to swap with, or None to discard.
        """
        options = game.options
        drawn_value = get_ai_card_value(drawn_card, options)

        # Unpredictable players occasionally make surprising play
        # BUT never discard excellent cards (Jokers, 2s, Kings, Aces)
        if random.random() < profile.unpredictability:
            if drawn_value > 1:  # Only be unpredictable with non-excellent cards
                face_down = [i for i, c in enumerate(player.cards) if not c.face_up]
                if face_down and random.random() < 0.5:
                    return random.choice(face_down)

        # Eagle Eye: If drawn card is Joker, look for existing visible Joker to pair
        if options.eagle_eye and drawn_card.rank == Rank.JOKER:
            for i, card in enumerate(player.cards):
                if card.face_up and card.rank == Rank.JOKER:
                    pair_pos = (i + 3) % 6 if i < 3 else i - 3
                    if not player.cards[pair_pos].face_up:
                        return pair_pos

        # Four of a Kind: If we have 3 of this rank and draw the 4th, prioritize keeping
        if options.four_of_a_kind:
            rank_count = count_rank_in_hand(player, drawn_card.rank)
            if rank_count >= 3:
                # We'd have 4 - swap into any face-down spot
                face_down = [i for i, c in enumerate(player.cards) if not c.face_up]
                if face_down:
                    return random.choice(face_down)

        # Check for column pair opportunity first
        # But DON'T pair negative value cards (2s, Jokers) - keeping them unpaired is better!
        # Exception: Eagle Eye makes pairing Jokers GOOD (doubled negative)
        should_pair = drawn_value > 0
        if options.eagle_eye and drawn_card.rank == Rank.JOKER:
            should_pair = True

        if should_pair:
            for i, card in enumerate(player.cards):
                pair_pos = (i + 3) % 6 if i < 3 else i - 3
                pair_card = player.cards[pair_pos]

                # Direct rank match
                if card.face_up and card.rank == drawn_card.rank and not pair_card.face_up:
                    return pair_pos

                if pair_card.face_up and pair_card.rank == drawn_card.rank and not card.face_up:
                    return i

                # Queens Wild: Queen can pair with anything
                if options.queens_wild:
                    if card.face_up and can_make_pair(card, drawn_card, options) and not pair_card.face_up:
                        return pair_pos
                    if pair_card.face_up and can_make_pair(pair_card, drawn_card, options) and not card.face_up:
                        return i

        # Find best swap among face-up cards that are BAD (positive value)
        # Don't swap good cards (Kings, 2s, etc.) just for marginal gains -
        # we want to keep good cards and put new good cards into face-down positions
        best_swap: Optional[int] = None
        best_gain = 0

        for i, card in enumerate(player.cards):
            if card.face_up:
                card_value = get_ai_card_value(card, options)
                # Only consider replacing cards that are actually bad (positive value)
                if card_value > 0:
                    gain = card_value - drawn_value
                    if gain > best_gain:
                        best_gain = gain
                        best_swap = i

        # Swap if we gain points (conservative players need more gain)
        min_gain = 2 if profile.swap_threshold <= 4 else 1
        if best_gain >= min_gain:
            return best_swap

        # Blackjack: Check if any swap would result in exactly 21
        if options.blackjack:
            current_score = player.calculate_score()
            if current_score >= 15:  # Only chase 21 from high scores
                for i, card in enumerate(player.cards):
                    if card.face_up:
                        # Calculate score if we swap here
                        potential_change = drawn_value - get_ai_card_value(card, options)
                        potential_score = current_score + potential_change
                        if potential_score == 21:
                            # Aggressive players more likely to chase 21
                            if random.random() < profile.aggression:
                                return i

        # Consider swapping with face-down cards for very good cards (negative or zero value)
        # 7s (lucky_sevens) and 10s (ten_penny) become "excellent" cards worth keeping
        is_excellent = (drawn_value <= 0 or
                        drawn_card.rank == Rank.ACE or
                        (options.lucky_sevens and drawn_card.rank == Rank.SEVEN) or
                        (options.ten_penny and drawn_card.rank == Rank.TEN))

        if is_excellent:
            face_down = [i for i, c in enumerate(player.cards) if not c.face_up]
            if face_down:
                # Pair hunters might hold out hoping for matches
                if profile.pair_hope > 0.6 and random.random() < profile.pair_hope:
                    return None
                return random.choice(face_down)

        # For medium cards, swap threshold based on profile
        if drawn_value <= profile.swap_threshold:
            face_down = [i for i, c in enumerate(player.cards) if not c.face_up]
            if face_down:
                # Pair hunters hold high cards hoping for matches
                if profile.pair_hope > 0.5 and drawn_value >= 6:
                    if random.random() < profile.pair_hope:
                        return None
                return random.choice(face_down)

        return None

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
    await asyncio.sleep(0.4 + random.uniform(0, 0.4))

    # Decide whether to swap or discard
    swap_pos = GolfAI.choose_swap_or_discard(drawn, cpu_player, profile, game)

    # If drawn from discard, must swap (always enforced)
    if swap_pos is None and game.drawn_from_discard:
        face_down = [i for i, c in enumerate(cpu_player.cards) if not c.face_up]
        if face_down:
            swap_pos = random.choice(face_down)
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
