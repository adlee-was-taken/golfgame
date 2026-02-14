# V3-12: Draw Source Distinction

## Overview

Drawing from the deck (face-down, unknown) vs discard (face-up, known) should feel different. Currently both animations are similar. This feature enhances the visual distinction.

**Dependencies:** None
**Dependents:** None

---

## Goals

1. Deck draw: Card emerges face-down, then flips
2. Discard draw: Card lifts straight up (already visible)
3. Different sound for each source
4. Visual hint about the strategic difference
5. Help new players understand the two options

---

## Current State

From `card-animations.js` (CardAnimations class):
```javascript
// Deck draw: suspenseful pause + flip reveal
animateDrawDeck(cardData, onComplete) {
    // Pulse deck, lift card face-down, move to holding, suspense pause, flip
    timeline.add({ targets: inner, rotateY: 0, duration: 245 });
}

// Discard draw: quick decisive grab
animateDrawDiscard(cardData, onComplete) {
    // Pulse discard, quick lift, direct move to holding (no flip needed)
    timeline.add({ targets: animCard, translateY: -12, scale: 1.05, duration: 42 });
}
```

The distinction exists and is already fairly pronounced. This feature enhances it further with:
- More distinct sounds for each source
- Visual "shuffleDeckVisual" effect when drawing from deck
- Better timing contrast

---

## Design

### Deck Draw (Unknown)

```
1. Deck "shuffles" slightly (optional)
2. Top card lifts off deck
3. Card floats to holding position (face-down)
4. Brief suspense pause
5. Card flips to reveal
6. Sound: "mysterious" flip sound
```

### Discard Draw (Known)

```
1. Card lifts directly (quick)
2. No flip needed - already visible
3. Moves to holding position
4. "Picked up" visual on discard pile
5. Sound: quick "pick" sound
```

### Visual Distinction

| Aspect | Deck Draw | Discard Draw |
|--------|-----------|--------------|
| Card state | Face-down → Face-up | Face-up entire time |
| Motion | Float + flip | Direct lift |
| Sound | Suspenseful flip | Quick pick |
| Duration | Longer (suspense) | Shorter (decisive) |
| Deck visual | Cards shuffle | N/A |
| Discard visual | N/A | "Picked up" state |

---

## Implementation

### Enhanced Deck Draw

The existing `animateDrawDeck()` in `card-animations.js` already has most of this functionality. Enhancements to add:

```javascript
// In card-animations.js - enhance existing animateDrawDeck

// The current implementation already:
// - Pulses deck before drawing (startDrawPulse)
// - Lifts card with wobble
// - Adds suspense pause before flip
// - Flips to reveal with sound

// Add distinct sound for deck draws:
animateDrawDeck(cardData, onComplete) {
    // ... existing code ...

    // Change sound from 'card' to 'draw-deck' for more mysterious feel
    this.playSound('draw-deck');  // Instead of 'card'

    // ... rest of existing code ...
}

// The shuffleDeckVisual already exists as startDrawPulse:
startDrawPulse(element) {
    if (!element) return;
    element.classList.add('draw-pulse');
    setTimeout(() => {
        element.classList.remove('draw-pulse');
    }, 450);
}
```

**Key existing features:**
- `startDrawPulse()` - gold ring pulse effect
- Suspense pause of 200ms before flip
- Flip duration 245ms with `easeInOutQuad` easing

### Enhanced Discard Draw

The existing `animateDrawDiscard()` in `card-animations.js` already has quick, decisive animation:

```javascript
// Current implementation already does:
// - Pulses discard before picking up (startDrawPulse)
// - Quick lift (42ms) with scale
// - Direct move (126ms) - much faster than deck draw
// - No flip needed (card already face-up)

// Enhancement: Add distinct sound for discard draws
_animateDrawDiscardCard(cardData, discardRect, holdingRect, onComplete) {
    // ... existing code ...

    // Change sound from 'card' to 'draw-discard' for decisive feel
    this.playSound('draw-discard');  // Instead of 'card'

    // ... rest of existing code ...
}
```

