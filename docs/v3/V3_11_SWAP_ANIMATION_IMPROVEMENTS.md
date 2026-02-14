# V3-11: Swap Animation Improvements

## Overview

When swapping a drawn card with a hand card, the current animation uses a "flip in place + teleport" approach. Physical card games have cards that slide past each other. This feature improves the swap animation to feel more physical.

**Dependencies:** None
**Dependents:** None

---

## Goals

1. Cards visibly exchange positions (not teleport)
2. Old card slides toward discard
3. New card slides into hand slot
4. Brief "crossing" moment visible
5. Smooth, performant animation
6. Works for both face-up and face-down swaps

---

## Current State

From `card-animations.js` (CardAnimations class):
```javascript
// Current swap uses anime.js with pulse effect for face-up swaps
// and flip animation for face-down swaps

animateSwap(position, oldCard, newCard, handCardElement, onComplete) {
    if (isAlreadyFaceUp) {
        // Face-up swap: subtle pulse, no flip needed
        this._animateFaceUpSwap(handCardElement, onComplete);
    } else {
        // Face-down swap: flip reveal then swap
        this._animateFaceDownSwap(position, oldCard, handCardElement, onComplete);
    }
}

_animateFaceUpSwap(handCardElement, onComplete) {
    anime({
        targets: handCardElement,
        scale: [1, 0.92, 1.08, 1],
        filter: ['brightness(1)', 'brightness(0.85)', 'brightness(1.15)', 'brightness(1)'],
        duration: 400,
        easing: 'easeOutQuad'
    });
}
```

The current animation uses a pulse effect for face-up swaps and a flip reveal for face-down swaps. It works but lacks the physical feeling of cards moving past each other.

---

## Design

### Animation Sequence

```
1. If face-down: Flip hand card to reveal (existing)
2. Lift both cards slightly (z-index, shadow)
3. Hand card arcs toward discard pile
4. Held card arcs toward hand slot
5. Cards cross paths visually (middle of arc)
6. Cards land at destinations
7. Landing pulse effect
```

### Arc Paths

Instead of straight lines, cards follow curved paths:

```
     Hand card path
    ╭─────────────────╮
    │                 │
  [Hand]          [Discard]
    │                 │
    ╰─────────────────╯
     Held card path
```

The curves create a visual "exchange" moment.

---

## Implementation

### Enhanced Swap Animation (Add to CardAnimations class)

```javascript
// In card-animations.js - enhance the existing animateSwap method

async animatePhysicalSwap(handCardEl, heldCardEl, handRect, discardRect, holdingRect, onComplete) {
    const T = window.TIMING?.swap || {
        lift: 80,
        arc: 280,
        settle: 60,
    };

    // Create animation elements that will travel
    const travelingHandCard = this.createTravelingCard(handCardEl);
    const travelingHeldCard = this.createTravelingCard(heldCardEl);

    document.body.appendChild(travelingHandCard);
    document.body.appendChild(travelingHeldCard);

    // Position at start
    this.positionAt(travelingHandCard, handRect);
    this.positionAt(travelingHeldCard, holdingRect || discardRect);

    // Hide originals
    handCardEl.style.visibility = 'hidden';
    heldCardEl.style.visibility = 'hidden';

    this.playSound('card');

    // Use anime.js timeline for coordinated arc movement
    const timeline = anime.timeline({
        easing: this.getEasing('move'),
        complete: () => {
            travelingHandCard.remove();
            travelingHeldCard.remove();
            handCardEl.style.visibility = 'visible';
            heldCardEl.style.visibility = 'visible';
            this.pulseDiscard();
            if (onComplete) onComplete();
        }
    });

    // Calculate arc midpoints
    const midY1 = (handRect.top + discardRect.top) / 2 - 40;  // Arc up
    const midY2 = ((holdingRect || discardRect).top + handRect.top) / 2 + 40;  // Arc down

    // Step 1: Lift both cards with shadow increase
    timeline.add({
        targets: [travelingHandCard, travelingHeldCard],
        translateY: -10,
        boxShadow: '0 8px 30px rgba(0, 0, 0, 0.5)',
        scale: 1.02,
        duration: T.lift,
        easing: this.getEasing('lift')
    });

    // Step 2: Hand card arcs to discard
    timeline.add({
        targets: travelingHandCard,
        left: discardRect.left,
        top: [
            { value: midY1, duration: T.arc / 2 },
            { value: discardRect.top, duration: T.arc / 2 }
        ],
        rotate: [0, -5, 0],
        duration: T.arc,
    }, `-=${T.lift / 2}`);

    // Held card arcs to hand (in parallel)
    timeline.add({
        targets: travelingHeldCard,
        left: handRect.left,
        top: [
            { value: midY2, duration: T.arc / 2 },
            { value: handRect.top, duration: T.arc / 2 }
        ],
        rotate: [0, 5, 0],
        duration: T.arc,
    }, `-=${T.arc + T.lift / 2}`);

    // Step 3: Settle
    timeline.add({
        targets: [travelingHandCard, travelingHeldCard],
        translateY: 0,
        boxShadow: '0 2px 10px rgba(0, 0, 0, 0.3)',
        scale: 1,
        duration: T.settle,
    });

    this.activeAnimations.set('physicalSwap', timeline);
}

createTravelingCard(sourceCard) {
    const clone = sourceCard.cloneNode(true);
    clone.className = 'traveling-card';
    clone.style.position = 'fixed';
    clone.style.pointerEvents = 'none';
    clone.style.zIndex = '1000';
    clone.style.borderRadius = '6px';
    return clone;
}

positionAt(element, rect) {
    element.style.left = `${rect.left}px`;
    element.style.top = `${rect.top}px`;
    element.style.width = `${rect.width}px`;
    element.style.height = `${rect.height}px`;
}
```

