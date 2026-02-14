# Plan 2: ai.py Refactor

## Overview

`ai.py` is 1,978 lines with a single function (`choose_swap_or_discard`) at **666 lines** and cyclomatic complexity 50+. The goal is to decompose it into testable, understandable pieces without changing any AI behavior.

Key constraint: **AI behavior must remain identical.** This is pure structural refactoring. We can validate with `python server/simulate.py 500` before and after - stats should match within normal variance.

---

## The Problem Functions

| Function | Lines | What It Does |
|----------|-------|-------------|
| `choose_swap_or_discard()` | ~666 | Decides which position (0-5) to swap drawn card into, or None to discard |
| `calculate_swap_score()` | ~240 | Scores a single position for swapping |
| `should_take_discard()` | ~160 | Decides whether to take from discard pile |
| `process_cpu_turn()` | ~240 | Orchestrates a full CPU turn with timing |

---

## Refactoring Plan

### Step 1: Extract Named Constants

Create section at top of `ai.py` (or a separate `ai_constants.py` if preferred):

```python
# =============================================================================
# AI Decision Constants
# =============================================================================

# Expected value of an unknown (face-down) card, based on deck distribution
EXPECTED_HIDDEN_VALUE = 4.5

# Pessimistic estimate for hidden cards (used in go-out safety checks)
PESSIMISTIC_HIDDEN_VALUE = 6.0

# Conservative estimate (used by conservative personality)
CONSERVATIVE_HIDDEN_VALUE = 2.5

# Cards at or above this value should never be swapped into unknown positions
HIGH_CARD_THRESHOLD = 8

# Maximum card value for unpredictability swaps
UNPREDICTABLE_MAX_VALUE = 7

# Pair potential discount when adjacent card matches
PAIR_POTENTIAL_DISCOUNT = 0.25

# Blackjack target score
BLACKJACK_TARGET = 21

# Base acceptable score range for go-out decisions
GO_OUT_SCORE_BASE = 12
GO_OUT_SCORE_MAX = 20
```

**Locations to update:** ~30 magic number sites across the file. Each becomes a named reference.

### Step 2: Extract Column/Pair Utility Functions

The "iterate columns, check pairs" pattern appears 8+ times. Create shared utilities:

```python
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
            # Pair cancels (with house rule exceptions)
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


def known_score(player: Player, options: GameOptions) -> int:
    """Calculate score from face-up cards only, using EXPECTED_HIDDEN_VALUE for unknowns."""
    # Centralized version of the repeated estimation logic
    ...
```

This replaces duplicated loops at roughly lines: 679, 949, 1002, 1053, 1145, 1213, 1232.

### Step 3: Decompose `choose_swap_or_discard()`

Break into focused sub-functions. The current flow is roughly:

1. **Go-out safety check** (lines ~1087-1186) - "I'm about to go out, pick the best swap to minimize my score"
2. **Score all 6 positions** (lines ~1190-1270) - Calculate swap benefit for each position
3. **Filter and rank candidates** (lines ~1270-1330) - Safety filters, personality tie-breaking
4. **Blackjack special case** (lines ~1330-1380) - If blackjack rule enabled, check for 21
5. **Endgame safety** (lines ~1380-1410) - Don't swap 8+ into unknowns in endgame
6. **Denial logic** (lines ~1410-1480) - Block opponent by taking their useful cards

Proposed decomposition:

