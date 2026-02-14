# V3-15: Discard Pile History

## Overview

In physical card games, you can see the top few cards of the discard pile fanned out slightly. This provides memory aid and context for recent play. Currently our discard pile shows only the top card.

**Dependencies:** None
**Dependents:** None

---

## Goals

1. Show 2-3 recent discards visually fanned
2. Help players track what's been discarded recently
3. Subtle visual depth without cluttering
4. Optional: expandable full discard view
5. Authentic card game feel

---

## Current State

From `app.js` and CSS:
```javascript
// Only shows the top card
updateDiscard(cardData) {
    this.discard.innerHTML = this.createCardHTML(cardData);
}
```

The discard pile is a single card element with no history visualization.

---

## Design

### Visual Treatment

```
Current:           With history:
┌─────┐            ┌─────┐
│  7  │            │  7  │  ← Top card (clickable)
│  ♥  │           ╱└─────┘
└─────┘          ╱  └─────┘  ← Previous (faded, offset)
                    └─────┘  ← Older (more faded)
```

### Fan Layout

- Top card: Full visibility, normal position
- Previous card: Offset 3-4px left and up, 50% opacity
- Older card: Offset 6-8px left and up, 25% opacity
- Maximum 3 visible cards (performance + clarity)

---

## Implementation

### Track Discard History

```javascript
// In app.js constructor
this.discardHistory = [];
this.maxVisibleHistory = 3;

// Update when discard changes
updateDiscardHistory(newCard) {
    if (!newCard) {
        this.discardHistory = [];
        return;
    }

    // Add new card to front
    this.discardHistory.unshift(newCard);

    // Keep only recent cards
    if (this.discardHistory.length > this.maxVisibleHistory) {
        this.discardHistory = this.discardHistory.slice(0, this.maxVisibleHistory);
    }
}

// Called from state differ or handleMessage
onDiscardChange(newCard, oldCard) {
    // Only add if it's a new card (not initial state)
    if (oldCard && newCard && oldCard.rank !== newCard.rank) {
        this.updateDiscardHistory(newCard);
    } else if (newCard && !oldCard) {
        this.updateDiscardHistory(newCard);
    }

    this.renderDiscardPile();
}
```

### Render Fanned Pile

```javascript
renderDiscardPile() {
    const container = this.discard;
    container.innerHTML = '';

    if (this.discardHistory.length === 0) {
        container.innerHTML = '<div class="card empty">Empty</div>';
        return;
    }

    // Render from oldest to newest (back to front)
    const cards = [...this.discardHistory].reverse();

    cards.forEach((cardData, index) => {
        const reverseIndex = cards.length - 1 - index;
        const card = this.createDiscardCard(cardData, reverseIndex);
        container.appendChild(card);
    });
}

createDiscardCard(cardData, depthIndex) {
    const card = document.createElement('div');
    card.className = 'card discard-card';
    card.dataset.depth = depthIndex;

    // Only top card is interactive
    if (depthIndex === 0) {
        card.classList.add('top-card');
        card.addEventListener('click', () => this.handleDiscardClick());
    }

    // Set card content
    card.innerHTML = this.createCardContentHTML(cardData);

    // Apply offset based on depth
    const offset = depthIndex * 4;
    card.style.setProperty('--depth-offset', `${offset}px`);

    return card;
}
```

### CSS Styling

```css
/* Discard pile container */
#discard {
    position: relative;
    width: var(--card-width);
    height: var(--card-height);
}

/* Stacked discard cards */
.discard-card {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    transition: transform 0.2s, opacity 0.2s;
}

/* Depth-based styling */
.discard-card[data-depth="0"] {
    z-index: 3;
    opacity: 1;
    transform: translate(0, 0);
}

.discard-card[data-depth="1"] {
    z-index: 2;
    opacity: 0.5;
    transform: translate(-4px, -4px);
    pointer-events: none;
}

.discard-card[data-depth="2"] {
    z-index: 1;
    opacity: 0.25;
    transform: translate(-8px, -8px);
    pointer-events: none;
}

/* Using CSS variable for dynamic offset */
.discard-card:not(.top-card) {
    transform: translate(
        calc(var(--depth-offset, 0px) * -1),
        calc(var(--depth-offset, 0px) * -1)
    );
}

/* Hover to expand history slightly */
#discard:hover .discard-card[data-depth="1"] {
    opacity: 0.7;
    transform: translate(-8px, -8px);
}

#discard:hover .discard-card[data-depth="2"] {
    opacity: 0.4;
    transform: translate(-16px, -16px);
}

/* Animation when new card is discarded */
@keyframes discard-land {
    0% {
        transform: translate(0, -20px) scale(1.05);
        opacity: 0;
    }
    100% {
        transform: translate(0, 0) scale(1);
        opacity: 1;
    }
}

.discard-card.top-card.just-landed {
    animation: discard-land 0.2s ease-out;
}

/* Shift animation for cards moving back */
@keyframes shift-back {
    0% { transform: translate(0, 0); }
    100% { transform: translate(var(--depth-offset) * -1, var(--depth-offset) * -1); }
}
```

