# V3-07: Animated Score Tallying

## Overview

In physical card games, scoring involves counting cards one by one, noting pairs, and calculating the total. Currently, scores just appear in the scoreboard. This feature adds animated score counting that highlights each card's contribution.

**Dependencies:** V3_03 (Round End Reveal should complete before tallying)
**Dependents:** None

---

## Goals

1. Animate score counting card-by-card
2. Highlight each card as its value is added
3. Show column pairs canceling to zero
4. Running total builds up visibly
5. Special effect for negative cards and pairs
6. Satisfying "final score" reveal

---

## Current State

From `showScoreboard()` in app.js:
```javascript
showScoreboard(scores, isFinal, rankings) {
    // Scores appear instantly in table
    // No animation of how score was calculated
}
```

The server calculates scores and sends them. The client just displays them.

---

## Design

### Tally Sequence

```
1. Round end reveal completes (V3_03)
2. Brief pause (300ms)
3. For each player (starting with knocker):
   a. Highlight player area
   b. Count through each column:
      - Highlight top card, show value
      - Highlight bottom card, show value
      - If pair: show "PAIR! +0" effect
      - If not pair: add values to running total
   c. Show final score with flourish
   d. Move to next player
4. Scoreboard slides in with all scores
```

### Visual Elements

- **Card value overlay** - Temporary badge showing card's point value
- **Running total** - Animated counter near player area
- **Pair effect** - Special animation when column pair cancels
- **Final score** - Large number with celebration effect

### Timing

```javascript
// In timing-config.js
tally: {
    initialPause: 300,        // After reveal, before tally
    cardHighlight: 200,       // Duration to show each card value
    columnPause: 150,         // Between columns
    pairCelebration: 400,     // Pair cancel effect
    playerPause: 500,         // Between players
    finalScoreReveal: 600,    // Final score animation
}
```

---

## Implementation

### Card Value Overlay

```javascript
// Create temporary overlay showing card value
showCardValue(cardElement, value, isNegative) {
    const overlay = document.createElement('div');
    overlay.className = 'card-value-overlay';
    if (isNegative) overlay.classList.add('negative');
    if (value === 0) overlay.classList.add('zero');

    const sign = value > 0 ? '+' : '';
    overlay.textContent = `${sign}${value}`;

    // Position over the card
    const rect = cardElement.getBoundingClientRect();
    overlay.style.left = `${rect.left + rect.width / 2}px`;
    overlay.style.top = `${rect.top + rect.height / 2}px`;

    document.body.appendChild(overlay);

    // Animate in
    overlay.classList.add('visible');

    return overlay;
}

hideCardValue(overlay) {
    overlay.classList.remove('visible');
    setTimeout(() => overlay.remove(), 200);
}
```

### CSS for Overlays

