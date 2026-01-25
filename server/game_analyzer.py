"""
Game Analyzer for 6-Card Golf AI decisions.

Evaluates AI decisions against optimal play baselines and generates
reports on decision quality, mistake rates, and areas for improvement.
"""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from enum import Enum

from game import Rank, RANK_VALUES, GameOptions
from constants import get_card_value_for_rank


# =============================================================================
# Card Value Utilities
# =============================================================================

def get_card_value(rank: str, options: Optional[dict] = None) -> int:
    """Get point value for a card rank string.

    This is a wrapper around constants.get_card_value_for_rank() for
    backwards compatibility with existing analyzer code.
    """
    return get_card_value_for_rank(rank, options)


def rank_quality(rank: str, options: Optional[dict] = None) -> str:
    """Categorize a card as excellent, good, neutral, bad, or terrible."""
    value = get_card_value(rank, options)
    if value <= -2:
        return "excellent"  # Jokers, 2s
    if value <= 0:
        return "good"  # Kings (or lucky 7s, ten_penny 10s)
    if value <= 2:
        return "decent"  # Aces, 2s without special rules
    if value <= 5:
        return "neutral"  # 3-5
    if value <= 7:
        return "bad"  # 6-7
    return "terrible"  # 8-10, J, Q


# =============================================================================
# Decision Classification
# =============================================================================

class DecisionQuality(Enum):
    """Classification of decision quality."""
    OPTIMAL = "optimal"      # Best possible decision
    GOOD = "good"            # Reasonable decision, minor suboptimality
    QUESTIONABLE = "questionable"  # Debatable, might be personality-driven
    MISTAKE = "mistake"      # Clear suboptimal play (2-5 point cost)
    BLUNDER = "blunder"      # Severe error (5+ point cost)


@dataclass
class DecisionAnalysis:
    """Analysis of a single decision."""
    move_id: int
    action: str
    card_rank: Optional[str]
    position: Optional[int]
    quality: DecisionQuality
    expected_value: float  # EV impact of this decision
    reasoning: str
    optimal_play: Optional[str] = None  # What should have been done


@dataclass
class GameSummary:
    """Summary analysis of a complete game."""
    game_id: str
    player_name: str
    total_decisions: int
    optimal_count: int
    good_count: int
    questionable_count: int
    mistake_count: int
    blunder_count: int
    total_ev_lost: float  # Points "left on table"
    decisions: list[DecisionAnalysis]

    @property
    def accuracy(self) -> float:
        """Percentage of optimal/good decisions."""
        if self.total_decisions == 0:
            return 100.0
        return (self.optimal_count + self.good_count) / self.total_decisions * 100

    @property
    def mistake_rate(self) -> float:
        """Percentage of mistakes + blunders."""
        if self.total_decisions == 0:
            return 0.0
        return (self.mistake_count + self.blunder_count) / self.total_decisions * 100


# =============================================================================
# Decision Evaluators
# =============================================================================

