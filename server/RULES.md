# 6-Card Golf Rules

> **Single Source of Truth** for all game rules, variants, and house rules.
> This document is the canonical reference - all implementations must match these specifications.

## Document Structure

This document follows a **vertical documentation structure**:
1. **Rules** - Human-readable game rules
2. **Implementation** - Code references (file:line)
3. **Tests** - Verification test references
4. **Edge Cases** - Documented edge case behaviors

---

# Part 1: Core Game Rules

## Overview

Golf is a card game where players try to achieve the **lowest score** over multiple rounds ("holes"). The name comes from golf scoring - lower is better.

## Players & Equipment

- **Players:** 2-6 players
- **Deck:** Standard 52-card deck (optionally with 2 Jokers)
- **Multiple decks:** For 5+ players, use 2 decks

| Implementation | File |
|----------------|------|
| Deck creation | `game.py:89-104` |
| Multi-deck support | `game.py:92-103` |

| Tests | File |
|-------|------|
| Standard 52 cards | `test_game.py:501-504` |
| Joker deck 54 cards | `test_game.py:506-509` |
| Multi-deck | `test_game.py:516-519` |

## Setup

1. Dealer shuffles and deals **6 cards face-down** to each player
2. Players arrange cards in a **2 row x 3 column grid**:
   ```
   [0] [1] [2]   <- Top row
   [3] [4] [5]   <- Bottom row
   ```
3. Remaining cards form the **draw pile** (face-down)
4. Top card of draw pile is flipped to start the **discard pile**
5. Each player flips **2 of their cards** face-up (configurable: 0, 1, or 2)

| Implementation | File |
|----------------|------|
| Deal 6 cards | `game.py:304-311` |
| Start discard pile | `game.py:313-317` |
| Initial flip phase | `game.py:326-352` |

| Tests | File |
|-------|------|
| Initial flip 2 cards | `test_game.py:454-469` |
| Initial flip 0 skips phase | `test_game.py:471-478` |
| Game starts after all flip | `test_game.py:480-491` |

---

## Card Values

| Card | Points | Notes |
|------|--------|-------|
| Ace | 1 | Low card |
| **2** | **-2** | Negative! Best non-special card |
| 3-10 | Face value | 3=3, 4=4, ..., 10=10 |
| Jack | 10 | Face card |
| Queen | 10 | Face card |
| **King** | **0** | Zero points |
| **Joker** | **-2** | Negative (requires `use_jokers` option) |

### Card Value Quality Tiers

| Tier | Cards | Strategy |
|------|-------|----------|
| **Excellent** | Joker (-2), 2 (-2) | Always keep, never pair (unless `negative_pairs_keep_value`) |
| **Good** | King (0) | Safe, good for pairing |
| **Good** | J♥, J♠ (0)* | Safe with `one_eyed_jacks` rule |
| **Decent** | Ace (1) | Low risk |
| **Neutral** | 3, 4, 5 | Acceptable |
| **Bad** | 6, 7 | Replace when possible |
| **Terrible** | 8, 9, 10, J♣, J♦, Q | High priority to replace |

*With `one_eyed_jacks` enabled, J♥ and J♠ are worth 0 points.

| Implementation | File |
|----------------|------|
| DEFAULT_CARD_VALUES | `constants.py:3-18` |
| RANK_VALUES derivation | `game.py:40-41` |
| get_card_value() | `game.py:44-67` |

| Tests | File |
|-------|------|
| Ace worth 1 | `test_game.py:29-30` |
| Two worth -2 | `test_game.py:32-33` |
| 3-10 face value | `test_game.py:35-43` |
| Jack worth 10 | `test_game.py:45-46` |
| Queen worth 10 | `test_game.py:48-49` |
| King worth 0 | `test_game.py:51-52` |
| Joker worth -2 | `test_game.py:54-55` |
| Card.value() method | `test_game.py:57-63` |
| Rank quality classification | `test_analyzer.py:47-74` |

---

## Column Pairing

**Critical Rule:** If both cards in a column have the **same rank**, that column scores **0 points** regardless of the individual card values.

### Column Positions
```
Column 0: positions (0, 3)
Column 1: positions (1, 4)
Column 2: positions (2, 5)
```

### Examples

**Matched column:**
```
[K] [5] [7]    K-K pair = 0
[K] [3] [9]    5+3 = 8, 7+9 = 16
               Total: 0 + 8 + 16 = 24
```

**All columns matched:**
```
[A] [5] [K]    All paired = 0 total
[A] [5] [K]
```

