"""
Golf AI Simulation Runner

Runs AI-vs-AI games to generate decision logs for analysis.
No server/websocket needed - runs games directly.

Usage:
    python simulate.py [num_games] [num_players]
    python simulate.py 100 --rules use_jokers,eagle_eye
    python simulate.py 100 --preset competitive
    python simulate.py 100 --compare baseline eagle_eye negative_pairs

Examples:
    python simulate.py 10              # Run 10 games with 4 players each
    python simulate.py 50 2            # Run 50 games with 2 players each
    python simulate.py 100 --preset eagle_eye
    python simulate.py detail --preset competitive
"""

import argparse
import random
from typing import Optional

from game import Game, Player, GamePhase, GameOptions
from ai import (
    GolfAI, CPUProfile, CPU_PROFILES,
    get_ai_card_value, has_worse_visible_card,
    filter_bad_pair_positions, get_column_partner_position
)
from game import Rank
from game_log import GameLogger


# Named rule presets for quick configuration
RULE_PRESETS: dict[str, dict] = {
    "baseline": {
        # Default classic rules, no special options
    },
    "jokers": {
        "use_jokers": True,
    },
    "eagle_eye": {
        "use_jokers": True,
        "eagle_eye": True,
    },
    "negative_pairs": {
        "use_jokers": True,
        "negative_pairs_keep_value": True,
    },
    "four_kind": {
        "four_of_a_kind": True,
    },
    "wolfpack": {
        "wolfpack": True,
    },
    "competitive": {
        "knock_penalty": True,
        "knock_bonus": True,
    },
    "wild": {
        "use_jokers": True,
        "lucky_swing": True,
        "eagle_eye": True,
        "negative_pairs_keep_value": True,
    },
    "all_bonuses": {
        "knock_bonus": True,
        "underdog_bonus": True,
        "four_of_a_kind": True,
        "wolfpack": True,
    },
}


def get_preset_options(preset_name: str) -> GameOptions:
    """Get GameOptions for a named preset."""
    if preset_name not in RULE_PRESETS:
        available = ", ".join(sorted(RULE_PRESETS.keys()))
        raise ValueError(f"Unknown preset '{preset_name}'. Available: {available}")

    rules = RULE_PRESETS[preset_name]
    return GameOptions(
        initial_flips=2,
        flip_mode="never",
        **rules
    )


def parse_rules_string(rules_str: str) -> GameOptions:
    """Parse comma-separated rule names into GameOptions."""
    if not rules_str:
        return GameOptions(initial_flips=2, flip_mode="never")

    rules = {}
    for rule in rules_str.split(","):
        rule = rule.strip()
        if rule:
            # Validate that it's a valid GameOptions field
            if not hasattr(GameOptions, rule):
                raise ValueError(f"Unknown rule '{rule}'. Check GameOptions for valid fields.")
            rules[rule] = True

    return GameOptions(initial_flips=2, flip_mode="never", **rules)


