# V3-13: Card Value Tooltips

## Overview

New players often forget card values, especially special cards (2=-2, K=0, Joker=-2). This feature adds tooltips showing card point values on long-press or hover.

**Dependencies:** None
**Dependents:** None

---

## Goals

1. Show card point value on long-press (mobile) or hover (desktop)
2. Especially helpful for special value cards
3. Show house rule modified values if active
4. Don't interfere with normal gameplay
5. Optional: disable for experienced players

---

## Current State

No card value tooltips exist. Players must remember:
- Standard values: A=1, 2-10=face, J/Q=10, K=0
- Special values: 2=-2, Joker=-2
- House rules: super_kings=-2, ten_penny=1, etc.

---

## Design

### Tooltip Content

```
┌─────────┐
│    K    │  ← Normal card display
│    ♠    │
└─────────┘
     │
     ▼
 ┌───────┐
 │ 0 pts │  ← Tooltip on hover/long-press
 └───────┘
```

For special cards:
```
 ┌────────────┐
 │ -2 pts     │
 │ (negative!)│
 └────────────┘
```

### Activation

- **Desktop:** Hover for 500ms (not instant to avoid cluttering)
- **Mobile:** Long-press (300ms threshold)
- **Dismiss:** Mouse leave / touch release

---

## Implementation

### JavaScript

```javascript
// Card tooltip system

initCardTooltips() {
    this.tooltip = document.createElement('div');
    this.tooltip.className = 'card-value-tooltip hidden';
    document.body.appendChild(this.tooltip);

    this.tooltipTimeout = null;
    this.currentTooltipTarget = null;
}

bindCardTooltipEvents(cardElement, cardData) {
    // Desktop hover
    cardElement.addEventListener('mouseenter', () => {
        this.scheduleTooltip(cardElement, cardData);
    });

    cardElement.addEventListener('mouseleave', () => {
        this.hideCardTooltip();
    });

    // Mobile long-press
    let pressTimer = null;

    cardElement.addEventListener('touchstart', (e) => {
        pressTimer = setTimeout(() => {
            this.showCardTooltip(cardElement, cardData);
            // Prevent triggering card click
            e.preventDefault();
        }, 300);
    });

    cardElement.addEventListener('touchend', () => {
        clearTimeout(pressTimer);
        this.hideCardTooltip();
    });

    cardElement.addEventListener('touchmove', () => {
        clearTimeout(pressTimer);
        this.hideCardTooltip();
    });
}

scheduleTooltip(cardElement, cardData) {
    this.hideCardTooltip();

    if (!cardData?.face_up || !cardData?.rank) return;

    this.tooltipTimeout = setTimeout(() => {
        this.showCardTooltip(cardElement, cardData);
    }, 500); // 500ms delay on desktop
}

showCardTooltip(cardElement, cardData) {
    if (!cardData?.face_up || !cardData?.rank) return;

    const value = this.getCardPointValue(cardData);
    const special = this.getCardSpecialNote(cardData);

    // Build tooltip content
    let content = `<span class="tooltip-value ${value < 0 ? 'negative' : ''}">${value} pts</span>`;
    if (special) {
        content += `<span class="tooltip-note">${special}</span>`;
    }

    this.tooltip.innerHTML = content;

    // Position tooltip
    const rect = cardElement.getBoundingClientRect();
    const tooltipRect = this.tooltip.getBoundingClientRect();

    let left = rect.left + rect.width / 2;
    let top = rect.bottom + 8;

    // Keep on screen
    if (left + tooltipRect.width / 2 > window.innerWidth) {
        left = window.innerWidth - tooltipRect.width / 2 - 10;
    }
    if (left - tooltipRect.width / 2 < 0) {
        left = tooltipRect.width / 2 + 10;
    }
    if (top + tooltipRect.height > window.innerHeight) {
        top = rect.top - tooltipRect.height - 8;
    }

    this.tooltip.style.left = `${left}px`;
    this.tooltip.style.top = `${top}px`;
    this.tooltip.classList.remove('hidden');

    this.currentTooltipTarget = cardElement;
}

hideCardTooltip() {
    clearTimeout(this.tooltipTimeout);
    this.tooltip.classList.add('hidden');
    this.currentTooltipTarget = null;
}

getCardPointValue(cardData) {
    const values = this.gameState?.card_values || {
        'A': 1, '2': -2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7,
        '8': 8, '9': 9, '10': 10, 'J': 10, 'Q': 10, 'K': 0, '★': -2
    };

    return values[cardData.rank] ?? 0;
}

getCardSpecialNote(cardData) {
    const rank = cardData.rank;
    const value = this.getCardPointValue(cardData);

    // Special notes for notable cards
    if (value < 0) {
        return 'Negative - keep it!';
    }
    if (rank === 'K' && value === 0) {
        return 'Safe card';
    }
    if (rank === 'K' && value === -2) {
        return 'Super King!';
    }
    if (rank === '10' && value === 1) {
        return 'Ten Penny rule';
    }
    if (rank === 'J' || rank === 'Q') {
        return 'High - replace if possible';
    }

    return null;
}
```