```css
/* Card value overlay */
.card-value-overlay {
    position: fixed;
    transform: translate(-50%, -50%) scale(0.5);
    background: rgba(30, 30, 46, 0.9);
    color: white;
    padding: 8px 14px;
    border-radius: 8px;
    font-size: 1.4em;
    font-weight: bold;
    opacity: 0;
    transition: transform 0.2s ease-out, opacity 0.2s ease-out;
    z-index: 200;
    pointer-events: none;
}

.card-value-overlay.visible {
    transform: translate(-50%, -50%) scale(1);
    opacity: 1;
}

.card-value-overlay.negative {
    background: linear-gradient(135deg, #27ae60 0%, #1e8449 100%);
    color: white;
}

.card-value-overlay.zero {
    background: linear-gradient(135deg, #f4a460 0%, #d4845a 100%);
}

/* Running total */
.running-total {
    position: absolute;
    bottom: -30px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(0, 0, 0, 0.8);
    color: white;
    padding: 4px 12px;
    border-radius: 15px;
    font-size: 1.2em;
    font-weight: bold;
}

.running-total.updating {
    animation: total-bounce 0.2s ease-out;
}

@keyframes total-bounce {
    0% { transform: translateX(-50%) scale(1); }
    50% { transform: translateX(-50%) scale(1.1); }
    100% { transform: translateX(-50%) scale(1); }
}

/* Pair cancel effect */
.pair-cancel-overlay {
    position: fixed;
    transform: translate(-50%, -50%);
    font-size: 1.2em;
    font-weight: bold;
    color: #f4a460;
    text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
    animation: pair-cancel 0.6s ease-out forwards;
    z-index: 200;
    pointer-events: none;
}

@keyframes pair-cancel {
    0% {
        transform: translate(-50%, -50%) scale(0.5);
        opacity: 0;
    }
    30% {
        transform: translate(-50%, -50%) scale(1.2);
        opacity: 1;
    }
    100% {
        transform: translate(-50%, -60%) scale(1);
        opacity: 0;
    }
}

/* Card highlight during tally */
.card.tallying {
    box-shadow: 0 0 15px rgba(244, 164, 96, 0.6);
    transform: scale(1.05);
    transition: box-shadow 0.1s, transform 0.1s;
}

/* Final score reveal */
.final-score-overlay {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%) scale(0);
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    color: white;
    padding: 20px 40px;
    border-radius: 15px;
    text-align: center;
    z-index: 250;
    animation: final-score-reveal 0.6s ease-out forwards;
}

.final-score-overlay .player-name {
    font-size: 1em;
    opacity: 0.8;
    margin-bottom: 5px;
}

.final-score-overlay .score-value {
    font-size: 3em;
    font-weight: bold;
}

.final-score-overlay .score-value.negative {
    color: #27ae60;
}

@keyframes final-score-reveal {
    0% {
        transform: translate(-50%, -50%) scale(0);
    }
    60% {
        transform: translate(-50%, -50%) scale(1.1);
    }
    100% {
        transform: translate(-50%, -50%) scale(1);
    }
}
```

### Main Tally Logic

```javascript
async runScoreTally(players, onComplete) {
    const T = window.TIMING?.tally || {};

    // Initial pause after reveal
    await this.delay(T.initialPause || 300);

    // Get card values from game state
    const cardValues = this.gameState?.card_values || this.getDefaultCardValues();

    // Tally each player
    for (const player of players) {
        const area = this.getPlayerArea(player.id);
        if (!area) continue;

        // Highlight player area
        area.classList.add('tallying-player');

        // Create running total display
        const runningTotal = document.createElement('div');
        runningTotal.className = 'running-total';
        runningTotal.textContent = '0';
        area.appendChild(runningTotal);

        let total = 0;
        const cards = area.querySelectorAll('.card');

        // Process each column
        const columns = [[0, 3], [1, 4], [2, 5]];

        for (const [topIdx, bottomIdx] of columns) {
            const topCard = cards[topIdx];
            const bottomCard = cards[bottomIdx];
            const topData = player.cards[topIdx];
            const bottomData = player.cards[bottomIdx];

            // Highlight top card
            topCard.classList.add('tallying');
            const topValue = cardValues[topData.rank] ?? 0;
            const topOverlay = this.showCardValue(topCard, topValue, topValue < 0);
            await this.delay(T.cardHighlight || 200);

            // Highlight bottom card
            bottomCard.classList.add('tallying');
            const bottomValue = cardValues[bottomData.rank] ?? 0;
            const bottomOverlay = this.showCardValue(bottomCard, bottomValue, bottomValue < 0);
            await this.delay(T.cardHighlight || 200);

            // Check for pair
            if (topData.rank === bottomData.rank) {
                // Pair! Show cancel effect
                this.hideCardValue(topOverlay);
                this.hideCardValue(bottomOverlay);
                this.showPairCancel(topCard, bottomCard);
                await this.delay(T.pairCelebration || 400);
            } else {
                // Add values to total
                total += topValue + bottomValue;
                this.updateRunningTotal(runningTotal, total);
                this.hideCardValue(topOverlay);
                this.hideCardValue(bottomOverlay);
            }

            // Clear card highlights
            topCard.classList.remove('tallying');
            bottomCard.classList.remove('tallying');

            await this.delay(T.columnPause || 150);
        }

        // Show final score for this player
        await this.showFinalScore(player.name, total);
        await this.delay(T.finalScoreReveal || 600);

        // Clean up
        runningTotal.remove();
        area.classList.remove('tallying-player');

        await this.delay(T.playerPause || 500);
    }

    onComplete();
}

showPairCancel(card1, card2) {
    // Position between the two cards
    const rect1 = card1.getBoundingClientRect();
    const rect2 = card2.getBoundingClientRect();
    const centerX = (rect1.left + rect1.right + rect2.left + rect2.right) / 4;
    const centerY = (rect1.top + rect1.bottom + rect2.top + rect2.bottom) / 4;

    const overlay = document.createElement('div');
    overlay.className = 'pair-cancel-overlay';
    overlay.textContent = 'PAIR! +0';
    overlay.style.left = `${centerX}px`;
    overlay.style.top = `${centerY}px`;

    document.body.appendChild(overlay);

    // Pulse both cards
    card1.classList.add('pair-matched');
    card2.classList.add('pair-matched');

    setTimeout(() => {
        overlay.remove();
        card1.classList.remove('pair-matched');
        card2.classList.remove('pair-matched');
    }, 600);

    this.playSound('pair');
}

updateRunningTotal(element, value) {
    element.textContent = value >= 0 ? value : value;
    element.classList.add('updating');
    setTimeout(() => element.classList.remove('updating'), 200);
}

async showFinalScore(playerName, score) {
    const overlay = document.createElement('div');
    overlay.className = 'final-score-overlay';
    overlay.innerHTML = `
        <div class="player-name">${playerName}</div>
        <div class="score-value ${score < 0 ? 'negative' : ''}">${score}</div>
    `;

    document.body.appendChild(overlay);

    this.playSound(score < 0 ? 'success' : 'card');

    await this.delay(800);

    overlay.style.opacity = '0';
    overlay.style.transition = 'opacity 0.3s';
    await this.delay(300);
    overlay.remove();
}

getDefaultCardValues() {
    return {
        'A': 1, '2': -2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7,
        '8': 8, '9': 9, '10': 10, 'J': 10, 'Q': 10, 'K': 0, '★': -2
    };
}
```