class SimulationStats:
    """Track simulation statistics."""

    def __init__(self):
        self.games_played = 0
        self.total_rounds = 0
        self.total_turns = 0
        self.player_wins: dict[str, int] = {}
        self.player_scores: dict[str, list[int]] = {}
        self.decisions: dict[str, dict] = {}  # player -> {action: count}

        # Dumb move tracking
        self.discarded_jokers = 0
        self.discarded_twos = 0
        self.discarded_kings = 0
        self.took_bad_card_without_pair = 0
        self.paired_negative_cards = 0
        self.swapped_good_for_bad = 0
        self.total_opportunities = 0  # Total decision points

    def record_game(self, game: Game, winner_name: str):
        self.games_played += 1
        self.total_rounds += game.current_round

        if winner_name not in self.player_wins:
            self.player_wins[winner_name] = 0
        self.player_wins[winner_name] += 1

        for player in game.players:
            if player.name not in self.player_scores:
                self.player_scores[player.name] = []
            self.player_scores[player.name].append(player.total_score)

    def record_turn(self, player_name: str, action: str):
        self.total_turns += 1
        if player_name not in self.decisions:
            self.decisions[player_name] = {}
        if action not in self.decisions[player_name]:
            self.decisions[player_name][action] = 0
        self.decisions[player_name][action] += 1

    def record_dumb_move(self, move_type: str):
        """Record a dumb move for analysis."""
        if move_type == "discarded_joker":
            self.discarded_jokers += 1
        elif move_type == "discarded_two":
            self.discarded_twos += 1
        elif move_type == "discarded_king":
            self.discarded_kings += 1
        elif move_type == "took_bad_without_pair":
            self.took_bad_card_without_pair += 1
        elif move_type == "paired_negative":
            self.paired_negative_cards += 1
        elif move_type == "swapped_good_for_bad":
            self.swapped_good_for_bad += 1

    def record_opportunity(self):
        """Record a decision opportunity for rate calculation."""
        self.total_opportunities += 1

    @property
    def dumb_move_rate(self) -> float:
        """Calculate overall dumb move rate."""
        total_dumb = (
            self.discarded_jokers +
            self.discarded_twos +
            self.discarded_kings +
            self.took_bad_card_without_pair +
            self.paired_negative_cards +
            self.swapped_good_for_bad
        )
        if self.total_opportunities == 0:
            return 0.0
        return total_dumb / self.total_opportunities * 100

    def report(self) -> str:
        lines = [
            "=" * 50,
            "SIMULATION RESULTS",
            "=" * 50,
            f"Games played: {self.games_played}",
            f"Total rounds: {self.total_rounds}",
            f"Total turns: {self.total_turns}",
            f"Avg turns/game: {self.total_turns / max(1, self.games_played):.1f}",
            "",
            "WIN RATES:",
        ]

        total_wins = sum(self.player_wins.values())
        for name, wins in sorted(self.player_wins.items(), key=lambda x: -x[1]):
            pct = wins / max(1, total_wins) * 100
            lines.append(f"  {name}: {wins} wins ({pct:.1f}%)")

        lines.append("")
        lines.append("AVERAGE SCORES (lower is better):")

        for name, scores in sorted(
            self.player_scores.items(),
            key=lambda x: sum(x[1]) / len(x[1]) if x[1] else 999
        ):
            avg = sum(scores) / len(scores) if scores else 0
            lines.append(f"  {name}: {avg:.1f}")

        lines.append("")
        lines.append("DECISION BREAKDOWN:")

        for name, actions in sorted(self.decisions.items()):
            total = sum(actions.values())
            lines.append(f"  {name}:")
            for action, count in sorted(actions.items()):
                pct = count / max(1, total) * 100
                lines.append(f"    {action}: {count} ({pct:.1f}%)")

        lines.append("")
        lines.append("DUMB MOVE ANALYSIS:")
        lines.append(f"  Total decision opportunities: {self.total_opportunities}")
        lines.append(f"  Dumb move rate: {self.dumb_move_rate:.3f}%")
        lines.append("")
        lines.append("  Blunders (should be 0):")
        lines.append(f"    Discarded Jokers: {self.discarded_jokers}")
        lines.append(f"    Discarded 2s: {self.discarded_twos}")
        lines.append(f"    Took bad card without pair: {self.took_bad_card_without_pair}")
        lines.append(f"    Paired negative cards: {self.paired_negative_cards}")
        lines.append("")
        lines.append("  Mistakes (should be < 0.1%):")
        lines.append(f"    Discarded Kings: {self.discarded_kings}")
        lines.append(f"    Swapped good for bad: {self.swapped_good_for_bad}")

        return "\n".join(lines)


def create_cpu_players(num_players: int) -> list[tuple[Player, CPUProfile]]:
    """Create CPU players with random profiles."""
    # Shuffle profiles and pick
    profiles = random.sample(CPU_PROFILES, min(num_players, len(CPU_PROFILES)))

    players = []
    for i, profile in enumerate(profiles):
        player = Player(id=f"cpu_{i}", name=profile.name)
        players.append((player, profile))

    return players


