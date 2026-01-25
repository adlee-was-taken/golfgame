# 6-Card Golf Rules

This document defines the canonical rules implemented in this game engine, based on standard 6-Card Golf rules from [Pagat.com](https://www.pagat.com/draw/golf.html) and [Bicycle Cards](https://bicyclecards.com/how-to-play/six-card-golf).

## Overview

Golf is a card game where players try to achieve the **lowest score** over multiple rounds ("holes"). The name comes from golf scoring - lower is better.

## Players & Equipment

- **Players:** 2-6 players
- **Deck:** Standard 52-card deck (optionally with 2 Jokers)
- **Multiple decks:** For 5+ players, use 2 decks

## Setup

1. Dealer shuffles and deals **6 cards face-down** to each player
2. Players arrange cards in a **2 row × 3 column grid**:
   ```
   [0] [1] [2]   ← Top row
   [3] [4] [5]   ← Bottom row
   ```
3. Remaining cards form the **draw pile** (face-down)
4. Top card of draw pile is flipped to start the **discard pile**
5. Each player flips **2 of their cards** face-up (standard rules)

## Card Values

| Card | Points |
|------|--------|
| Ace | 1 |
| 2 | **-2** (negative!) |
| 3-10 | Face value |
| Jack | 10 |
| Queen | 10 |
| King | **0** |
| Joker | -2 |

## Column Pairing

**Critical rule:** If both cards in a column have the **same rank**, that column scores **0 points** regardless of the individual card values.

Example:
```
[K] [5] [7]    K-K pair = 0
[K] [3] [9]    5+3 = 8, 7+9 = 16
               Total: 0 + 8 + 16 = 24
```

**Note:** Paired 2s score 0 (not -4). The pair cancels out, it doesn't double the negative.

## Turn Structure

On your turn:

### 1. Draw Phase
Choose ONE:
- Draw the **top card from the draw pile** (face-down deck)
- Take the **top card from the discard pile** (face-up)

### 2. Play Phase

**If you drew from the DECK:**
- **Swap:** Replace any card in your grid (old card goes to discard face-up)
- **Discard:** Put the drawn card on the discard pile and flip one face-down card

**If you took from the DISCARD PILE:**
- **You MUST swap** - you cannot re-discard the same card
- Replace any card in your grid (old card goes to discard)

### Important Rules

- Swapped cards are always placed **face-up**
- You **cannot look** at a face-down card before deciding to replace it
- When swapping a face-down card, reveal it only as it goes to discard

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

## Winning

- Standard game: **9 rounds** ("9 holes")
- Player with the **lowest total score** wins
- Optionally play 18 rounds for a longer game

---

# House Rules (Optional)

Our implementation supports these optional rule variations:

## Standard Options

| Option | Description | Default |
|--------|-------------|---------|
| `initial_flips` | Cards revealed at start (0, 1, or 2) | 2 |
| `flip_on_discard` | Must flip a card after discarding from deck | Off |
| `knock_penalty` | +10 if you go out but don't have lowest score | Off |
| `use_jokers` | Add Jokers to deck (-2 points each) | Off |

## Point Modifiers

| Option | Effect |
|--------|--------|
| `lucky_swing` | Single Joker worth **-5** (instead of two -2 Jokers) |
| `super_kings` | Kings worth **-2** (instead of 0) |
| `ten_penny` | 10s worth **1** (instead of 10) |

## Bonuses & Penalties

| Option | Effect |
|--------|--------|
| `knock_bonus` | First to reveal all cards gets **-5** bonus |
| `underdog_bonus` | Lowest scorer each round gets **-3** |
| `tied_shame` | Tying another player's score = **+5** penalty to both |
| `blackjack` | Exact score of 21 becomes **0** |

## Special Rules

| Option | Effect |
|--------|--------|
| `eagle_eye` | Jokers worth **+2 unpaired**, **-4 paired** (spot the pair!) |

---

# Game Theory Notes

## Expected Turn Count

With standard rules (2 initial flips):
- Start: 2 face-up, 4 face-down
- Each turn reveals 1 card (swap or discard+flip)
- **Minimum turns to go out:** 4
- **Typical range:** 4-8 turns per player per round

## Strategic Considerations

### Good Cards (keep these)
- **Jokers** (-2 or -5): Best cards in the game
- **2s** (-2): Second best, but don't pair them!
- **Kings** (0): Safe, good for pairing
- **Aces** (1): Low risk

### Bad Cards (replace these)
- **10, J, Q** (10 points): Worst cards
- **8, 9** (8-9 points): High priority to replace

### Pairing Strategy
- Pairing is powerful - column score goes to 0
- **Don't pair negative cards** - you lose the negative benefit
- Target pairs with mid-value cards (3-7) for maximum gain

### When to Go Out
- Go out with **score ≤ 10** when confident you're lowest
- Consider opponent visible cards before going out early
- With `knock_penalty`, be careful - +10 hurts if you're wrong

---

# Test Coverage

The game engine has comprehensive test coverage in `test_game.py`:

- **Card Values:** All 13 ranks verified
- **Column Pairing:** Matching, non-matching, negative card edge cases
- **House Rules:** All scoring modifiers tested
- **Draw/Discard:** Deck draws, discard draws, must-swap rule
- **Turn Flow:** Turn advancement, wrap-around, player validation
- **Round End:** Final turn triggering, one-more-turn logic
- **Multi-Round:** Score accumulation, hand reset

Run tests with:
```bash
pytest test_game.py -v
```