### Edge Case: Paired Negative Cards

> **IMPORTANT:** Paired 2s score **0**, not -4. The pair **cancels** the value, it doesn't **double** it.

This is a common source of bugs. When two 2s are paired:
- Individual values: -2 + -2 = -4
- **Paired value: 0** (pair rule overrides)

The same applies to paired Jokers (standard rules) - they score 0, not -4.

| Implementation | File |
|----------------|------|
| Column pair detection | `game.py:158-178` |
| Pair cancels to 0 | `game.py:174-175` |

| Tests | File |
|-------|------|
| Matching column scores 0 | `test_game.py:83-91` |
| All columns matched = 0 | `test_game.py:93-98` |
| No columns matched = sum | `test_game.py:100-106` |
| **Paired 2s = 0 (not -4)** | `test_game.py:108-115` |
| Unpaired negatives keep value | `test_game.py:117-124` |

---

## Turn Structure

### 1. Draw Phase

Choose ONE:
- Draw the **top card from the draw pile** (face-down deck)
- Take the **top card from the discard pile** (face-up)

### 2. Play Phase

**If you drew from the DECK:**
- **Swap:** Replace any card in your grid (old card goes to discard face-up)
- **Discard:** Put the drawn card on the discard pile (optionally flip a face-down card)

**If you took from the DISCARD PILE:**
- **You MUST swap** - you cannot re-discard the same card
- Replace any card in your grid (old card goes to discard)

### Important Rules

- Swapped cards are always placed **face-up**
- You **cannot look** at a face-down card before deciding to replace it
- When swapping a face-down card, reveal it only as it goes to discard

| Implementation | File |
|----------------|------|
| Draw from deck/discard | `game.py:354-384` |
| Swap card | `game.py:409-426` |
| Cannot re-discard from discard | `game.py:428-433`, `game.py:443-445` |
| Discard from deck draw | `game.py:435-460` |
| Flip after discard | `game.py:462-476` |

| Tests | File |
|-------|------|
| Can draw from deck | `test_game.py:200-205` |
| Can draw from discard | `test_game.py:207-214` |
| Can discard deck draw | `test_game.py:216-221` |
| **Cannot discard discard draw** | `test_game.py:223-228` |
| Must swap discard draw | `test_game.py:230-238` |
| Swap makes card face-up | `test_game.py:240-247` |
| Cannot peek before swap | `test_game.py:249-256` |

---

## Round End

### Triggering the Final Turn

When any player has **all 6 cards face-up**, the round enters "final turn" phase.

### Final Turn Phase

- Each **other player** gets exactly **one more turn**
- The player who triggered final turn does NOT get another turn
- After all players have had their final turn, the round ends

### Scoring

1. All remaining face-down cards are revealed
2. Calculate each player's score (with column pairing)
3. Add round score to total score

| Implementation | File |
|----------------|------|
| Check all face-up | `game.py:478-483` |
| Final turn phase | `game.py:488-502` |
| End round scoring | `game.py:504-555` |

| Tests | File |
|-------|------|
| Revealing all triggers final turn | `test_game.py:327-341` |
| Other players get final turn | `test_game.py:343-358` |
| Finisher doesn't get extra turn | `test_game.py:360-373` |
| All cards revealed at round end | `test_game.py:375-388` |

---

## Winning

- Standard game: **9 rounds** ("9 holes")
- Player with the **lowest total score** wins
- Optionally play 18 rounds for a longer game

| Implementation | File |
|----------------|------|
| Multi-round tracking | `game.py:557-567` |
| Total score accumulation | `game.py:548-549` |

| Tests | File |
|-------|------|
| Next round resets hands | `test_game.py:398-418` |
| Scores accumulate across rounds | `test_game.py:420-444` |

---

# Part 2: House Rules

Our implementation supports these optional rule variations. All are **disabled by default**.

## Standard Options

| Option | Description | Default |
|--------|-------------|---------|
| `initial_flips` | Cards revealed at start (0, 1, or 2) | 2 |
| `flip_mode` | What happens when discarding from deck (see below) | `never` |
| `knock_penalty` | +10 if you go out but don't have lowest score | Off |
| `use_jokers` | Add Jokers to deck (-2 points each) | Off |
| `flip_as_action` | Use turn to flip a card instead of drawing | Off |
| `knock_early` | Flip all remaining cards (≤2) to go out early | Off |

### Flip Mode Options

The `flip_mode` setting controls what happens when you draw from the deck and choose to discard (not swap):