def run_cpu_turn(
    game: Game,
    player: Player,
    profile: CPUProfile,
    logger: Optional[GameLogger],
    game_id: Optional[str],
    stats: SimulationStats
) -> str:
    """Run a single CPU turn synchronously. Returns action taken."""

    # Decide whether to draw from discard or deck
    discard_top = game.discard_top()
    take_discard = GolfAI.should_take_discard(discard_top, player, profile, game)

    source = "discard" if take_discard else "deck"
    drawn = game.draw_card(player.id, source)

    if not drawn:
        return "no_card"

    action = "take_discard" if take_discard else "draw_deck"
    stats.record_turn(player.name, action)

    # Check for dumb move: taking bad card from discard without good reason
    if take_discard:
        drawn_val = get_ai_card_value(drawn, game.options)
        # Bad cards are 8, 9, 10, J, Q (value >= 8)
        if drawn_val >= 8:
            # Check if there's pair potential
            has_pair_potential = False
            for i, card in enumerate(player.cards):
                if card.face_up and card.rank == drawn.rank:
                    partner_pos = get_column_partner_position(i)
                    if not player.cards[partner_pos].face_up:
                        has_pair_potential = True
                        break

            # Check if player has a WORSE visible card to replace
            has_worse_to_replace = has_worse_visible_card(player, drawn_val, game.options)

            # Only flag as dumb if no pair potential AND no worse card to replace
            if not has_pair_potential and not has_worse_to_replace:
                stats.record_dumb_move("took_bad_without_pair")

    # Log draw decision
    if logger and game_id:
        reason = f"took {discard_top.rank.value} from discard" if take_discard else "drew from deck"
        logger.log_move(
            game_id=game_id,
            player=player,
            is_cpu=True,
            action=action,
            card=drawn,
            game=game,
            decision_reason=reason,
        )

    # Decide whether to swap or discard
    swap_pos = GolfAI.choose_swap_or_discard(drawn, player, profile, game)

    # If drawn from discard, must swap
    if swap_pos is None and game.drawn_from_discard:
        face_down = [i for i, c in enumerate(player.cards) if not c.face_up]
        if face_down:
            # Use filter to avoid bad pairs with negative cards
            safe_positions = filter_bad_pair_positions(face_down, drawn, player, game.options)
            swap_pos = random.choice(safe_positions)
        else:
            # Find worst card using house rules
            worst_pos = 0
            worst_val = -999
            for i, c in enumerate(player.cards):
                card_val = get_ai_card_value(c, game.options)
                if card_val > worst_val:
                    worst_val = card_val
                    worst_pos = i
            swap_pos = worst_pos

    # Record this as a decision opportunity for dumb move rate calculation
    stats.record_opportunity()

    if swap_pos is not None:
        old_card = player.cards[swap_pos]
        partner_pos = get_column_partner_position(swap_pos)
        partner = player.cards[partner_pos]

        # Check for dumb moves: swapping good card for bad
        drawn_val = get_ai_card_value(drawn, game.options)
        old_val = get_ai_card_value(old_card, game.options)

        # Only flag as dumb if:
        # 1. Old card was face-up and good (value <= 1)
        # 2. We're putting a worse card in
        # 3. We're NOT creating a pair (pairing is a valid reason to replace a good card)
        # 4. We're NOT in a forced-swap-from-discard situation
        creates_pair = partner.face_up and partner.rank == drawn.rank
        if old_card.face_up and old_val < drawn_val and old_val <= 1:
            if not creates_pair:
                stats.record_dumb_move("swapped_good_for_bad")

        # Check for dumb move: creating bad pair with negative card
        if (partner.face_up and
            partner.rank == drawn.rank and
            drawn_val < 0 and
            not (game.options.eagle_eye and drawn.rank == Rank.JOKER) and
            not game.options.negative_pairs_keep_value):
            stats.record_dumb_move("paired_negative")
            print(f"  !!! PAIRED NEGATIVE: {player.name} paired {drawn.rank.value} "
                  f"at pos {swap_pos} (partner at {partner_pos})")

        game.swap_card(player.id, swap_pos)
        action = "swap"
        stats.record_turn(player.name, action)

        if logger and game_id:
            logger.log_move(
                game_id=game_id,
                player=player,
                is_cpu=True,
                action="swap",
                card=drawn,
                position=swap_pos,
                game=game,
                decision_reason=f"swapped {drawn.rank.value} for {old_card.rank.value} at pos {swap_pos}",
            )
    else:
        # Check for dumb moves: discarding excellent cards
        if drawn.rank == Rank.JOKER:
            stats.record_dumb_move("discarded_joker")
        elif drawn.rank == Rank.TWO:
            stats.record_dumb_move("discarded_two")
        elif drawn.rank == Rank.KING:
            stats.record_dumb_move("discarded_king")

        game.discard_drawn(player.id)
        action = "discard"
        stats.record_turn(player.name, action)

        if logger and game_id:
            logger.log_move(
                game_id=game_id,
                player=player,
                is_cpu=True,
                action="discard",
                card=drawn,
                game=game,
                decision_reason=f"discarded {drawn.rank.value}",
            )

        if game.flip_on_discard:
            flip_pos = GolfAI.choose_flip_after_discard(player, profile)
            game.flip_and_end_turn(player.id, flip_pos)

            if logger and game_id:
                flipped = player.cards[flip_pos]
                logger.log_move(
                    game_id=game_id,
                    player=player,
                    is_cpu=True,
                    action="flip",
                    card=flipped,
                    position=flip_pos,
                    game=game,
                    decision_reason=f"flipped position {flip_pos}",
                )

    return action