class DecisionEvaluator:
    """Evaluates individual decisions against optimal play."""

    def __init__(self, options: Optional[dict] = None):
        self.options = options or {}

    def evaluate_take_discard(
        self,
        discard_rank: str,
        hand: list[dict],
        took_discard: bool
    ) -> DecisionAnalysis:
        """
        Evaluate decision to take from discard vs draw from deck.

        Optimal play:
        - Always take: Jokers, Kings, 2s
        - Take if: Value < worst visible card
        - Don't take: High cards (8+) with good hand
        """
        discard_value = get_card_value(discard_rank, self.options)
        discard_qual = rank_quality(discard_rank, self.options)

        # Find worst visible card in hand
        visible_cards = [c for c in hand if c.get('face_up')]
        worst_visible_value = max(
            (get_card_value(c['rank'], self.options) for c in visible_cards),
            default=5  # Assume average if no visible
        )

        # Determine if taking was correct
        should_take = False
        reasoning = ""

        # Auto-take excellent cards
        if discard_qual == "excellent":
            should_take = True
            reasoning = f"{discard_rank} is excellent (value={discard_value}), always take"
        # Auto-take good cards
        elif discard_qual == "good":
            should_take = True
            reasoning = f"{discard_rank} is good (value={discard_value}), should take"
        # Take if better than worst visible
        elif discard_value < worst_visible_value - 1:
            should_take = True
            reasoning = f"{discard_rank} ({discard_value}) better than worst visible ({worst_visible_value})"
        # Don't take bad cards
        elif discard_qual in ("bad", "terrible"):
            should_take = False
            reasoning = f"{discard_rank} is {discard_qual} (value={discard_value}), should not take"
        else:
            # Neutral - personality can influence
            should_take = None  # Either is acceptable
            reasoning = f"{discard_rank} is neutral, either choice reasonable"

        # Evaluate the actual decision
        if should_take is None:
            quality = DecisionQuality.GOOD
            ev = 0
        elif took_discard == should_take:
            quality = DecisionQuality.OPTIMAL
            ev = 0
        else:
            # Wrong decision
            if discard_qual == "excellent" and not took_discard:
                quality = DecisionQuality.BLUNDER
                ev = -abs(discard_value)  # Lost opportunity
                reasoning = f"Failed to take {discard_rank} - significant missed opportunity"
            elif discard_qual == "terrible" and took_discard:
                quality = DecisionQuality.BLUNDER
                ev = discard_value - 5  # Expected deck draw ~5
                reasoning = f"Took terrible card {discard_rank} when should have drawn from deck"
            elif discard_qual == "good" and not took_discard:
                quality = DecisionQuality.MISTAKE
                ev = -2
                reasoning = f"Missed good card {discard_rank}"
            elif discard_qual == "bad" and took_discard:
                quality = DecisionQuality.MISTAKE
                ev = discard_value - 5
                reasoning = f"Took bad card {discard_rank}"
            else:
                quality = DecisionQuality.QUESTIONABLE
                ev = -1
                reasoning = f"Suboptimal choice with {discard_rank}"

        return DecisionAnalysis(
            move_id=0,
            action="take_discard" if took_discard else "draw_deck",
            card_rank=discard_rank,
            position=None,
            quality=quality,
            expected_value=ev,
            reasoning=reasoning,
            optimal_play="take" if should_take else "draw" if should_take is False else "either"
        )

    def evaluate_swap(
        self,
        drawn_rank: str,
        hand: list[dict],
        swapped: bool,
        swap_position: Optional[int],
        was_from_discard: bool
    ) -> DecisionAnalysis:
        """
        Evaluate swap vs discard decision.

        Optimal play:
        - Swap excellent cards into face-down positions
        - Swap if drawn card better than position card
        - Don't discard good cards
        """
        drawn_value = get_card_value(drawn_rank, self.options)
        drawn_qual = rank_quality(drawn_rank, self.options)

        # If from discard, must swap - evaluate position choice
        if was_from_discard and not swapped:
            # This shouldn't happen per rules
            return DecisionAnalysis(
                move_id=0,
                action="invalid",
                card_rank=drawn_rank,
                position=swap_position,
                quality=DecisionQuality.BLUNDER,
                expected_value=-10,
                reasoning="Must swap when drawing from discard",
                optimal_play="swap"
            )

        if not swapped:
            # Discarded the drawn card
            if drawn_qual == "excellent":
                return DecisionAnalysis(
                    move_id=0,
                    action="discard",
                    card_rank=drawn_rank,
                    position=None,
                    quality=DecisionQuality.BLUNDER,
                    expected_value=abs(drawn_value) + 5,  # Lost value + avg replacement
                    reasoning=f"Discarded excellent card {drawn_rank}!",
                    optimal_play="swap into face-down"
                )
            elif drawn_qual == "good":
                return DecisionAnalysis(
                    move_id=0,
                    action="discard",
                    card_rank=drawn_rank,
                    position=None,
                    quality=DecisionQuality.MISTAKE,
                    expected_value=3,
                    reasoning=f"Discarded good card {drawn_rank}",
                    optimal_play="swap into face-down"
                )
            else:
                # Discarding neutral/bad card is fine
                return DecisionAnalysis(
                    move_id=0,
                    action="discard",
                    card_rank=drawn_rank,
                    position=None,
                    quality=DecisionQuality.OPTIMAL,
                    expected_value=0,
                    reasoning=f"Correctly discarded {drawn_qual} card {drawn_rank}",
                )

        # Swapped - evaluate position choice
        if swap_position is not None and 0 <= swap_position < len(hand):
            replaced_card = hand[swap_position]
            if replaced_card.get('face_up'):
                replaced_rank = replaced_card.get('rank', '?')
                replaced_value = get_card_value(replaced_rank, self.options)
                ev_change = replaced_value - drawn_value

                if ev_change > 0:
                    quality = DecisionQuality.OPTIMAL
                    reasoning = f"Good swap: {drawn_rank} ({drawn_value}) for {replaced_rank} ({replaced_value})"
                elif ev_change < -3:
                    quality = DecisionQuality.MISTAKE
                    reasoning = f"Bad swap: lost {-ev_change} points swapping {replaced_rank} for {drawn_rank}"
                elif ev_change < 0:
                    quality = DecisionQuality.QUESTIONABLE
                    reasoning = f"Marginal swap: {drawn_rank} for {replaced_rank}"
                else:
                    quality = DecisionQuality.GOOD
                    reasoning = f"Neutral swap: {drawn_rank} for {replaced_rank}"

                return DecisionAnalysis(
                    move_id=0,
                    action="swap",
                    card_rank=drawn_rank,
                    position=swap_position,
                    quality=quality,
                    expected_value=ev_change,
                    reasoning=reasoning,
                )
            else:
                # Swapped into face-down - generally good for good cards
                if drawn_qual in ("excellent", "good", "decent"):
                    return DecisionAnalysis(
                        move_id=0,
                        action="swap",
                        card_rank=drawn_rank,
                        position=swap_position,
                        quality=DecisionQuality.OPTIMAL,
                        expected_value=5 - drawn_value,  # vs expected ~5 hidden
                        reasoning=f"Good: swapped {drawn_rank} into unknown position",
                    )
                else:
                    return DecisionAnalysis(
                        move_id=0,
                        action="swap",
                        card_rank=drawn_rank,
                        position=swap_position,
                        quality=DecisionQuality.QUESTIONABLE,
                        expected_value=0,
                        reasoning=f"Risky: swapped {drawn_qual} card {drawn_rank} into unknown",
                    )

        return DecisionAnalysis(
            move_id=0,
            action="swap",
            card_rank=drawn_rank,
            position=swap_position,
            quality=DecisionQuality.GOOD,
            expected_value=0,
            reasoning="Swap decision",
        )


