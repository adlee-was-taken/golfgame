# Card Animation System

This document describes the unified animation system for the Golf card game client.

For detailed animation flow diagrams (what triggers what, in what order, with what flags), see [`docs/ANIMATION-FLOWS.md`](../docs/ANIMATION-FLOWS.md).

## Architecture

**When to use anime.js vs CSS:**
- **Anime.js (CardAnimations)**: Card movements, flips, swaps, draws - anything involving card elements
- **CSS keyframes/transitions**: Simple UI feedback (button hover, badge entrance, status message fades) - non-card elements

**General rule:** If it moves a card, use anime.js. If it's UI chrome, CSS is fine.

| What | How |
|------|-----|
| Card movements | anime.js |
| Card flips | anime.js |
| Swap animations | anime.js |
| Pulse/glow effects on cards | anime.js |
| Button hover/active states | CSS transitions |
| Badge entrance/exit | CSS transitions |
| Status message fades | CSS transitions |
| Card hover states | anime.js `hoverIn()`/`hoverOut()` |
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

## Animation Coordination

### Server-Client Timing

Server CPU timing (in `server/ai.py` `CPU_TIMING`) must account for client animation durations:
- `post_draw_settle`: Must be >= draw animation duration (~1.1s for deck draw)
- `post_action_pause`: Must be >= swap/discard animation duration (~0.5s)

### Preventing Animation Overlap

Animation overlay cards are marked with `data-animating="true"` while active.
Methods like `animateUnifiedSwap` and `animateOpponentDiscard` check for active
animations and wait before starting new ones.

### Card Hover Initialization

Call `cardAnimations.initHoverListeners(container)` after dynamically creating cards.
This is done automatically in `renderGame()` for player and opponent card areas.

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

All durations are configured in `timing-config.js` and read via `window.TIMING`.

| Animation | Duration | Config Key | Notes |
|-----------|----------|------------|-------|
| Flip | 320ms | `card.flip` | 3D rotateY with slight overshoot |
| Deck lift | 120ms | `draw.deckLift` | Visible lift before travel |
| Deck move | 250ms | `draw.deckMove` | Smooth travel to hold position |
| Deck flip | 320ms | `draw.deckFlip` | Reveal drawn card |
| Discard lift | 80ms | `draw.discardLift` | Quick decisive grab |
| Discard move | 200ms | `draw.discardMove` | Travel to hold position |
| Swap lift | 100ms | `swap.lift` | Pickup before arc travel |
| Swap arc | 320ms | `swap.arc` | Arc travel between positions |
| Swap settle | 100ms | `swap.settle` | Landing with gentle overshoot |
| Swap pulse | 400ms | — | Scale + brightness (face-up swap) |
| Turn shake | 400ms | — | Every 3 seconds |

### Easing Functions

Custom cubic bezier curves give cards natural weight and momentum:

```javascript
window.TIMING.anime.easing = {
    flip: 'cubicBezier(0.34, 1.2, 0.64, 1)',    // Slight overshoot snap
    move: 'cubicBezier(0.22, 0.68, 0.35, 1.0)',  // Smooth deceleration
    lift: 'cubicBezier(0.0, 0.0, 0.2, 1)',       // Quick out, soft stop
    settle: 'cubicBezier(0.34, 1.05, 0.64, 1)',  // Tiny overshoot on landing
    arc: 'cubicBezier(0.45, 0, 0.15, 1)',        // Smooth S-curve for arcs
    pulse: 'easeInOutSine',                        // Smooth oscillation (loops)
}
```

---

## CSS Rules

### What CSS Does

- Static card appearance (colors, borders, sizing)
- Layout and positioning
- Card hover states (`:hover` scale/shadow - no movement)
- Show/hide via `.hidden` class
- **UI chrome animations** (buttons, badges, status messages):
  - Button hover/active transitions
  - Badge entrance/exit animations
  - Status message fade in/out
  - Modal transitions

### What CSS Does NOT Do (on card elements)

- No `transition` on any card element (`.card`, `.card-inner`, `.real-card`, `.swap-card`, `.held-card-floating`)
- No `@keyframes` for card movements or flips
- No `.flipped`, `.moving`, `.flipping` transition triggers for cards

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
const T = window.TIMING;
const timeline = anime.timeline({
    easing: T.anime.easing.move,
    complete: () => { /* cleanup */ }
});

timeline.add({ targets: el, translateY: -15, duration: T.card.lift, easing: T.anime.easing.lift });
timeline.add({ targets: el, left: x, top: y, duration: T.card.move });
timeline.add({ targets: inner, rotateY: 0, duration: T.card.flip, easing: T.anime.easing.flip });
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
