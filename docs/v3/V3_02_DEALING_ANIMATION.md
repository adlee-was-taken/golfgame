# V3-02: Dealing Animation

## Overview

In physical card games, cards are dealt one at a time from the dealer to each player in turn. Currently, cards appear instantly when a round starts. This feature adds an animated dealing sequence that mimics the physical ritual.

**Dependencies:** V3_01 (Dealer Rotation - need to know who is dealing)
**Dependents:** None

---

## Goals

1. Animate cards being dealt from a central deck position
2. Deal one card at a time to each player in clockwise order
3. Play shuffle sound before dealing begins
4. Play card sound as each card lands
5. Maintain quick perceived pace (stagger start times, not end times)
6. Show dealing from dealer's position (or center as fallback)

---

## Current State

From `app.js`, when `game_started` or `round_started` message received:

```javascript
case 'game_started':
case 'round_started':
    this.gameState = data.game_state;
    this.playSound('shuffle');
    this.showGameScreen();
    this.renderGame();  // Cards appear instantly
    break;
```

Cards are rendered immediately via `renderGame()` which populates the card grids.

---

## Design

### Animation Sequence

```
1. Shuffle sound plays
2. Brief pause (300ms) - deck appears to shuffle
3. Deal round 1: One card to each player (clockwise from dealer's left)
4. Deal round 2-6: Repeat until all 6 cards dealt to each player
5. Flip discard pile top card
6. Initial flip phase begins (or game starts if initial_flips=0)
```

### Visual Flow

```
                    [Deck]
                      |
    ┌─────────────────┼─────────────────┐
    │                 │                 │
    ▼                 ▼                 ▼
[Opponent 1]    [Opponent 2]    [Opponent 3]
                      |
                      ▼
              [Local Player]
```

Cards fly from deck position to each player's card slot, face-down.

### Timing

```javascript
// New timing values in timing-config.js
dealing: {
    shufflePause: 400,      // Pause after shuffle sound
    cardFlyTime: 150,       // Time for card to fly to destination
    cardStagger: 80,        // Delay between cards (overlap for speed)
    roundPause: 50,         // Brief pause between deal rounds
    discardFlipDelay: 200,  // Pause before flipping discard
}
```

Total time for 4-player game (24 cards):
- 400ms shuffle + 24 cards × 80ms stagger + 200ms discard = ~2.5 seconds

This feels unhurried but not slow.

### Implementation Approach

#### Option A: Overlay Animation (Recommended)

Create temporary card elements that animate from deck to destinations, then remove them and show the real cards.

Pros:
- Clean separation from game state
- Easy to skip/interrupt
- No complex state management

Cons:
- Brief flash when swapping to real cards (mitigate with timing)

#### Option B: Animate Real Cards

Start with cards at deck position, animate to final positions.

Pros:
- No element swap
- More "real"

Cons:
- Complex coordination with renderGame()
- State management issues

**Recommendation:** Option A - overlay animation

---

## Implementation

### Add to `card-animations.js`

Add the dealing animation as a method on the existing `CardAnimations` class:

```javascript
// Add to CardAnimations class in card-animations.js

/**
 * Run the dealing animation using anime.js timelines
 * @param {Object} gameState - The game state with players and their cards
 * @param {Function} getPlayerRect - Function(playerId, cardIdx) => {left, top, width, height}
 * @param {Function} onComplete - Callback when animation completes
 */
async animateDealing(gameState, getPlayerRect, onComplete) {
    const T = window.TIMING?.dealing || {
        shufflePause: 400,
        cardFlyTime: 150,
        cardStagger: 80,
        roundPause: 50,
        discardFlipDelay: 200,
    };

    const deckRect = this.getDeckRect();
    const discardRect = this.getDiscardRect();
    if (!deckRect) {
        if (onComplete) onComplete();
        return;
    }

    // Get player order starting from dealer's left
    const dealerIdx = gameState.dealer_idx || 0;
    const playerOrder = this.getDealOrder(gameState.players, dealerIdx);

    // Create container for animation cards
    const container = document.createElement('div');
    container.className = 'deal-animation-container';
    container.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;pointer-events:none;z-index:1000;';
    document.body.appendChild(container);

    // Shuffle sound and pause
    this.playSound('shuffle');
    await this.delay(T.shufflePause);

    // Deal 6 rounds of cards using anime.js
    const allCards = [];
    for (let cardIdx = 0; cardIdx < 6; cardIdx++) {
        for (const player of playerOrder) {
            const targetRect = getPlayerRect(player.id, cardIdx);
            if (!targetRect) continue;

            // Create card at deck position
            const deckColor = this.getDeckColor();
            const card = this.createAnimCard(deckRect, true, deckColor);
            card.classList.add('deal-anim-card');
            container.appendChild(card);
            allCards.push({ card, targetRect });

            // Animate using anime.js
            anime({
                targets: card,
                left: targetRect.left,
                top: targetRect.top,
                width: targetRect.width,
                height: targetRect.height,
                duration: T.cardFlyTime,
                easing: this.getEasing('move'),
            });

            this.playSound('card');
            await this.delay(T.cardStagger);
        }

        // Brief pause between rounds
        if (cardIdx < 5) {
            await this.delay(T.roundPause);
        }
    }

    // Wait for last cards to land
    await this.delay(T.cardFlyTime);

    // Flip discard pile card
    if (discardRect && gameState.discard_top) {
        await this.delay(T.discardFlipDelay);
        this.playSound('flip');
    }

    // Clean up
    container.remove();
    if (onComplete) onComplete();
}

getDealOrder(players, dealerIdx) {
    // Rotate so dealing starts to dealer's left
    const order = [...players];
    const startIdx = (dealerIdx + 1) % order.length;
    return [...order.slice(startIdx), ...order.slice(0, startIdx)];
}

delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}
```