# =============================================================================
# Game Analyzer
# =============================================================================

class GameAnalyzer:
    """Analyzes logged games for decision quality."""

    def __init__(self, db_path: str = "games.db"):
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {db_path}")

    def get_game_options(self, game_id: str) -> Optional[dict]:
        """Load game options from database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT options_json FROM games WHERE id = ?",
                (game_id,)
            )
            row = cursor.fetchone()
            if row and row[0]:
                return json.loads(row[0])
        return None

    def get_player_moves(self, game_id: str, player_name: str) -> list[dict]:
        """Get all moves for a player in a game."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM moves
                WHERE game_id = ? AND player_name = ?
                ORDER BY move_number
            """, (game_id, player_name))
            return [dict(row) for row in cursor.fetchall()]

    def analyze_player_game(self, game_id: str, player_name: str) -> GameSummary:
        """Analyze all decisions made by a player in a game."""
        options = self.get_game_options(game_id)
        moves = self.get_player_moves(game_id, player_name)
        evaluator = DecisionEvaluator(options)

        decisions = []
        draw_context = None  # Track the draw for evaluating subsequent swap

        for move in moves:
            action = move['action']
            card_rank = move['card_rank']
            position = move['position']
            hand = json.loads(move['hand_json']) if move['hand_json'] else []
            discard_top = json.loads(move['discard_top_json']) if move['discard_top_json'] else None

            if action in ('take_discard', 'draw_deck'):
                # Evaluate draw decision
                if discard_top:
                    analysis = evaluator.evaluate_take_discard(
                        discard_rank=discard_top.get('rank', '?'),
                        hand=hand,
                        took_discard=(action == 'take_discard')
                    )
                    analysis.move_id = move['id']
                    decisions.append(analysis)

                # Store context for swap evaluation
                draw_context = {
                    'rank': card_rank,
                    'from_discard': action == 'take_discard',
                    'hand': hand
                }

            elif action == 'swap':
                if draw_context:
                    analysis = evaluator.evaluate_swap(
                        drawn_rank=draw_context['rank'],
                        hand=draw_context['hand'],
                        swapped=True,
                        swap_position=position,
                        was_from_discard=draw_context['from_discard']
                    )
                    analysis.move_id = move['id']
                    decisions.append(analysis)
                    draw_context = None

            elif action == 'discard':
                if draw_context:
                    analysis = evaluator.evaluate_swap(
                        drawn_rank=draw_context['rank'],
                        hand=draw_context['hand'],
                        swapped=False,
                        swap_position=None,
                        was_from_discard=draw_context['from_discard']
                    )
                    analysis.move_id = move['id']
                    decisions.append(analysis)
                    draw_context = None

        # Tally results
        counts = {q: 0 for q in DecisionQuality}
        total_ev_lost = 0.0

        for d in decisions:
            counts[d.quality] += 1
            if d.expected_value < 0:
                total_ev_lost += abs(d.expected_value)

        return GameSummary(
            game_id=game_id,
            player_name=player_name,
            total_decisions=len(decisions),
            optimal_count=counts[DecisionQuality.OPTIMAL],
            good_count=counts[DecisionQuality.GOOD],
            questionable_count=counts[DecisionQuality.QUESTIONABLE],
            mistake_count=counts[DecisionQuality.MISTAKE],
            blunder_count=counts[DecisionQuality.BLUNDER],
            total_ev_lost=total_ev_lost,
            decisions=decisions
        )

    def find_blunders(self, limit: int = 20) -> list[dict]:
        """Find all blunders across all games."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT m.*, g.room_code
                FROM moves m
                JOIN games g ON m.game_id = g.id
                WHERE m.is_cpu = 1
                ORDER BY m.timestamp DESC
                LIMIT ?
            """, (limit * 10,))  # Get more, then filter

            blunders = []
            options_cache = {}

            for row in cursor:
                move = dict(row)
                game_id = move['game_id']

                # Cache options lookup
                if game_id not in options_cache:
                    options_cache[game_id] = self.get_game_options(game_id)

                options = options_cache[game_id]
                card_rank = move['card_rank']

                if not card_rank:
                    continue

                # Check for obvious blunders
                quality = rank_quality(card_rank, options)
                action = move['action']

                is_blunder = False
                reason = ""

                if action == 'discard' and quality in ('excellent', 'good'):
                    is_blunder = True
                    reason = f"Discarded {quality} card {card_rank}"
                elif action == 'take_discard' and quality == 'terrible':
                    # Check if this was for pairing - that's smart play!
                    hand = json.loads(move['hand_json']) if move['hand_json'] else []
                    card_value = get_card_value(card_rank, options)

                    has_matching_visible = any(
                        c.get('rank') == card_rank and c.get('face_up')
                        for c in hand
                    )

                    # Also check if player has worse visible cards (taking to swap is smart)
                    has_worse_visible = any(
                        c.get('face_up') and get_card_value(c.get('rank', '?'), options) > card_value
                        for c in hand
                    )

                    if has_matching_visible:
                        # Taking to pair - this is good play, not a blunder
                        pass
                    elif has_worse_visible:
                        # Taking to swap for a worse card - reasonable play
                        pass
                    else:
                        is_blunder = True
                        reason = f"Took terrible card {card_rank} with no improvement path"

                if is_blunder:
                    blunders.append({
                        **move,
                        'blunder_reason': reason
                    })

                    if len(blunders) >= limit:
                        break

            return blunders


# =============================================================================
# Report Generation
# =============================================================================

def generate_player_report(summary: GameSummary) -> str:
    """Generate a text report for a player's game performance."""
    lines = [
        f"=== Decision Analysis: {summary.player_name} ===",
        f"Game: {summary.game_id[:8]}...",
        f"",
        f"Total Decisions: {summary.total_decisions}",
        f"Accuracy: {summary.accuracy:.1f}%",
        f"",
        f"Breakdown:",
        f"  Optimal:      {summary.optimal_count}",
        f"  Good:         {summary.good_count}",
        f"  Questionable: {summary.questionable_count}",
        f"  Mistakes:     {summary.mistake_count}",
        f"  Blunders:     {summary.blunder_count}",
        f"",
        f"Points Lost to Errors: {summary.total_ev_lost:.1f}",
        f"",
    ]

    # List specific issues
    issues = [d for d in summary.decisions
              if d.quality in (DecisionQuality.MISTAKE, DecisionQuality.BLUNDER)]

    if issues:
        lines.append("Issues Found:")
        for d in issues:
            marker = "!!!" if d.quality == DecisionQuality.BLUNDER else "!"
            lines.append(f"  {marker} {d.reasoning}")

    return "\n".join(lines)


