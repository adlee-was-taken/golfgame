# V3-08: Card Hover/Selection Enhancement

## Overview

When holding a drawn card, players must choose which card to swap with. Currently, clicking a card immediately swaps. This feature adds better hover feedback showing the potential swap before committing.

**Dependencies:** None
**Dependents:** None

---

## Goals

1. Clear visual preview of the swap before clicking
2. Show where the held card will go
3. Show where the hand card will go (discard)
4. Distinct hover states for face-up vs face-down cards
5. Mobile-friendly (no hover, but clear tap targets)

---

## Current State

From `app.js`:
```javascript
handleCardClick(position) {
    // ... if holding drawn card ...
    if (this.drawnCard) {
        this.animateSwap(position);  // Immediately swaps
        return;
    }
}
```

Cards have basic hover effects in CSS but no swap preview.

---

## Design

### Desktop Hover Preview

When hovering over a hand card while holding a drawn card:

```
1. Hovered card lifts slightly and dims
2. Ghost of held card appears in that slot (semi-transparent)
3. Arrow or line hints at the swap direction
4. "Click to swap" tooltip (optional)
```

### Mobile Tap Preview

Since mobile has no hover:
- First tap = select/highlight the card
- Second tap = confirm swap
- Or: long-press shows preview, release to swap

**Recommendation:** Immediate swap on tap (current behavior) is fine for mobile. Focus on desktop hover preview.

---

## Implementation

### CSS Hover Enhancements

```css
/* Card hover when holding drawn card */
.player-area.can-swap .card {
    cursor: pointer;
    transition: transform 0.15s, box-shadow 0.15s, opacity 0.15s;
}

.player-area.can-swap .card:hover {
    transform: translateY(-5px) scale(1.02);
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.3);
}

/* Dimmed state showing "this will be replaced" */
.player-area.can-swap .card:hover::after {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.3);
    border-radius: inherit;
    pointer-events: none;
}

/* Ghost preview of incoming card */
.card-ghost-preview {
    position: absolute;
    opacity: 0.6;
    pointer-events: none;
    transform: scale(0.95);
    z-index: 5;
    border: 2px dashed rgba(244, 164, 96, 0.8);
}

/* Swap indicator arrow */
.swap-indicator {
    position: absolute;
    pointer-events: none;
    z-index: 10;
    opacity: 0;
    transition: opacity 0.15s;
}

.player-area.can-swap .card:hover ~ .swap-indicator {
    opacity: 1;
}

/* Different highlight for face-down cards */
.player-area.can-swap .card.card-back:hover {
    box-shadow: 0 8px 20px rgba(244, 164, 96, 0.4);
}

/* "Unknown" indicator for face-down hover */
.card.card-back:hover::before {
    content: '?';
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    font-size: 2em;
    color: rgba(255, 255, 255, 0.5);
}
```

### JavaScript Implementation

```javascript
// Add swap preview functionality
setupSwapPreview() {
    this.ghostPreview = document.createElement('div');
    this.ghostPreview.className = 'card-ghost-preview hidden';
    this.playerCards.appendChild(this.ghostPreview);
}

// Call during render when player is holding a card
updateSwapPreviewState() {
    const canSwap = this.drawnCard && this.isMyTurn();

    this.playerArea.classList.toggle('can-swap', canSwap);

    if (!canSwap) {
        this.ghostPreview?.classList.add('hidden');
        return;
    }

    // Set up ghost preview content
    if (this.drawnCard && this.ghostPreview) {
        this.ghostPreview.className = 'card-ghost-preview card card-front hidden';

        if (this.drawnCard.rank === '★') {
            this.ghostPreview.classList.add('joker');
        } else if (this.isRedSuit(this.drawnCard.suit)) {
            this.ghostPreview.classList.add('red');
        } else {
            this.ghostPreview.classList.add('black');
        }

        this.ghostPreview.innerHTML = this.renderCardContent(this.drawnCard);
    }
}

// Bind hover events to cards
bindCardHoverEvents() {
    const cards = this.playerCards.querySelectorAll('.card');

    cards.forEach((card, index) => {
        card.addEventListener('mouseenter', () => {
            if (!this.drawnCard || !this.isMyTurn()) return;
            this.showSwapPreview(card, index);
        });

        card.addEventListener('mouseleave', () => {
            this.hideSwapPreview();
        });
    });
}

showSwapPreview(targetCard, position) {
    if (!this.ghostPreview) return;

    // Position ghost at target card location
    const rect = targetCard.getBoundingClientRect();
    const containerRect = this.playerCards.getBoundingClientRect();

    this.ghostPreview.style.left = `${rect.left - containerRect.left}px`;
    this.ghostPreview.style.top = `${rect.top - containerRect.top}px`;
    this.ghostPreview.style.width = `${rect.width}px`;
    this.ghostPreview.style.height = `${rect.height}px`;

    this.ghostPreview.classList.remove('hidden');

    // Highlight target card
    targetCard.classList.add('swap-target');

    // Show what will happen
    this.setStatus(`Swap with position ${position + 1}`, 'swap-preview');
}

hideSwapPreview() {
    this.ghostPreview?.classList.add('hidden');

    // Remove target highlight
    this.playerCards.querySelectorAll('.card').forEach(card => {
        card.classList.remove('swap-target');
    });

    // Restore normal status
    this.updateStatusFromGameState();
}
```