### CSS for Deal Animation

```css
/* In style.css - minimal, anime.js handles all animation */

/* Deal animation container */
.deal-animation-container {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    pointer-events: none;
    z-index: 1000;
}

/* Deal cards inherit from .draw-anim-card (already exists in card-animations.js) */
.deal-anim-card {
    /* Uses same structure as createAnimCard() */
}
```

### Integration in app.js

```javascript
// In handleMessage, game_started/round_started case:

case 'game_started':
case 'round_started':
    this.clearNextHoleCountdown();
    this.nextRoundBtn.classList.remove('waiting');
    this.roundWinnerNames = new Set();
    this.gameState = data.game_state;
    this.previousState = JSON.parse(JSON.stringify(data.game_state));
    this.locallyFlippedCards = new Set();
    this.selectedCards = [];
    this.animatingPositions = new Set();
    this.opponentSwapAnimation = null;

    this.showGameScreen();

    // NEW: Run deal animation using CardAnimations
    this.runDealAnimation(() => {
        this.renderGame();
    });
    break;

// New method using CardAnimations
runDealAnimation(onComplete) {
    // Hide cards initially
    this.playerCards.style.visibility = 'hidden';
    this.opponentsRow.style.visibility = 'hidden';

    // Use the global cardAnimations instance
    window.cardAnimations.animateDealing(
        this.gameState,
        (playerId, cardIdx) => this.getCardSlotRect(playerId, cardIdx),
        () => {
            // Show real cards
            this.playerCards.style.visibility = 'visible';
            this.opponentsRow.style.visibility = 'visible';
            onComplete();
        }
    );
}

// Helper to get card slot position
getCardSlotRect(playerId, cardIdx) {
    if (playerId === this.playerId) {
        // Local player
        const cards = this.playerCards.querySelectorAll('.card');
        return cards[cardIdx]?.getBoundingClientRect();
    } else {
        // Opponent
        const opponentAreas = this.opponentsRow.querySelectorAll('.opponent-area');
        for (const area of opponentAreas) {
            if (area.dataset.playerId === playerId) {
                const cards = area.querySelectorAll('.card');
                return cards[cardIdx]?.getBoundingClientRect();
            }
        }
    }
    return null;
}
```

---

## Timing Tuning

### Perceived Speed Tricks

1. **Overlap card flights** - Start next card before previous lands
2. **Ease-out timing** - Cards decelerate into position (feels snappier)
3. **Batch by round** - 6 deal rounds feels rhythmic
4. **Quick stagger** - 80ms between cards feels like rapid dealing

### Accessibility

```javascript
// Respect reduced motion preference
if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    // Skip animation, just show cards
    this.renderGame();
    return;
}
```

---

## Edge Cases

### Animation Interrupted

If player disconnects or game state changes during dealing:
- Cancel animation
- Show cards immediately
- Continue with normal game flow

### Varying Player Counts

2-6 players supported:
- Fewer players = faster deal (fewer cards per round)
- 2 players: 12 cards total, ~1.5 seconds
- 6 players: 36 cards total, ~3.5 seconds

### Opponent Areas Not Ready

If opponent areas haven't rendered yet:
- Fall back to animating to center positions
- Or skip animation for that player

---

## Test Scenarios

1. **2-player game** - Dealing alternates correctly
2. **6-player game** - All players receive cards in order
3. **Quick tap through** - Animation can be interrupted
4. **Round 2+** - Dealing starts from correct dealer position
5. **Mobile** - Animation runs smoothly at 60fps
6. **Reduced motion** - Animation skipped appropriately

---

## Acceptance Criteria

- [ ] Cards animate from deck to player positions
- [ ] Deal order follows clockwise from dealer's left
- [ ] Shuffle sound plays before dealing
- [ ] Card sound plays as each card lands
- [ ] Animation completes in < 4 seconds for 6 players
- [ ] Real cards appear after animation (no flash)
- [ ] Reduced motion preference respected
- [ ] Works on mobile (60fps)
- [ ] Can be interrupted without breaking game

---

## Implementation Order

1. Add timing values to `timing-config.js`
2. Create `deal-animation.js` with DealAnimation class
3. Add CSS for deal animation cards
4. Add `data-player-id` to opponent areas for targeting
5. Add `getCardSlotRect()` helper method
6. Integrate animation in game_started/round_started handler
7. Test with various player counts
8. Add reduced motion support
9. Tune timing for best feel

---

## Notes for Agent

- Add `animateDealing()` as a method on the existing `CardAnimations` class
- Use `createAnimCard()` to create deal cards (already exists, handles 3D structure)
- Use anime.js for all card movements, not CSS transitions
- The existing `CardManager` handles persistent cards - don't modify it
- Timing values should all be in `timing-config.js` under `dealing` key
- Consider: Show dealer's hands actually dealing? (complex, skip for V3)
- The shuffle sound already exists - reuse it via `playSound('shuffle')`
- Cards should deal face-down (use `createAnimCard(rect, true, deckColor)`)