### CSS

```css
/* Card value tooltip */
.card-value-tooltip {
    position: fixed;
    transform: translateX(-50%);
    background: rgba(26, 26, 46, 0.95);
    color: white;
    padding: 6px 12px;
    border-radius: 8px;
    font-size: 0.85em;
    text-align: center;
    z-index: 500;
    pointer-events: none;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    transition: opacity 0.15s;
}

.card-value-tooltip.hidden {
    opacity: 0;
    pointer-events: none;
}

.card-value-tooltip::before {
    content: '';
    position: absolute;
    top: -6px;
    left: 50%;
    transform: translateX(-50%);
    border: 6px solid transparent;
    border-bottom-color: rgba(26, 26, 46, 0.95);
}

.tooltip-value {
    display: block;
    font-size: 1.2em;
    font-weight: bold;
}

.tooltip-value.negative {
    color: #27ae60;
}

.tooltip-note {
    display: block;
    font-size: 0.85em;
    color: rgba(255, 255, 255, 0.7);
    margin-top: 2px;
}

/* Visual indicator that tooltip is available */
.card[data-has-tooltip]:hover {
    cursor: help;
}
```

### Integration with renderGame

```javascript
// In renderGame, after creating card elements
renderPlayerCards() {
    // ... existing card rendering ...

    const cards = this.playerCards.querySelectorAll('.card');
    const myData = this.getMyPlayerData();

    cards.forEach((cardEl, i) => {
        const cardData = myData?.cards[i];
        if (cardData?.face_up) {
            cardEl.dataset.hasTooltip = 'true';
            this.bindCardTooltipEvents(cardEl, cardData);
        }
    });
}

// Similar for opponent cards
renderOpponentCards(player, container) {
    // ... existing card rendering ...

    const cards = container.querySelectorAll('.card');
    player.cards.forEach((cardData, i) => {
        if (cardData?.face_up && cards[i]) {
            cards[i].dataset.hasTooltip = 'true';
            this.bindCardTooltipEvents(cards[i], cardData);
        }
    });
}
```

---

## House Rule Awareness

Tooltip values should reflect active house rules:

```javascript
getCardPointValue(cardData) {
    // Use server-provided values which include house rules
    if (this.gameState?.card_values) {
        return this.gameState.card_values[cardData.rank] ?? 0;
    }

    // Fallback to defaults
    return DEFAULT_CARD_VALUES[cardData.rank] ?? 0;
}
```

The server already provides `card_values` in game state that accounts for:
- `super_kings` (K = -2)
- `ten_penny` (10 = 1)
- `lucky_swing` (Joker = -5)
- etc.

---

## Performance Considerations

- Only bind tooltip events to face-up cards
- Remove tooltip events when cards re-render
- Use event delegation if performance becomes an issue

```javascript
// Event delegation approach
this.playerCards.addEventListener('mouseenter', (e) => {
    const card = e.target.closest('.card');
    if (card && card.dataset.hasTooltip) {
        const cardData = this.getCardDataForElement(card);
        this.scheduleTooltip(card, cardData);
    }
}, true);
```

---

## Settings Option (Optional)

Let players disable tooltips:

```javascript
// In settings
this.showCardTooltips = localStorage.getItem('showCardTooltips') !== 'false';

// Check before showing
showCardTooltip(cardElement, cardData) {
    if (!this.showCardTooltips) return;
    // ... rest of method
}
```

---

## Test Scenarios

1. **Hover on face-up card** - Tooltip appears after delay
2. **Long-press on mobile** - Tooltip appears
3. **Move mouse away** - Tooltip disappears
4. **Face-down card** - No tooltip
5. **Special cards (K, 2, Joker)** - Show special note
6. **House rules active** - Modified values shown
7. **Rapid card changes** - No stale tooltips

---

## Acceptance Criteria

- [ ] Hover (500ms delay) shows tooltip on desktop
- [ ] Long-press (300ms) shows tooltip on mobile
- [ ] Tooltip shows point value
- [ ] Negative values highlighted green
- [ ] Special notes for notable cards
- [ ] House rule modified values displayed
- [ ] Tooltips don't interfere with gameplay
- [ ] Tooltips position correctly (stay on screen)
- [ ] Face-down cards have no tooltip

---

## Implementation Order

1. Create tooltip element and basic CSS
2. Implement `showCardTooltip()` method
3. Implement `hideCardTooltip()` method
4. Add desktop hover events
5. Add mobile long-press events
6. Integrate with `renderGame()`
7. Add house rule awareness
8. Test on mobile and desktop
9. Optional: Add settings toggle

---

## Notes for Agent

- **CSS vs anime.js**: CSS is appropriate for tooltip show/hide transitions (simple UI)
- The 500ms delay prevents tooltips appearing during normal play
- Mobile long-press should be discoverable but not intrusive
- Use server-provided `card_values` for house rule accuracy
- Consider: Quick reference card in rules screen? (Separate feature)
- Don't show tooltip during swap animation
