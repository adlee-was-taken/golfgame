# V3-10: Column Pair Indicator

## Overview

When two cards in a column match (forming a pair that scores 0), there's currently no persistent visual indicator. This feature adds a subtle connector showing paired columns at a glance.

**Dependencies:** V3_04 (Column Pair Celebration - this builds on that)
**Dependents:** None

---

## Goals

1. Show which columns are currently paired
2. Visual connector between paired cards
3. Score indicator showing "+0" or "locked"
4. Don't clutter the interface
5. Help new players understand pairing

---

## Current State

After V3_04 (celebration), pairs get a brief animation when formed. But after that animation, there's no indication which columns are paired. Players must remember or scan visually.

---

## Design

### Visual Options

**Option A: Connecting Line**
Draw a subtle line or bracket connecting paired cards.

**Option B: Shared Glow**
Both cards have a subtle shared glow color.

**Option C: Zero Badge**
Small "0" badge on the column.

**Option D: Lock Icon**
Small lock icon indicating "locked in" pair.

**Recommendation:** Option A (line) + Option C (badge) - clear and informative.

### Visual Treatment

```
Normal columns:        Paired column:
┌───┐  ┌───┐          ┌───┐ ─┐
│ K │  │ 7 │          │ 5 │  │ [0]
└───┘  └───┘          └───┘  │
                             │
┌───┐  ┌───┐          ┌───┐ ─┘
│ Q │  │ 3 │          │ 5 │
└───┘  └───┘          └───┘
```

---

## Implementation

### Detecting Pairs

```javascript
getColumnPairs(cards) {
    const pairs = [];
    const columns = [[0, 3], [1, 4], [2, 5]];

    for (let i = 0; i < columns.length; i++) {
        const [top, bottom] = columns[i];
        const topCard = cards[top];
        const bottomCard = cards[bottom];

        if (topCard?.face_up && bottomCard?.face_up &&
            topCard?.rank && topCard.rank === bottomCard?.rank) {
            pairs.push({
                column: i,
                topPosition: top,
                bottomPosition: bottom,
                rank: topCard.rank
            });
        }
    }

    return pairs;
}
```

### Rendering Pair Indicators

```javascript
renderPairIndicators(playerId, cards) {
    const pairs = this.getColumnPairs(cards);
    const container = this.getPairIndicatorContainer(playerId);

    // Clear existing indicators
    container.innerHTML = '';

    if (pairs.length === 0) return;

    const cardElements = this.getCardElements(playerId);

    for (const pair of pairs) {
        const topCard = cardElements[pair.topPosition];
        const bottomCard = cardElements[pair.bottomPosition];

        if (!topCard || !bottomCard) continue;

        // Create connector line
        const connector = this.createPairConnector(topCard, bottomCard, pair.column);
        container.appendChild(connector);

        // Add paired class to cards
        topCard.classList.add('paired');
        bottomCard.classList.add('paired');
    }
}

createPairConnector(topCard, bottomCard, columnIndex) {
    const connector = document.createElement('div');
    connector.className = 'pair-connector';
    connector.dataset.column = columnIndex;

    // Calculate position
    const topRect = topCard.getBoundingClientRect();
    const bottomRect = bottomCard.getBoundingClientRect();
    const containerRect = topCard.closest('.card-grid').getBoundingClientRect();

    // Position connector to the right of the column
    const x = topRect.right - containerRect.left + 5;
    const y = topRect.top - containerRect.top;
    const height = bottomRect.bottom - topRect.top;

    connector.style.cssText = `
        left: ${x}px;
        top: ${y}px;
        height: ${height}px;
    `;

    // Add zero badge
    const badge = document.createElement('div');
    badge.className = 'pair-badge';
    badge.textContent = '0';
    connector.appendChild(badge);

    return connector;
}

getPairIndicatorContainer(playerId) {
    // Get or create indicator container
    const area = playerId === this.playerId
        ? this.playerCards
        : this.opponentsRow.querySelector(`[data-player-id="${playerId}"] .card-grid`);

    if (!area) return document.createElement('div'); // Fallback

    let container = area.querySelector('.pair-indicators');
    if (!container) {
        container = document.createElement('div');
        container.className = 'pair-indicators';
        area.style.position = 'relative';
        area.appendChild(container);
    }

    return container;
}
```

### CSS

