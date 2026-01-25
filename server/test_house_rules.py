"""
House Rules Testing Suite

Tests all house rule combinations to:
1. Find edge cases and bugs
2. Establish baseline performance metrics
3. Verify rules affect gameplay as expected
"""

import random
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from game import Game, Player, GamePhase, GameOptions
from ai import GolfAI, CPUProfile, CPU_PROFILES, get_ai_card_value


@dataclass
class RuleTestResult:
    """Results from testing a house rule configuration."""
    name: str
    options: GameOptions
    games_played: int
    scores: list[int]
    turn_counts: list[int]
    negative_scores: int  # Count of scores < 0
    zero_scores: int  # Count of exactly 0
    high_scores: int  # Count of scores > 25
    errors: list[str]

    @property
    def mean_score(self) -> float:
        return sum(self.scores) / len(self.scores) if self.scores else 0

    @property
    def median_score(self) -> float:
        if not self.scores:
            return 0
        s = sorted(self.scores)
        n = len(s)
        if n % 2 == 0:
            return (s[n//2 - 1] + s[n//2]) / 2
        return s[n//2]

    @property
    def mean_turns(self) -> float:
        return sum(self.turn_counts) / len(self.turn_counts) if self.turn_counts else 0

    @property
    def min_score(self) -> int:
        return min(self.scores) if self.scores else 0

    @property
    def max_score(self) -> int:
        return max(self.scores) if self.scores else 0


def run_game_with_options(options: GameOptions, num_players: int = 4) -> tuple[list[int], int, Optional[str]]:
    """
    Run a single game with given options.
    Returns (scores, turn_count, error_message).
    """
    profiles = random.sample(CPU_PROFILES, min(num_players, len(CPU_PROFILES)))

    game = Game()
    player_profiles: dict[str, CPUProfile] = {}

    for i, profile in enumerate(profiles):
        player = Player(id=f"cpu_{i}", name=profile.name)
        game.add_player(player)
        player_profiles[player.id] = profile

    try:
        game.start_game(num_decks=1, num_rounds=1, options=options)

        # Initial flips
        for player in game.players:
            positions = GolfAI.choose_initial_flips(options.initial_flips)
            game.flip_initial_cards(player.id, positions)

        # Play game
        turn = 0
        max_turns = 300  # Higher limit for edge cases

        while game.phase in (GamePhase.PLAYING, GamePhase.FINAL_TURN) and turn < max_turns:
            current = game.current_player()
            if not current:
                break

            profile = player_profiles[current.id]

            # Draw
            discard_top = game.discard_top()
            take_discard = GolfAI.should_take_discard(discard_top, current, profile, game)
            source = "discard" if take_discard else "deck"
            drawn = game.draw_card(current.id, source)

            if not drawn:
                # Deck exhausted - this is an edge case
                break

            # Swap or discard
            swap_pos = GolfAI.choose_swap_or_discard(drawn, current, profile, game)

            if swap_pos is None and game.drawn_from_discard:
                face_down = [i for i, c in enumerate(current.cards) if not c.face_up]
                if face_down:
                    swap_pos = random.choice(face_down)
                else:
                    worst_pos = 0
                    worst_val = -999
                    for i, c in enumerate(current.cards):
                        card_val = get_ai_card_value(c, game.options)
                        if card_val > worst_val:
                            worst_val = card_val
                            worst_pos = i
                    swap_pos = worst_pos

            if swap_pos is not None:
                game.swap_card(current.id, swap_pos)
            else:
                game.discard_drawn(current.id)
                if game.flip_on_discard:
                    flip_pos = GolfAI.choose_flip_after_discard(current, profile)
                    game.flip_and_end_turn(current.id, flip_pos)

            turn += 1

        if turn >= max_turns:
            return [], turn, f"Game exceeded {max_turns} turns - possible infinite loop"

        scores = [p.total_score for p in game.players]
        return scores, turn, None

    except Exception as e:
        return [], 0, f"Exception: {str(e)}"


def test_rule_config(name: str, options: GameOptions, num_games: int = 50) -> RuleTestResult:
    """Test a specific rule configuration."""

    all_scores = []
    turn_counts = []
    errors = []
    negative_count = 0
    zero_count = 0
    high_count = 0

    for _ in range(num_games):
        scores, turns, error = run_game_with_options(options)

        if error:
            errors.append(error)
            continue

        all_scores.extend(scores)
        turn_counts.append(turns)

        for s in scores:
            if s < 0:
                negative_count += 1
            elif s == 0:
                zero_count += 1
            elif s > 25:
                high_count += 1

    return RuleTestResult(
        name=name,
        options=options,
        games_played=num_games,
        scores=all_scores,
        turn_counts=turn_counts,
        negative_scores=negative_count,
        zero_scores=zero_count,
        high_scores=high_count,
        errors=errors
    )


# =============================================================================
# House Rule Configurations to Test
# =============================================================================

def get_test_configs() -> list[tuple[str, GameOptions]]:
    """Get all house rule configurations to test."""

    configs = []

    # Baseline (no house rules)
    configs.append(("BASELINE", GameOptions(
        initial_flips=2,
        flip_on_discard=False,
        use_jokers=False,
    )))

    # === Standard Options ===

    configs.append(("flip_on_discard", GameOptions(
        initial_flips=2,
        flip_on_discard=True,
    )))

    configs.append(("initial_flips=0", GameOptions(
        initial_flips=0,
        flip_on_discard=False,
    )))

    configs.append(("initial_flips=1", GameOptions(
        initial_flips=1,
        flip_on_discard=False,
    )))

    configs.append(("knock_penalty", GameOptions(
        initial_flips=2,
        knock_penalty=True,
    )))

    configs.append(("use_jokers", GameOptions(
        initial_flips=2,
        use_jokers=True,
    )))

    # === Point Modifiers ===

    configs.append(("lucky_swing", GameOptions(
        initial_flips=2,
        use_jokers=True,
        lucky_swing=True,
    )))

    configs.append(("super_kings", GameOptions(
        initial_flips=2,
        super_kings=True,
    )))

    configs.append(("lucky_sevens", GameOptions(
        initial_flips=2,
        lucky_sevens=True,
    )))

    configs.append(("ten_penny", GameOptions(
        initial_flips=2,
        ten_penny=True,
    )))

    # === Bonuses/Penalties ===

    configs.append(("knock_bonus", GameOptions(
        initial_flips=2,
        knock_bonus=True,
    )))

    configs.append(("underdog_bonus", GameOptions(
        initial_flips=2,
        underdog_bonus=True,
    )))

    configs.append(("tied_shame", GameOptions(
        initial_flips=2,
        tied_shame=True,
    )))

    configs.append(("blackjack", GameOptions(
        initial_flips=2,
        blackjack=True,
    )))

    # === Gameplay Twists ===

    configs.append(("queens_wild", GameOptions(
        initial_flips=2,
        queens_wild=True,
    )))

    configs.append(("four_of_a_kind", GameOptions(
        initial_flips=2,
        four_of_a_kind=True,
    )))

    configs.append(("eagle_eye", GameOptions(
        initial_flips=2,
        use_jokers=True,
        eagle_eye=True,
    )))

    # === Interesting Combinations ===

    configs.append(("CHAOS (all point mods)", GameOptions(
        initial_flips=2,
        use_jokers=True,
        lucky_swing=True,
        super_kings=True,
        lucky_sevens=True,
        ten_penny=True,
    )))

    configs.append(("COMPETITIVE (penalties)", GameOptions(
        initial_flips=2,
        knock_penalty=True,
        tied_shame=True,
    )))

    configs.append(("GENEROUS (bonuses)", GameOptions(
        initial_flips=2,
        knock_bonus=True,
        underdog_bonus=True,
    )))

    configs.append(("WILD CARDS", GameOptions(
        initial_flips=2,
        use_jokers=True,
        queens_wild=True,
        four_of_a_kind=True,
        eagle_eye=True,
    )))

    configs.append(("CLASSIC+ (jokers + flip)", GameOptions(
        initial_flips=2,
        flip_on_discard=True,
        use_jokers=True,
    )))

    configs.append(("EVERYTHING", GameOptions(
        initial_flips=2,
        flip_on_discard=True,
        knock_penalty=True,
        use_jokers=True,
        lucky_swing=True,
        super_kings=True,
        lucky_sevens=True,
        ten_penny=True,
        knock_bonus=True,
        underdog_bonus=True,
        tied_shame=True,
        blackjack=True,
        queens_wild=True,
        four_of_a_kind=True,
        eagle_eye=True,
    )))

    return configs


# =============================================================================
# Reporting
# =============================================================================

def print_results_table(results: list[RuleTestResult]):
    """Print a summary table of all results."""

    print("\n" + "=" * 100)
    print("HOUSE RULES TEST RESULTS")
    print("=" * 100)

    # Find baseline for comparison
    baseline = next((r for r in results if r.name == "BASELINE"), results[0])
    baseline_mean = baseline.mean_score

    print(f"\n{'Rule Config':<25} {'Games':>6} {'Mean':>7} {'Med':>6} {'Min':>5} {'Max':>5} {'Turns':>6} {'Neg%':>6} {'Err':>4} {'vs Base':>8}")
    print("-" * 100)

    for r in results:
        if not r.scores:
            print(f"{r.name:<25} {'ERROR':>6} - no scores collected")
            continue

        neg_pct = r.negative_scores / len(r.scores) * 100 if r.scores else 0
        diff = r.mean_score - baseline_mean
        diff_str = f"{diff:+.1f}" if r.name != "BASELINE" else "---"

        err_str = str(len(r.errors)) if r.errors else ""

        print(f"{r.name:<25} {r.games_played:>6} {r.mean_score:>7.1f} {r.median_score:>6.1f} "
              f"{r.min_score:>5} {r.max_score:>5} {r.mean_turns:>6.0f} {neg_pct:>5.1f}% {err_str:>4} {diff_str:>8}")

    print("-" * 100)


def print_anomalies(results: list[RuleTestResult]):
    """Identify and print any anomalies or edge cases."""

    print("\n" + "=" * 100)
    print("ANOMALY DETECTION")
    print("=" * 100)

    baseline = next((r for r in results if r.name == "BASELINE"), results[0])
    issues_found = False

    for r in results:
        issues = []

        # Check for errors
        if r.errors:
            issues.append(f"  ERRORS: {r.errors[:3]}")  # Show first 3

        # Check for extreme scores
        if r.min_score < -15:
            issues.append(f"  Very low min score: {r.min_score} (possible scoring bug)")

        if r.max_score > 60:
            issues.append(f"  Very high max score: {r.max_score} (possible stuck game)")

        # Check for unusual turn counts
        if r.mean_turns > 150:
            issues.append(f"  High turn count: {r.mean_turns:.0f} avg (games taking too long)")

        if r.mean_turns < 20:
            issues.append(f"  Low turn count: {r.mean_turns:.0f} avg (games ending too fast)")

        # Check for dramatic score shifts from baseline
        if r.name != "BASELINE" and r.scores:
            diff = r.mean_score - baseline.mean_score
            if abs(diff) > 10:
                issues.append(f"  Large score shift from baseline: {diff:+.1f} points")

        # Check for too many negative scores (unless expected)
        neg_pct = r.negative_scores / len(r.scores) * 100 if r.scores else 0
        if neg_pct > 20 and "super_kings" not in r.name.lower() and "lucky" not in r.name.lower():
            issues.append(f"  High negative score rate: {neg_pct:.1f}%")

        if issues:
            issues_found = True
            print(f"\n{r.name}:")
            for issue in issues:
                print(issue)

    if not issues_found:
        print("\nNo anomalies detected - all configurations behaving as expected.")


def print_expected_effects(results: list[RuleTestResult]):
    """Verify house rules have expected effects."""

    print("\n" + "=" * 100)
    print("EXPECTED EFFECTS VERIFICATION")
    print("=" * 100)

    baseline = next((r for r in results if r.name == "BASELINE"), None)
    if not baseline:
        print("No baseline found!")
        return

    checks = []

    # Find specific results
    def find(name):
        return next((r for r in results if r.name == name), None)

    # super_kings should lower scores (Kings worth -2 instead of 0)
    r = find("super_kings")
    if r and r.scores:
        diff = r.mean_score - baseline.mean_score
        expected = "LOWER scores"
        actual = "lower" if diff < -1 else "higher" if diff > 1 else "similar"
        status = "✓" if diff < 0 else "✗"
        checks.append((r.name, expected, f"{actual} ({diff:+.1f})", status))

    # lucky_sevens should lower scores (7s worth 0 instead of 7)
    r = find("lucky_sevens")
    if r and r.scores:
        diff = r.mean_score - baseline.mean_score
        expected = "LOWER scores"
        actual = "lower" if diff < -1 else "higher" if diff > 1 else "similar"
        status = "✓" if diff < 0 else "✗"
        checks.append((r.name, expected, f"{actual} ({diff:+.1f})", status))

    # ten_penny should lower scores (10s worth 1 instead of 10)
    r = find("ten_penny")
    if r and r.scores:
        diff = r.mean_score - baseline.mean_score
        expected = "LOWER scores"
        actual = "lower" if diff < -1 else "higher" if diff > 1 else "similar"
        status = "✓" if diff < 0 else "✗"
        checks.append((r.name, expected, f"{actual} ({diff:+.1f})", status))

    # use_jokers should lower scores (jokers are -2)
    r = find("use_jokers")
    if r and r.scores:
        diff = r.mean_score - baseline.mean_score
        expected = "LOWER scores"
        actual = "lower" if diff < -1 else "higher" if diff > 1 else "similar"
        status = "✓" if diff < 0 else "?"  # Might be small effect
        checks.append((r.name, expected, f"{actual} ({diff:+.1f})", status))

    # knock_bonus should lower scores (-5 for going out)
    r = find("knock_bonus")
    if r and r.scores:
        diff = r.mean_score - baseline.mean_score
        expected = "LOWER scores"
        actual = "lower" if diff < -1 else "higher" if diff > 1 else "similar"
        status = "✓" if diff < 0 else "?"
        checks.append((r.name, expected, f"{actual} ({diff:+.1f})", status))

    # tied_shame should raise scores (+5 penalty for ties)
    r = find("tied_shame")
    if r and r.scores:
        diff = r.mean_score - baseline.mean_score
        expected = "HIGHER scores"
        actual = "lower" if diff < -1 else "higher" if diff > 1 else "similar"
        status = "✓" if diff > 0 else "?"
        checks.append((r.name, expected, f"{actual} ({diff:+.1f})", status))

    # flip_on_discard might slightly lower scores (more info)
    r = find("flip_on_discard")
    if r and r.scores:
        diff = r.mean_score - baseline.mean_score
        expected = "SIMILAR or lower"
        actual = "lower" if diff < -1 else "higher" if diff > 1 else "similar"
        status = "✓" if diff <= 1 else "?"
        checks.append((r.name, expected, f"{actual} ({diff:+.1f})", status))

    # CHAOS mode should have very low scores
    r = find("CHAOS (all point mods)")
    if r and r.scores:
        diff = r.mean_score - baseline.mean_score
        expected = "MUCH LOWER scores"
        actual = "much lower" if diff < -5 else "lower" if diff < -1 else "similar"
        status = "✓" if diff < -3 else "✗"
        checks.append((r.name, expected, f"{actual} ({diff:+.1f})", status))

    print(f"\n{'Rule':<30} {'Expected':<20} {'Actual':<20} {'Status'}")
    print("-" * 80)
    for name, expected, actual, status in checks:
        print(f"{name:<30} {expected:<20} {actual:<20} {status}")


# =============================================================================
# Main
# =============================================================================

def main():
    num_games = int(sys.argv[1]) if len(sys.argv) > 1 else 30

    print(f"Testing house rules with {num_games} games each...")
    print("This may take a few minutes...\n")

    configs = get_test_configs()
    results = []

    for i, (name, options) in enumerate(configs):
        print(f"[{i+1}/{len(configs)}] Testing: {name}...")
        result = test_rule_config(name, options, num_games)
        results.append(result)

        # Quick status
        if result.errors:
            print(f"  WARNING: {len(result.errors)} errors")
        else:
            print(f"  Mean: {result.mean_score:.1f}, Turns: {result.mean_turns:.0f}")

    # Reports
    print_results_table(results)
    print_expected_effects(results)
    print_anomalies(results)

    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    total_games = sum(r.games_played for r in results)
    total_errors = sum(len(r.errors) for r in results)
    print(f"Total games run: {total_games}")
    print(f"Total errors: {total_errors}")

    if total_errors == 0:
        print("All house rule configurations working correctly!")


if __name__ == "__main__":
    main()