**Current timing comparison (already implemented):**

| Phase | Deck Draw | Discard Draw |
|-------|-----------|--------------|
| Pulse delay | 250ms | 200ms |
| Lift | 105ms | 42ms |
| Travel | 175ms | 126ms |
| Suspense | 200ms | 0ms |
| Flip | 245ms | 0ms |
| Settle | 150ms | 80ms |
| **Total** | **~1125ms** | **~448ms** |

The distinction is already pronounced - discard draw is ~2.5x faster.

### Deck Visual Effects

The `draw-pulse` class already exists with a CSS animation (gold ring expanding). For additional deck depth effect, use CSS only:

```css
/* Deck "depth" visual - multiple card shadows */
#deck {
    box-shadow:
        1px 1px 0 0 rgba(0, 0, 0, 0.1),
        2px 2px 0 0 rgba(0, 0, 0, 0.1),
        3px 3px 0 0 rgba(0, 0, 0, 0.1),
        4px 4px 8px rgba(0, 0, 0, 0.3);
}

/* Existing draw-pulse animation handles the visual feedback */
.draw-pulse {
    /* Already defined in style.css */
}
```

### Distinct Sounds

```javascript
// In playSound() method

} else if (type === 'draw-deck') {
    // Mysterious "what's this?" sound
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.type = 'triangle';
    osc.frequency.setValueAtTime(300, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(500, ctx.currentTime + 0.1);
    osc.frequency.exponentialRampToValueAtTime(350, ctx.currentTime + 0.15);

    gain.gain.setValueAtTime(0.08, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.2);

    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.2);

} else if (type === 'draw-discard') {
    // Quick decisive "grab" sound
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.type = 'square';
    osc.frequency.setValueAtTime(600, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(300, ctx.currentTime + 0.05);

    gain.gain.setValueAtTime(0.08, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.06);

    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.06);
}
```

---

## Timing Comparison

| Phase | Deck Draw | Discard Draw |
|-------|-----------|--------------|
| Lift | 150ms | 80ms |
| Travel | 250ms | 200ms |
| Suspense | 200ms | 0ms |
| Flip | 350ms | 0ms |
| Settle | 150ms | 80ms |
| **Total** | **~1100ms** | **~360ms** |

Deck draw is intentionally longer to build suspense.

---

## Test Scenarios

1. **Draw from deck** - Longer animation with flip
2. **Draw from discard** - Quick decisive grab
3. **Rapid alternating draws** - Animations don't conflict
4. **CPU draws** - Same visual distinction

---

## Acceptance Criteria

- [ ] Deck draw has suspenseful pause before flip
- [ ] Discard draw is quick and direct
- [ ] Different sounds for each source
- [ ] Deck shows visual "dealing" effect
- [ ] Timing difference is noticeable but not tedious
- [ ] Both animations complete cleanly
- [ ] Works for both local player and opponents

---

## Implementation Order

1. Add distinct sounds to `playSound()`
2. Enhance `animateDrawDeck()` with suspense
3. Enhance `animateDrawDiscard()` for quick grab
4. Add deck visual effects (CSS)
5. Add `shuffleDeckVisual()` method
6. Test both draw types
7. Tune timing for feel

---

## Notes for Agent

- Most of this is already implemented in `card-animations.js`
- Main enhancement is adding distinct sounds (`draw-deck` vs `draw-discard`)
- The existing timing difference (1125ms vs 448ms) is already significant
- Deck draw suspense shouldn't be annoying, just noticeable
- Discard draw being faster reflects the strategic advantage (you know what you're getting)
- Consider: Show deck count visual changing? (Nice to have)
- Sound design matters here - different tones communicate different meanings
- Mobile performance should still be smooth