### CSS for Traveling Cards

Minimal CSS needed - anime.js handles all animation properties including box-shadow and scale:

```css
/* Traveling card during swap - base styles only */
.traveling-card {
    position: fixed;
    border-radius: 6px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
    /* All animation handled by anime.js */
}
```

### Timing Configuration

```javascript
// In timing-config.js
swap: {
    lift: 80,         // Time to lift cards
    arc: 280,         // Time for arc travel
    settle: 60,       // Time to settle into place
    // Total: ~420ms (similar to current)
}
```

### Note on Animation Approach

All swap animations use anime.js timelines, not CSS transitions or Web Animations API. This provides:
- Better coordination between multiple elements
- Consistent with rest of animation system
- Easier timing control via `window.TIMING`
- Proper animation cancellation via `activeAnimations` tracking

---

## Integration Points

### For Local Player Swap

```javascript
// In animateSwap() method
animateSwap(position) {
    const cardElements = this.playerCards.querySelectorAll('.card');
    const handCardEl = cardElements[position];

    // Get positions
    const handRect = handCardEl.getBoundingClientRect();
    const discardRect = this.discard.getBoundingClientRect();
    const holdingRect = this.getHoldingRect();

    // If face-down, flip first (existing logic)
    // ...

    // Then do physical swap
    this.animatePhysicalSwap(
        handCardEl,
        this.heldCardFloating,
        handRect,
        discardRect,
        holdingRect
    );
}
```

### For Opponent Swap

The opponent swap animation in `fireSwapAnimation()` can use similar arc logic for the visible card traveling to discard.

---

## Test Scenarios

1. **Swap face-up card** - Direct arc exchange
2. **Swap face-down card** - Flip first, then arc
3. **Fast repeated swaps** - No animation overlap
4. **Mobile** - Animation performs at 60fps
5. **Different screen sizes** - Arcs scale appropriately

---

## Acceptance Criteria

- [ ] Cards visibly travel to new positions (not teleport)
- [ ] Arc paths create "crossing" visual
- [ ] Lift and settle effects enhance physicality
- [ ] Animation total time ~400ms (not slower than current)
- [ ] Works for face-up and face-down cards
- [ ] Performant on mobile (60fps)
- [ ] Landing effect on discard pile
- [ ] Opponent swaps also improved

---

## Implementation Order

1. Add swap timing to `timing-config.js`
2. Implement `createTravelingCard()` helper
3. Implement `animateArc()` with Web Animations API
4. Implement `animatePhysicalSwap()` method
5. Add CSS for traveling cards
6. Integrate with local player swap
7. Integrate with opponent swap animation
8. Test on various devices
9. Tune arc height and timing

---

## Notes for Agent

- Add `animatePhysicalSwap()` to the existing CardAnimations class
- Use anime.js timelines for coordinated multi-element animation
- Arc height should scale with card distance
- The "crossing" moment is the key visual improvement
- Keep total animation time similar to current (~400ms)
- Track animation in `activeAnimations` for proper cancellation
- Consider: option for "fast mode" with simpler animations?
- Make sure sound timing aligns with visual (card leaving hand)
- Existing `animateSwap()` can call this new method internally