def run_game(
    players_with_profiles: list[tuple[Player, CPUProfile]],
    options: GameOptions,
    logger: Optional[GameLogger],
    stats: SimulationStats,
    verbose: bool = False
) -> tuple[str, int]:
    """Run a complete game. Returns (winner_name, winner_score)."""

    game = Game()
    profiles: dict[str, CPUProfile] = {}

    for player, profile in players_with_profiles:
        # Reset player state
        player.cards = []
        player.score = 0
        player.total_score = 0
        player.rounds_won = 0

        game.add_player(player)
        profiles[player.id] = profile

    game.start_game(num_decks=1, num_rounds=1, options=options)

    # Log game start
    game_id = None
    if logger:
        game_id = logger.log_game_start(
            room_code="SIM",
            num_players=len(players_with_profiles),
            options=options
        )

    # Do initial flips for all players
    if options.initial_flips > 0:
        for player, profile in players_with_profiles:
            positions = GolfAI.choose_initial_flips(options.initial_flips)
            game.flip_initial_cards(player.id, positions)

    # Play until game over
    turn_count = 0
    max_turns = 200  # Safety limit

    while game.phase in (GamePhase.PLAYING, GamePhase.FINAL_TURN) and turn_count < max_turns:
        current = game.current_player()
        if not current:
            break

        profile = profiles[current.id]
        action = run_cpu_turn(game, current, profile, logger, game_id, stats)

        if verbose and turn_count % 10 == 0:
            print(f"  Turn {turn_count}: {current.name} - {action}")

        turn_count += 1

    # Log game end
    if logger and game_id:
        logger.log_game_end(game_id)

    # Find winner
    winner = min(game.players, key=lambda p: p.total_score)
    stats.record_game(game, winner.name)

    return winner.name, winner.total_score


def run_simulation(
    num_games: int = 10,
    num_players: int = 4,
    options: Optional[GameOptions] = None,
    verbose: bool = True
) -> SimulationStats:
    """Run multiple games and report statistics."""

    if options is None:
        options = GameOptions(initial_flips=2, flip_mode="never")

    # Build description of active rules
    active_rules = []
    for field_name in ["use_jokers", "eagle_eye", "negative_pairs_keep_value",
                       "knock_penalty", "knock_bonus", "four_of_a_kind",
                       "wolfpack", "lucky_swing", "underdog_bonus"]:
        if getattr(options, field_name, False):
            active_rules.append(field_name)

    rules_desc = ", ".join(active_rules) if active_rules else "baseline (no special rules)"

    print(f"\nRunning {num_games} games with {num_players} players each...")
    print(f"Rules: {rules_desc}")
    print("=" * 50)

    logger = GameLogger()
    stats = SimulationStats()

    for i in range(num_games):
        players = create_cpu_players(num_players)

        if verbose:
            names = [p.name for p, _ in players]
            print(f"\nGame {i+1}/{num_games}: {', '.join(names)}")

        winner, score = run_game(players, options, logger, stats, verbose=False)

        if verbose:
            print(f"  Winner: {winner} (score: {score})")

    print("\n")
    print(stats.report())

    print("\n" + "=" * 50)
    print("ANALYSIS")
    print("=" * 50)
    print("\nRun analysis with:")
    print("  python game_analyzer.py blunders")
    print("  python game_analyzer.py summary")

    return stats