### Card Position Labels (Optional Enhancement)

Show position numbers on cards during swap selection:

```css
.player-area.can-swap .card::before {
    content: attr(data-position);
    position: absolute;
    top: -8px;
    left: -8px;
    width: 18px;
    height: 18px;
    background: rgba(0, 0, 0, 0.7);
    color: white;
    border-radius: 50%;
    font-size: 11px;
    display: flex;
    align-items: center;
    justify-content: center;
}
```

```javascript
// In renderGame, add data-position to cards
const cards = this.playerCards.querySelectorAll('.card');
cards.forEach((card, i) => {
    card.dataset.position = i + 1;
});
```

---

## Visual Preview Options

### Option A: Ghost Card (Recommended)

Semi-transparent copy of the held card appears over the target slot.

### Option B: Arrow Indicator

Arrow from held card to target slot, and from target to discard.

### Option C: Split Preview

Show both cards side-by-side with swap arrows.

**Recommendation:** Option A is simplest and most intuitive.

---

## Face-Down Card Interaction

When swapping with a face-down card, player is taking a risk:

- Show "?" indicator to emphasize unknown
- Maybe show estimated value range? (Too complex for V3)
- Different hover color (orange = warning)

```css
.player-area.can-swap .card.card-back:hover {
    border: 2px solid #f4a460;
}

.player-area.can-swap .card.card-back:hover::after {
    content: 'Unknown';
    position: absolute;
    bottom: -20px;
    left: 50%;
    transform: translateX(-50%);
    font-size: 0.7em;
    color: #f4a460;
    white-space: nowrap;
}
```

---

## Test Scenarios

1. **Hover over face-up card** - Shows preview, card lifts
2. **Hover over face-down card** - Shows warning styling
3. **Move between cards** - Preview updates smoothly
4. **Mouse leaves card area** - Preview disappears
5. **Not holding card** - No special hover effects
6. **Not my turn** - No hover effects
7. **Mobile tap** - Works without preview (existing behavior)

---

## Acceptance Criteria

- [ ] Cards lift on hover when holding drawn card
- [ ] Ghost preview shows incoming card
- [ ] Face-down cards have distinct hover (unknown warning)
- [ ] Preview disappears on mouse leave
- [ ] No effects when not holding card
- [ ] No effects when not your turn
- [ ] Mobile tap still works normally
- [ ] Smooth transitions, no jank

---

## Implementation Order

1. Add `can-swap` class toggle to player area
2. Add CSS for hover lift effect
3. Create ghost preview element
4. Implement `showSwapPreview()` method
5. Implement `hideSwapPreview()` method
6. Bind mouseenter/mouseleave events
7. Add face-down card distinct styling
8. Test on desktop and mobile
9. Optional: Add position labels

---

## Notes for Agent

- **CSS vs anime.js**: CSS is appropriate for simple hover effects (performant, no JS overhead)
- Keep hover effects performant (CSS transforms preferred)
- Don't break existing click-to-swap behavior
- Mobile should work exactly as before (immediate swap)
- Consider reduced motion preferences
- The ghost preview should match the actual card appearance
- Position labels help new players understand the grid