---

## Integration with Round End

```javascript
// In runRoundEndReveal completion callback

async runRoundEndReveal(oldState, newState, onComplete) {
    // ... existing reveal logic ...

    // After all reveals complete
    await this.runScoreTally(newState.players, () => {
        // Now show the scoreboard
        onComplete();
    });
}
```

---

## Simplified Mode

For faster games, offer a simplified tally that just shows final scores:

```javascript
if (this.settings.quickTally) {
    // Just flash the final scores, skip card-by-card
    for (const player of players) {
        const score = this.calculateScore(player.cards);
        await this.showFinalScore(player.name, score);
        await this.delay(400);
    }
    onComplete();
    return;
}
```

---

## Test Scenarios

1. **Normal hand** - Values add up correctly
2. **Paired column** - Shows "PAIR! +0" effect
3. **All pairs** - Total is 0, multiple pair celebrations
4. **Negative cards** - Green highlight, reduces total
5. **Multiple players** - Tallies sequentially
6. **Various scores** - Positive, negative, zero

---

## Acceptance Criteria

- [ ] Cards highlight as they're counted
- [ ] Point values show as temporary overlays
- [ ] Running total updates with each card
- [ ] Paired columns show cancel effect
- [ ] Final score has celebration animation
- [ ] Tally order: knocker first, then clockwise
- [ ] Sound effects enhance the experience
- [ ] Total time under 10 seconds for 4 players
- [ ] Scoreboard appears after tally completes

---

## Implementation Order

1. Add tally timing to `timing-config.js`
2. Create CSS for all overlays and animations
3. Implement `showCardValue()` and `hideCardValue()`
4. Implement `showPairCancel()`
5. Implement `updateRunningTotal()`
6. Implement `showFinalScore()`
7. Implement main `runScoreTally()` method
8. Integrate with round end reveal
9. Test various scoring scenarios
10. Add quick tally option

---

## Notes for Agent

- **CSS vs anime.js**: Use CSS for UI overlays (value badges, running total). Use anime.js for card highlight effects.
- Card highlighting can use `window.cardAnimations` methods or simple anime.js calls
- The tally should feel satisfying, not tedious
- Keep individual card highlight times short
- Pair cancellation is a highlight moment - give it emphasis
- Consider accessibility: values should be readable
- The running total helps players follow the math
- Don't forget to handle house rules affecting card values (use `gameState.card_values`)