def print_blunder_report(blunders: list[dict]):
    """Print a report of found blunders."""
    print(f"\n=== Blunder Report ({len(blunders)} found) ===\n")

    for b in blunders:
        print(f"Player: {b['player_name']}")
        print(f"Action: {b['action']} {b['card_rank']}")
        print(f"Reason: {b['blunder_reason']}")
        print(f"Room: {b.get('room_code', 'N/A')}")
        print("-" * 40)


# =============================================================================
# CLI Interface
# =============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python game_analyzer.py blunders [limit]")
        print("  python game_analyzer.py game <game_id> <player_name>")
        print("  python game_analyzer.py summary")
        sys.exit(1)

    command = sys.argv[1]

    try:
        analyzer = GameAnalyzer()
    except FileNotFoundError:
        print("No games.db found. Play some games first!")
        sys.exit(1)

    if command == "blunders":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        blunders = analyzer.find_blunders(limit)
        print_blunder_report(blunders)

    elif command == "game" and len(sys.argv) >= 4:
        game_id = sys.argv[2]
        player_name = sys.argv[3]
        summary = analyzer.analyze_player_game(game_id, player_name)
        print(generate_player_report(summary))

    elif command == "summary":
        # Quick summary of recent games
        with sqlite3.connect("games.db") as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT g.id, g.room_code, g.started_at, g.num_players,
                       COUNT(m.id) as move_count
                FROM games g
                LEFT JOIN moves m ON g.id = m.game_id
                GROUP BY g.id
                ORDER BY g.started_at DESC
                LIMIT 10
            """)

            print("\n=== Recent Games ===\n")
            for row in cursor:
                print(f"Game: {row['id'][:8]}... Room: {row['room_code']}")
                print(f"  Players: {row['num_players']}, Moves: {row['move_count']}")
                print(f"  Started: {row['started_at']}")
                print()

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
