# Card Animation System

This document describes the unified animation system for the Golf card game client.

## Architecture

**All card animations use anime.js.** There are no CSS transitions on card elements.

| What | How |
|------|-----|
| Card movements | anime.js |
| Card flips | anime.js |
| Swap animations | anime.js |
| Pulse/glow effects | anime.js |
| Hover states | CSS `:hover` only |
| Show/hide | CSS `.hidden` class only |

### Why anime.js?

- Consistent timing and easing across all animations
- Coordinated multi-element sequences via timelines
- Proper animation cancellation via `activeAnimations` tracking
- No conflicts between CSS and JS animation systems

---

## Core Files

| File | Purpose |
|------|---------|
| `card-animations.js` | Unified `CardAnimations` class - all animation logic |
| `timing-config.js` | Centralized timing/easing configuration |
| `style.css` | Static styles only (no transitions on cards) |

---

## CardAnimations Class API

Global instance available at `window.cardAnimations`.

### Draw Animations

```javascript
// Draw from deck - lift, move to hold area, flip to reveal
cardAnimations.animateDrawDeck(cardData, onComplete)

// Draw from discard - quick grab, no flip
cardAnimations.animateDrawDiscard(cardData, onComplete)

// For opponent draw-then-discard - deck to discard with flip
cardAnimations.animateDeckToDiscard(card, onComplete)
```

### Flip Animations

```javascript
// Generic flip animation on any card element
cardAnimations.animateFlip(element, cardData, onComplete)

// Initial flip at game start (local player)
cardAnimations.animateInitialFlip(cardElement, cardData, onComplete)

// Opponent card flip (fire-and-forget)
cardAnimations.animateOpponentFlip(cardElement, cardData, rotation)
```

### Swap Animations

```javascript
// Player swaps drawn card with hand card
cardAnimations.animateSwap(position, oldCard, newCard, handCardElement, onComplete)

// Opponent swap (fire-and-forget)
cardAnimations.animateOpponentSwap(playerId, position, discardCard, sourceCardElement, rotation, wasFaceUp)
```

### Discard Animations

```javascript
// Animate held card swooping to discard pile
cardAnimations.animateDiscard(heldCardElement, targetCard, onComplete)
```

### Ambient Effects (Looping)

```javascript
// "Your turn to draw" shake effect
cardAnimations.startTurnPulse(element)
cardAnimations.stopTurnPulse(element)

// CPU thinking glow
cardAnimations.startCpuThinking(element)
cardAnimations.stopCpuThinking(element)

// Initial flip phase - clickable cards glow
cardAnimations.startInitialFlipPulse(element)
cardAnimations.stopInitialFlipPulse(element)
cardAnimations.stopAllInitialFlipPulses()
```

### One-Shot Effects

```javascript
// Pulse when card lands on discard
cardAnimations.pulseDiscard()

// Pulse effect on face-up swap
cardAnimations.pulseSwap(element)

// Pop-in when element appears (use sparingly)
cardAnimations.popIn(element)

// Gold ring expanding effect before draw
cardAnimations.startDrawPulse(element)
```

### Utility Methods

```javascript
// Check if animation is in progress
cardAnimations.isBusy()

// Cancel all running animations
cardAnimations.cancel()
cardAnimations.cancelAll()

// Clean up animation elements
cardAnimations.cleanup()
```

---

## Animation Overlay Pattern

For complex animations (flips, swaps), the system:

1. Creates a temporary overlay element (`.draw-anim-card`)
2. Positions it exactly over the source card
3. Hides the original card (`opacity: 0` or `.swap-out`)
4. Animates the overlay
5. Removes overlay and reveals updated original card

This ensures smooth animations without modifying the DOM structure of game cards.

---

## Timing Configuration

All timing values are in `timing-config.js` and exposed as `window.TIMING`.

### Key Durations

| Animation | Duration | Notes |
|-----------|----------|-------|
| Flip | 245ms | 3D rotateY animation |
| Deck lift | 63ms | Before moving to hold |
| Deck move | 105ms | To hold position |
| Discard lift | 25ms | Quick grab |
| Discard move | 76ms | To hold position |
| Swap pulse | 400ms | Scale + brightness |
| Turn shake | 400ms | Every 3 seconds |

### Easing Functions

```javascript
window.TIMING.anime.easing = {
    flip: 'easeInOutQuad',   // Smooth acceleration/deceleration
    move: 'easeOutCubic',    // Fast start, gentle settle
    lift: 'easeOutQuad',     // Quick lift
    pulse: 'easeInOutSine',  // Smooth oscillation
}
```

---

## CSS Rules

### What CSS Does

- Static card appearance (colors, borders, sizing)
- Layout and positioning
- Hover states (`:hover` scale/shadow)
- Show/hide via `.hidden` class

### What CSS Does NOT Do

- No `transition` on any card element
- No `@keyframes` for card animations
- No `.flipped`, `.moving`, `.flipping` transition triggers

### Important Classes

| Class | Purpose |
|-------|---------|
| `.draw-anim-card` | Temporary overlay during animation |
| `.draw-anim-inner` | 3D flip container |
| `.swap-out` | Hides original during swap animation |
| `.hidden` | Opacity 0, no display change |
| `.draw-pulse` | Gold ring expanding effect |

---

## Common Patterns

### Preventing Premature UI Updates

The `isDrawAnimating` flag in `app.js` prevents the held card from appearing before the draw animation completes:

```javascript
// In renderGame()
if (!this.isDrawAnimating && /* other conditions */) {
    // Show held card
}
```

### Animation Sequencing

Use anime.js timelines for coordinated sequences:

```javascript
const timeline = anime.timeline({
    easing: 'easeOutQuad',
    complete: () => { /* cleanup */ }
});

timeline.add({ targets: el, translateY: -15, duration: 100 });
timeline.add({ targets: el, left: x, top: y, duration: 200 });
timeline.add({ targets: inner, rotateY: 0, duration: 245 });
```

### Fire-and-Forget Animations

For opponent/CPU animations that don't block game flow:

```javascript
// No onComplete callback needed
cardAnimations.animateOpponentFlip(cardElement, cardData);
```

---

## Debugging

### Check Active Animations

```javascript
console.log(window.cardAnimations.activeAnimations);
```

### Force Cleanup

```javascript
window.cardAnimations.cancelAll();
```

### Animation Not Working?

1. Check that anime.js is loaded before card-animations.js
2. Verify element exists and is visible
3. Check for CSS transitions that might conflict
4. Look for errors in console