```css
/* Pair indicators container */
.pair-indicators {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    pointer-events: none;
    z-index: 5;
}

/* Connector line */
.pair-connector {
    position: absolute;
    width: 3px;
    background: linear-gradient(180deg,
        rgba(244, 164, 96, 0.6) 0%,
        rgba(244, 164, 96, 0.8) 50%,
        rgba(244, 164, 96, 0.6) 100%
    );
    border-radius: 2px;
}

/* Bracket style alternative */
.pair-connector::before,
.pair-connector::after {
    content: '';
    position: absolute;
    left: 0;
    width: 8px;
    height: 3px;
    background: rgba(244, 164, 96, 0.6);
}

.pair-connector::before {
    top: 0;
    border-radius: 2px 0 0 0;
}

.pair-connector::after {
    bottom: 0;
    border-radius: 0 0 0 2px;
}

/* Zero badge */
.pair-badge {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background: #f4a460;
    color: #1a1a2e;
    font-size: 0.7em;
    font-weight: bold;
    padding: 2px 6px;
    border-radius: 10px;
    white-space: nowrap;
}

/* Paired card subtle highlight */
.card.paired {
    box-shadow: 0 0 8px rgba(244, 164, 96, 0.3);
}

/* Opponent paired cards - smaller/subtler */
.opponent-area .pair-connector {
    width: 2px;
}

.opponent-area .pair-badge {
    font-size: 0.6em;
    padding: 1px 4px;
}

.opponent-area .card.paired {
    box-shadow: 0 0 5px rgba(244, 164, 96, 0.2);
}
```

### Integration with renderGame

```javascript
// In renderGame(), after rendering cards
renderGame() {
    // ... existing rendering ...

    // Update pair indicators for all players
    for (const player of this.gameState.players) {
        this.renderPairIndicators(player.id, player.cards);
    }
}
```

### Handling Window Resize

Pair connectors are positioned absolutely, so they need updating on resize:

```javascript
constructor() {
    // ... existing constructor ...

    // Debounced resize handler for pair indicators
    window.addEventListener('resize', this.debounce(() => {
        if (this.gameState) {
            for (const player of this.gameState.players) {
                this.renderPairIndicators(player.id, player.cards);
            }
        }
    }, 100));
}

debounce(fn, delay) {
    let timeout;
    return (...args) => {
        clearTimeout(timeout);
        timeout = setTimeout(() => fn.apply(this, args), delay);
    };
}
```

---

## Alternative: CSS-Only Approach

Simpler approach using only CSS classes:

```javascript
// In renderGame, just add classes
for (const player of this.gameState.players) {
    const pairs = this.getColumnPairs(player.cards);
    const cards = this.getCardElements(player.id);

    // Clear previous
    cards.forEach(c => c.classList.remove('paired', 'pair-top', 'pair-bottom'));

    for (const pair of pairs) {
        cards[pair.topPosition]?.classList.add('paired', 'pair-top');
        cards[pair.bottomPosition]?.classList.add('paired', 'pair-bottom');
    }
}
```

```css
/* CSS-only pair indication */
.card.pair-top {
    border-bottom: 3px solid #f4a460;
    border-bottom-left-radius: 0;
    border-bottom-right-radius: 0;
}

.card.pair-bottom {
    border-top: 3px solid #f4a460;
    border-top-left-radius: 0;
    border-top-right-radius: 0;
}

.card.paired::after {
    content: '';
    position: absolute;
    right: -10px;
    top: 0;
    bottom: 0;
    width: 3px;
    background: rgba(244, 164, 96, 0.5);
}

.card.pair-bottom::after {
    top: -100%; /* Extend up to connect */
}
```

**Recommendation:** Start with CSS-only approach. Add connector elements if more visual clarity needed.

---

## Test Scenarios

1. **Single pair** - One column shows indicator
2. **Multiple pairs** - Multiple indicators (rare but possible)
3. **No pairs** - No indicators
4. **Pair broken** - Indicator disappears
5. **Pair formed** - Indicator appears (after celebration)
6. **Face-down card in column** - No indicator
7. **Opponent pairs** - Smaller indicators visible

---

## Acceptance Criteria

- [ ] Paired columns show visual connector
- [ ] "0" badge indicates the score contribution
- [ ] Indicators update when cards change
- [ ] Works for local player and opponents
- [ ] Smaller/subtler for opponents
- [ ] Handles window resize
- [ ] Doesn't clutter interface
- [ ] Helps new players understand pairing

---

## Implementation Order

1. Implement `getColumnPairs()` method
2. Choose approach: CSS-only or connector elements
3. If connector: implement `createPairConnector()`
4. Add CSS for indicators
5. Integrate into `renderGame()`
6. Add resize handling
7. Test various pair scenarios
8. Adjust styling for opponents

---

## Notes for Agent

- **CSS vs anime.js**: CSS is appropriate for static indicators (not animated elements)
- Keep indicators subtle - informative not distracting
- Opponent indicators should be smaller/lighter
- CSS-only approach is simpler to maintain
- The badge helps players learning the scoring system
- Consider: toggle option to hide indicators? (For experienced players)
- Make sure indicators don't overlap cards on mobile