| Value | Name | Behavior |
|-------|------|----------|
| `never` | **Standard** | No flip when discarding - your turn ends immediately. This is the classic rule. |
| `always` | **Speed Golf** | Must flip one face-down card when discarding. Accelerates the game by revealing more information each turn. |
| `endgame` | **Endgame** | Flip after discard if any player has 1 hidden card remaining. |

**Standard (never):** When you draw from the deck and choose not to use the card, simply discard it and your turn ends.

**Speed Golf (always):** When you discard from the deck, you must also flip one of your face-down cards. This accelerates the game by revealing more information each turn, leading to faster rounds.

**Endgame:** When any player has only 1 (or 0) face-down cards remaining, discarding from the deck triggers a flip. This accelerates the endgame by revealing more information as rounds approach their conclusion.

| Implementation | File |
|----------------|------|
| GameOptions dataclass | `game.py:200-222` |
| FlipMode enum | `game.py:12-24` |
| flip_on_discard property | `game.py:449-470` |
| flip_is_optional property | `game.py:472-479` |
| skip_flip_and_end_turn() | `game.py:520-540` |

## Point Modifiers

| Option | Effect | Standard Value | Modified Value |
|--------|--------|----------------|----------------|
| `lucky_swing` | Single Joker in deck | 2 Jokers @ -2 each | 1 Joker @ **-5** |
| `super_kings` | Kings are negative | King = 0 | King = **-2** |
| `ten_penny` | 10s are low | 10 = 10 | 10 = **1** |

| Implementation | File |
|----------------|------|
| LUCKY_SWING_JOKER_VALUE | `constants.py:59` |
| SUPER_KINGS_VALUE | `constants.py:57` |
| TEN_PENNY_VALUE | `constants.py:58` |
| WOLFPACK_BONUS | `constants.py:66` |
| FOUR_OF_A_KIND_BONUS | `constants.py:67` |
| Value application | `game.py:58-66` |

| Tests | File |
|-------|------|
| Super Kings -2 | `test_game.py:142-149` |
| Ten Penny | `test_game.py:151-158` |
| Lucky Swing Joker -5 | `test_game.py:160-173` |
| Lucky Swing single joker | `test_game.py:511-514` |

## Bonuses & Penalties

| Option | Effect | When Applied |
|--------|--------|--------------|
| `knock_bonus` | First to reveal all cards gets **-5** | Round end |
| `underdog_bonus` | Lowest scorer each round gets **-3** | Round end |
| `tied_shame` | Tying another player's score = **+5** penalty to both | Round end |
| `blackjack` | Exact score of 21 becomes **0** | Round end |
| `wolfpack` | 2 pairs of Jacks = **-20** bonus | Scoring |
| `four_of_a_kind` | 4 cards of same rank in 2 columns = **-20** bonus | Scoring |

> **Note:** Wolfpack and Four of a Kind stack. Four Jacks = -20 (wolfpack) + -20 (four of a kind) = **-40 total**.

| Implementation | File |
|----------------|------|
| Blackjack 21->0 | `game.py:513-517` |
| Knock penalty | `game.py:519-525` |
| Knock bonus | `game.py:527-531` |
| Underdog bonus | `game.py:533-538` |
| Tied shame | `game.py:540-546` |
| Wolfpack (-20 bonus) | `game.py:180-182` |
| Four of a kind (-20 bonus) | `game.py:192-205` |

| Tests | File |
|-------|------|
| Blackjack 21 becomes 0 | `test_game.py:175-183` |
| House rules integration | `test_house_rules.py` (full file) |

## Special Rules

| Option | Effect |
|--------|--------|
| `eagle_eye` | Jokers worth **+2 unpaired**, **-4 paired** (reward spotting pairs) |

| Implementation | File |
|----------------|------|
| Eagle eye unpaired value | `game.py:60-61` |
| Eagle eye paired value | `game.py:169-173` |

## New Variants

These rules add alternative gameplay options based on traditional Golf variants.

### Flip as Action

Use your turn to flip one of your face-down cards without drawing. Ends your turn immediately.

**Strategic impact:** Lets you gather information without risking a bad deck draw. Conservative players can learn their hand safely. However, you miss the chance to actively improve your hand.

### Four of a Kind

Having 4 cards of the same rank across two columns (two complete column pairs of the same rank) scores a **-20 bonus**.

**Strategic impact:** Rewards collecting matching cards beyond just column pairs. Changes whether you should take a third or fourth copy of a rank. Stacks with Wolfpack: four Jacks = -40 total.

