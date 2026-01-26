"""
Score distribution analysis for Golf AI.

Generates box plots and statistics to verify AI plays reasonably.
"""

import random
import sys
from collections import defaultdict

from game import Game, Player, GamePhase, GameOptions
from ai import GolfAI, CPUProfile, CPU_PROFILES, get_ai_card_value


def run_game_for_scores(num_players: int = 4) -> dict[str, int]:
    """Run a single game and return final scores by player name."""

    # Pick random profiles
    profiles = random.sample(CPU_PROFILES, min(num_players, len(CPU_PROFILES)))

    game = Game()
    player_profiles: dict[str, CPUProfile] = {}

    for i, profile in enumerate(profiles):
        player = Player(id=f"cpu_{i}", name=profile.name)
        game.add_player(player)
        player_profiles[player.id] = profile

    options = GameOptions(initial_flips=2, flip_mode="never", use_jokers=False)
    game.start_game(num_decks=1, num_rounds=1, options=options)

    # Initial flips
    for player in game.players:
        positions = GolfAI.choose_initial_flips(options.initial_flips)
        game.flip_initial_cards(player.id, positions)

    # Play game
    turn = 0
    max_turns = 200

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

    # Return scores
    return {p.name: p.total_score for p in game.players}


def collect_scores(num_games: int = 100, num_players: int = 4) -> dict[str, list[int]]:
    """Run multiple games and collect all scores by player."""

    all_scores: dict[str, list[int]] = defaultdict(list)

    print(f"Running {num_games} games with {num_players} players each...")

    for i in range(num_games):
        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{num_games} games completed")

        scores = run_game_for_scores(num_players)
        for name, score in scores.items():
            all_scores[name].append(score)

    return dict(all_scores)


def print_statistics(all_scores: dict[str, list[int]]):
    """Print statistical summary."""

    print("\n" + "=" * 60)
    print("SCORE STATISTICS BY PLAYER")
    print("=" * 60)

    # Combine all scores
    combined = []
    for scores in all_scores.values():
        combined.extend(scores)

    combined.sort()

    def percentile(data, p):
        k = (len(data) - 1) * p / 100
        f = int(k)
        c = f + 1 if f + 1 < len(data) else f
        return data[f] + (k - f) * (data[c] - data[f])

    def stats(data):
        data = sorted(data)
        n = len(data)
        mean = sum(data) / n
        q1 = percentile(data, 25)
        median = percentile(data, 50)
        q3 = percentile(data, 75)
        return {
            'n': n,
            'min': min(data),
            'q1': q1,
            'median': median,
            'q3': q3,
            'max': max(data),
            'mean': mean,
            'iqr': q3 - q1
        }

    print(f"\n{'Player':<12} {'N':>5} {'Min':>6} {'Q1':>6} {'Med':>6} {'Q3':>6} {'Max':>6} {'Mean':>7}")
    print("-" * 60)

    for name in sorted(all_scores.keys()):
        s = stats(all_scores[name])
        print(f"{name:<12} {s['n']:>5} {s['min']:>6.0f} {s['q1']:>6.1f} {s['median']:>6.1f} {s['q3']:>6.1f} {s['max']:>6.0f} {s['mean']:>7.1f}")

    print("-" * 60)
    s = stats(combined)
    print(f"{'OVERALL':<12} {s['n']:>5} {s['min']:>6.0f} {s['q1']:>6.1f} {s['median']:>6.1f} {s['q3']:>6.1f} {s['max']:>6.0f} {s['mean']:>7.1f}")

    print(f"\nInterquartile Range (IQR): {s['iqr']:.1f}")
    print(f"Typical score range: {s['q1']:.0f} to {s['q3']:.0f}")

    # Score distribution buckets
    print("\n" + "=" * 60)
    print("SCORE DISTRIBUTION")
    print("=" * 60)

    buckets = defaultdict(int)
    for score in combined:
        if score < -5:
            bucket = "< -5"
        elif score < 0:
            bucket = "-5 to -1"
        elif score < 5:
            bucket = "0 to 4"
        elif score < 10:
            bucket = "5 to 9"
        elif score < 15:
            bucket = "10 to 14"
        elif score < 20:
            bucket = "15 to 19"
        elif score < 25:
            bucket = "20 to 24"
        else:
            bucket = "25+"
        buckets[bucket] += 1

    bucket_order = ["< -5", "-5 to -1", "0 to 4", "5 to 9", "10 to 14", "15 to 19", "20 to 24", "25+"]

    total = len(combined)
    for bucket in bucket_order:
        count = buckets.get(bucket, 0)
        pct = count / total * 100
        bar = "#" * int(pct / 2)
        print(f"{bucket:>10}: {count:>4} ({pct:>5.1f}%) {bar}")

    return stats(combined)