def run_detailed_game(num_players: int = 4, options: Optional[GameOptions] = None):
    """Run a single game with detailed output."""

    if options is None:
        options = GameOptions(initial_flips=2, flip_mode="never")

    # Build description of active rules
    active_rules = []
    for field_name in ["use_jokers", "eagle_eye", "negative_pairs_keep_value",
                       "knock_penalty", "knock_bonus", "four_of_a_kind",
                       "wolfpack", "lucky_swing", "underdog_bonus"]:
        if getattr(options, field_name, False):
            active_rules.append(field_name)

    rules_desc = ", ".join(active_rules) if active_rules else "baseline (no special rules)"

    print(f"\nRunning detailed game with {num_players} players...")
    print(f"Rules: {rules_desc}")
    print("=" * 50)

    logger = GameLogger()
    stats = SimulationStats()

    players_with_profiles = create_cpu_players(num_players)

    game = Game()
    profiles: dict[str, CPUProfile] = {}

    for player, profile in players_with_profiles:
        game.add_player(player)
        profiles[player.id] = profile
        print(f"  {player.name} ({profile.style})")

    game.start_game(num_decks=1, num_rounds=1, options=options)

    game_id = logger.log_game_start(
        room_code="DETAIL",
        num_players=num_players,
        options=options
    )

    # Initial flips
    print("\nInitial flips:")
    for player, profile in players_with_profiles:
        positions = GolfAI.choose_initial_flips(options.initial_flips)
        game.flip_initial_cards(player.id, positions)
        visible = [(i, c.rank.value) for i, c in enumerate(player.cards) if c.face_up]
        print(f"  {player.name}: {visible}")

    print(f"\nDiscard pile: {game.discard_top().rank.value}")
    print("\n" + "-" * 50)

    # Play game
    turn = 0
    while game.phase in (GamePhase.PLAYING, GamePhase.FINAL_TURN) and turn < 100:
        current = game.current_player()
        if not current:
            break

        profile = profiles[current.id]
        discard_before = game.discard_top()

        # Show state before turn
        visible = [(i, c.rank.value) for i, c in enumerate(current.cards) if c.face_up]
        hidden = sum(1 for c in current.cards if not c.face_up)

        print(f"\nTurn {turn + 1}: {current.name}")
        print(f"  Hand: {visible} + {hidden} hidden")
        print(f"  Discard: {discard_before.rank.value}")

        # Run turn
        action = run_cpu_turn(game, current, profile, logger, game_id, stats)

        # Show result
        discard_after = game.discard_top()
        print(f"  Action: {action}")
        print(f"  New discard: {discard_after.rank.value if discard_after else 'empty'}")

        if game.phase == GamePhase.FINAL_TURN and game.finisher_id == current.id:
            print(f"  >>> {current.name} went out! Final turn phase.")

        turn += 1

    # Game over
    logger.log_game_end(game_id)

    print("\n" + "=" * 50)
    print("FINAL SCORES")
    print("=" * 50)

    for player in sorted(game.players, key=lambda p: p.total_score):
        cards = [c.rank.value for c in player.cards]
        print(f"  {player.name}: {player.total_score} points")
        print(f"    Cards: {cards}")

    winner = min(game.players, key=lambda p: p.total_score)
    print(f"\nWinner: {winner.name}!")

    print(f"\nGame logged as: {game_id[:8]}...")
    print("Run: python game_analyzer.py game", game_id, winner.name)


