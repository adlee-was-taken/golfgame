# Animation Flow Reference

Complete reference for how card animations are triggered, sequenced, and cleaned up.
All animations use anime.js via the `CardAnimations` class (`client/card-animations.js`).
Timing is configured in `client/timing-config.js`.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Animation Flags](#animation-flags)
3. [Flow 1: Local Player Draws from Deck](#flow-1-local-player-draws-from-deck)
4. [Flow 2: Local Player Draws from Discard](#flow-2-local-player-draws-from-discard)
5. [Flow 3: Local Player Swaps](#flow-3-local-player-swaps)
6. [Flow 4: Local Player Discards](#flow-4-local-player-discards)
7. [Flow 5: Opponent Draws from Deck then Swaps](#flow-5-opponent-draws-from-deck-then-swaps)
8. [Flow 6: Opponent Draws from Deck then Discards](#flow-6-opponent-draws-from-deck-then-discards)
9. [Flow 7: Opponent Draws from Discard then Swaps](#flow-7-opponent-draws-from-discard-then-swaps)
10. [Flow 8: Initial Card Flip](#flow-8-initial-card-flip)
11. [Flow 9: Deal Animation](#flow-9-deal-animation)
12. [Flow 10: Round End Reveal](#flow-10-round-end-reveal)
13. [Flag Lifecycle Summary](#flag-lifecycle-summary)
14. [Safety Clears](#safety-clears)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        app.js                                │
│                                                              │
│  User Click / WebSocket ──► triggerAnimationsForStateChange  │
│         │                           │                        │
│         ▼                           ▼                        │
│   Set flags ──────────────► CardAnimations method            │
│         │                           │                        │
│         ▼                           ▼                        │
│   renderGame() skips        anime.js timeline runs           │
│   flagged elements                  │                        │
│         │                           ▼                        │
│         │                    Callback fires                   │
│         │                           │                        │
│         ▼                           ▼                        │
│   Flags cleared ◄──────── renderGame() called                │
│         │                                                    │
│         ▼                                                    │
│   Normal rendering resumes                                   │
└─────────────────────────────────────────────────────────────┘
```

**Key principle:** Flags block `renderGame()` from updating the DOM while animations are in flight. The animation callback clears flags and triggers a fresh render.

---

## Animation Flags

Flags in `app.js` that prevent `renderGame()` from updating the discard pile or held card during animations:

| Flag | Type | Blocks | Purpose |
|------|------|--------|---------|
| `isDrawAnimating` | bool | Discard pile, held card | Draw animation in progress |
| `localDiscardAnimating` | bool | Discard pile | Local player discarding drawn card |
| `opponentDiscardAnimating` | bool | Discard pile | Opponent discarding without swap |
| `opponentSwapAnimation` | object/null | Discard pile, turn indicator | Opponent swap `{ playerId, position }` |
| `dealAnimationInProgress` | bool | Flip prompts | Deal animation running |
| `swapAnimationInProgress` | bool | Game state application | Local swap — defers incoming state |

**renderGame() skip logic:**
```
if (localDiscardAnimating OR opponentSwapAnimation OR
    opponentDiscardAnimating OR isDrawAnimating):
    → skip discard pile update
```

---

## Flow 1: Local Player Draws from Deck

**Trigger:** User clicks deck

```
User clicks deck
       │
       ▼
  drawFromDeck()
  ├─ Validate: isMyTurn(), no drawnCard
  └─ Send: { type: 'draw', source: 'deck' }
       │
       ▼
  Server responds: 'card_drawn'
  ├─ Store drawnCard, drawnFromDiscard=false
  ├─ Clear stale flags (opponentSwap, opponentDiscard)
  ├─ SET isDrawAnimating = true
  └─ hideDrawnCard()
       │
       ▼
  cardAnimations.animateDrawDeck(card, callback)
       │
       ├─ Pulse deck (gold ring)
       ├─ Wait pulseDelay (200ms)
       │
       ▼
  _animateDrawDeckCard() timeline:
  ┌─────────────────────────────────────────┐
  │ 1. Lift off deck     (120ms, lift ease) │
  │    translateY: -15, rotate wobble       │
  │                                         │
  │ 2. Move to hold pos  (250ms, move ease) │
  │    left/top to holdingRect              │
  │                                         │
  │ 3. Brief pause       (80ms)             │
  │                                         │
  │ 4. Flip to reveal    (320ms, flip ease) │
  │    rotateY: 180→0, play flip sound      │
  │                                         │
  │ 5. View pause        (120ms)            │
  └─────────────────────────────────────────┘
       │
       ▼
  Callback:
  ├─ CLEAR isDrawAnimating = false
  ├─ displayHeldCard(card) with popIn
  ├─ renderGame()
  └─ Show toast: "Swap with a card or discard"
```

**Total animation time:** ~200 + 120 + 250 + 80 + 320 + 120 = ~1090ms

---

## Flow 2: Local Player Draws from Discard

**Trigger:** User clicks discard pile

```
User clicks discard
       │
       ▼
  drawFromDiscard()
  ├─ Validate: isMyTurn(), no drawnCard, discard_top exists
  └─ Send: { type: 'draw', source: 'discard' }
       │
       ▼
  Server responds: 'card_drawn'
  ├─ Store drawnCard, drawnFromDiscard=true
  ├─ Clear stale flags
  ├─ SET isDrawAnimating = true
  └─ hideDrawnCard()
       │
       ▼
  cardAnimations.animateDrawDiscard(card, callback)
       │
       ├─ Pulse discard (gold ring)
       ├─ Wait pulseDelay (200ms)
       │
       ▼
  _animateDrawDiscardCard() timeline:
  ┌─────────────────────────────────────────┐
  │ Hide actual discard pile (opacity: 0)   │
  │                                         │
  │ 1. Quick lift         (80ms, lift ease) │
  │    translateY: -12, scale: 1.05         │
  │                                         │
  │ 2. Move to hold pos  (200ms, move ease) │
  │    left/top to holdingRect              │
  │                                         │
  │ 3. Brief settle       (60ms)            │
  └─────────────────────────────────────────┘
       │
       ▼
  Callback:
  ├─ Restore discard pile opacity
  ├─ CLEAR isDrawAnimating = false
  ├─ displayHeldCard(card) with popIn
  ├─ renderGame()
  └─ Show toast: "Swap with a card or discard"
```

**Total animation time:** ~200 + 80 + 200 + 60 = ~540ms

---

## Flow 3: Local Player Swaps

**Trigger:** User clicks hand card while holding a drawn card

```
User clicks hand card (position N)
       │
       ▼
  handleCardClick(position)
  └─ drawnCard exists → animateSwap(position)
       │
       ▼
  animateSwap(position)
  ├─ SET swapAnimationInProgress = true
  ├─ Hide originals (swap-out class, visibility:hidden)
  ├─ Store drawnCard, clear this.drawnCard
  ├─ SET skipNextDiscardFlip = true
  └─ Send: { type: 'swap', position }
       │
       ├──────────────────────────────────┐
       │ Face-up card?                    │ Face-down card?
       ▼                                  ▼
  Card data known                    Store pendingSwapData
  immediately                        Wait for server response
       │                                  │
       │                                  ▼
       │                           Server: 'game_state'
       │                           ├─ Detect swapAnimationInProgress
       │                           ├─ Store pendingGameState
       │                           └─ updateSwapAnimation(discard_top)
       │                                  │
       ▼──────────────────────────────────▼
  cardAnimations.animateUnifiedSwap()
       │
       ▼
  _doArcSwap() timeline:
  ┌───────────────────────────────────────────┐
  │ (If face-down: flip first, 320ms)         │
  │                                           │
  │ 1. Lift both cards    (100ms, lift ease)  │
  │    translateY: -10, scale: 1.03           │
  │                                           │
  │ 2a. Hand card arcs    (320ms, arc ease)   │
  │     → discard pile                        │
  │                                           │
  │ 2b. Held card arcs    (320ms, arc ease)   │  ← parallel
  │     → hand slot                           │     with 2a
  │                                           │
  │ 3. Settle             (100ms, settle ease)│
  │    scale: 1.02→1 (gentle overshoot)       │
  └───────────────────────────────────────────┘
       │
       ▼
  Callback → completeSwapAnimation()
  ├─ Clean up animation state, remove classes
  ├─ CLEAR swapAnimationInProgress = false
  ├─ Apply pendingGameState if exists
  └─ renderGame()
```

**Total animation time:** ~100 + 320 + 100 = ~520ms (face-up), ~840ms (face-down)

---

## Flow 4: Local Player Discards

**Trigger:** User clicks discard button while holding a drawn card

```
User clicks discard button
       │
       ▼
  discardDrawn()
  ├─ Store discardedCard
  ├─ Send: { type: 'discard' }
  ├─ Clear drawnCard, hide toast/button
  ├─ Get heldRect (position of floating card)
  ├─ Hide floating held card
  ├─ SET skipNextDiscardFlip = true
  └─ SET localDiscardAnimating = true
       │
       ▼
  cardAnimations.animateHeldToDiscard(card, heldRect, callback)
       │
       ▼
  Timeline:
  ┌───────────────────────────────────────────┐
  │ 1. Lift               (100ms, lift ease)  │
  │    translateY: -8, scale: 1.02            │
  │                                           │
  │ 2. Arc to discard     (320ms, arc ease)   │
  │    left/top with arc peak above           │
  │                                           │
  │ 3. Settle             (100ms, settle ease)│
  │    scale: 1.02→1                          │
  └───────────────────────────────────────────┘
       │
       ▼
  Callback:
  ├─ updateDiscardPileDisplay(card)
  ├─ pulseDiscardLand()
  ├─ SET skipNextDiscardFlip = true
  └─ CLEAR localDiscardAnimating = false
```

**Total animation time:** ~100 + 320 + 100 = ~520ms

---

## Flow 5: Opponent Draws from Deck then Swaps

**Trigger:** State change detected via WebSocket `game_state` update

```
Server sends game_state (opponent drew + swapped)
       │
       ▼
  triggerAnimationsForStateChange(old, new)
       │
       ├─── STEP 1: Draw Detection ───────────────────────┐
       │    drawn_card: null → something                   │
       │    drawn_player_id != local player                │
       │    Discard unchanged → drew from DECK             │
       │                                                   │
       │    ├─ Clear stale opponent flags                  │
       │    ├─ SET isDrawAnimating = true                  │
       │    └─ animateDrawDeck(null, callback)             │
       │         │                                         │
       │         └─ Callback: CLEAR isDrawAnimating        │
       │                                                   │
       ├─── STEP 2: Swap Detection ───────────────────────┐
       │    discard_top changed                            │
       │    Previous player's hand has different card      │
       │    NOT justDetectedDraw (skip guard)              │
       │                                                   │
       │    └─ fireSwapAnimation(playerId, card, pos)      │
       │         │                                         │
       │         ▼                                         │
       │    SET opponentSwapAnimation = { playerId, pos }  │
       │    Hide source card (swap-out)                    │
       │         │                                         │
       │         ▼                                         │
       │    animateUnifiedSwap() → _doArcSwap()            │
       │    (same timeline as Flow 3)                      │
       │         │                                         │
       │         ▼                                         │
       │    Callback:                                      │
       │    ├─ Restore source card                         │
       │    ├─ CLEAR opponentSwapAnimation = null          │
       │    └─ renderGame()                                │
       └───────────────────────────────────────────────────┘
```

**Note:** STEP 1 and STEP 2 are detected in the same `triggerAnimationsForStateChange` call. The draw animation fires first; the swap animation fires after (may overlap slightly depending on timing).

---

## Flow 6: Opponent Draws from Deck then Discards

**Trigger:** State change — opponent drew from deck but didn't swap (discarded drawn card)

```
Server sends game_state (opponent drew + discarded)
       │
       ▼
  triggerAnimationsForStateChange(old, new)
       │
       ├─── STEP 1: Draw Detection ──────────────────┐
       │    (Same as Flow 5 — draw from deck)         │
       │    SET isDrawAnimating = true                 │
       │    animateDrawDeck(null, callback)            │
       │                                               │
       ├─── STEP 2: Discard Detection ────────────────┐
       │    discard_top changed                        │
       │    No hand position changed (no swap)         │
       │                                               │
       │    └─ fireDiscardAnimation(card, playerId)    │
       │         │                                     │
       │         ▼                                     │
       │    SET opponentDiscardAnimating = true         │
       │    SET skipNextDiscardFlip = true              │
       │         │                                     │
       │         ▼                                     │
       │    animateOpponentDiscard(card, callback)     │
       │                                               │
       │    Timeline:                                  │
       │    ┌────────────────────────────────────────┐ │
       │    │ (Wait for draw overlay to clear)       │ │
       │    │                                        │ │
       │    │ 1. Lift        (100ms, lift ease)      │ │
       │    │ 2. Arc→discard (320ms, arc ease)       │ │
       │    │ 3. Settle      (100ms, settle ease)    │ │
       │    └────────────────────────────────────────┘ │
       │         │                                     │
       │         ▼                                     │
       │    Callback:                                  │
       │    ├─ CLEAR opponentDiscardAnimating = false   │
       │    ├─ updateDiscardPileDisplay(card)           │
       │    └─ pulseDiscardLand()                      │
       └───────────────────────────────────────────────┘
```

---

## Flow 7: Opponent Draws from Discard then Swaps

**Trigger:** State change — opponent took from discard pile and swapped

```
Server sends game_state (opponent drew from discard + swapped)
       │
       ▼
  triggerAnimationsForStateChange(old, new)
       │
       ├─── STEP 1: Draw Detection ──────────────────┐
       │    drawn_card: null → something               │
       │    Discard top CHANGED → drew from DISCARD    │
       │                                               │
       │    ├─ Clear stale opponent flags              │
       │    ├─ SET isDrawAnimating = true              │
       │    └─ animateDrawDiscard(card, callback)      │
       │                                               │
       ├─── STEP 2: Skip Guard ───────────────────────┐
       │    justDetectedDraw AND discard changed?      │
       │    YES → SKIP STEP 2                          │
       │                                               │
       │    The discard change was from REMOVING a     │
       │    card (draw), not ADDING one (discard).     │
       │    The swap detection comes from a LATER      │
       │    state update when the turn completes.      │
       └───────────────────────────────────────────────┘
       │
       ▼
  (Next state update detects the swap via STEP 2)
  └─ fireSwapAnimation() — same as Flow 5
```

**Critical:** The skip guard (`!justDetectedDraw`) prevents double-animating when an opponent draws from the discard pile. Without it, the discard change would trigger both a draw animation AND a discard animation.

---

## Flow 8: Initial Card Flip

**Trigger:** User clicks face-down card during the initial flip phase (start of round)

```
User clicks face-down card (position N)
       │
       ▼
  handleCardClick(position)
  ├─ Check: waiting_for_initial_flip
  ├─ Validate: card is face-down, not already tracked
  ├─ Add to locallyFlippedCards set
  ├─ Add to selectedCards array
  └─ fireLocalFlipAnimation(position, card)
       │
       ▼
  fireLocalFlipAnimation()
  ├─ Add to animatingPositions set (prevent overlap)
  └─ cardAnimations.animateInitialFlip(cardEl, card, callback)
       │
       ▼
  Timeline:
  ┌──────────────────────────────────┐
  │ Create overlay at card position  │
  │ Hide original (opacity: 0)      │
  │                                  │
  │ 1. Flip          (320ms, flip)  │
  │    rotateY: 180→0               │
  │    Play flip sound              │
  └──────────────────────────────────┘
       │
       ▼
  Callback:
  ├─ Remove overlay, restore original
  └─ Remove from animatingPositions
       │
       ▼
  renderGame() (called after click)
  └─ Shows flipped state immediately (optimistic)
       │
       ▼
  (If all required flips selected)
  └─ Send: { type: 'flip_cards', positions: [...] }
       │
       ▼
  Server confirms → clear locallyFlippedCards
```

---

## Flow 9: Deal Animation

**Trigger:** `game_started` or `round_started` WebSocket message

```
Server: 'game_started' / 'round_started'
       │
       ▼
  Reset all state, cancel animations
  SET dealAnimationInProgress = true
  renderGame() — layout card slots
  Hide player/opponent cards (visibility: hidden)
       │
       ▼
  cardAnimations.animateDealing(gameState, getPlayerRect, callback)
       │
       ▼
  ┌─────────────────────────────────────────────────┐
  │ Shuffle pause (400ms)                           │
  │                                                 │
  │ For each deal round (6 total):                  │
  │   For each player (dealer's left first):        │
  │     ┌─────────────────────────────────────┐     │
  │     │ Create overlay at deck position     │     │
  │     │ Fly to player card slot (150ms)     │     │
  │     │ Play card sound                     │     │
  │     │ Stagger delay (80ms)                │     │
  │     └─────────────────────────────────────┘     │
  │   Round pause (50ms)                            │
  │                                                 │
  │ Wait for last cards to land                     │
  │ Flip discard card (200ms delay + flip sound)    │
  │ Clean up all overlays                           │
  └─────────────────────────────────────────────────┘
       │
       ▼
  Callback:
  ├─ CLEAR dealAnimationInProgress = false
  ├─ Show real cards (visibility: visible)
  ├─ renderGame()
  └─ animateOpponentInitialFlips()
       │
       ▼
  ┌─────────────────────────────────────────────────┐
  │ For each opponent:                              │
  │   Random delay (500-2500ms window)              │
  │   For each face-up card:                        │
  │     Temporarily show as face-down               │
  │     animateOpponentFlip() (320ms)               │
  │     Stagger (400ms between cards)               │
  └─────────────────────────────────────────────────┘
```

**Total deal time:** ~400 + (6 rounds x players x 230ms) + 350ms flip

---

## Flow 10: Round End Reveal

**Trigger:** `round_over` WebSocket message after round ends

```
Server: 'game_state' (phase → 'round_over')
  ├─ Detect roundJustEnded
  ├─ Save pre/post reveal states
  └─ Update gameState but DON'T render
       │
       ▼
Server: 'round_over' (scores, rankings)
       │
       ▼
  runRoundEndReveal(scores, rankings)
  ├─ SET revealAnimationInProgress = true
  ├─ renderGame() — show current layout
  ├─ Compute cardsToReveal (face-down → face-up)
  └─ Get reveal order (knocker first, then clockwise)
       │
       ▼
  ┌──────────────────────────────────────────┐
  │ For each player (in reveal order):       │
  │   Highlight player area                  │
  │   Pause (200ms)                          │
  │                                          │
  │   For each face-down card:               │
  │     animateRevealFlip(id, pos, card)     │
  │     ├─ Local: animateInitialFlip (320ms) │
  │     └─ Opponent: animateOpponentFlip     │
  │     Stagger (100ms)                      │
  │                                          │
  │   Wait for last flip + pause             │
  │   Remove highlight                       │
  └──────────────────────────────────────────┘
       │
       ▼
  CLEAR revealAnimationInProgress = false
  renderGame()
       │
       ▼
  Run score tally animation
  Show scoreboard
```

---

## Flag Lifecycle Summary

Every flag follows the same pattern: **SET before animation, CLEAR in callback**.

```
SET flag ──► Animation runs ──► Callback fires ──► CLEAR flag
                                                       │
                                                       ▼
                                                  renderGame()
```

### Where each flag is cleared

| Flag | Normal Clear | Safety Clears |
|------|-------------|---------------|
| `isDrawAnimating` | Draw animation callback | — |
| `localDiscardAnimating` | Discard animation callback | Fallback path |
| `opponentDiscardAnimating` | Opponent discard callback | `your_turn`, `card_drawn`, before opponent draw |
| `opponentSwapAnimation` | Swap animation callback | `your_turn`, `card_drawn`, before opponent draw, new round |
| `dealAnimationInProgress` | Deal complete callback | — |
| `swapAnimationInProgress` | `completeSwapAnimation()` | — |

---

## Safety Clears

Stale flags can freeze the UI. Multiple locations clear opponent flags as a safety net:

| Location | Clears | When |
|----------|--------|------|
| `your_turn` message handler | `opponentSwapAnimation`, `opponentDiscardAnimating` | Player's turn starts |
| `card_drawn` handler (deck) | `opponentSwapAnimation`, `opponentDiscardAnimating` | Local player draws |
| `card_drawn` handler (discard) | `opponentSwapAnimation`, `opponentDiscardAnimating` | Local player draws |
| Before opponent draw animation | `opponentSwapAnimation`, `opponentDiscardAnimating` | New opponent animation starts |
| `game_started`/`round_started` | All flags | New round resets everything |

**Rule:** If you add a new animation flag, add safety clears in the `your_turn` handler and at round start.