def create_box_plot(all_scores: dict[str, list[int]], output_file: str = "score_distribution.png"):
    """Create a box plot visualization."""

    try:
        import matplotlib.pyplot as plt
        import matplotlib
        matplotlib.use('Agg')  # Non-interactive backend
    except ImportError:
        print("\nMatplotlib not installed. Install with: pip install matplotlib")
        print("Skipping box plot generation.")
        return False

    # Prepare data
    names = sorted(all_scores.keys())
    data = [all_scores[name] for name in names]

    # Also add combined data
    combined = []
    for scores in all_scores.values():
        combined.extend(scores)
    names.append("ALL")
    data.append(combined)

    # Create figure
    fig, ax = plt.subplots(figsize=(12, 6))

    # Box plot
    bp = ax.boxplot(data, labels=names, patch_artist=True)

    # Color boxes
    colors = ['#FF9999', '#99FF99', '#9999FF', '#FFFF99',
              '#FF99FF', '#99FFFF', '#FFB366', '#B366FF', '#CCCCCC']
    for patch, color in zip(bp['boxes'], colors[:len(bp['boxes'])]):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    # Labels
    ax.set_xlabel('Player (AI Personality)', fontsize=12)
    ax.set_ylabel('Round Score (lower is better)', fontsize=12)
    ax.set_title('6-Card Golf AI Score Distribution', fontsize=14)

    # Add horizontal line at 0
    ax.axhline(y=0, color='green', linestyle='--', alpha=0.5, label='Zero (par)')

    # Add reference lines
    ax.axhline(y=10, color='orange', linestyle=':', alpha=0.5, label='Good (10)')
    ax.axhline(y=20, color='red', linestyle=':', alpha=0.5, label='Poor (20)')

    ax.legend(loc='upper right')
    ax.grid(axis='y', alpha=0.3)

    # Save
    plt.tight_layout()
    plt.savefig(output_file, dpi=150)
    print(f"\nBox plot saved to: {output_file}")

    return True


def create_ascii_box_plot(all_scores: dict[str, list[int]]):
    """Create an ASCII box plot for terminal display."""

    print("\n" + "=" * 70)
    print("ASCII BOX PLOT (Score Distribution)")
    print("=" * 70)

    def percentile(data, p):
        data = sorted(data)
        k = (len(data) - 1) * p / 100
        f = int(k)
        c = f + 1 if f + 1 < len(data) else f
        return data[f] + (k - f) * (data[c] - data[f])

    # Find global min/max for scaling
    all_vals = []
    for scores in all_scores.values():
        all_vals.extend(scores)

    global_min = min(all_vals)
    global_max = max(all_vals)

    # Scale to 50 characters
    width = 50

    def scale(val):
        if global_max == global_min:
            return width // 2
        return int((val - global_min) / (global_max - global_min) * (width - 1))

    # Print scale
    print(f"\n{' ' * 12} {global_min:<6} {'':^{width-12}} {global_max:>6}")
    print(f"{' ' * 12} |{'-' * (width - 2)}|")

    # Add combined
    combined = list(all_vals)
    scores_to_plot = dict(all_scores)
    scores_to_plot["COMBINED"] = combined

    for name in sorted(scores_to_plot.keys()):
        scores = scores_to_plot[name]

        q1 = percentile(scores, 25)
        med = percentile(scores, 50)
        q3 = percentile(scores, 75)
        min_val = min(scores)
        max_val = max(scores)

        # Build the line
        line = [' '] * width

        # Whiskers
        min_pos = scale(min_val)
        max_pos = scale(max_val)
        q1_pos = scale(q1)
        q3_pos = scale(q3)
        med_pos = scale(med)

        # Left whisker
        line[min_pos] = '|'
        for i in range(min_pos + 1, q1_pos):
            line[i] = '-'

        # Box
        for i in range(q1_pos, q3_pos + 1):
            line[i] = '='

        # Median
        line[med_pos] = '|'

        # Right whisker
        for i in range(q3_pos + 1, max_pos):
            line[i] = '-'
        line[max_pos] = '|'

        print(f"{name:>11} {''.join(line)}")

    print(f"\n Legend: |---[===|===]---| = min--Q1--median--Q3--max")
    print(f" Lower scores are better (left side of plot)")


if __name__ == "__main__":
    num_games = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    num_players = int(sys.argv[2]) if len(sys.argv) > 2 else 4

    # Collect scores
    all_scores = collect_scores(num_games, num_players)

    # Print statistics
    print_statistics(all_scores)

    # ASCII box plot (always works)
    create_ascii_box_plot(all_scores)

    # Try matplotlib box plot
    create_box_plot(all_scores)