def compare_rule_sets(presets: list[str], num_games: int = 100, num_players: int = 4):
    """Run simulations with different rule sets and compare results."""
    print(f"\nComparing {len(presets)} rule sets with {num_games} games each...")
    print("=" * 60)

    results: dict[str, SimulationStats] = {}

    for preset in presets:
        print(f"\n{'='*60}")
        print(f"RUNNING PRESET: {preset}")
        print(f"{'='*60}")
        options = get_preset_options(preset)
        stats = run_simulation(num_games, num_players, options, verbose=False)
        results[preset] = stats

    # Print comparison summary
    print("\n")
    print("=" * 70)
    print("COMPARISON SUMMARY")
    print("=" * 70)

    # Header
    print(f"\n{'Preset':<20} {'Avg Score':<12} {'Dumb %':<10} {'Swap %':<10} {'Discard %':<10}")
    print("-" * 70)

    for preset in presets:
        stats = results[preset]

        # Calculate average score across all players
        all_scores = []
        for scores in stats.player_scores.values():
            all_scores.extend(scores)
        avg_score = sum(all_scores) / len(all_scores) if all_scores else 0

        # Calculate swap vs discard ratio
        total_swaps = 0
        total_discards = 0
        for actions in stats.decisions.values():
            total_swaps += actions.get("swap", 0)
            total_discards += actions.get("discard", 0)

        total_actions = total_swaps + total_discards
        swap_pct = (total_swaps / total_actions * 100) if total_actions > 0 else 0
        discard_pct = (total_discards / total_actions * 100) if total_actions > 0 else 0

        print(f"{preset:<20} {avg_score:<12.1f} {stats.dumb_move_rate:<10.3f} {swap_pct:<10.1f} {discard_pct:<10.1f}")

    # Detailed dumb move breakdown
    print("\n\nDUMB MOVE BREAKDOWN BY PRESET:")
    print("-" * 70)
    print(f"{'Preset':<20} {'Jokers':<8} {'2s':<8} {'Kings':<8} {'BadTake':<8} {'NegPair':<8} {'BadSwap':<8}")
    print("-" * 70)

    for preset in presets:
        stats = results[preset]
        print(f"{preset:<20} {stats.discarded_jokers:<8} {stats.discarded_twos:<8} "
              f"{stats.discarded_kings:<8} {stats.took_bad_card_without_pair:<8} "
              f"{stats.paired_negative_cards:<8} {stats.swapped_good_for_bad:<8}")


def main():
    """Main entry point with argparse CLI."""
    parser = argparse.ArgumentParser(
        description="Golf AI Simulation Runner - test AI behavior under different rule sets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python simulate.py 100                          # 100 games, baseline rules
  python simulate.py 100 4                        # 100 games, 4 players
  python simulate.py 100 --preset eagle_eye       # Use eagle_eye preset
  python simulate.py 100 --rules use_jokers,knock_penalty
  python simulate.py 100 --compare baseline eagle_eye negative_pairs
  python simulate.py detail --preset competitive  # Single detailed game

Available presets:
  baseline       - Classic rules (no special options)
  jokers         - Jokers enabled
  eagle_eye      - Jokers + eagle_eye rule
  negative_pairs - Jokers + negative pairs keep value
  four_kind      - Four of a kind bonus
  wolfpack       - Wolfpack bonus
  competitive    - Knock penalty + knock bonus
  wild           - Jokers + lucky_swing + eagle_eye + negative_pairs
  all_bonuses    - All bonus rules enabled
"""
    )

    parser.add_argument(
        "num_games",
        nargs="?",
        default="10",
        help="Number of games to run, or 'detail' for a single detailed game"
    )
    parser.add_argument(
        "num_players",
        nargs="?",
        type=int,
        default=4,
        help="Number of players (default: 4)"
    )
    parser.add_argument(
        "--preset",
        type=str,
        help="Use a named rule preset (e.g., eagle_eye, competitive)"
    )
    parser.add_argument(
        "--rules",
        type=str,
        help="Comma-separated list of rules to enable (e.g., use_jokers,knock_penalty)"
    )
    parser.add_argument(
        "--compare",
        nargs="+",
        metavar="PRESET",
        help="Compare multiple presets side-by-side"
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Reduce output verbosity"
    )

    args = parser.parse_args()

    # Determine options
    options = None
    if args.preset and args.rules:
        parser.error("Cannot use both --preset and --rules")

    if args.preset:
        options = get_preset_options(args.preset)
    elif args.rules:
        options = parse_rules_string(args.rules)

    # Handle compare mode
    if args.compare:
        num_games = int(args.num_games) if args.num_games != "detail" else 100
        compare_rule_sets(args.compare, num_games, args.num_players)
        return

    # Handle detail mode
    if args.num_games == "detail":
        run_detailed_game(args.num_players, options)
        return

    # Standard batch simulation
    num_games = int(args.num_games)
    run_simulation(num_games, args.num_players, options, verbose=not args.quiet)


if __name__ == "__main__":
    main()