### Negative Pairs Keep Value

When you pair 2s or Jokers in a column, they keep their combined **-4 points** instead of becoming 0.

**Strategic impact:** Major change! Pairing your best cards is now beneficial. Two 2s paired = -4 points, not 0. Encourages hunting for duplicate negative cards.

### One-Eyed Jacks

The Jack of Hearts (J♥) and Jack of Spades (J♠) - the "one-eyed" Jacks - are worth **0 points** instead of 10.

**Strategic impact:** Two of the four Jacks become safe cards, comparable to Kings. J♥ and J♠ are now good cards to keep. Only J♣ and J♦ remain dangerous. Reduces the "Jack disaster" by half.

### Early Knock

If you have **2 or fewer face-down cards**, you may use your turn to flip all remaining cards at once and immediately trigger the end of the round (all other players get one final turn).

**Strategic impact:** High-risk, high-reward option! If you're confident your hidden cards are low, you can knock early to surprise opponents. But if those hidden cards are bad, you've just locked in a terrible score. Best used when you've deduced your face-down cards are safe.

| Implementation | File |
|----------------|------|
| GameOptions new fields | `game.py:450-459` |
| flip_card_as_action() | `game.py:936-962` |
| knock_early() | `game.py:963-1010` |
| One-eyed Jacks value | `game.py:65-67` |
| Four of a kind scoring | `game.py:192-205` |
| Negative pairs scoring | `game.py:169-185` |

---

# Part 3: AI Decision Making

## AI Profiles

8 distinct AI personalities with different play styles:

| Name | Style | Swap Threshold | Pair Hope | Aggression |
|------|-------|----------------|-----------|------------|
| Sofia | Calculated & Patient | 4 | 0.2 | 0.2 |
| Maya | Aggressive Closer | 6 | 0.4 | 0.85 |
| Priya | Pair Hunter | 7 | 0.8 | 0.5 |
| Marcus | Steady Eddie | 5 | 0.35 | 0.4 |
| Kenji | Risk Taker | 8 | 0.7 | 0.75 |
| Diego | Chaotic Gambler | 6 | 0.5 | 0.6 |
| River | Adaptive Strategist | 5 | 0.45 | 0.55 |
| Sage | Sneaky Finisher | 5 | 0.3 | 0.9 |

| Implementation | File |
|----------------|------|
| CPUProfile dataclass | `ai.py:164-182` |
| CPU_PROFILES list | `ai.py:186-253` |

## Key AI Decision Functions

### should_knock_early()

Decides whether to use the knock_early action to flip all remaining cards at once.

**Logic priority:**
1. Only consider if knock_early rule is enabled and player has 1-2 face-down cards
2. Aggressive players with good visible scores are more likely to knock
3. Consider opponent scores and game phase
4. Factor in personality profile aggression

### should_use_flip_action()

Decides whether to use flip_as_action instead of drawing (information gathering).

**Logic priority:**
1. Only consider if flip_as_action rule is enabled
2. Don't use if discard pile has a good card we want
3. Conservative players (low aggression) prefer this safe option
4. Prioritize positions where column partner is visible (pair info)

### should_take_discard()

Decides whether to take from discard pile or draw from deck.

**Logic priority:**
1. Always take Jokers (and pair if Eagle Eye)
2. Always take Kings
3. Always take one-eyed Jacks (J♥, J♠) if rule enabled
4. Take 10s if ten_penny enabled
5. Take cards that complete a column pair (**except negative cards**, unless `negative_pairs_keep_value`)
6. Take low cards based on game phase threshold
7. Consider four_of_a_kind potential when collecting ranks
8. Consider end-game pressure
9. Take if we have worse visible cards

| Implementation | File |
|----------------|------|
| should_take_discard() | `ai.py:333-412` |
| Negative card pair avoidance | `ai.py:365-374` |

| Tests | File |
|-------|------|
| Maya doesn't take 10 with good hand | `test_maya_bug.py:52-83` |
| Unpredictability doesn't take bad cards | `test_maya_bug.py:85-116` |
| Pair potential respected | `test_maya_bug.py:289-315` |

### choose_swap_or_discard()

Decides whether to swap the drawn card into hand or discard it.

**Logic priority:**
1. Eagle Eye: Pair Jokers if visible match exists
2. Check for column pair opportunity (**except negative cards**)
3. Find best swap among BAD face-up cards (positive value)
4. Consider Blackjack (21) pursuit
5. Swap excellent cards into face-down positions
6. Apply profile-based thresholds