```python
def choose_swap_or_discard(player, drawn_card, profile, game, ...) -> Optional[int]:
    """Main orchestrator - delegates to focused sub-functions."""

    # Check if we should force a go-out swap
    go_out_pos = _check_go_out_swap(player, drawn_card, profile, game, ...)
    if go_out_pos is not None:
        return go_out_pos

    # Score all positions
    candidates = _score_all_positions(player, drawn_card, profile, game, ...)

    # Apply filters and select best
    best = _select_best_candidate(candidates, player, drawn_card, profile, game, ...)

    if best is not None:
        return best

    # Try denial as fallback
    return _check_denial_swap(player, drawn_card, profile, game, ...)


def _check_go_out_swap(player, drawn_card, profile, game, ...) -> Optional[int]:
    """If player is close to going out, find the best position to minimize final score.

    Handles:
    - All-but-one face-up: find the best slot for the drawn card
    - Acceptable score threshold based on game state and personality
    - Pair completion opportunities
    """
    # Lines ~1087-1186 of current choose_swap_or_discard
    ...


def _score_all_positions(player, drawn_card, profile, game, ...) -> list[tuple[int, float]]:
    """Calculate swap benefit score for each of the 6 positions.

    Returns list of (position, score) tuples, sorted by score descending.
    Each score represents how much the swap improves the player's hand.
    """
    # Lines ~1190-1270 - calls calculate_swap_score() for each position
    ...


def _select_best_candidate(candidates, player, drawn_card, profile, game, ...) -> Optional[int]:
    """From scored candidates, apply personality modifiers and safety filters.

    Handles:
    - Minimum improvement threshold
    - Personality tie-breaking (pair_hunter prefers pair columns, etc.)
    - Unpredictability (occasional random choice with value threshold)
    - High-card safety filter (never swap 8+ into hidden positions)
    - Blackjack special case (swap to reach exactly 21)
    - Endgame safety (discard 8+ rather than force into unknown)
    """
    # Lines ~1270-1410
    ...


def _check_denial_swap(player, drawn_card, profile, game, ...) -> Optional[int]:
    """Check if we should swap to deny opponents a useful card.

    Only triggers for profiles with denial_aggression > 0.
    Skips hidden positions for high cards (8+).
    """
    # Lines ~1410-1480
    ...
```

### Step 4: Simplify `calculate_swap_score()`

Currently ~240 lines. Some of its complexity comes from inlined pair calculations and standings pressure. Extract:

```python
def _pair_improvement(player, position, new_card, options) -> float:
    """Calculate pair-related benefit of swapping into this position."""
    # Would the swap create a new pair? Break an existing pair?
    ...

def _standings_pressure(player, game) -> float:
    """Calculate how much standings position should affect decisions."""
    # Shared between calculate_swap_score and should_take_discard
    ...
```

### Step 5: Simplify `should_take_discard()`

Currently ~160 lines. Much of the complexity is from re-deriving information that `calculate_swap_score` also computes. After Step 2's utilities exist, this should shrink significantly since `project_score()` and `known_score()` handle the repeated estimation logic.

### Step 6: Clean up `process_cpu_turn()`

Currently ~240 lines. This function is the CPU turn orchestrator and is mostly fine structurally, but has some inline logic for:
- Flip-as-action decisions (~30 lines)
- Knock-early decisions (~30 lines)
- Game logging (~20 lines repeated twice)

Extract:
```python
def _should_flip_as_action(player, game, profile) -> Optional[int]:
    """Decide whether to use flip-as-action and which position."""
    ...

def _should_knock_early(player, game, profile) -> bool:
    """Decide whether to knock early."""
    ...

def _log_cpu_action(game_id, player, action, card=None, position=None, reason=""):
    """Log a CPU action if logger is available."""
    ...
```

---

## Execution Order

1. **Step 1** (constants) - Safe, mechanical, reduces cognitive load immediately
2. **Step 2** (utilities) - Foundation for everything else
3. **Step 3** (decompose choose_swap_or_discard) - The big win
4. **Step 4** (simplify calculate_swap_score) - Benefits from Step 2 utilities
5. **Step 5** (simplify should_take_discard) - Benefits from Step 2 utilities
6. **Step 6** (clean up process_cpu_turn) - Lower priority

**Run `python server/simulate.py 500` before Step 1 and after each step to verify identical behavior.**

---

## Validation Strategy

```bash
# Before any changes - capture baseline
python server/simulate.py 500 > /tmp/ai_baseline.txt

# After each step
python server/simulate.py 500 > /tmp/ai_after_stepN.txt

# Compare key metrics:
# - Average scores per personality
# - "Swapped 8+ into unknown" rate (should stay < 0.1%)
# - Win rate distribution
```

---

## Files Touched

- `server/ai.py` - major restructuring (same file, new internal organization)
- No new files needed (all changes within ai.py unless we decide to split constants out)

## Risk Assessment

- **Low risk** if done mechanically (cut-paste into functions, update call sites)
- **Medium risk** if we accidentally change conditional logic order or miss an early return
- Simulation tests are the safety net - run after every step