### Integration with State Changes

```javascript
// In state-differ.js or wherever discard changes are detected
detectDiscardChange(oldState, newState) {
    const oldDiscard = oldState?.discard_pile?.[oldState.discard_pile.length - 1];
    const newDiscard = newState?.discard_pile?.[newState.discard_pile.length - 1];

    if (this.cardsDifferent(oldDiscard, newDiscard)) {
        return {
            type: 'discard_change',
            oldCard: oldDiscard,
            newCard: newDiscard
        };
    }
    return null;
}

// Handle the change
handleDiscardChange(change) {
    this.onDiscardChange(change.newCard, change.oldCard);
}
```

### Round/Game Reset

```javascript
// Clear history at start of new round
onNewRound() {
    this.discardHistory = [];
    this.renderDiscardPile();
}

// Or when deck is reshuffled (if that's a game mechanic)
onDeckReshuffle() {
    this.discardHistory = [];
}
```

---

## Optional: Expandable Full History

For players who want to see all discards:

```javascript
// Toggle full discard view
showDiscardHistory() {
    const modal = document.getElementById('discard-history-modal');
    modal.innerHTML = this.buildFullDiscardView();
    modal.classList.add('visible');
}

buildFullDiscardView() {
    // Show all cards in discard pile from game state
    const discards = this.gameState.discard_pile || [];
    return discards.map(card =>
        `<div class="card mini">${this.createCardContentHTML(card)}</div>`
    ).join('');
}
```

```css
#discard-history-modal {
    position: fixed;
    bottom: 80px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(26, 26, 46, 0.95);
    padding: 12px;
    border-radius: 12px;
    display: none;
    max-width: 90vw;
    overflow-x: auto;
}

#discard-history-modal.visible {
    display: flex;
    gap: 8px;
}

#discard-history-modal .card.mini {
    width: 40px;
    height: 56px;
    font-size: 0.7em;
}
```

---

## Mobile Considerations

On smaller screens, reduce the fan offset:

```css
@media (max-width: 600px) {
    .discard-card[data-depth="1"] {
        transform: translate(-2px, -2px);
    }
    .discard-card[data-depth="2"] {
        transform: translate(-4px, -4px);
    }

    /* Skip hover expansion on touch */
    #discard:hover .discard-card {
        transform: translate(
            calc(var(--depth-offset, 0px) * -0.5),
            calc(var(--depth-offset, 0px) * -0.5)
        );
    }
}
```

---

## Test Scenarios

1. **First discard** - Single card shows
2. **Second discard** - Two cards fanned
3. **Third+ discards** - Three cards max, oldest drops off
4. **New round** - History clears
5. **Draw from discard** - Top card removed, others shift forward
6. **Hover interaction** - Cards fan out slightly more
7. **Mobile view** - Smaller offset, still visible

---

## Acceptance Criteria

- [ ] Recent 2-3 discards visible in fanned pile
- [ ] Older cards progressively more faded
- [ ] Only top card is interactive
- [ ] History updates smoothly when cards change
- [ ] History clears on new round
- [ ] Hover expands fan slightly (desktop)
- [ ] Works on mobile with smaller offsets
- [ ] Optional: expandable full history view

---

## Implementation Order

1. Add `discardHistory` array tracking
2. Implement `renderDiscardPile()` method
3. Add CSS for fanned stack
4. Integrate with state change detection
5. Add round reset handling
6. Add hover expansion effect
7. Test on various screen sizes
8. Optional: Add full history modal

---

## Notes for Agent

- **CSS vs anime.js**: CSS is appropriate for static fan layout. If adding "landing" animation for new discards, use anime.js.
- Keep visible history small (3 cards max) for clarity
- The fan offset should be subtle, not dramatic
- History helps players remember what was recently played
- Consider: Should drawing from discard affect history display?
- Mobile: smaller offset but still visible
- Don't overcomplicate - this is a nice-to-have feature