**Critical:** When placing cards into face-down positions, the AI must avoid creating wasteful pairs with visible negative cards.

| Implementation | File |
|----------------|------|
| choose_swap_or_discard() | `ai.py:414-536` |
| Negative card pair avoidance | `ai.py:441-446` |

| Tests | File |
|-------|------|
| Don't discard excellent cards | `test_maya_bug.py:179-209` |
| Full Maya bug scenario | `test_maya_bug.py:211-254` |

---

# Part 4: Edge Cases & Known Issues

## Edge Case: Pairing Negative Cards

**Problem:** Pairing 2s or Jokers wastes their negative value.
- Unpaired 2: contributes -2 to score
- Paired 2s: contribute 0 to score (lost 2 points!)

**AI Safeguards:**
1. `should_take_discard()`: Only considers pairing if `discard_value > 0`
2. `choose_swap_or_discard()`: Sets `should_pair = drawn_value > 0`
3. `filter_bad_pair_positions()`: Filters out positions that would create wasteful pairs when placing negative cards into face-down positions

| Implementation | File |
|----------------|------|
| get_column_partner_position() | `ai.py:163-168` |
| filter_bad_pair_positions() | `ai.py:171-213` |
| Applied in choose_swap_or_discard | `ai.py:517`, `ai.py:538` |
| Applied in forced swap | `ai.py:711-713` |

| Tests | File |
|-------|------|
| Paired 2s = 0 (game logic) | `test_game.py:108-115` |
| AI avoids pairing logic | `ai.py:365-374`, `ai.py:441-446` |
| Filter with visible two | `test_maya_bug.py:320-347` |
| Filter allows positive pairs | `test_maya_bug.py:349-371` |
| Choose swap avoids 2 pairs | `test_maya_bug.py:373-401` |
| Forced swap avoids 2 pairs | `test_maya_bug.py:403-425` |
| Fallback when all bad | `test_maya_bug.py:427-451` |

## Edge Case: Forced Swap from Discard

When drawing from discard pile and `choose_swap_or_discard()` returns `None` (discard), the AI is forced to swap anyway. The fallback picks randomly from face-down positions, or finds the worst face-up card.

| Implementation | File |
|----------------|------|
| Forced swap fallback | `ai.py:665-686` |

| Tests | File |
|-------|------|
| Forced swap uses house rules | `test_maya_bug.py:143-177` |
| All face-up finds worst | `test_maya_bug.py:260-287` |

## Edge Case: Deck Exhaustion

When the deck is empty, the discard pile (except top card) is reshuffled back into the deck.

| Implementation | File |
|----------------|------|
| Reshuffle discard pile | `game.py:386-407` |

## Edge Case: Empty Discard Pile

Cannot draw from empty discard pile.

| Tests | File |
|-------|------|
| Empty discard returns None | `test_game.py:558-569` |

---

# Part 5: Test Coverage Summary

## Test Files

| File | Tests | Focus |
|------|-------|-------|
| `test_game.py` | 44 | Core game rules |
| `test_house_rules.py` | 10+ | House rule integration |
| `test_analyzer.py` | 18 | AI decision evaluation |
| `test_maya_bug.py` | 18 | Bug regression & AI edge cases |

**Total: 83+ tests**

## Coverage by Category

| Category | Tests | Files | Status |
|----------|-------|-------|--------|
| Card Values | 8 | `test_game.py`, `test_analyzer.py` | Complete |
| Column Pairing | 5 | `test_game.py` | Complete |
| House Rules Scoring | 4 | `test_game.py` | Complete |
| Draw/Discard Mechanics | 7 | `test_game.py` | Complete |
| Turn Flow | 4 | `test_game.py` | Complete |
| Round End | 4 | `test_game.py` | Complete |
| Multi-Round | 2 | `test_game.py` | Complete |
| Initial Flip | 3 | `test_game.py` | Complete |
| Deck Management | 4 | `test_game.py` | Complete |
| Edge Cases | 3 | `test_game.py` | Complete |
| Take Discard Evaluation | 6 | `test_analyzer.py` | Complete |
| Swap Evaluation | 6 | `test_analyzer.py` | Complete |
| House Rules Evaluation | 2 | `test_analyzer.py` | Complete |
| Maya Bug Regression | 6 | `test_maya_bug.py` | Complete |
| AI Edge Cases | 3 | `test_maya_bug.py` | Complete |
| Bad Pair Avoidance | 5 | `test_maya_bug.py` | Complete |

## Test Plan: Critical Paths

### Game State Transitions

```
WAITING -> INITIAL_FLIP -> PLAYING -> FINAL_TURN -> ROUND_OVER -> GAME_OVER
                |                         ^
                v (initial_flips=0)       |
                +-------------------------+
```

| Transition | Trigger | Tests |
|------------|---------|-------|
| WAITING -> INITIAL_FLIP | start_game() | `test_game.py:454-469` |
| WAITING -> PLAYING | start_game(initial_flips=0) | `test_game.py:471-478` |
| INITIAL_FLIP -> PLAYING | All players flip | `test_game.py:480-491` |
| PLAYING -> FINAL_TURN | Player all face-up | `test_game.py:327-341` |
| FINAL_TURN -> ROUND_OVER | All final turns done | `test_game.py:343-358` |
| ROUND_OVER -> PLAYING | start_next_round() | `test_game.py:398-418` |
| ROUND_OVER -> GAME_OVER | Final round complete | `test_game.py:420-444` |

### AI Decision Tree

```
Draw Phase:
  ├── should_knock_early() returns True (if knock_early enabled, ≤2 face-down)
  │   └── Knock early - flip all remaining cards, trigger final turn
  ├── should_use_flip_action() returns position (if flip_as_action enabled)
  │   └── Flip card at position, end turn
  ├── should_take_discard() returns True
  │   └── Draw from discard pile
  │       └── MUST swap (can_discard_drawn=False)
  └── should_take_discard() returns False
      └── Draw from deck
          ├── choose_swap_or_discard() returns position
          │   └── Swap at position
          └── choose_swap_or_discard() returns None
              └── Discard drawn card
                  └── flip_on_discard?
                      ├── flip_mode="always" -> MUST flip (choose_flip_after_discard)
                      └── flip_mode="endgame" -> should_skip_optional_flip()?
                          ├── True -> skip flip, end turn
                          └── False -> flip (choose_flip_after_discard)
```

| Decision Point | Tests |
|----------------|-------|
| Take Joker/King from discard | `test_analyzer.py:96-114` |
| Don't take bad cards | `test_maya_bug.py:52-116` |
| Swap excellent cards | `test_maya_bug.py:179-209` |
| Avoid pairing negatives | `test_maya_bug.py:320-451` |
| Forced swap from discard | `test_maya_bug.py:143-177`, `test_maya_bug.py:403-425` |

### Scoring Edge Cases

| Scenario | Expected | Test |
|----------|----------|------|
| Paired 2s (standard) | 0 (not -4) | `test_game.py:108-115` |
| Paired 2s (negative_pairs_keep_value) | -4 | `game.py:169-185` |
| Paired Jokers (standard) | 0 | Implicit |
| Paired Jokers (eagle_eye) | -4 | `game.py:169-173` |
| Paired Jokers (negative_pairs_keep_value) | -4 | `game.py:169-185` |
| Unpaired negative cards | -2 each | `test_game.py:117-124` |
| All columns matched | 0 total | `test_game.py:93-98` |
| Blackjack (21) | 0 | `test_game.py:175-183` |
| One-eyed Jacks (J♥, J♠) | 0 (with rule) | `game.py:65-67` |
| Four of a kind | -20 bonus | `game.py:192-205` |
| Wolfpack (4 Jacks) | -20 bonus | `game.py:180-182` |
| Four Jacks + Four of a Kind | -40 total | Stacks |

## Running Tests

```bash
# Run all tests
cd server && python -m pytest -v

# Run specific test file
python -m pytest test_game.py -v

# Run specific test class
python -m pytest test_game.py::TestCardValues -v

# Run with coverage
python -m pytest --cov=. --cov-report=html

# Run tests matching pattern
python -m pytest -k "pair" -v
```

## Test Quality Checklist

- [x] All card values verified against RULES.md
- [x] Column pairing logic tested (including negatives)
- [x] House rules tested individually
- [x] Draw/discard constraints enforced
- [x] Turn flow and player validation
- [x] Round end and final turn logic
- [x] Multi-round score accumulation
- [x] AI decision quality evaluation
- [x] Bug regression tests for Maya bug
- [x] AI avoids wasteful negative card pairs

## Disadvantageous Moves (AI Quality Metrics)

### Definition: "Dumb Moves"

Moves that are objectively suboptimal and should occur at **minimal background noise level** (< 1% of opportunities).

| Move Type | Severity | Expected Prevalence | Test Coverage |
|-----------|----------|---------------------|---------------|
| **Discarding Joker/2** | Blunder | 0% | `test_maya_bug.py:179-209` |
| **Discarding King** | Mistake | 0% | `test_analyzer.py:183-192` |
| **Taking 10/J/Q without pair** | Blunder | 0% | `test_maya_bug.py:52-116` |
| **Pairing negative cards** | Mistake | 0% | `test_maya_bug.py:373-401` |
| **Swapping good card for bad** | Mistake | 0% | `test_analyzer.py:219-237` |

### Definition: "Questionable Moves"

Moves that may be suboptimal but have legitimate strategic reasons. Should be < 5% of opportunities.

| Move Type | When Acceptable | Monitoring |
|-----------|-----------------|------------|
| Not taking low card (3-5) | Pair hunting, early game | Profile-based |
| Discarding medium card (4-6) | Full hand, pair potential | Context check |
| Going out with high score | Pressure, knock_bonus | Threshold based |

### AI Quality Assertions

These assertions should pass when running extended simulations:

```python
# In test suite or simulation
def test_ai_quality_metrics():
    """Run N games and verify dumb moves are at noise level."""
    stats = run_simulation(games=1000)

    # ZERO tolerance blunders
    assert stats.discarded_jokers == 0
    assert stats.discarded_twos == 0
    assert stats.took_bad_card_without_pair == 0
    assert stats.paired_negative_cards == 0

    # Near-zero tolerance mistakes
    assert stats.discarded_kings < stats.total_turns * 0.001  # < 0.1%
    assert stats.swapped_good_for_bad < stats.total_turns * 0.001

    # Acceptable variance
    assert stats.questionable_moves < stats.total_turns * 0.05  # < 5%
```

### Tracking Implementation

Decision quality should be logged for analysis:

| Field | Description |
|-------|-------------|
| `decision_type` | take_discard, swap, discard, flip |
| `decision_quality` | OPTIMAL, GOOD, QUESTIONABLE, MISTAKE, BLUNDER |
| `expected_value` | EV calculation for the decision |
| `profile_name` | AI personality that made decision |
| `game_phase` | early, mid, late |

See `game_analyzer.py` for decision evaluation logic.

## Recommended Additional Tests

| Area | Description | Priority |
|------|-------------|----------|
| AI Quality Metrics | Simulation-based dumb move detection | **Critical** |
| WebSocket | Integration tests for real-time communication | High |
| Concurrent games | Multiple simultaneous rooms | Medium |
| Deck exhaustion | Reshuffle when deck empty | Medium |
| All house rule combos | Interaction between rules | Medium |
| AI personality variance | Verify distinct behaviors | Low |
| Performance | Load testing with many players | Low |

---

# Part 6: Strategic Notes

## Card Priority (for AI and Players)

### Always Keep
- **Jokers** (-2 or -5): Best cards in game
- **2s** (-2): Second best, but **don't pair them!**

### Keep When Possible
- **Kings** (0): Safe, excellent for pairing
- **Aces** (1): Low risk

### Replace When Possible
- **6, 7** (6-7 points): Moderate priority
- **8, 9** (8-9 points): High priority
- **10, J, Q** (10 points): Highest priority

## Pairing Strategy

- Pairing is powerful - column score goes to 0
- **Never pair negative cards** (2s, Jokers) - you lose the negative benefit
- Target pairs with mid-value cards (3-7) for maximum gain
- High-value pairs (10, J, Q) are valuable (+20 point swing)

## When to Go Out

- Go out with **score <= 10** when confident you're lowest
- Consider opponent visible cards before going out early
- With `knock_penalty`, be careful - +10 hurts if you're wrong
- With `knock_bonus`, more incentive to finish first

---

# Part 7: Configuration

## Configuration Files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Project metadata, dependencies, tool config |
| `server/config.py` | Centralized configuration loader |
| `server/constants.py` | Card values and game constants |
| `.env.example` | Environment variable documentation |
| `.env` | Local environment overrides (not committed) |

## Environment Variables

Configuration precedence (highest to lowest):
1. Environment variables
2. `.env` file
3. Default values in code

### Server Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Host to bind to |
| `PORT` | `8000` | Port to listen on |
| `DEBUG` | `false` | Enable debug mode |
| `LOG_LEVEL` | `INFO` | Logging level |
| `DATABASE_URL` | `sqlite:///games.db` | Database connection |

### Room Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_PLAYERS_PER_ROOM` | `6` | Max players per game |
| `ROOM_TIMEOUT_MINUTES` | `60` | Inactive room cleanup |
| `ROOM_CODE_LENGTH` | `4` | Room code length |

### Game Defaults

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_ROUNDS` | `9` | Rounds per game |
| `DEFAULT_INITIAL_FLIPS` | `2` | Cards to flip at start |
| `DEFAULT_USE_JOKERS` | `false` | Enable jokers |
| `DEFAULT_FLIP_MODE` | `never` | Flip mode: `never`, `always`, or `endgame` |

### Security

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | (empty) | Secret key for sessions |
| `INVITE_ONLY` | `false` | Require invitation to register |
| `ADMIN_EMAILS` | (empty) | Comma-separated admin emails |

## Running the Server

```bash
# Development (with auto-reload)
DEBUG=true python server/main.py

# Production
PORT=8080 LOG_LEVEL=WARNING python server/main.py

# With .env file
cp .env.example .env
# Edit .env as needed
python server/main.py

# Using uvicorn directly
uvicorn server.main:app --host 0.0.0.0 --port 8000
```

---

# Part 8: Authentication

## Overview

The authentication system supports:
- User accounts stored in SQLite (`users` table)
- Admin accounts that can manage other users
- Invite codes (or room codes) for registration
- Session-based authentication with bearer tokens

## First-Time Setup

When the server starts with no admin accounts:
1. A default `admin` account is created (or accounts for each email in `ADMIN_EMAILS`)
2. The admin account has **no password** initially
3. On first login attempt, use `/api/auth/setup-password` to set the password

```bash
# Check if admin needs setup
curl http://localhost:8000/api/auth/check-setup/admin

# Set admin password (first time only)
curl -X POST http://localhost:8000/api/auth/setup-password \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "new_password": "your-secure-password"}'
```

## API Endpoints

### Public Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/check-setup/{username}` | GET | Check if user needs password setup |
| `/api/auth/setup-password` | POST | Set password (first login only) |
| `/api/auth/login` | POST | Login with username/password |
| `/api/auth/register` | POST | Register with invite code |
| `/api/auth/logout` | POST | Logout current session |

### Authenticated Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/me` | GET | Get current user info |
| `/api/auth/password` | PUT | Change own password |

### Admin Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/admin/users` | GET | List all users |
| `/api/admin/users/{id}` | GET | Get user by ID |
| `/api/admin/users/{id}` | PUT | Update user |
| `/api/admin/users/{id}/password` | PUT | Change user password |
| `/api/admin/users/{id}` | DELETE | Deactivate user |
| `/api/admin/invites` | POST | Create invite code |
| `/api/admin/invites` | GET | List invite codes |
| `/api/admin/invites/{code}` | DELETE | Deactivate invite code |

## Registration Flow

1. User obtains an invite code (from admin) or a room code (from active game)
2. User calls `/api/auth/register` with username, password, and invite code
3. If valid, account is created and session token is returned

```bash
# Register with room code
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "player1", "password": "pass123", "invite_code": "ABCD"}'
```

## Authentication Header

After login, include the token in requests:

```
Authorization: Bearer <token>
```

## Database Schema

```sql
-- Users table
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE,
    password_hash TEXT NOT NULL,  -- SHA-256 with salt
    role TEXT DEFAULT 'user',     -- 'user' or 'admin'
    created_at TIMESTAMP,
    last_login TIMESTAMP,
    is_active BOOLEAN DEFAULT 1,
    invited_by TEXT
);

-- Sessions table
CREATE TABLE sessions (
    token TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id),
    created_at TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);

-- Invite codes table
CREATE TABLE invite_codes (
    code TEXT PRIMARY KEY,
    created_by TEXT REFERENCES users(id),
    created_at TIMESTAMP,
    expires_at TIMESTAMP,
    max_uses INTEGER DEFAULT 1,
    use_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT 1
);
```

| Implementation | File |
|----------------|------|
| AuthManager class | `auth.py:87-460` |
| User model | `auth.py:27-50` |
| Password hashing | `auth.py:159-172` |
| Session management | `auth.py:316-360` |

| Tests | File |
|-------|------|
| User creation | `test_auth.py:22-60` |
| Authentication | `test_auth.py:63-120` |
| Invite codes | `test_auth.py:123-175` |
| Admin functions | `test_auth.py:178-220` |

---

*Last updated: Document generated from codebase analysis*
*Reference implementations: config.py, constants.py, game.py, ai.py, auth.py*
*Test suites: test_game.py, test_house_rules.py, test_analyzer.py, test_maya_bug.py, test_auth.py*
